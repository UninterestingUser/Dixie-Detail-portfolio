"""Deleting test records (public-api.md): the customers marked test, made by
api_smoke_test or from a number in TEST_PHONE_NUMBERS, with their
appointments, quote requests with their photos and quotes, offline
requests, second vehicle requests, the quotes their jobs and requests were
priced from, vehicles,
addresses and consents, and the change history of each. Real records are
never touched: only a record marked test, or one belonging to a test
customer, is deleted."""

from dataclasses import dataclass, field

from django.db import transaction

from appointments import booking
from appointments.models import Appointment
from customers.models import Address, Customer
from vehicles.models import Vehicle

from . import photos
from pricebook.models import Quote

from .models import QuoteRequest, SecondVehicleRequest, TimeRequest


@dataclass
class Deleted:
    customers: int = 0
    appointments: int = 0
    quote_requests: int = 0
    photos: int = 0
    time_requests: int = 0
    second_vehicle_requests: int = 0
    quotes: int = 0
    kept: list = field(default_factory=list)

    def __str__(self):
        text = (
            f"Deleted {self.customers} test customer(s), {self.appointments} appointment(s), "
            f"{self.quote_requests} quote request(s) with {self.photos} photo(s), {self.time_requests} offline request(s) "
            f"and {self.second_vehicle_requests} second vehicle request(s), with {self.quotes} quote(s)"
        )
        return text + "".join(f"\nKept: {reason}" for reason in self.kept)


def priced_from(customer_ids, appointments, requests, offline, second):
    """The quotes the test customers' jobs and requests were priced from."""
    ids = set(Appointment.history.filter(customer_id__in=customer_ids, quote__isnull=False).values_list("quote_id", flat=True))
    ids |= set(requests.filter(quote__isnull=False).values_list("quote_id", flat=True))
    ids |= set(offline.filter(quote__isnull=False).values_list("quote_id", flat=True))
    ids |= set(second.values_list("web_quote__quote_id", flat=True))
    return ids & set(Quote.objects.filter(pk__in=ids).values_list("pk", flat=True))


@transaction.atomic
def delete(customers=None, dry_run=False):
    """Delete the test customers given (every test customer by default) and
    everything of theirs, or with dry_run count it only."""
    customers = list(customers if customers is not None else Customer.objects.filter(is_test=True))
    customers = [customer for customer in customers if customer.is_test]
    ids = [customer.pk for customer in customers]
    deleted = Deleted()
    appointments = Appointment.objects.filter(customer_id__in=ids)
    requests = QuoteRequest.objects.filter(customer_id__in=ids)
    offline = TimeRequest.objects.filter(customer_id__in=ids)
    second = SecondVehicleRequest.objects.filter(customer_id__in=ids)
    quote_ids = priced_from(ids, appointments, requests, offline, second)
    if dry_run:
        deleted.quotes = len(quote_ids)
        deleted.second_vehicle_requests = second.count()
        deleted.customers, deleted.appointments = len(ids), appointments.count()
        deleted.quote_requests, deleted.time_requests = requests.count(), offline.count()
        deleted.photos = sum(request.photos.count() for request in requests)
        return deleted
    quotes_before = len(quote_ids)
    # Jobs first: removing one keeps any quote a request still refers to.
    for appointment in list(appointments):
        try:
            deleted.appointments += booking.remove(appointment)
        except booking.BookingError as error:
            deleted.kept.append(f"appointment {appointment.pk}: {error}")
    # Then the requests, which free their quotes; then the quotes.
    for request in requests:
        deleted.photos += photos.delete_photos(request.photos.all())
    deleted.quote_requests = requests.delete()[1].get(QuoteRequest._meta.label, 0)
    deleted.time_requests = offline.delete()[1].get(TimeRequest._meta.label, 0)
    deleted.second_vehicle_requests = second.delete()[1].get(SecondVehicleRequest._meta.label, 0)
    booking.delete_unused_quotes(quote_ids)
    deleted.quotes = quotes_before - Quote.objects.filter(pk__in=quote_ids).count()
    for customer in customers:
        if customer.appointments.exists():
            deleted.kept.append(f"customer {customer.pk} still has a job")
            continue
        Vehicle.objects.filter(customer=customer).delete()
        Address.objects.filter(customer=customer).delete()
        customer.delete()
        Customer.history.filter(id=customer.pk).delete()
        deleted.customers += 1
    Vehicle.history.filter(customer_id__in=ids).delete()
    Address.history.filter(customer_id__in=ids).delete()
    return deleted
