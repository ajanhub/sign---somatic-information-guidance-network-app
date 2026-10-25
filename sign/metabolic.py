"""Metabolic calculations: BMR, TDEE, calorie targets and unit conversions.

No UI or database code lives here, so everything is easy to unit test.
"""

from __future__ import annotations

from dataclasses import dataclass

ACTIVITY_LEVELS = {
    "Sedentary": 1.2,
    "Lightly Active": 1.375,
    "Moderately Active": 1.55,
    "Very Active": 1.725,
}

GOALS = {
    "Maintenance": 0,
    "Deficit": -400,
    "Surplus": 400,
}

SEXES = ("male", "female")

KG_PER_LB = 0.45359237
CM_PER_INCH = 2.54

MIN_AGE, MAX_AGE = 10, 100
MIN_HEIGHT_CM, MAX_HEIGHT_CM = 100.0, 250.0
MIN_WEIGHT_KG, MAX_WEIGHT_KG = 25.0, 300.0

ADULT_AGE = 18
UNDERWEIGHT_BMI = 18.5
MIN_DAILY_CALORIES = 1200

KCAL_PER_GRAM = {"protein": 4, "carbs": 4, "fats": 9}

IMPERIAL = "imperial"
METRIC = "metric"


class ValidationError(ValueError):
    """Raised when a user-supplied number is missing or out of range."""


# ---------------------------------------------------------------- units


def lbs_to_kg(pounds: float) -> float:
    return pounds * KG_PER_LB


def kg_to_lbs(kilograms: float) -> float:
    return kilograms / KG_PER_LB


def inches_to_cm(inches: float) -> float:
    return inches * CM_PER_INCH


def cm_to_inches(centimeters: float) -> float:
    return centimeters / CM_PER_INCH


def feet_inches_to_cm(feet: int, inches: float) -> float:
    return inches_to_cm(feet * 12 + inches)


def cm_to_feet_inches(centimeters: float) -> tuple[int, int]:
    """Split a height in cm into whole feet and whole inches (rounded)."""
    total_inches = int(round(cm_to_inches(centimeters)))
    return total_inches // 12, total_inches % 12


def weight_to_display(kilograms: float, units: str) -> float:
    """Convert stored kg to the user's chosen unit, rounded to 0.1."""
    value = kg_to_lbs(kilograms) if units == IMPERIAL else kilograms
    return round(value, 1)


def weight_from_display(value: float, units: str) -> float:
    """Convert a value typed in the user's unit back to kg."""
    return lbs_to_kg(value) if units == IMPERIAL else float(value)


def weight_unit_label(units: str) -> str:
    return "lb" if units == IMPERIAL else "kg"


def format_weight(kilograms: float, units: str) -> str:
    return f"{weight_to_display(kilograms, units):.1f} {weight_unit_label(units)}"


def format_height(centimeters: float, units: str) -> str:
    if units == IMPERIAL:
        feet, inches = cm_to_feet_inches(centimeters)
        return f"{feet} ft {inches} in"
    return f"{centimeters:.0f} cm"


# -------------------------------------------------------------- profile


@dataclass(frozen=True)
class Profile:
    """A user's body metrics, always stored in metric units."""

    age: int
    sex: str
    height_cm: float
    weight_kg: float
    activity_level: str
    goal: str = "Maintenance"
    target_weight_kg: float | None = None

    def __post_init__(self) -> None:
        if not MIN_AGE <= self.age <= MAX_AGE:
            raise ValidationError(
                f"Age must be between {MIN_AGE} and {MAX_AGE}."
            )
        if self.sex not in SEXES:
            raise ValidationError("Sex must be 'male' or 'female'.")
        if not MIN_HEIGHT_CM <= self.height_cm <= MAX_HEIGHT_CM:
            raise ValidationError(
                f"Height must be between {MIN_HEIGHT_CM:.0f} and "
                f"{MAX_HEIGHT_CM:.0f} cm (about 3 ft 3 in to 8 ft 2 in)."
            )
        validate_weight_kg(self.weight_kg, "Weight")
        if self.target_weight_kg is not None:
            validate_weight_kg(self.target_weight_kg, "Target weight")
        if self.activity_level not in ACTIVITY_LEVELS:
            raise ValidationError("Choose one of the listed activity levels.")
        if self.goal not in GOALS:
            raise ValidationError("Choose one of the listed goals.")


