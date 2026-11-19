"""Forms for the control app's screens."""

import datetime
from decimal import Decimal

from django import forms
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.utils import timezone

from core.fields import format_phone, normalize_phone
from customers.models import Address, Customer
from geo.models import LocationSettings
from geo.verification import VerificationError, parse_location
from pricebook.models import PricebookVersion, Service
from vehicles.models import ClassificationRule, SizeVariant, Vehicle, VehicleClass


class PhoneInput(forms.TextInput):
    input_type = "tel"

    def __init__(self):
        super().__init__(attrs={"inputmode": "tel", "autocomplete": "tel-national"})


class OptionDataSelect(forms.Select):
    """A select whose options carry data attributes, from option_data(value)
    -> {name: value}, so the booking form can show the condition level only
    for a service that takes one, and the hand price only for a level
    booked by quote (decision 0103)."""

    def __init__(self, *args, option_data=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.option_data = option_data or (lambda value: {})

    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex, attrs)
        key = str(getattr(value, "value", value))
        option["attrs"].update({f"data-{name}": text for name, text in self.option_data(key).items()})
        return option


def condition_choices(version):
    """The condition levels of a version as booking-form choices."""
    if version is None:
        return [(1, "1: adds nothing"), (2, "2"), (3, "3")], set()
    choices, by_quote = [], set()
    for level in version.condition_levels.all():
        if level.booked_by_quote:
            text = f"{level.level}: priced by hand"
            by_quote.add(str(level.level))
        elif level.adjustment_percent:
            text = f"{level.level}: adds {level.adjustment_percent.normalize():f}%"
        else:
            text = f"{level.level}: adds nothing"
        choices.append((level.level, text))
    return choices, by_quote


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
        fields = ["year", "make", "model", "color", "vehicle_class", "size_variant", "notes", "active"]
        widgets = {
            "year": forms.NumberInput(attrs={"inputmode": "numeric"}),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }
        help_texts = {
            "color": "Tells a customer's identical vehicles apart, such as silver or dark blue.",
            "active": "Untick for a vehicle the customer no longer has. Its jobs are kept; it is left out of matching and the booking form.",
        }
        labels = {"active": "Still the customer's"}

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
        choices=[], coerce=int, empty_value=None, required=False, initial=1,
        help_text="Full Detail and Interior Only. Level 1 adds nothing.",
    )
    # A condition level booked by quote has no price: the owner types the
    # price and time on site, kept as a quote record (decisions 0059 and 0103).
    hand_price = forms.DecimalField(
        label="Price before tax", min_value=Decimal("0.01"), max_digits=8, decimal_places=2, required=False,
        widget=forms.NumberInput(attrs={"inputmode": "decimal", "step": "0.01"}),
        help_text="Your price for the whole job, add-ons included.",
    )
    hand_minutes = forms.IntegerField(
        label="Time on site, in minutes", min_value=45, max_value=24 * 60, required=False,
        widget=forms.NumberInput(attrs={"step": 15}),
        help_text="Setup and breakdown included, in steps of 15 minutes. This is what the availability check uses.",
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
    # A manager booking off hours gives a reason, shown only while the
    # choice breaks a scheduling rule (decisions 0056 and 0096).
    override_reason = forms.CharField(required=False, max_length=500, label="Reason for booking off hours",
                                      widget=forms.Textarea(attrs={"rows": 2, "required": True}))
    # A manager adding an add-on that doesn't go with the service gives a
    # reason, logged with the job (decision 0106).
    add_on_reason = forms.CharField(
        required=False, max_length=500, label="Reason for an add-on outside the rules", widget=forms.Textarea(attrs={"rows": 2}),
        help_text="Only for an add-on that doesn't go with the service, such as Seat Extraction with Exterior Only.",
    )

    def __init__(self, *args, customer, editing=False, is_manager=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.customer, self.editing, self.is_manager = customer, editing, is_manager
        # The add-ons outside the rules this booking adds, as the alert words
        # them, and whether the job is priced with them anyway.
        self.add_on_breaks, self.add_on_override = [], False
        if not is_manager:
            del self.fields["add_on_reason"]
        # Vehicles no longer on the record are left out, except the job's own.
        current = self.initial.get("vehicle")
        current = getattr(current, "pk", current)
        self.fields["vehicle"].queryset = (
            customer.vehicles.filter(Q(active=True) | Q(pk=current)).select_related("vehicle_class", "size_variant").order_by("make", "model", "year", "color")
        )
        self.fields["address"].queryset = customer.addresses.filter(active=True)
        self.fields["service"].queryset = Service.objects.filter(
            on_price_list=True, kind__in=[Service.Kind.MAIN, Service.Kind.MAINTENANCE_PLAN]
        ).order_by("kind", "name")
        self.fields["vehicle_class"].queryset = VehicleClass.objects.offered()
        self.fields["size_variant"].queryset = SizeVariant.objects.filter(active=True, vehicle_class__active=True, vehicle_class__pending=False).select_related("vehicle_class")
        self.fields["size_variant"].label_from_instance = lambda size: f"{size.vehicle_class}: {size.label}"
        self.fields["add_ons"].queryset = Service.objects.filter(on_price_list=True, kind=Service.Kind.ADD_ON).order_by("name")
        # Which services take a level, and which level is priced by hand,
        # from the version in effect today; clean() checks the job's own day.
        version = PricebookVersion.current()
        takes_level = {str(pk) for pk in version.condition_service_ids()} if version else set()
        choices, by_quote = condition_choices(version)
        self.fields["condition_level"].choices = choices
        self.fields["condition_level"].widget = OptionDataSelect(option_data=lambda key: {"by-quote": "1"} if key in by_quote else {})
        self.fields["condition_level"].widget.choices = choices
        service_widget = OptionDataSelect(option_data=lambda key: {"takes-level": "1"} if key in takes_level else {})
        service_widget.choices = self.fields["service"].choices
        self.fields["service"].widget = service_widget
        self.takes_level = self.by_quote = False
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
        self.check_condition(cleaned, service)
        self.check_add_ons(cleaned, service)
        if cleaned.get("repeat"):
            if service and service.kind != Service.Kind.MAINTENANCE_PLAN:
                self.add_error("repeat", "Only a maintenance plan can repeat.")
            if not cleaned.get("visits"):
                self.add_error("visits", "Say how many visits the series has.")
        return cleaned

    def check_add_ons(self, cleaned, service):
        """An add-on must go with the service in the version in effect on the
        job's day (decision 0106). A manager can add another with a reason;
        anyone else picks another. A job being changed keeps the add-ons it
        was booked with, unless its service or add-ons change."""
        from appointments.booking import version_for
        from pricebook.pricing import add_on_rule_text, unfit_add_ons

        add_ons = list(cleaned.get("add_ons") or [])
        day = cleaned.get("date")
        version = version_for(day) if day else PricebookVersion.current()
        if service is None or not add_ons or version is None:
            return
        unfit = unfit_add_ons(version, service, add_ons)
        if not unfit:
            return
        if self.editing and self.unchanged_services(service, add_ons):
            self.add_on_override = True
            return
        words = "; ".join(add_on_rule_text(add_on, service) for add_on in unfit)
        if not self.is_manager:
            self.add_error("add_ons", f"{words}. Pick another, or ask a manager to add it with a reason.")
            return
        if not cleaned.get("add_on_reason", "").strip():
            self.add_error("add_on_reason", f"{words}: give the reason for adding it.")
            return
        self.add_on_override = True
        self.add_on_breaks = [add_on_rule_text(add_on, service) for add_on in unfit]

    def unchanged_services(self, service, add_ons):
        initial_service = self.initial.get("service")
        initial_add_ons = {getattr(item, "pk", item) for item in self.initial.get("add_ons") or []}
        return getattr(initial_service, "pk", initial_service) == service.pk and initial_add_ons == {add_on.pk for add_on in add_ons}

    def check_condition(self, cleaned, service):
        """The condition level, only for a service that takes one in the
        version in effect on the job's day; and for a level booked by quote,
        the hand price and time on site (decision 0103)."""
        from appointments.booking import version_for

        day = cleaned.get("date")
        version = version_for(day) if day else PricebookVersion.current()
        self.takes_level = bool(service and version and version.takes_condition_level(service))
        self.by_quote = False
        if not self.takes_level:
            return
        number = cleaned.get("condition_level")
        if number is None:
            self.add_error("condition_level", f"{service} needs a condition level.")
            return
        level = version.condition_levels.filter(level=number).first()
        self.by_quote = bool(level and level.booked_by_quote)
        if not self.by_quote:
            return
        if cleaned.get("hand_price") is None:
            self.add_error("hand_price", f"Condition level {number} is priced by hand: enter the price before tax.")
        minutes = cleaned.get("hand_minutes")
        if minutes is None:
            self.add_error("hand_minutes", f"Condition level {number} is priced by hand: enter the time on site.")
        elif minutes % 15:
            self.add_error("hand_minutes", "Use steps of 15 minutes.")

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
            condition_level=data.get("condition_level") if self.takes_level else None,
            add_ons=list(data.get("add_ons") or []),
            crew_size=data.get("crew_size") or service.default_crew_size,
            hand_amount=data.get("hand_price") if self.by_quote else None,
            hand_minutes=data.get("hand_minutes") if self.by_quote else None,
            add_on_override=self.add_on_override,
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
        help_text="Used by Full Detail and Interior Only. A level priced by hand has no test price.",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["service"].queryset = Service.objects.filter(
            on_price_list=True, kind__in=[Service.Kind.MAIN, Service.Kind.MAINTENANCE_PLAN]
        ).order_by("kind", "name")
        self.fields["size_variant"].queryset = SizeVariant.objects.filter(active=True, vehicle_class__active=True, vehicle_class__pending=False).select_related("vehicle_class")
        self.fields["size_variant"].label_from_instance = lambda size: f"{size.vehicle_class}: {size.label}"


class AddressForm(forms.ModelForm):
    """A service address the owner types. Saving checks it with the Census
    geocoder, then Google; for one neither finds, the owner pastes its
    location from Google Maps."""

    by_hand = forms.BooleanField(
        required=False, label="Set the location by hand",
        help_text="When neither the Census geocoder nor Google finds the address, such as a street in a new neighborhood.",
    )
    location = forms.CharField(
        required=False, max_length=60, label="Latitude, longitude",
        help_text="In Google Maps, right-click the driveway, click the numbers at the top of the menu to copy them, and paste them here, such as 35.16123, -84.87701.",
    )
    hand_county = forms.CharField(
        required=False, max_length=100, label="County",
        help_text="Optional. In Tennessee the location gives the county; give it for an address in another state, such as Whitfield.",
    )

    class Meta:
        model = Address
        fields = ["line1", "line2", "city", "state", "zip_code", "notes", "active", "approved_out_of_area"]
        labels = {"line1": "Street", "line2": "Unit or apartment", "zip_code": "ZIP code"}
        widgets = {"notes": forms.Textarea(attrs={"rows": 3}), "state": forms.TextInput(attrs={"maxlength": 2, "autocapitalize": "characters"})}

    def __init__(self, *args, can_approve=False, **kwargs):
        super().__init__(*args, **kwargs)
        if not can_approve:
            self.fields["approved_out_of_area"].disabled = True
            self.fields["approved_out_of_area"].help_text = "Only a manager can approve an address outside the service area."
        if self.instance.verification == Address.Verification.BY_HAND:
            point = self.instance.point
            self.initial.update(by_hand=True, hand_county=self.instance.county,
                                location=f"{point[0]}, {point[1]}" if point else "")

    def clean_state(self):
        state = self.cleaned_data["state"].strip().upper()
        if len(state) != 2 or not state.isalpha():
            raise ValidationError("Enter the two-letter state, such as TN.")
        return state

    def clean(self):
        cleaned = super().clean()
        cleaned["point"] = None
        if cleaned.get("by_hand"):
            try:
                cleaned["point"] = parse_location(cleaned.get("location", ""))
            except VerificationError as error:
                self.add_error("location", str(error))
        return cleaned

    def parts_changed(self):
        return any(name in self.changed_data for name in Address.PARTS)


class LocationSettingsForm(forms.ModelForm):
    """The home base, Google's daily caps, the drive-time fallback and the
    tax sourcing rule. A changed home base is checked with the Census
    geocoder unless coordinates are given."""

    class Meta:
        model = LocationSettings
        fields = [
            "home_line1", "home_city", "home_state", "home_zip_code", "home_latitude", "home_longitude",
            "place_details_daily_cap", "text_search_daily_cap", "routes_daily_cap",
            "estimate_road_factor", "estimate_speed_mph", "drive_time_cache_days", "tax_sourcing",
        ]
        help_texts = {
            "home_latitude": "Leave both coordinates blank to look the home base up with the Census geocoder.",
            "place_details_daily_cap": "Keep below the Place Details daily limit set in Google Cloud.",
            "text_search_daily_cap": "Keep below the Text Search daily limit set in Google Cloud. Used for typed addresses the Census geocoder cannot find.",
            "routes_daily_cap": "Keep below the Routes daily limit set in Google Cloud. Past the cap, drive times are estimated.",
            "tax_sourcing": "Decision 0025. Change only on the accountant's advice.",
        }

    def clean_home_state(self):
        return self.cleaned_data["home_state"].strip().upper()

    def clean(self):
        cleaned = super().clean()
        if (cleaned.get("home_latitude") is None) != (cleaned.get("home_longitude") is None):
            self.add_error("home_longitude", "Give both coordinates, or neither.")
        return cleaned

    def home_changed(self):
        return any(name in self.changed_data for name in ("home_line1", "home_city", "home_state", "home_zip_code"))


class ApproveRateForm(forms.Form):
    effective_from = forms.DateField(label="In effect from", widget=forms.DateInput(attrs={"type": "date"}))


class StateRateForm(forms.Form):
    percent = forms.DecimalField(label="Rate (%)", min_value=0, max_value=20, max_digits=6, decimal_places=3)
    effective_from = forms.DateField(label="In effect from", widget=forms.DateInput(attrs={"type": "date"}))


class ReviewForm(forms.ModelForm):
    """One review on the Reviews screen (decision 0109)."""

    stars = forms.TypedChoiceField(
        label="Star rating",
        choices=[("", "No rating")] + [(str(n), f"{n} star{'s' if n > 1 else ''}") for n in range(5, 0, -1)],
        coerce=int,
        empty_value=None,
        required=False,
    )

    class Meta:
        from marketing.models import Review

        model = Review
        fields = ["name", "text", "reviewed_on", "stars", "google_url", "shown"]
        widgets = {
            "reviewed_on": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "text": forms.Textarea(attrs={"rows": 6}),
        }

    def clean_name(self):
        return " ".join(self.cleaned_data["name"].split())

    def clean_text(self):
        return self.cleaned_data["text"].strip()

    def clean_google_url(self):
        url = self.cleaned_data["google_url"].strip()
        if url and not url.startswith("https://"):
            raise ValidationError("Give the link that starts with https://.")
        return url
