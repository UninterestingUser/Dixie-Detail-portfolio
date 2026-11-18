"""Forms for deciding website requests and booking them (control-app.md)."""

import datetime
from decimal import Decimal

from django import forms
from django.utils import timezone

from staff.authorization import authorizable_services
from vehicles.models import VehicleClass


class BookTimeForm(forms.Form):
    """A date and an arrival time, checked against the scheduling rules. A
    manager can book outside a rule with a reason."""

    date = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))
    time = forms.TimeField(widget=forms.TimeInput(attrs={"type": "time", "step": 900}))
    override_reason = forms.CharField(
        label="Reason for booking off hours", required=False, max_length=300,
        help_text="Only when the time breaks a scheduling rule. Managers only; it's logged with the job.",
    )

    def start(self):
        data = self.cleaned_data
        return timezone.make_aware(datetime.datetime.combine(data["date"], data["time"]))


class OfflineBookForm(BookTimeForm):
    honor_shown = forms.BooleanField(label="Honor the price the customer saw", required=False)


class DeclineForm(forms.Form):
    reason = forms.CharField(label="Reason", max_length=300, help_text="Kept with the request. Tell the customer yourself.")


def hours_and_minutes(minutes):
    """150 as "2:30"."""
    return f"{minutes // 60}:{minutes % 60:02d}"


# Time on site for a hand price: 0:30 to 12:00 in 15-minute steps.
TIME_ON_SITE_CHOICES = [(minutes, hours_and_minutes(minutes)) for minutes in range(30, 12 * 60 + 1, 15)]


class HandPriceForm(forms.Form):
    """The owner's price for a quote request: one price before tax, the time
    on site and the crew, which become a quote record (decision 0059). The
    people checked under Crew are assigned when it is booked, and their
    number is the crew size."""

    service = forms.ModelChoiceField(queryset=None, help_text="What the price is for.")
    vehicle_class = forms.ModelChoiceField(queryset=VehicleClass.objects.all(), label="Vehicle class")
    amount = forms.DecimalField(label="Price before tax", min_value=Decimal("0.01"), max_digits=8, decimal_places=2,
                                widget=forms.NumberInput(attrs={"inputmode": "decimal", "step": "0.01"}))
    time_on_site_minutes = forms.TypedChoiceField(
        label="Time on site", coerce=int, choices=TIME_ON_SITE_CHOICES,
        help_text="Hours and minutes, setup and breakdown included. This is what the availability check uses.",
    )
    crew = forms.ModelMultipleChoiceField(
        queryset=None, label="Crew", widget=forms.CheckboxSelectMultiple,
        help_text="Assigned when it's booked. One person or two: the number checked is the crew size.",
    )

    def __init__(self, *args, **kwargs):
        from staff.authorization import default_staff
        from staff.models import StaffMember

        super().__init__(*args, **kwargs)
        self.fields["service"].queryset = authorizable_services()
        self.fields["crew"].queryset = StaffMember.objects.filter(active=True).order_by("name")
        if not self.is_bound and "crew" not in self.initial:
            member = default_staff()
            self.initial["crew"] = [member.pk] if member else []
        # A time priced earlier outside the list is kept as a choice.
        minutes = self.initial.get("time_on_site_minutes")
        if minutes and minutes not in dict(TIME_ON_SITE_CHOICES):
            self.fields["time_on_site_minutes"].choices = sorted([*TIME_ON_SITE_CHOICES, (minutes, hours_and_minutes(minutes))])

    def clean_crew(self):
        crew = list(self.cleaned_data["crew"])
        if len(crew) > 2:
            raise forms.ValidationError("A crew is one or two people.")
        return crew