def validate_weight_kg(kilograms: float, label: str = "Weight") -> None:
    if not MIN_WEIGHT_KG <= kilograms <= MAX_WEIGHT_KG:
        raise ValidationError(
            f"{label} must be between {MIN_WEIGHT_KG:.0f} and "
            f"{MAX_WEIGHT_KG:.0f} kg (about {kg_to_lbs(MIN_WEIGHT_KG):.0f} to "
            f"{kg_to_lbs(MAX_WEIGHT_KG):.0f} lb)."
        )


# ------------------------------------------------------------- formulas


def bmr(profile: Profile) -> float:
    """Basal metabolic rate (kcal/day), Mifflin-St Jeor equation."""
    base = (
        10 * profile.weight_kg
        + 6.25 * profile.height_cm
        - 5 * profile.age
    )
    return base + 5 if profile.sex == "male" else base - 161


def tdee(profile: Profile) -> float:
    """Total daily energy expenditure (kcal/day)."""
    return bmr(profile) * ACTIVITY_LEVELS[profile.activity_level]


def bmi(weight_kg: float, height_cm: float) -> float:
    meters = height_cm / 100
    return weight_kg / (meters * meters)


@dataclass(frozen=True)
class CalorieTargets:
    """Daily calorie numbers for one profile."""

    bmr: float
    tdee: float
    maintenance: int
    deficit: int | None
    surplus: int | None
    selected: int
    selected_goal: str
    notes: tuple[str, ...]


def calorie_targets(profile: Profile) -> CalorieTargets:
    """Compute maintenance, deficit and surplus targets with safety limits.

    Safety rules (the app is meant for students and families):
    * Under 18: only a maintenance estimate. Growing bodies need extra
      energy and weight goals should be set with a doctor.
    * BMI below 18.5: no deficit is offered.
    * A deficit never goes below 1,200 kcal per day.
    """
    base_bmr = bmr(profile)
    total = tdee(profile)
    maintenance = int(round(total))
    notes: list[str] = []
    deficit: int | None = None
    surplus: int | None = None

    if profile.age < ADULT_AGE:
        notes.append(
            "Because you are under 18, SIGN only shows a maintenance "
            "estimate. Growing bodies need extra energy, so weight-change "
            "goals should be set with a pediatrician or doctor."
        )
    else:
        current_bmi = bmi(profile.weight_kg, profile.height_cm)
        if current_bmi < UNDERWEIGHT_BMI:
            notes.append(
                "Your BMI is below 18.5, so SIGN does not offer a calorie "
                "deficit. Please talk with a clinician before trying to "
                "lose weight."
            )
        elif maintenance <= MIN_DAILY_CALORIES:
            notes.append(
                "Your maintenance estimate is already at or below "
                f"{MIN_DAILY_CALORIES:,} kcal, so SIGN does not offer a "
                "deficit."
            )
        else:
            raw_deficit = maintenance + GOALS["Deficit"]
            if raw_deficit < MIN_DAILY_CALORIES:
                deficit = MIN_DAILY_CALORIES
                notes.append(
                    f"The deficit target was raised to {MIN_DAILY_CALORIES:,}"
                    " kcal, the lowest amount SIGN will suggest."
                )
            else:
                deficit = raw_deficit
        surplus = maintenance + GOALS["Surplus"]

    selected, applied = maintenance, "Maintenance"
    if profile.goal == "Deficit" and deficit is not None:
        selected, applied = deficit, "Deficit"
    elif profile.goal == "Surplus" and surplus is not None:
        selected, applied = surplus, "Surplus"
    elif profile.goal != "Maintenance":
        notes.append(
            f"Your goal is {profile.goal}, but it is not available for "
            "your profile, so maintenance is shown instead."
        )

    return CalorieTargets(
        bmr=base_bmr,
        tdee=total,
        maintenance=maintenance,
        deficit=deficit,
        surplus=surplus,
        selected=selected,
        selected_goal=applied,
        notes=tuple(notes),
    )


def macro_breakdown(
    protein_g: float, carbs_g: float, fats_g: float
) -> dict[str, dict[str, float]]:
    """Grams, kcal and percent of macro calories for protein/carbs/fats."""
    grams = {"protein": protein_g, "carbs": carbs_g, "fats": fats_g}
    kcal = {name: grams[name] * KCAL_PER_GRAM[name] for name in grams}
    total = sum(kcal.values())
    return {
        name: {
            "grams": grams[name],
            "kcal": kcal[name],
            "percent": (kcal[name] / total * 100) if total else 0.0,
        }
        for name in grams
    }
