"""Forms for the scheduling settings screen and the open-times view."""

import datetime

from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone

from geo.verification import VerificationError, parse_location
from pricebook.models import PricebookVersion, Service
from scheduling.models import DateException, SchedulingSettings
from vehicles.models import SizeVariant, VehicleClass


def time_input():
    return forms.TimeInput(format="%H:%M", attrs={"type": "time"})


def parse_times(text):
    """"8:00, 8:30, 13:00" as sorted times, without repeats."""
    times = set()
    for part in (text or "").replace(";", ",").split(","):
        part = part.strip()
        if not part:
            continue
        try:
            times.add(datetime.time.fromisoformat(part.zfill(5) if len(part) == 4 else part))
        except ValueError:
            raise ValidationError(f"{part!r} is not a time. Write times as 08:00, 08:30, 13:00.") from None
    return sorted(times)


def format_times(times):
    return ", ".join(time.strftime("%H:%M") for time in times)


class StartTimesField(forms.CharField):
    def __init__(self, **kwargs):
        super().__init__(required=False, help_text="Arrival times, Eastern, separated by commas, such as 08:00, 08:30, 09:00.", **kwargs)

    def prepare_value(self, value):
        return format_times(value) if isinstance(value, list) else value

    def clean(self, value):
        return parse_times(super().clean(value))


def check_hours(form, cleaned, needed):
    opens, closes = cleaned.get("opens_at"), cleaned.get("closes_at")
    if needed and (opens is None or closes is None):
        form.add_error("closes_at", "Give the opening and closing times.")
    elif opens and closes and opens >= closes:
        form.add_error("closes_at", "Closing comes after opening.")
    for time in cleaned.get("start_times") or []:
        if opens and closes and not opens <= time < closes:
            form.add_error("start_times", f"{time:%H:%M} is outside the hours.")


class SchedulingSettingsForm(forms.ModelForm):
    class Meta:
        model = SchedulingSettings
        fields = [
            "minimum_notice_days", "furthest_bookable_days",
            "setup_minutes_one_person", "breakdown_minutes_one_person", "time_on_site_rounding_minutes",
            "jobs_per_day", "minimum_gap_minutes", "round_start_up_to_minutes",
            "time_off_buffer_minutes", "time_off_check_minutes", "stale_copy_warning_minutes",
            "leave_buffer_minutes",
        ]
        labels = {
            "setup_minutes_one_person": "Setup minutes, one person",
            "breakdown_minutes_one_person": "Breakdown minutes, one person",
            "time_on_site_rounding_minutes": "Round time on site to the nearest",
            "minimum_gap_minutes": "Minimum gap before a later job, minutes",
            "round_start_up_to_minutes": "Round a later job's start up to",
            "time_off_buffer_minutes": "Time Off buffer, minutes",
            "time_off_check_minutes": "Check Time Off every, minutes",
            "stale_copy_warning_minutes": "Warn when the Time Off copy is older than, minutes",
            "leave_buffer_minutes": "Time-to-leave buffer, minutes",
        }

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("jobs_per_day") == 0:
            self.add_error("jobs_per_day", "A day takes at least one job.")
        if cleaned.get("time_on_site_rounding_minutes") == 0:
            self.add_error("time_on_site_rounding_minutes", "Pick a step.")
        notice, furthest = cleaned.get("minimum_notice_days"), cleaned.get("furthest_bookable_days")
        if notice is not None and furthest is not None and furthest < notice:
            self.add_error("furthest_bookable_days", "The furthest date comes after the minimum notice.")
        return cleaned


class WeekdayForm(forms.Form):
    is_open = forms.BooleanField(required=False, label="Open")
    opens_at = forms.TimeField(required=False, widget=time_input(), label="Opens")
    closes_at = forms.TimeField(required=False, widget=time_input(), label="Closes")
    start_times = StartTimesField(label="Start times")

    def clean(self):
        cleaned = super().clean()
        check_hours(self, cleaned, cleaned.get("is_open"))
        if cleaned.get("is_open") and not cleaned.get("start_times"):
            self.add_error("start_times", "An open day needs at least one start time.")
        return cleaned


