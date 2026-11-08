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


class HandPriceForm(forms.Form):
    """The owner's price for a quote request: one price before tax and the
    time on site, which become a quote record (decision 0059)."""

    service = forms.ModelChoiceField(queryset=None, help_text="What the price is for.")
    vehicle_class = forms.ModelChoiceField(queryset=VehicleClass.objects.all(), label="Vehicle class")
    amount = forms.DecimalField(label="Price before tax", min_value=Decimal("0.01"), max_digits=8, decimal_places=2)
    time_on_site_minutes = forms.IntegerField(
        label="Time on site, in minutes", min_value=45, max_value=24 * 60, widget=forms.NumberInput(attrs={"step": 15}),
        help_text="Setup and breakdown included, in steps of 15 minutes. This is what the availability check uses.",
    )
    crew_size = forms.TypedChoiceField(choices=[(1, "1"), (2, "2")], coerce=int, initial=1, label="Crew")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["service"].queryset = authorizable_services()

    def clean_time_on_site_minutes(self):
        minutes = self.cleaned_data["time_on_site_minutes"]
        if minutes % 15:
            raise forms.ValidationError("Use steps of 15 minutes.")
        return minutes
