"""Forms for the customer screens."""

from django import forms
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.utils import timezone

from core.fields import format_phone, normalize_phone
from customers.models import Customer
from vehicles.models import SizeVariant, Vehicle, VehicleClass


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
            Q(active=True) | Q(pk=self.instance.vehicle_class_id)
        )
        self.fields["size_variant"].queryset = SizeVariant.objects.select_related("vehicle_class").filter(
            Q(active=True, vehicle_class__active=True) | Q(pk=self.instance.size_variant_id)
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
