"""Price a job from the terminal with the pricing engine, without storing it.

Example:
  python manage.py quote --service "Full Detail" --class "Medium" \
      --size 2 --condition 2 --add-on "Seat Extraction"
"""

from django.core.management.base import BaseCommand, CommandError

from core.scheduling import format_minutes
from pricebook.models import Service
from pricebook.pricing import PricingError, format_hours, price_job
from promotions.models import Promotion
from vehicles.models import VehicleClass


class Command(BaseCommand):
    help = "Price a job and print its lines, the total, the service time and the time on site."

    def add_arguments(self, parser):
        parser.add_argument("--service", required=True, help='The main service, such as "Full Detail".')
        parser.add_argument("--class", dest="vehicle_class", required=True, help="The vehicle class.")
        parser.add_argument("--size", type=int, help="The size variant: 1, 2 or 3.")
        parser.add_argument("--condition", type=int, help="The condition level: 1, 2 or 3.")
        parser.add_argument("--add-on", action="append", default=[], help="An add-on; repeat for more.")
        parser.add_argument(
            "--promotion", action="append", default=[], help="A promotion's name or code; repeat for more."
        )
        parser.add_argument("--crew", type=int, help="1 or 2 people. Defaults to the service's usual crew.")

    def handle(self, *args, **options):
        service = self.find(Service, options["service"])
        vehicle_class = self.find(VehicleClass, options["vehicle_class"])
        size_variant = None
        if options["size"] is not None:
            size_variant = vehicle_class.size_variants.filter(value=options["size"]).first()
            if size_variant is None:
                raise CommandError(f"{vehicle_class} has no size variant {options['size']}.")
        add_ons = [self.find(Service, name) for name in options["add_on"]]
        promotions = []
        for text in options["promotion"]:
            promotion = (
                Promotion.objects.filter(name__iexact=text).first()
                or Promotion.objects.filter(promo_code__iexact=text).first()
            )
            if promotion is None:
                raise CommandError(f"No promotion is named or coded {text!r}.")
            promotions.append(promotion)
        try:
            job = price_job(
                service,
                vehicle_class,
                size_variant=size_variant,
                condition_level=options["condition"],
                add_ons=add_ons,
                promotions=promotions,
                crew_size=options["crew"],
            )
        except PricingError as error:
            raise CommandError(str(error)) from error

        size = f", {job.lines[0].size_variant_label}" if job.lines[0].size_variant_label else ""
        self.stdout.write(f"{service} for {vehicle_class}{size}, pricebook version {job.version.number}")
        for line in job.lines:
            hours = f"  {format_hours(line.one_person_service_hours)} h" if line.one_person_service_hours else ""
            self.stdout.write(f"  {line.description:<40} {self.money(line.amount):>10}{hours}")
        self.stdout.write(f"  {'Total before tax':<40} {self.money(job.total_before_tax):>10}")
        self.stdout.write("  Sales tax is added from Phase 3.")
        crew = "one person" if job.crew_size == 1 else "two people"
        stay = job.time_on_site
        service_time = f"Service time: {format_hours(job.one_person_service_hours)} hours for one person"
        if job.crew_size == 2:
            service_time += f"; {format_minutes(stay.service_minutes)} for two people"
        self.stdout.write(service_time)
        self.stdout.write(
            f"Time on site: {format_minutes(stay.total_minutes)} for {crew}"
            f" ({format_minutes(stay.setup_minutes)} setup + {format_minutes(stay.service_minutes)} service"
            f" + {format_minutes(stay.breakdown_minutes)} breakdown)"
        )
        if job.full_day:
            self.stdout.write("Full day: flagged for a second person; the estimate card shows \"full day\".")

    def find(self, model, name):
        found = model.objects.filter(name__iexact=name).first()
        if found is None:
            raise CommandError(f"No {model._meta.verbose_name} is named {name!r}.")
        return found

    @staticmethod
    def money(amount):
        return f"-${-amount:,.2f}" if amount < 0 else f"${amount:,.2f}"
