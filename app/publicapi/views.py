"""The public API's endpoints, all under /api/public/v1/ (public-api.md).
Each view checks its input strictly and answers JSON; http.api_view adds
CORS, the rate limit and the generic errors."""

from . import bookings, catalog, quote_requests, quotes, time_requests, validate
from .http import api_view, bad_request, read_json

# Pricebook and catalog answers change rarely; the website and browsers may
# keep them five minutes.
CACHE_SECONDS = 300


@api_view(["GET"], "read", cache_seconds=CACHE_SECONDS)
def services(request):
    return catalog.pricebook()


@api_view(["GET"], "read", cache_seconds=CACHE_SECONDS)
def reviews(request):
    """The reviews shown on the website, in the owner's order (decision 0109)."""
    query(request, ())
    return catalog.reviews()


@api_view(["GET"], "read", cache_seconds=CACHE_SECONDS)
def price_table(request):
    query(request, ())
    return catalog.price_table()


@api_view(["GET"], "read", cache_seconds=CACHE_SECONDS)
def booking_options(request):
    return catalog.booking_options()


def query(request, allowed):
    for name in request.GET:
        if name not in allowed:
            raise bad_request(name)
    return request.GET


@api_view(["GET"], "read", cache_seconds=CACHE_SECONDS)
def vehicle_years(request):
    query(request, ())
    return catalog.years()


@api_view(["GET"], "read", cache_seconds=CACHE_SECONDS)
def vehicle_makes(request):
    params = query(request, ("year",))
    return catalog.makes(validate.integer(params.get("year"), "year", 1900, 2100))


@api_view(["GET"], "read", cache_seconds=CACHE_SECONDS)
def vehicle_models(request):
    params = query(request, ("year", "make"))
    year = validate.integer(params.get("year"), "year", 1900, 2100)
    return catalog.models(year, validate.text(params.get("make"), "make", 60))


@api_view(["GET"], "read", cache_seconds=CACHE_SECONDS)
def vehicle_lookup(request):
    params = query(request, ("year", "make", "model", "type", "size"))
    vehicle = catalog.parse_vehicle({name: params[name] for name in ("year", "make", "model", "type") if name in params})
    size = validate.integer(params.get("size"), "size", 1, 9, required=False)
    return catalog.lookup_json(catalog.resolve(vehicle, size))


@api_view(["GET"], "read", cache_seconds=CACHE_SECONDS)
def photo_cards(request):
    query(request, ())
    return {"photo_cards": catalog.cards_json()}


@api_view(["POST"], "address")
def addresses(request):
    data = read_json(request)
    validate.only(data, ["place_id"], ["session_token"])
    if not isinstance(data["place_id"], str) or len(data["place_id"]) > 300:
        raise bad_request("place_id")
    session_token = data.get("session_token") or ""
    if not isinstance(session_token, str) or len(session_token) > 64:
        raise bad_request("session_token")
    return 201, quotes.place_json(quotes.verify_place(data["place_id"], session_token))


@api_view(["POST"], "quote")
def create_quote(request):
    data = read_json(request)
    validate.only(data, ["vehicle", "service"], ["size", "condition", "add_ons", "place"])
    vehicle = catalog.parse_vehicle(data["vehicle"])
    size = validate.integer(data.get("size"), "size", 1, 9, required=False)
    service = quotes.parse_service(data["service"])
    condition = validate.integer(data.get("condition"), "condition", 1, 3, required=False)
    add_ons = quotes.parse_add_ons(data.get("add_ons"))
    place = quotes.find_place(validate.token(data["place"], "place")) if data.get("place") else None
    web = quotes.issue(catalog.resolve(vehicle, size), service, condition, add_ons, place, answered=size)
    return 201, quotes.quote_json(web)


@api_view(["GET"], "read")
def open_times(request):
    params = query(request, ("quote", "from", "days"))
    web = quotes.find_quote(validate.number(params.get("quote"), "quote"))
    first = validate.date(params["from"], "from") if "from" in params else None
    days = validate.integer(params.get("days"), "days", 1, quotes.MAX_DAYS, required=False) or 14
    return quotes.open_times_json(web, first, days)


@api_view(["POST"], "booking")
def create_booking(request):
    return bookings.book(request, read_json(request))


@api_view(["POST"], "upload_session")
def upload_session(request):
    return quote_requests.open_session(request, read_json(request))


@api_view(["POST"], "photo")
def upload_photo(request, session):
    return quote_requests.upload(request, session)


@api_view(["DELETE"], "photo")
def delete_photo(request, session, photo):
    return quote_requests.remove(request, session, photo)


@api_view(["POST"], "quote_request")
def create_quote_request(request):
    return quote_requests.send(request, read_json(request))


@api_view(["POST"], "offline")
def create_offline_quote_request(request):
    return quote_requests.receive_offline(request, read_json(request))


@api_view(["POST"], "offline")
def create_time_request(request):
    return time_requests.receive(request, read_json(request))
