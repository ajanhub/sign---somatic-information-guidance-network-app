"""Rule-based symptom triage.

The care level is decided here, by fixed rules, and never by an AI model.
SIGN does not diagnose; it only recommends how quickly to seek care.

Rules, checked in this order (the first match wins):

1. EMERGENCY - any red-flag toggle is selected, or the free-text notes
   mention an emergency phrase. Overrides everything else, including AI.
2. URGENT - severity 7 or higher, OR symptoms older than 72 hours that are
   getting worse. Be seen within 24 hours.
3. PRIMARY_CARE - severity 4 to 6, OR symptoms older than 7 days, OR a
   "caution" symptom is selected even though it is mild.
4. SELF_CARE - everything else (severity 3 or lower, no red flags).

Rule 3's extra conditions fill gaps in the original spec, which defined
only severity 3 or lower and 7 or higher. They err on the side of caution.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import NamedTuple


class Tier(Enum):
    EMERGENCY = "emergency"
    URGENT = "urgent"
    PRIMARY_CARE = "primary_care"
    SELF_CARE = "self_care"


@dataclass(frozen=True)
class TierInfo:
    label: str
    headline: str
    action: str
    color: str


TIER_INFO = {
    Tier.EMERGENCY: TierInfo(
        label="Emergency",
        headline="CALL 911 NOW",
        action=(
            "Call 911 or go to the nearest emergency room right away."
        ),
        color="#b71c1c",
    ),
    Tier.URGENT: TierInfo(
        label="Urgent care",
        headline="Get seen within 24 hours",
        action=(
            "Visit an urgent care clinic or contact your primary care "
            "clinician within the next 24 hours. If anything gets worse or "
            "an emergency warning sign appears, call 911."
        ),
        color="#e65100",
    ),
    Tier.PRIMARY_CARE: TierInfo(
        label="Primary care",
        headline="Schedule a primary care visit",
        action=(
            "Make an appointment with your primary care clinician in the "
            "next few days. If it gets worse or cannot wait, go to urgent "
            "care instead."
        ),
        color="#1565c0",
    ),
    Tier.SELF_CARE: TierInfo(
        label="Self-care",
        headline="Self-care and monitoring",
        action=(
            "Comfort measures at home are reasonable for now. Keep track of "
            "how you feel and see a clinician if things do not improve."
        ),
        color="#2e7d32",
    ),
}

# ------------------------------------------------------------ symptom data

SYMPTOMS: dict[str, tuple[str, ...]] = {
    "General / Systemic": (
        "Fatigue or low energy",
        "Fever or chills",
        "Body aches",
        "Loss of appetite",
        "Night sweats",
        "Dizziness or lightheadedness",
        "Unintended weight change",
    ),
    "Head / Neurological": (
        "Headache",
        "Dizziness",
        "Blurred vision",
        "Sensitivity to light",
        "Numbness or tingling",
        "Trouble concentrating",
        "Ringing in the ears",
    ),
    "Respiratory / Chest": (
        "Cough",
        "Sore throat",
        "Stuffy or runny nose",
        "Sneezing",
        "Wheezing",
        "Shortness of breath with activity",
    ),
    "Gastrointestinal": (
        "Nausea",
        "Vomiting",
        "Diarrhea",
        "Constipation",
        "Stomach pain or cramps",
        "Bloating or gas",
        "Heartburn",
    ),
    "Musculoskeletal": (
        "Joint pain",
        "Muscle soreness",
        "Back pain",
        "Neck stiffness",
        "Swelling",
        "Stiffness",
        "Limited movement",
        "Pain after a sprain or strain",
    ),
    "Skin": (
        "Rash",
        "Itching",
        "Dryness or flaking",
        "Redness",
        "Bruising",
        "Blisters",
        "Minor cut or scrape",
        "Insect bite or sting",
        "Redness spreading or warm to the touch",
    ),
}

# Worth a clinician's opinion even when the person rates them as mild.
CAUTION_SYMPTOMS = frozenset(
    {
        "Wheezing",
        "Shortness of breath with activity",
        "Blurred vision",
        "Numbness or tingling",
        "Neck stiffness",
        "Redness spreading or warm to the touch",
    }
)

PROGRESSIONS = ("Getting worse", "About the same", "Getting better")
WORSENING = PROGRESSIONS[0]

URGENT_SEVERITY = 7
MODERATE_SEVERITY = 4
LONG_DURATION_HOURS = 72
PERSISTENT_HOURS = 7 * 24


# --------------------------------------------------------------- red flags


class RedFlag(NamedTuple):
    key: str
    label: str
    response: str  # "911", "988" or "poison"


RED_FLAGS = (
    RedFlag(
        "chest_pressure",
        "Sudden chest pressure or pain, especially spreading to the arm, "
        "jaw, neck or back",
        "911",
    ),
    RedFlag(
        "shortness_of_breath",
        "Sudden or severe trouble breathing",
        "911",
    ),
    RedFlag(
        "loss_of_consciousness",
        "Fainting or loss of consciousness with no clear reason",
        "911",
    ),
    RedFlag(
        "uncontrolled_bleeding",
        "Bleeding that will not stop with firm, steady pressure",
        "911",
    ),
    RedFlag(
        "stroke_signs",
        "Sudden face drooping, arm or leg weakness, or trouble speaking "
        "or understanding",
        "911",
    ),
    RedFlag(
        "worst_headache",
        "Sudden, severe headache - the worst of your life",
        "911",
    ),
    RedFlag(
        "confusion",
        "New confusion or trouble staying awake",
        "911",
    ),
    RedFlag(
        "allergic_reaction",
        "Swelling of the face, lips or throat, or trouble swallowing, "
        "after an allergen, sting or medicine",
        "911",
    ),
    RedFlag(
        "vomiting_blood",
        "Vomiting blood, or black, tar-like stools",
        "911",
    ),
    RedFlag(
        "poisoning",
        "Possible poisoning, or taking too much of a medicine",
        "poison",
    ),
    RedFlag(
        "self_harm",
        "Thoughts of harming yourself or ending your life",
        "988",
    ),
)

RED_FLAGS_BY_KEY = {flag.key: flag for flag in RED_FLAGS}

# Phrases in free text that trigger the emergency tier. These deliberately
# over-trigger (for example "no chest pain" still matches); when in doubt,
# SIGN chooses the safer answer.
_TEXT_PATTERNS = {
    "self_harm": r"suicid|kill (myself|me)|end (my|this) life|want to die|"
    r"wanna die|hurt(ing)? myself|self[- ]?harm|better off dead",
    "chest_pressure": r"chest (pain|pressure|tightness|is tight|hurts)|"
    r"pain in my chest|pressure in my chest",
    "shortness_of_breath": r"(can'?t|cannot|can not|unable to) breathe|"
    r"trouble breathing|difficulty breathing|struggling to breathe|gasping",
    "uncontrolled_bleeding": r"(won'?t|will not|can'?t|cannot) stop "
    r"bleeding|bleeding (a lot|heavily|badly)|blood everywhere",
    "stroke_signs": r"face (is )?droop|slurred speech|one side of (my|the) "
    r"(body|face)",
    "poisoning": r"overdos|poison|swallowed (bleach|pills|cleaner|"
    r"detergent)|took too many (pills|tablets|meds)",
    "loss_of_consciousness": r"passed out|blacked out|lost consciousness|"
    r"unconscious",
    "allergic_reaction": r"throat (is )?(closing|swelling)|"
    r"face (is )?swelling|anaphyla",
    "vomiting_blood": r"vomit(ing)? blood|throwing up blood|"
    r"blood in (my )?vomit|tarry stool",
    "worst_headache": r"worst headache",
}
_COMPILED_PATTERNS = {
    key: re.compile(pattern, re.IGNORECASE)
    for key, pattern in _TEXT_PATTERNS.items()
}


def scan_free_text(text: str) -> tuple[str, ...]:
    """Return keys of red flags that the free text appears to describe."""
    cleaned = (text or "").replace("’", "'")
    return tuple(
        key
        for key, pattern in _COMPILED_PATTERNS.items()
        if pattern.search(cleaned)
    )


def emergency_headline(flags: tuple[RedFlag, ...] | list[RedFlag]) -> str:
    responses = {flag.response for flag in flags}
    if "911" in responses:
        return "CALL 911 NOW"
    if responses == {"988"}:
        return "CALL OR TEXT 988 NOW"
    if responses == {"poison"}:
        return "CALL POISON CONTROL NOW"
    return "GET HELP RIGHT NOW"


def emergency_steps(flags: tuple[RedFlag, ...] | list[RedFlag]) -> list[str]:
    """Plain-language instructions that match the flags that were raised."""
    responses = {flag.response for flag in flags}
    steps: list[str] = []
    if "911" in responses:
        steps.append(
            "Call 911 now, or ask someone to take you to the nearest "
            "emergency room. Do not drive yourself."
        )
    if "988" in responses:
        steps.append(
            "Call or text 988 (Suicide & Crisis Lifeline) to reach a "
            "trained counselor right now. If you are in immediate danger, "
            "call 911."
        )
    if "poison" in responses:
        steps.append(
            "Call Poison Control at 1-800-222-1222. If the person has "
            "collapsed, is having a seizure or is not breathing, call 911 "
            "instead."
        )
    steps.append(
        "Do not wait for symptoms to pass or for more information from "
        "this app. If someone is nearby, tell them what is happening."
    )
    return steps


# ------------------------------------------------------------ input/result


def format_duration(hours: float) -> str:
    """Describe a number of hours as '5 hours' or '3 days'."""
    if hours < 1:
        return "less than 1 hour"
    if hours < 48:
        count = int(round(hours))
        return f"{count} hour{'s' if count != 1 else ''}"
    days = round(hours / 24, 1)
    return f"{days:g} days"


@dataclass(frozen=True)
class TriageInput:
    region: str
    symptoms: tuple[str, ...]
    duration_hours: float
    severity: int
    progression: str
    red_flags: tuple[str, ...] = ()
    notes: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "symptoms", tuple(self.symptoms))
        object.__setattr__(self, "red_flags", tuple(self.red_flags))
        if self.region not in SYMPTOMS:
            raise ValueError(f"Unknown body region: {self.region!r}")
        if not isinstance(self.severity, int) or not 1 <= self.severity <= 10:
            raise ValueError("Severity must be a whole number from 1 to 10.")
        if self.duration_hours < 0:
            raise ValueError("Duration cannot be negative.")
        if self.progression not in PROGRESSIONS:
            raise ValueError(f"Unknown progression: {self.progression!r}")
        unknown = [k for k in self.red_flags if k not in RED_FLAGS_BY_KEY]
        if unknown:
            raise ValueError(f"Unknown red flag(s): {unknown}")


@dataclass(frozen=True)
class TriageResult:
    tier: Tier
    reasons: tuple[str, ...]
    red_flags: tuple[RedFlag, ...] = ()

    @property
    def info(self) -> TierInfo:
        return TIER_INFO[self.tier]

    @property
    def headline(self) -> str:
        if self.tier is Tier.EMERGENCY:
            return emergency_headline(self.red_flags)
        return self.info.headline

    @property
    def steps(self) -> list[str]:
        if self.tier is Tier.EMERGENCY:
            return emergency_steps(self.red_flags)
        return [self.info.action]


def assess(inp: TriageInput) -> TriageResult:
    """Apply the triage rules and return the care level with reasons."""
    selected = set(inp.red_flags)
    from_text = [k for k in scan_free_text(inp.notes) if k not in selected]
    if selected or from_text:
        flags: list[RedFlag] = []
        reasons: list[str] = []
        for flag in RED_FLAGS:
            if flag.key in selected:
                flags.append(flag)
                reasons.append(f"Warning sign selected: {flag.label}.")
            elif flag.key in from_text:
                flags.append(flag)
                reasons.append(
                    "Your notes mention a possible warning sign: "
                    f"{flag.label}."
                )
        return TriageResult(Tier.EMERGENCY, tuple(reasons), tuple(flags))

    worsening = inp.progression == WORSENING

    urgent: list[str] = []
    if inp.severity >= URGENT_SEVERITY:
        urgent.append(
            f"Severity {inp.severity}/10 is high (7 or above)."
        )
    if inp.duration_hours > LONG_DURATION_HOURS and worsening:
        urgent.append(
            "Symptoms have lasted more than 72 hours and are getting worse."
        )
    if urgent:
        return TriageResult(Tier.URGENT, tuple(urgent))

    primary: list[str] = []
    if inp.severity >= MODERATE_SEVERITY:
        primary.append(f"Severity {inp.severity}/10 is moderate (4 to 6).")
    if inp.duration_hours > PERSISTENT_HOURS:
        primary.append("Symptoms have lasted more than 7 days.")
    caution = [s for s in inp.symptoms if s in CAUTION_SYMPTOMS]
    if caution:
        primary.append(
            "You selected a symptom that deserves a clinician's opinion "
            f"even when mild: {', '.join(caution)}."
        )
    if primary:
        return TriageResult(Tier.PRIMARY_CARE, tuple(primary))

    reasons = [
        f"Severity {inp.severity}/10 is mild (3 or below).",
        "No emergency warning signs were selected.",
    ]
    if worsening:
        reasons.append(
            "Symptoms are getting worse, so check on them often and move "
            "up a level of care if they keep worsening."
        )
    return TriageResult(Tier.SELF_CARE, tuple(reasons))
