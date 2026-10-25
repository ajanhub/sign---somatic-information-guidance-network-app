"""Emergency helplines and facility-finder links."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import quote_plus


@dataclass(frozen=True)
class Helpline:
    """A phone number the user can call for help."""

    name: str
    short_name: str
    display: str
    dial: str
    description: str

    @property
    def tel_url(self) -> str:
        return f"tel:{self.dial}"


HELPLINES = (
    Helpline(
        name="Emergency Services",
        short_name="Emergency",
        display="911",
        dial="911",
        description=(
            "Police, fire and ambulance. Call for chest pain, trouble "
            "breathing, stroke signs, severe bleeding, or anyone in "
            "immediate danger."
        ),
    ),
    Helpline(
        name="Suicide & Crisis Lifeline",
        short_name="Crisis Lifeline",
        display="988",
        dial="988",
        description=(
            "Free, 24/7 support by call or text for suicidal thoughts, "
            "emotional distress or any mental health crisis."
        ),
    ),
    Helpline(
        name="Poison Control",
        short_name="Poison Control",
        display="1-800-222-1222",
        dial="18002221222",
        description=(
            "Free, 24/7 expert help if someone may have swallowed, "
            "breathed in or touched something harmful, or taken too much "
            "of a medicine. Call 911 instead if the person has collapsed, "
            "is having a seizure or is not breathing."
        ),
    ),
)

# Maps a red flag's "response" value (see sign.triage) to its helpline.
HELPLINE_BY_RESPONSE = {
    "911": HELPLINES[0],
    "988": HELPLINES[1],
    "poison": HELPLINES[2],
}

# (button label, Google Maps search text)
FACILITY_SEARCHES = (
    ("Urgent Care near me", "Urgent Care near me"),
    ("Emergency Room near me", "Emergency Room near me"),
    ("Pharmacy near me", "Pharmacy near me"),
)


def facility_search_url(query: str) -> str:
    """Return a Google Maps search URL for ``query``."""
    return (
        "https://www.google.com/maps/search/?api=1&query="
        + quote_plus(query)
    )
