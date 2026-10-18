"""Finding a customer by name or by phone number in any format."""

import re

from django.db.models import Q

from customers.models import Customer

LETTERS = re.compile(r"[^\W\d_]")
NON_DIGITS = re.compile(r"\D")
# Fewer digits than this match too many numbers to be useful.
MIN_PHONE_DIGITS = 3
LIMIT = 50


def phone_digits(text):
    """The digits of a typed phone number or part of one, without a leading
    country code 1 on a full number: "+1 (423) 555-0101" -> "4235550101"."""
    digits = NON_DIGITS.sub("", text)
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    return digits


def phone_matches(digits):
    # A regex lookup, because a phone field turns other lookups' values into
    # full 10-digit numbers. The value is digits only.
    return Q(mobile__regex=digits) | Q(second_contacts__phone__regex=digits)


def name_matches(word):
    return (
        Q(first_name__icontains=word)
        | Q(last_name__icontains=word)
        | Q(company__icontains=word)
        | Q(second_contacts__name__icontains=word)
    )


def find_customers(query):
    """Customers matching the query, best known first, and whether there are
    more than LIMIT.

    A query with no letters is a phone number, whole or in part, in any
    format. Otherwise every word must match the customer's first or last
    name, company or a second contact's name; a word of digits only matches
    part of a phone number instead.
    """
    query = query.strip()
    if not query:
        return [], False
    if not LETTERS.search(query):
        digits = phone_digits(query)
        if len(digits) < MIN_PHONE_DIGITS:
            return [], False
        condition = phone_matches(digits)
    else:
        condition = Q()
        for word in query.split():
            if LETTERS.search(word):
                condition &= name_matches(word)
            elif len(phone_digits(word)) >= MIN_PHONE_DIGITS:
                condition &= phone_matches(phone_digits(word))
    found = list(
        Customer.objects.filter(pk__in=Customer.objects.filter(condition).values("pk"))
        .prefetch_related("vehicles", "second_contacts")
        .order_by("last_name", "first_name", "pk")[: LIMIT + 1]
    )
    return found[:LIMIT], len(found) > LIMIT
