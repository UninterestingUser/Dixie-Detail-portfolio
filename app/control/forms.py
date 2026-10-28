"""Forms for the control app's screens."""

import datetime

from django import forms
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.utils import timezone

from core.fields import format_phone, normalize_phone
from customers.models import Address, Customer
from pricebook.models import Service
from vehicles.models import ClassificationRule, SizeVariant, Vehicle, VehicleClass


class PhoneInput(forms.TextInput):
    input_type = "tel"

    def __init__(self):
        super().__init__(attrs={"inputmode": "tel", "autocomplete": "tel-national"})


class CustomerForm(forms.ModelForm):
    # Typed in any format; stored as 10 digits (decision 0049).
    mobile = forms.CharField(required=False, max_length=30, widget=PhoneInput(), help_text="Any format, such as 423-555-0142.")

    class Meta:
        model = Customer
        fields = ["first_name", "last_name", "company", "mobile", "email", "source", "notes"]
        widgets = {"notes": forms.Textarea(attrs={"rows": 4})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.mobile:
            self.initial["mobile"] = format_phone(self.instance.mobile)

    def clean_mobile(self):
        return normalize_phone(self.cleaned_data["mobile"])


class VehicleForm(forms.ModelForm):
    class Meta:
        model = Vehicle
        fields = ["year", "make", "model", "color", "vehicle_class", "size_variant", "notes"]
        widgets = {
            "year": forms.NumberInput(attrs={"inputmode": "numeric"}),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }
        help_texts = {"color": "Tells a customer's identical vehicles apart, such as silver or dark blue."}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Retired classes and size variants are not offered, except the one the
        # vehicle already has.
        self.fields["vehicle_class"].queryset = VehicleClass.objects.filter(
            Q(active=True, pending=False) | Q(pk=self.instance.vehicle_class_id)
        )
        self.fields["size_variant"].queryset = SizeVariant.objects.select_related("vehicle_class").filter(
            Q(active=True, vehicle_class__active=True, vehicle_class__pending=False) | Q(pk=self.instance.size_variant_id)
        )

    def clean_year(self):
        year = self.cleaned_data["year"]
        latest = timezone.localdate().year + 2
        if year is not None and not 1900 <= year <= latest:
            raise ValidationError(f"Enter a year from 1900 to {latest}.")
        return year

    def clean(self):
        cleaned = super().clean()
        size_variant, vehicle_class = cleaned.get("size_variant"), cleaned.get("vehicle_class")
        if size_variant and size_variant.vehicle_class_id != getattr(vehicle_class, "pk", None):
            self.add_error("size_variant", "Pick a size variant of the vehicle class above, or leave it blank.")
        return cleaned


class AppointmentForm(forms.Form):
    """Booking a job, or changing one. The price is never entered: it comes
    from the pricing engine (decision 0059)."""

    REPEAT_CHOICES = [("", "A single visit"), ("monthly", "Monthly"), ("quarterly", "Quarterly")]

    vehicle = forms.ModelChoiceField(queryset=Vehicle.objects.none())
    address = forms.ModelChoiceField(queryset=Address.objects.none(), required=False, label="Service address")
    date = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))
    time = forms.TimeField(widget=forms.TimeInput(format="%H:%M", attrs={"type": "time", "step": 900}), help_text="Arrival time, Eastern.")
    service = forms.ModelChoiceField(queryset=Service.objects.none())
    vehicle_class = forms.ModelChoiceField(queryset=VehicleClass.objects.none())
    size_variant = forms.ModelChoiceField(queryset=SizeVariant.objects.none(), required=False, label="Size")
    condition_level = forms.TypedChoiceField(
        choices=[("", "Not needed"), (1, "1: adds nothing"), (2, "2"), (3, "3")], coerce=int, empty_value=None, required=False,
        help_text="Needed for Full Detail, Interior Only and Exterior Only.",
    )
    add_ons = forms.ModelMultipleChoiceField(queryset=Service.objects.none(), required=False, widget=forms.CheckboxSelectMultiple)
    crew_size = forms.TypedChoiceField(
        choices=[("", "The service's default"), (1, "1 person"), (2, "2 people")], coerce=int, empty_value=None, required=False, label="Crew",
    )
    repeat = forms.ChoiceField(choices=REPEAT_CHOICES, required=False, help_text="Maintenance plans only.")
    visits = forms.IntegerField(min_value=2, max_value=24, initial=12, required=False, help_text="How many visits in the series, the first included.")
    notes = forms.CharField(widget=forms.Textarea(attrs={"rows": 3}), required=False)
    reason = forms.CharField(required=False, max_length=200, label="Reason for changing the services",
                             help_text="Needed when you change what a booked job is priced from.")

    def __init__(self, *args, customer, editing=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.customer, self.editing = customer, editing
        self.fields["vehicle"].queryset = customer.vehicles.select_related("vehicle_class", "size_variant").order_by("make", "model", "year", "color")
        self.fields["address"].queryset = customer.addresses.filter(active=True)
        self.fields["service"].queryset = Service.objects.filter(
            on_price_list=True, kind__in=[Service.Kind.MAIN, Service.Kind.MAINTENANCE_PLAN]
        ).order_by("kind", "name")
        self.fields["vehicle_class"].queryset = VehicleClass.objects.offered()
        self.fields["size_variant"].queryset = SizeVariant.objects.filter(active=True, vehicle_class__active=True, vehicle_class__pending=False).select_related("vehicle_class")
        self.fields["size_variant"].label_from_instance = lambda size: f"{size.vehicle_class}: {size.label}"
        self.fields["add_ons"].queryset = Service.objects.filter(on_price_list=True, kind=Service.Kind.ADD_ON).order_by("name")
        if editing:
            del self.fields["repeat"], self.fields["visits"]
            # A job not priced from the pricebook, such as an imported custom
            # job, can be edited without giving it a service.
            self.fields["service"].required = False
            self.fields["vehicle_class"].required = False
        else:
            del self.fields["reason"]

    def clean(self):
        cleaned = super().clean()
        service, vehicle_class, size = cleaned.get("service"), cleaned.get("vehicle_class"), cleaned.get("size_variant")
        if size and vehicle_class and size.vehicle_class_id != vehicle_class.pk:
            self.add_error("size_variant", "Pick a size of the vehicle class above, or leave it blank.")
        if service and not vehicle_class:
            self.add_error("vehicle_class", "Pick the vehicle class to price the service.")
        if service and service.condition_applies and cleaned.get("condition_level") is None:
            self.add_error("condition_level", f"{service} needs a condition level.")
        if cleaned.get("repeat"):
            if service and service.kind != Service.Kind.MAINTENANCE_PLAN:
                self.add_error("repeat", "Only a maintenance plan can repeat.")
            if not cleaned.get("visits"):
                self.add_error("visits", "Say how many visits the series has.")
        return cleaned

    def inputs(self):
        from appointments.booking import JobInputs

        data = self.cleaned_data
        service = data.get("service")
        if service is None:
            return None
        return JobInputs(
            service=service,
            vehicle_class=data["vehicle_class"],
            size_variant=data.get("size_variant"),
            condition_level=data.get("condition_level") if service.condition_applies else None,
            add_ons=list(data.get("add_ons") or []),
            crew_size=data.get("crew_size") or service.default_crew_size,
        )

    def start(self):
        data = self.cleaned_data
        return timezone.make_aware(datetime.datetime.combine(data["date"], data["time"]))


class FinalPriceForm(forms.Form):
    final_price = forms.DecimalField(min_value=0, max_digits=10, decimal_places=2, label="Final price before tax",
                                     widget=forms.NumberInput(attrs={"inputmode": "decimal", "step": "0.01"}))
    reason = forms.CharField(max_length=500, required=False, label="Reason for the on-site adjustment")


class PublishForm(forms.Form):
    effective_date = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}), help_text="Today or later.")

    def clean_effective_date(self):
        date = self.cleaned_data["effective_date"]
        if date < timezone.localdate():
            raise ValidationError("The effective date must be today or later.")
        return date


