"""A fake Google Calendar for tests: no network, the calls the sync makes,
and Google's behavior where the sync depends on it. A deleted event stays,
marked cancelled, and is listed only with show_deleted; a repeating event
is listed visit by visit; down=True makes every call fail as if Google
could not be reached."""

import copy
import datetime

from .google import CalendarError, Conflict, NotFound

UTC = datetime.timezone.utc


def parse(edge):
    if "dateTime" in edge:
        return datetime.datetime.fromisoformat(edge["dateTime"].replace("Z", "+00:00"))
    return datetime.datetime.combine(datetime.date.fromisoformat(edge["date"]), datetime.time(), UTC)


def shift(edge, delta):
    if "dateTime" in edge:
        return {**edge, "dateTime": (parse(edge) + delta).isoformat()}
    return {**edge, "date": (datetime.date.fromisoformat(edge["date"]) + delta).isoformat()}


class FakeCalendar:
    def __init__(self):
        self.calendars = {}
        self.down = False
        self.calls = []
        self.counter = 0

    def events(self, calendar_id):
        return self.calendars.setdefault(calendar_id, {})

    def check(self, name, *args):
        self.calls.append((name, *args))
        if self.down:
            raise CalendarError("Google Calendar could not be reached: fake outage")

    # As the owner, in Google ---------------------------------------------

    def add_by_hand(self, calendar_id, body, event_id=None):
        """Add an event as the owner would in Google: no private properties.
        A body with "recurrence" ["RRULE:FREQ=WEEKLY;COUNT=n"] or
        FREQ=DAILY repeats."""
        self.counter += 1
        event_id = event_id or f"hand{self.counter}"
        self.events(calendar_id)[event_id] = {**copy.deepcopy(body), "id": event_id, "status": body.get("status", "confirmed")}
        return event_id

    def edit_by_hand(self, calendar_id, event_id, **changes):
        self.events(calendar_id)[event_id].update(copy.deepcopy(changes))

    def delete_by_hand(self, calendar_id, event_id):
        self.events(calendar_id)[event_id]["status"] = "cancelled"

    def live(self, calendar_id):
        """The events not deleted, by ID."""
        return {k: v for k, v in self.events(calendar_id).items() if v.get("status") != "cancelled"}

    # The API --------------------------------------------------------------

    def expand(self, event):
        rule = next((r for r in event.get("recurrence", []) if r.startswith("RRULE:")), None)
        if rule is None:
            return [event]
        parts = dict(part.split("=") for part in rule[len("RRULE:"):].split(";"))
        step = {"DAILY": datetime.timedelta(days=1), "WEEKLY": datetime.timedelta(days=7)}[parts["FREQ"]]
        visits = []
        for n in range(int(parts.get("COUNT", 10))):
            start = shift(event["start"], step * n)
            stamp = parse(start).astimezone(UTC).strftime("%Y%m%dT%H%M%SZ") if "dateTime" in start else start["date"].replace("-", "")
            visit = {k: v for k, v in event.items() if k != "recurrence"}
            visits.append({**visit, "id": f"{event['id']}_{stamp}", "recurringEventId": event["id"],
                           "start": start, "end": shift(event["end"], step * n)})
        return visits

    def list_events(self, calendar_id, time_min, time_max=None, show_deleted=False):
        self.check("list", calendar_id)
        found = []
        for event in self.events(calendar_id).values():
            for visit in self.expand(event):
                if visit.get("status") == "cancelled" and not show_deleted:
                    continue
                if parse(visit["end"]) <= time_min or (time_max is not None and parse(visit["start"]) >= time_max):
                    continue
                found.append(copy.deepcopy(visit))
        return found

    def get_event(self, calendar_id, event_id):
        self.check("get", calendar_id, event_id)
        if event_id not in self.events(calendar_id):
            raise NotFound("404")
        return copy.deepcopy(self.events(calendar_id)[event_id])

    def insert_event(self, calendar_id, event_id, body):
        self.check("insert", calendar_id, event_id)
        if event_id in self.events(calendar_id):
            raise Conflict("409")
        if body.get("attendees"):
            raise AssertionError("Customers are never added as guests")
        self.events(calendar_id)[event_id] = {**copy.deepcopy(body), "id": event_id}
        return copy.deepcopy(self.events(calendar_id)[event_id])

    def update_event(self, calendar_id, event_id, body):
        self.check("update", calendar_id, event_id)
        if event_id not in self.events(calendar_id):
            raise NotFound("404")
        if body.get("attendees"):
            raise AssertionError("Customers are never added as guests")
        self.events(calendar_id)[event_id] = {**copy.deepcopy(body), "id": event_id}
        return copy.deepcopy(self.events(calendar_id)[event_id])

    def delete_event(self, calendar_id, event_id):
        self.check("delete", calendar_id, event_id)
        event = self.events(calendar_id).get(event_id)
        if event is None or event.get("status") == "cancelled":
            raise NotFound("410")
        event["status"] = "cancelled"
