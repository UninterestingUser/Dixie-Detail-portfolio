"""Reading a replayed offline request without refusing it (decision 0114).

A request Cloudflare replays was already accepted from the customer, so a
problem with what it holds (an expired quote, an unknown vehicle, an address
that can't be matched, a malformed phone number) must never lose it. Each
field is read on its own: one that can't be read becomes empty, and the
problem is listed for the owner. Only a bad signature or a body that can't
be read at all is refused (time_requests.check_signature, http.read_json),
and a request without a usable request id, because a second replay of it
couldn't be told from the first.
"""

import uuid

from .http import ApiError, bad_request


class Lenient:
    """The body's fields, read one by one, with the problems found."""

    def __init__(self, data, required, optional):
        if not isinstance(data, dict):
            raise bad_request("body", "The request didn't arrive as a form.")
        self.data = data
        self.problems = []
        missing = [name for name in required if data.get(name) in (None, "")]
        if missing:
            self.problems.append("Not sent: " + ", ".join(missing))
        extra = sorted(name for name in data if name not in required and name not in optional)
        if extra:
            self.problems.append("Not used: " + ", ".join(extra))

    def take(self, label, read, default=None):
        """read(), or default with the problem listed when it fails."""
        try:
            return read()
        except ApiError as error:
            reason = "couldn't be read as sent" if error.code == "bad_request" else error.message
            self.problems.append(f"{label}: {reason}")
        except (KeyError, TypeError, ValueError, AttributeError):
            self.problems.append(f"{label}: couldn't be read as sent")
        return default

    def note(self, problem):
        if problem:
            self.problems.append(problem)

    def problem_text(self):
        return "; ".join(dict.fromkeys(self.problems))


def request_id(data):
    """The website's request id, which makes a second replay harmless. A
    request without one can't be kept safely, so it alone is refused."""
    try:
        return uuid.UUID(str(data["request_id"]))
    except (KeyError, TypeError, ValueError) as error:
        raise bad_request("request_id", "The request has no request id, so it can't be kept.") from error