# The vehicle catalog screens (decision 0076).


def size_choices(vehicle_classes):
    """The size choices for an override or queue decision: from the facts,
    always ask, or one size variant of any of these classes."""
    choices = [("", "Worked out from the facts"), ("ask", "Always ask the customer")]
    for size in SizeVariant.objects.filter(vehicle_class__in=vehicle_classes, active=True).select_related("vehicle_class"):
        choices.append((str(size.pk), f"{size.vehicle_class}: {size.label}"))
    return choices


class SizeChoiceMixin:
    """A size field whose value is "", "ask" or a size variant's id, checked
    against the chosen vehicle class, which comes before it in the form.
    cleaned_data gets size_variant and ask_size."""

    def clean_size(self):
        cleaned = self.cleaned_data
        choice, vehicle_class = cleaned.get("size", ""), cleaned.get("vehicle_class")
        cleaned["size_variant"], cleaned["ask_size"] = None, choice == "ask"
        if choice and choice != "ask":
            size = SizeVariant.objects.filter(pk=choice).first()
            if size is None or vehicle_class is None or size.vehicle_class_id != vehicle_class.pk:
                self.add_error("size", "Pick a size of the vehicle class above.")
            cleaned["size_variant"] = size
        return choice


def year_field(label):
    return forms.IntegerField(required=False, min_value=1900, max_value=2100, label=label, widget=forms.NumberInput(attrs={"inputmode": "numeric"}))


