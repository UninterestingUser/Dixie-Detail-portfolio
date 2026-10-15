from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction
from django.test import SimpleTestCase, TestCase

from core.fields import format_phone, normalize_phone
from customers.models import Customer, SecondContact


class NormalizePhoneTests(SimpleTestCase):
    def test_formats_reduce_to_10_digits(self):
        for typed in ("(423) 555-0142", "423.555.0142", "423-555-0142", "+1 423 555 0142", "14235550142"):
            with self.subTest(typed=typed):
                self.assertEqual(normalize_phone(typed), "4235550142")

    def test_empty_stays_empty(self):
        for typed in (None, "", "   "):
            with self.subTest(typed=typed):
                self.assertEqual(normalize_phone(typed), "")

    def test_rejects_anything_not_10_digits(self):
        for typed in ("555-0142", "24235550142", "423555014212", "call me"):
            with self.subTest(typed=typed), self.assertRaises(ValidationError):
                normalize_phone(typed)

    def test_display_format(self):
        self.assertEqual(format_phone("4235550142"), "(423) 555-0142")


class StoredPhoneTests(TestCase):
    def test_customer_mobile_saved_as_10_digits(self):
        customer = Customer.objects.create(first_name="Pat", mobile="(423) 555-0142")
        self.assertEqual(customer.mobile, "4235550142")
        with connection.cursor() as cursor:
            cursor.execute("SELECT mobile FROM customers_customer WHERE id = %s", [customer.pk])
            self.assertEqual(cursor.fetchone()[0], "4235550142")

    def test_lookup_with_formatted_number_matches(self):
        customer = Customer.objects.create(first_name="Pat", mobile="423-555-0142")
        self.assertEqual(Customer.objects.get(mobile="+1 (423) 555-0142"), customer)

    def test_second_contact_phone_saved_as_10_digits(self):
        customer = Customer.objects.create(first_name="Pat")
        contact = SecondContact.objects.create(customer=customer, name="Sam", phone="1-423-555-0199")
        contact.refresh_from_db()
        self.assertEqual(contact.phone, "4235550199")

    def test_invalid_number_is_refused(self):
        with self.assertRaises(ValidationError):
            Customer.objects.create(first_name="Pat", mobile="555-0142")

    def test_database_refuses_anything_but_10_digits(self):
        # Bypasses the model field, to prove the database check holds on its own.
        # Each fits the 10-character column, so the check constraint is what refuses it.
        for raw in ("423-555-01", "5550142"):
            with self.subTest(raw=raw), self.assertRaises(IntegrityError), transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute(
                        "INSERT INTO customers_customer"
                        " (first_name, last_name, company, mobile, email, source, notes, created_at)"
                        " VALUES ('Pat', '', '', %s, '', '', '', now())",
                        [raw],
                    )

    def test_customer_without_a_number_is_kept(self):
        self.assertEqual(Customer.objects.create(first_name="Pat").mobile, "")


class CustomerHistoryTests(TestCase):
    def test_change_keeps_the_earlier_value(self):
        customer = Customer.objects.create(first_name="Pat", mobile="4235550142")
        customer.mobile = "4235550199"
        customer.save()
        self.assertEqual(
            [record.mobile for record in customer.history.order_by("history_date")],
            ["4235550142", "4235550199"],
        )