class SharedServiceForm(forms.Form):
    shares = forms.BooleanField(required=False, label="Can share a day")
    max_per_day = forms.IntegerField(required=False, min_value=1, max_value=10, label="Up to, a day")

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("shares") and not cleaned.get("max_per_day"):
            self.add_error("max_per_day", "Say how many a day.")
        return cleaned


def sharing_candidates():
    """The services a day can be shared by: those on the price list that
    are booked as jobs."""
    return Service.objects.filter(on_price_list=True, kind__in=[Service.Kind.MAIN, Service.Kind.MAINTENANCE_PLAN]).order_by("kind", "name")


class DateExceptionForm(forms.ModelForm):
    start_times = StartTimesField(label="Start times")

    class Meta:
        model = DateException
        fields = ["date", "kind", "opens_at", "closes_at", "start_times", "reason"]
        widgets = {"date": forms.DateInput(attrs={"type": "date"}), "opens_at": time_input(), "closes_at": time_input()}
        help_texts = {"reason": "Shown on the open-times view, such as Thanksgiving."}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["start_times"].help_text = "For different hours. Leave blank to use the weekday's start times within the hours."

    def clean_date(self):
        date = self.cleaned_data["date"]
        if date < timezone.localdate():
            raise ValidationError("Pick today or a later date.")
        return date

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("kind") == DateException.Kind.HOURS:
            check_hours(self, cleaned, True)
        else:
            cleaned["opens_at"] = cleaned["closes_at"] = None
            cleaned["start_times"] = []
        return cleaned


class OpenTimesForm(forms.Form):
    """The job to look for times for: what is priced, and optionally where."""

    service = forms.ModelChoiceField(queryset=Service.objects.none())
    vehicle_class = forms.ModelChoiceField(queryset=VehicleClass.objects.none())
    size_variant = forms.ModelChoiceField(queryset=SizeVariant.objects.none(), required=False, label="Size")
    condition_level = forms.TypedChoiceField(choices=[("", "Not needed"), (1, "1"), (2, "2"), (3, "3")], coerce=int, empty_value=None, required=False)
    crew_size = forms.TypedChoiceField(choices=[("", "The service's default"), (1, "1 person"), (2, "2 people")], coerce=int, empty_value=None, required=False, label="Crew")
    location = forms.CharField(required=False, label="Job location",
                               help_text="Optional. Paste the latitude and longitude from Google Maps to count the drive from other jobs that day.")
    first = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date"}), label="From")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["service"].queryset = sharing_candidates()
        self.fields["vehicle_class"].queryset = VehicleClass.objects.offered()
        self.fields["size_variant"].queryset = SizeVariant.objects.filter(active=True, vehicle_class__active=True, vehicle_class__pending=False).select_related("vehicle_class")
        self.fields["size_variant"].label_from_instance = lambda size: f"{size.vehicle_class}: {size.label}"

    def clean_location(self):
        text = self.cleaned_data["location"].strip()
        if not text:
            return None
        try:
            return parse_location(text)
        except VerificationError as error:
            raise ValidationError(str(error)) from None

    def clean(self):
        cleaned = super().clean()
        service, vehicle_class, size = cleaned.get("service"), cleaned.get("vehicle_class"), cleaned.get("size_variant")
        if size and vehicle_class and size.vehicle_class_id != vehicle_class.pk:
            self.add_error("size_variant", "Pick a size of the vehicle class above, or leave it blank.")
        version = PricebookVersion.current()
        if service and version and version.takes_condition_level(service) and cleaned.get("condition_level") is None:
            self.add_error("condition_level", f"{service} needs a condition level.")
        return cleaned