class YearRangeMixin:
    def check_years(self, cleaned):
        low, high = cleaned.get("year_from"), cleaned.get("year_to")
        if low is not None and high is not None and low > high:
            self.add_error("year_to", "The last year comes after the first.")


class ModelOverrideForm(SizeChoiceMixin, YearRangeMixin, forms.Form):
    year_from = year_field("From model year")
    year_to = year_field("To model year")
    vehicle_class = forms.ModelChoiceField(queryset=VehicleClass.objects.offered(), label="Vehicle class")
    size = forms.ChoiceField(required=False, label="Size")
    note = forms.CharField(required=False, max_length=500, widget=forms.Textarea(attrs={"rows": 2}), help_text="Why, for the history.")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["year_from"].help_text = "Leave both years empty for every year of the model."
        self.fields["size"].choices = size_choices(VehicleClass.objects.offered())

    def clean(self):
        cleaned = super().clean()
        self.check_years(cleaned)
        return cleaned


class ThirdRowForm(YearRangeMixin, forms.Form):
    FLAGS = [("always", "Always has a third row"), ("never", "Never has a third row"),
             ("optional", "Optional: ask the customer"), ("clear", "Clear: use the third-row list and NHTSA")]
    year_from = year_field("From model year")
    year_to = year_field("To model year")
    flag = forms.ChoiceField(choices=FLAGS, label="Third row")
    note = forms.CharField(required=False, max_length=500, widget=forms.Textarea(attrs={"rows": 2}), help_text="Why, for the history.")

    def clean(self):
        cleaned = super().clean()
        self.check_years(cleaned)
        return cleaned


class RuleForm(forms.ModelForm):
    """A rule's name, position, class, note and whether it is active. Its
    conditions are edited row by row on the same screen."""

    class Meta:
        model = ClassificationRule
        fields = ["name", "position", "vehicle_class", "active", "note"]
        widgets = {
            "position": forms.NumberInput(attrs={"inputmode": "numeric"}),
            "note": forms.Textarea(attrs={"rows": 2}),
        }
        help_texts = {"position": "Rules are tried from the lowest number up; 75 goes between 70 and 80."}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["vehicle_class"].queryset = VehicleClass.objects.filter(Q(active=True, pending=False) | Q(pk=self.instance.vehicle_class_id))


class VehicleClassSettingsForm(forms.ModelForm):
    class Meta:
        model = VehicleClass
        fields = ["size_variant_measures", "booking", "photo_card", "photo"]
        labels = {"size_variant_measures": "The size variant measures", "photo_card": "Photo card caption", "photo": "Photo card picture"}


class VehicleOverrideForm(forms.Form):
    vehicle_class = forms.ModelChoiceField(queryset=VehicleClass.objects.offered(), label="Vehicle class")
    size_variant = forms.ModelChoiceField(queryset=SizeVariant.objects.none(), required=False, label="Size")
    note = forms.CharField(required=False, max_length=500, widget=forms.Textarea(attrs={"rows": 2}), help_text="Such as lifted, or a long-bed conversion.")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["size_variant"].queryset = SizeVariant.objects.filter(active=True, vehicle_class__active=True, vehicle_class__pending=False).select_related("vehicle_class")
        self.fields["size_variant"].label_from_instance = lambda size: f"{size.vehicle_class}: {size.label}"

    def clean(self):
        cleaned = super().clean()
        size, vehicle_class = cleaned.get("size_variant"), cleaned.get("vehicle_class")
        if size and vehicle_class and size.vehicle_class_id != vehicle_class.pk:
            self.add_error("size_variant", "Pick a size of the vehicle class above, or leave it blank.")
        return cleaned


class TestPriceForm(forms.Form):
    service = forms.ModelChoiceField(queryset=Service.objects.none())
    vehicle_class = forms.ModelChoiceField(queryset=VehicleClass.objects.offered(), label="Vehicle class")
    size_variant = forms.ModelChoiceField(queryset=SizeVariant.objects.none(), required=False, label="Size")
    condition_level = forms.TypedChoiceField(
        choices=[(1, "1: adds nothing"), (2, "2"), (3, "3")], coerce=int, initial=1, label="Condition level",
        help_text="Used by Full Detail, Interior Only and Exterior Only.",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["service"].queryset = Service.objects.filter(
            on_price_list=True, kind__in=[Service.Kind.MAIN, Service.Kind.MAINTENANCE_PLAN]
        ).order_by("kind", "name")
        self.fields["size_variant"].queryset = SizeVariant.objects.filter(active=True, vehicle_class__active=True, vehicle_class__pending=False).select_related("vehicle_class")
        self.fields["size_variant"].label_from_instance = lambda size: f"{size.vehicle_class}: {size.label}"
