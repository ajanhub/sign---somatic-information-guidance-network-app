"""Builds the printable 'Appointment Preparation Summary' text.

This is assembled directly from the user's own entries (no AI), so it is
always accurate to what they typed and always available, even offline.
"""

from __future__ import annotations

from datetime import datetime
from typing import Sequence

from sign.metabolic import Profile, bmi, cm_to_feet_inches, kg_to_lbs
from sign.triage import TriageInput, TriageResult, format_duration

RULE = "=" * 60
MAX_WEIGHTS_SHOWN = 5


def _weight_line(kilograms: float) -> str:
    return f"{kilograms:.1f} kg ({kg_to_lbs(kilograms):.1f} lb)"


def build_summary(
    inp: TriageInput,
    result: TriageResult,
    profile: Profile | None = None,
    weights: Sequence[tuple[str, float]] = (),
    generated: datetime | None = None,
) -> str:
    """Return the summary as plain text.

    ``weights`` is a list of (YYYY-MM-DD, kg) pairs, oldest first.
    """
    stamp = (generated or datetime.now()).strftime("%Y-%m-%d %H:%M")
    lines = [
        RULE,
        "SIGN - APPOINTMENT PREPARATION SUMMARY",
        RULE,
        f"Created: {stamp}",
        "Made from answers the user typed into SIGN, an educational tool. "
        "This is not a medical record or a diagnosis.",
        "",
        "ABOUT ME (self-reported)",
    ]

    if profile is not None:
        feet, inches = cm_to_feet_inches(profile.height_cm)
        lines += [
            f"- Age: {profile.age}",
            f"- Sex assigned at birth: {profile.sex.capitalize()}",
            f"- Height: {profile.height_cm:.0f} cm ({feet} ft {inches} in)",
            f"- Weight: {_weight_line(profile.weight_kg)}",
            f"- BMI: {bmi(profile.weight_kg, profile.height_cm):.1f}",
        ]
    else:
        lines.append("- No profile saved in SIGN")

    flags = (
        "; ".join(flag.label for flag in result.red_flags)
        if result.red_flags
        else "None selected"
    )
    lines += [
        "",
        "SYMPTOMS",
        f"- Body area: {inp.region}",
        "- Symptoms: "
        + (", ".join(inp.symptoms) if inp.symptoms else "None selected"),
        f"- Started about: {format_duration(inp.duration_hours)} ago",
        f"- Severity (1-10): {inp.severity}",
        f"- Trend: {inp.progression}",
        f"- Emergency warning signs: {flags}",
    ]
    if inp.notes.strip():
        lines.append(f"- My notes: {inp.notes.strip()}")

    lines += ["", "LOGGED MEASUREMENTS"]
    if weights:
        recent = list(weights)[-MAX_WEIGHTS_SHOWN:]
        lines.append(
            f"- Latest weight: {_weight_line(recent[-1][1])} "
            f"on {recent[-1][0]}"
        )
        if len(recent) > 1:
            history = ", ".join(
                f"{day}: {kg:.1f} kg" for day, kg in reversed(recent)
            )
            lines.append(f"- Recent weights (newest first): {history}")
    else:
        lines.append("- No weight entries logged")

    lines += [
        "",
        "SIGN CARE LEVEL (from fixed rules, not a diagnosis)",
        f"- {result.info.label}: {result.headline}",
    ]
    lines += [f"- {reason}" for reason in result.reasons]

    lines += [
        "",
        "QUESTIONS TO ASK MY CLINICIAN",
        "- What could be causing these symptoms, and are any tests needed?",
        "- Which warning signs mean I should come back or go to the ER?",
        "- Is there anything I should avoid or do differently meanwhile?",
        "- Could my medicines or health conditions affect this?",
        "",
        "TO FILL IN BY HAND",
        "- Medicines and supplements I take: ____________________________",
        "- Allergies: ___________________________________________________",
        "- Health conditions: ___________________________________________",
        "",
        RULE,
    ]
    return "\n".join(lines)
