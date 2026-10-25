"""SIGN - Somatic Information Guidance Network.

Run with:  streamlit run app.py
"""

from __future__ import annotations

import base64
import html
import os
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import streamlit as st

from sign import ai_guidance, report
from sign.config import (
    APP_FULL_NAME,
    DISCLAIMER_POINTS,
    DISCLAIMER_SUMMARY,
)
from sign.database import MAX_MEAL_CALORIES, Database
from sign.directory import (
    FACILITY_SEARCHES,
    HELPLINE_BY_RESPONSE,
    HELPLINES,
    facility_search_url,
)
from sign.metabolic import (
    ACTIVITY_LEVELS,
    GOALS,
    IMPERIAL,
    MAX_AGE,
    MAX_HEIGHT_CM,
    MAX_WEIGHT_KG,
    METRIC,
    MIN_AGE,
    MIN_HEIGHT_CM,
    MIN_WEIGHT_KG,
    Profile,
    ValidationError,
    calorie_targets,
    cm_to_feet_inches,
    feet_inches_to_cm,
    format_weight,
    macro_breakdown,
    weight_from_display,
    weight_to_display,
    weight_unit_label,
)
from sign.triage import (
    PROGRESSIONS,
    RED_FLAGS,
    RED_FLAGS_BY_KEY,
    SYMPTOMS,
    Tier,
    TriageInput,
    assess,
    emergency_headline,
    emergency_steps,
    scan_free_text,
)

st.set_page_config(page_title="SIGN", page_icon="🩺", layout="wide")

VIEW_DASHBOARD = "Dashboard"
VIEW_TRACKER = "Calories & Weight"
VIEW_EVALUATION = "Symptom Evaluation"
VIEW_GUIDANCE = "Guidance & Export"
VIEW_DIRECTORY = "Emergency Directory"
VIEWS = [
    VIEW_DASHBOARD,
    VIEW_TRACKER,
    VIEW_EVALUATION,
    VIEW_GUIDANCE,
    VIEW_DIRECTORY,
]

STEP_TITLES = (
    "Body area",
    "Symptoms",
    "Duration and severity",
    "Emergency warning signs",
)

REGION_EXPLANATIONS = {
    "General / Systemic": "Affects your whole body (e.g., fever, tiredness, body aches, chills).",
    "Head / Neurological": "Brain, nerve, and head symptoms (e.g., headaches, dizziness, numbness, tingling).",
    "Respiratory / Chest": "Lungs, breathing, and chest area (e.g., cough, congestion, chest tightness).",
    "Gastrointestinal": "Stomach, digestion, and gut (e.g., nausea, abdominal pain, diarrhea, heartburn).",
    "Musculoskeletal": "Muscles, joints, bones, or back (e.g., sprains, joint swelling, stiffness).",
    "Skin": "Surface reactions (e.g., rash, hives, itching, unusual spots).",
}

DEFAULT_DB_PATH = Path(__file__).parent / "data" / "sign.db"
SLATE = "#37474f"
EMERGENCY_RED = "#b71c1c"


# ------------------------------------------------------------ logo helper


def get_logo_html(size_px: int = 70) -> str:
    """Return an HTML snippet for a circular logo that blends seamlessly into the background."""
    paths_to_check = [
        Path(__file__).parent / "logo.png",
        Path(__file__).parent / "signapplogocanva.png",
        Path(__file__).parent / "assets" / "logo.png",
    ]
    logo_file = next((p for p in paths_to_check if p.exists()), None)
    if logo_file:
        encoded = base64.b64encode(logo_file.read_bytes()).decode()
        return (
            f'<div style="display:flex;align-items:center;gap:12px;">'
            f'<img src="data:image/png;base64,{encoded}" '
            f'style="width:{size_px}px;height:{size_px}px;border-radius:50%;'
            f'object-fit:cover;box-shadow:0 2px 8px rgba(0,0,0,0.4);border:2px solid #2e3842;">'
            f'<div><span style="font-size:1.45rem;font-weight:800;letter-spacing:0.04em;">SIGN</span><br>'
            f'<span style="font-size:0.75rem;color:#94a3b8;">Health Guidance Network</span></div>'
            f'</div>'
        )
    return (
        f'<div style="display:flex;align-items:center;gap:10px;">'
        f'<div style="width:{size_px}px;height:{size_px}px;border-radius:50%;background:#1e293b;'
        f'display:flex;align-items:center;justify-content:center;font-size:1.8rem;border:2px solid #334155;">🩺</div>'
        f'<div><span style="font-size:1.45rem;font-weight:800;letter-spacing:0.04em;">SIGN</span><br>'
        f'<span style="font-size:0.75rem;color:#94a3b8;">Health Guidance Network</span></div>'
        f'</div>'
    )


# ------------------------------------------------------------ shared helpers


@st.cache_resource
def _open_database(path: str) -> Database:
    return Database(path)


def get_db() -> Database:
    return _open_database(os.environ.get("SIGN_DB_PATH") or str(DEFAULT_DB_PATH))


def init_state() -> None:
    defaults = {
        "acknowledged": False,
        "view": VIEW_DASHBOARD,
        "units": IMPERIAL,
        "wiz_step": 0,
        "wiz": {},
        "triage": None,
        "guidance_cache": {},
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def go_to(view: str) -> None:
    st.session_state["view"] = view


def banner(title: str, lines=(), color: str = EMERGENCY_RED) -> None:
    body = "".join(
        '<div style="margin-top:0.4rem;font-size:1.05rem;">'
        f"{html.escape(line)}</div>"
        for line in lines
    )
    st.markdown(
        f'<div style="background:{color};color:#ffffff;padding:1.1rem 1.3rem;'
        'border-radius:0.6rem;margin:0.5rem 0 1rem 0;">'
        '<div style="font-size:1.7rem;font-weight:800;letter-spacing:0.02em;">'
        f"{html.escape(title)}</div>{body}</div>",
        unsafe_allow_html=True,
    )


def call_label(display: str) -> str:
    return "Call or text 988" if display == "988" else f"Call {display}"


def render_hotline_bar() -> None:
    columns = st.columns(len(HELPLINES))
    for column, helpline in zip(columns, HELPLINES):
        column.link_button(
            f"{helpline.short_name}: {helpline.display}", helpline.tel_url
        )


def render_emergency(flags) -> None:
    banner(emergency_headline(flags), emergency_steps(flags), EMERGENCY_RED)
    helplines = []
    for flag in flags:
        helpline = HELPLINE_BY_RESPONSE[flag.response]
        if helpline not in helplines:
            helplines.append(helpline)
    for column, helpline in zip(st.columns(len(helplines)), helplines):
        column.link_button(call_label(helpline.display), helpline.tel_url)


# ------------------------------------------------------------ disclaimer gate


def acknowledge() -> None:
    st.session_state["acknowledged"] = True


def render_gate() -> None:
    st.markdown(get_logo_html(size_px=80), unsafe_allow_html=True)
    st.write("")
    banner("Please read before you start", (DISCLAIMER_SUMMARY,), SLATE)
    for point in DISCLAIMER_POINTS:
        st.markdown(f"- {point}")
    st.markdown("**In an emergency, use these numbers:**")
    render_hotline_bar()
    agreed = st.checkbox(
        "I understand that SIGN is educational only and does not replace professional medical care.",
        key="gate_check",
    )
    st.button(
        "Continue to SIGN",
        type="primary",
        disabled=not agreed,
        key="gate_continue",
        on_click=acknowledge,
    )


# ------------------------------------------------------------ top horizontal navigation


def wipe_data() -> None:
    get_db().clear_all()
    st.session_state["triage"] = None
    st.session_state["guidance_cache"] = {}
    st.session_state["wiz"] = {}
    st.session_state["wiz_step"] = 0
    st.session_state["wipe_confirm"] = False
    st.session_state["wipe_done"] = True


def render_top_navigation() -> None:
    nav_logo, nav_views, nav_units = st.columns([2.2, 5.0, 1.4], vertical_alignment="center")

    with nav_logo:
        st.markdown(get_logo_html(size_px=58), unsafe_allow_html=True)

    with nav_views:
        chosen_view = st.segmented_control(
            "Navigation",
            VIEWS,
            default=st.session_state["view"],
            label_visibility="collapsed",
            key="top_nav_selector",
        )
        if chosen_view and chosen_view != st.session_state["view"]:
            st.session_state["view"] = chosen_view
            st.rerun()

    with nav_units:
        st.segmented_control(
            "Units",
            [IMPERIAL, METRIC],
            key="units",
            format_func=lambda u: "lb / ft" if u == IMPERIAL else "kg / cm",
            label_visibility="collapsed",
        )

    st.markdown('<hr style="margin:0.7rem 0 1.5rem 0;opacity:0.25;">', unsafe_allow_html=True)


# ------------------------------------------------------------------ dashboard


def view_dashboard() -> None:
    st.header("Dashboard")
    database = get_db()
    units = st.session_state["units"]
    profile = database.get_profile()
    totals = database.daily_totals(date.today())
    history = database.weight_history()

    left, middle, right = st.columns(3)
    with left:
        st.subheader("Calories today")
        st.metric("Logged", f"{totals['calories']:,} kcal")
        if profile:
            target = calorie_targets(profile).selected
            st.progress(
                min(totals["calories"] / target, 1.0),
                text=f"Daily target: {target:,} kcal",
            )
        else:
            st.caption("Save your profile to see a daily target.")

    with middle:
        st.subheader("Latest weight")
        if history:
            latest_day, latest_kg = history[-1]
            delta = None
            if len(history) > 1:
                change = weight_to_display(latest_kg, units) - weight_to_display(
                    history[-2][1], units
                )
                delta = f"{change:+.1f} {weight_unit_label(units)}"
            st.metric(
                f"On {latest_day}",
                format_weight(latest_kg, units),
                delta=delta,
                delta_color="off",
            )
        else:
            st.caption("No weight logged yet.")

    with right:
        st.subheader("Feeling unwell?")
        st.write("Answer a few questions to find out how quickly to get care.")
        st.button(
            "🩺 Evaluate a symptom",
            type="primary",
            key="dash_triage",
            on_click=go_to,
            args=(VIEW_EVALUATION,),
        )

    if profile is None:
        st.info("Start by saving your profile so SIGN can estimate your calorie needs.")
        st.button(
            "Set up my profile",
            key="dash_profile",
            on_click=go_to,
            args=(VIEW_TRACKER,),
        )
    if st.session_state.get("triage"):
        st.divider()
        st.write("You have a recent symptom check from this session.")
        st.button(
            "View my results",
            key="dash_results",
            on_click=go_to,
            args=(VIEW_GUIDANCE,),
        )


# -------------------------------------------------------------------- tracker


def view_tracker() -> None:
    st.header("Calories & Weight")
    database = get_db()
    profile_tab, meals_tab, weight_tab = st.tabs(
        ["Profile & targets", "Meals", "Weight"]
    )
    with profile_tab:
        tab_profile(database)
    with meals_tab:
        tab_meals(database)
    with weight_tab:
        tab_weight(database)


def tab_profile(database: Database) -> None:
    units = st.session_state["units"]
    unit = weight_unit_label(units)
    profile = database.get_profile()
    sexes = ["Male", "Female"]
    activity_names = list(ACTIVITY_LEVELS)
    goal_names = list(GOALS)
    min_w = weight_to_display(MIN_WEIGHT_KG, units)
    max_w = weight_to_display(MAX_WEIGHT_KG, units)
    height_default = profile.height_cm if profile else 170.0
    weight_default = weight_to_display(
        profile.weight_kg if profile else 70.0, units
    )
    target_default = (
        weight_to_display(profile.target_weight_kg, units)
        if profile and profile.target_weight_kg
        else 0.0
    )

    with st.form("profile_form"):
        left, right = st.columns(2)
        age = left.number_input(
            "Age",
            min_value=MIN_AGE,
            max_value=MAX_AGE,
            value=profile.age if profile else 25,
            step=1,
        )
        sex_label = right.radio(
            "Sex assigned at birth (used only in the calorie formula)",
            sexes,
            index=sexes.index(profile.sex.capitalize()) if profile else 0,
            horizontal=True,
        )
        if units == IMPERIAL:
            feet_default, inches_default = cm_to_feet_inches(height_default)
            feet_col, inch_col = left.columns(2)
            feet = feet_col.number_input(
                "Height (ft)", min_value=3, max_value=8,
                value=feet_default, step=1,
            )
            inches = inch_col.number_input(
                "Height (in)", min_value=0, max_value=11,
                value=inches_default, step=1,
            )
            height_cm = feet_inches_to_cm(int(feet), int(inches))
        else:
            height_cm = left.number_input(
                "Height (cm)",
                min_value=MIN_HEIGHT_CM,
                max_value=MAX_HEIGHT_CM,
                value=float(round(height_default, 1)),
                step=0.5,
                format="%.1f",
            )
        weight_value = right.number_input(
            f"Current weight ({unit})",
            min_value=min_w,
            max_value=max_w,
            value=weight_default,
            step=0.1,
            format="%.1f",
        )
        target_value = right.number_input(
            f"Target weight ({unit}) - optional, 0 means none",
            min_value=0.0,
            max_value=max_w,
            value=target_default,
            step=0.1,
            format="%.1f",
        )
        activity = left.selectbox(
            "Activity level",
            activity_names,
            index=activity_names.index(profile.activity_level) if profile else 0,
            format_func=lambda name: f"{name} (x{ACTIVITY_LEVELS[name]})",
        )
        goal = right.radio(
            "Goal",
            goal_names,
            index=goal_names.index(profile.goal) if profile else 0,
            horizontal=True,
        )
        submitted = st.form_submit_button(
            "Save profile", type="primary", key="save_profile"
        )

    if submitted:
        try:
            new_profile = Profile(
                age=int(age),
                sex=sex_label.lower(),
                height_cm=float(height_cm),
                weight_kg=weight_from_display(weight_value, units),
                activity_level=activity,
                goal=goal,
                target_weight_kg=(
                    weight_from_display(target_value, units)
                    if target_value > 0
                    else None
                ),
            )
        except ValidationError as error:
            st.error(str(error))
        else:
            database.save_profile(new_profile)
            latest = database.latest_weight()
            if latest is None or abs(latest[1] - new_profile.weight_kg) > 0.05:
                database.log_weight(date.today(), new_profile.weight_kg)
            st.success("Profile saved.")
            profile = database.get_profile()

    if profile is None:
        st.info("Save your profile to see your calorie targets.")
        return

    targets = calorie_targets(profile)
    st.subheader("Your daily calorie estimates")
    cols = st.columns(4)
    cols[0].metric("BMR", f"{targets.bmr:,.0f} kcal")
    cols[1].metric("Maintenance (TDEE)", f"{targets.maintenance:,} kcal")
    cols[2].metric(
        "Deficit (-400)",
        f"{targets.deficit:,} kcal" if targets.deficit else "Not offered",
    )
    cols[3].metric(
        "Surplus (+400)",
        f"{targets.surplus:,} kcal" if targets.surplus else "Not offered",
    )
    st.success(
        f"Your daily target ({targets.selected_goal.lower()}): "
        f"**{targets.selected:,} kcal**"
    )
    for note in targets.notes:
        st.info(note)
    st.caption(
        "Estimates use the Mifflin-St Jeor equation. They are starting "
        "points, not a prescription. Talk to a doctor or dietitian before "
        "making big changes to how you eat."
    )


def tab_meals(database: Database) -> None:
    today = date.today()
    st.subheader("Log a meal or snack")
    with st.form("meal_form", clear_on_submit=True):
        top_left, top_right = st.columns([2, 1])
        meal_name = top_left.text_input("Meal or food name")
        meal_day = top_right.date_input(
            "Date", value=today, max_value=today, key="meal_day"
        )
        c1, c2, c3, c4 = st.columns(4)
        calories = c1.number_input(
            "Calories (kcal)", min_value=0, max_value=MAX_MEAL_CALORIES,
            value=0, step=10,
        )
        protein = c2.number_input(
            "Protein (g)", min_value=0.0, max_value=1000.0,
            value=0.0, step=1.0, format="%.1f",
        )
        carbs = c3.number_input(
            "Carbs (g)", min_value=0.0, max_value=1000.0,
            value=0.0, step=1.0, format="%.1f",
        )
        fats = c4.number_input(
            "Fats (g)", min_value=0.0, max_value=1000.0,
            value=0.0, step=1.0, format="%.1f",
        )
        submitted = st.form_submit_button(
            "Add meal", type="primary", key="add_meal"
        )
    if submitted:
        try:
            database.add_meal(
                meal_day, meal_name, int(calories), protein, carbs, fats
            )
        except ValidationError as error:
            st.error(str(error))
        else:
            st.success(f"Added {meal_name.strip()}.")

    st.subheader("Daily log")
    log_day = st.date_input(
        "Show entries for", value=today, max_value=today, key="log_day"
    )
    meals = database.meals_on(log_day)
    if not meals:
        st.info("No meals logged for this day yet.")
        return
    for meal in meals:
        row = st.columns([4, 1.4, 1.2, 1.2, 1.2, 0.8])
        row[0].write(meal["meal_name"])
        row[1].write(f"{meal['calories']:,} kcal")
        row[2].write(f"P {meal['protein']:g} g")
        row[3].write(f"C {meal['carbs']:g} g")
        row[4].write(f"F {meal['fats']:g} g")
        if row[5].button("✕", key=f"del_meal_{meal['id']}", help="Delete"):
            database.delete_meal(meal["id"])
            st.rerun()

    totals = database.daily_totals(log_day)
    st.metric("Total for the day", f"{totals['calories']:,} kcal")
    breakdown = macro_breakdown(
        totals["protein"], totals["carbs"], totals["fats"]
    )
    if any(item["grams"] > 0 for item in breakdown.values()):
        chart = pd.DataFrame(
            {"Calories from macros": [
                breakdown["protein"]["kcal"],
                breakdown["carbs"]["kcal"],
                breakdown["fats"]["kcal"],
            ]},
            index=["Protein", "Carbs", "Fats"],
        )
        st.bar_chart(chart)
        st.caption(
            f"Protein {breakdown['protein']['percent']:.0f}% - "
            f"Carbs {breakdown['carbs']['percent']:.0f}% - "
            f"Fats {breakdown['fats']['percent']:.0f}% of macro calories "
            "(from grams: 4, 4 and 9 kcal per gram)."
        )


def tab_weight(database: Database) -> None:
    units = st.session_state["units"]
    unit = weight_unit_label(units)
    profile = database.get_profile()
    history = database.weight_history()
    min_w = weight_to_display(MIN_WEIGHT_KG, units)
    max_w = weight_to_display(MAX_WEIGHT_KG, units)
    if history:
        start_kg = history[-1][1]
    else:
        start_kg = profile.weight_kg if profile else 70.0

    st.subheader("Log your weight")
    with st.form("weight_form"):
        left, right = st.columns(2)
        day = left.date_input(
            "Date", value=date.today(), max_value=date.today(),
            key="weight_day",
        )
        value = right.number_input(
            f"Weight ({unit})",
            min_value=min_w,
            max_value=max_w,
            value=weight_to_display(start_kg, units),
            step=0.1,
            format="%.1f",
        )
        submitted = st.form_submit_button(
            "Log weight", type="primary", key="log_weight"
        )
    if submitted:
        try:
            database.log_weight(day, weight_from_display(value, units))
        except ValidationError as error:
            st.error(str(error))
        else:
            st.success("Weight logged.")
            history = database.weight_history()

    if profile and profile.target_weight_kg and history:
        gap = weight_to_display(history[-1][1], units) - weight_to_display(
            profile.target_weight_kg, units
        )
        st.caption(
            f"Target: {format_weight(profile.target_weight_kg, units)} "
            f"({abs(gap):.1f} {unit} {'above' if gap > 0 else 'below'} your latest weight)."
        )
    if len(history) >= 2:
        chart = pd.DataFrame(
            {f"Weight ({unit})": [
                weight_to_display(kg, units) for _, kg in history
            ]},
            index=pd.to_datetime([day for day, _ in history]),
        )
        st.line_chart(chart)
    elif history:
        st.info("Log at least two weights to see a trend line.")
    if history:
        recent = pd.DataFrame(
            {
                "Date": [day for day, _ in reversed(history[-10:])],
                f"Weight ({unit})": [
                    weight_to_display(kg, units)
                    for _, kg in reversed(history[-10:])
                ],
            }
        )
        st.dataframe(recent, hide_index=True)


# -------------------------------------------------------------- symptom evaluation


def set_step(step: int) -> None:
    st.session_state["wiz_step"] = step
    st.rerun()


def view_evaluation() -> None:
    st.header("Symptom Evaluation")
    st.error(
        "**If you think this is an emergency, call 911 now.** For a mental "
        "health crisis, call or text 988. Do not wait to finish this questionnaire."
    )
    step = st.session_state["wiz_step"]
    wiz = st.session_state["wiz"]
    st.progress(
        (step + 1) / len(STEP_TITLES),
        text=f"Step {step + 1} of {len(STEP_TITLES)}: {STEP_TITLES[step]}",
    )
    if step == 0:
        wizard_region(wiz)
    elif step == 1:
        wizard_symptoms(wiz)
    elif step == 2:
        wizard_duration(wiz)
    else:
        wizard_red_flags(wiz)


def wizard_region(wiz: dict) -> None:
    regions = list(SYMPTOMS)
    current = wiz.get("region", regions[0])

    left_col, right_col = st.columns([1.6, 1.2])

    with left_col:
        with st.form("wiz_form_0"):
            region = st.radio(
                "Which area best matches what you are feeling?",
                regions,
                index=regions.index(current),
            )
            next_clicked = st.form_submit_button(
                "Next", type="primary", key="wiz_next_0"
            )

    with right_col:
        st.markdown("**What these areas mean:**")
        for reg_name, explanation in REGION_EXPLANATIONS.items():
            st.markdown(f"• **{reg_name}**  \n*{explanation}*")

    if next_clicked:
        if wiz.get("region") != region:
            wiz["symptoms"] = ()
        wiz["region"] = region
        set_step(1)


def wizard_symptoms(wiz: dict) -> None:
    region = wiz.get("region", list(SYMPTOMS)[0])
    options = list(SYMPTOMS[region])

    alert_keys = wiz.get("alert_flags")
    if alert_keys:
        render_emergency([RED_FLAGS_BY_KEY[key] for key in alert_keys])
        st.warning(
            "Your notes mention something that can be an emergency. Please get help first."
        )
        if st.button(
            "I understand - continue my symptom evaluation",
            key="wiz_alert_continue",
        ):
            wiz["alert_ack_text"] = wiz.get("notes", "")
            wiz.pop("alert_flags", None)
            set_step(2)

    with st.form("wiz_form_1"):
        selected = st.multiselect(
            f"Select every symptom that applies ({region})",
            options,
            default=[s for s in wiz.get("symptoms", ()) if s in options],
        )
        notes = st.text_area(
            "Anything else? (optional, a few words)",
            value=wiz.get("notes", ""),
            max_chars=500,
        )
        back_col, next_col = st.columns(2)
        back_clicked = back_col.form_submit_button("Back", key="wiz_back_1")
        next_clicked = next_col.form_submit_button(
            "Next", type="primary", key="wiz_next_1"
        )

    if not (back_clicked or next_clicked):
        return
    wiz["symptoms"] = tuple(selected)
    wiz["notes"] = notes
    if back_clicked:
        wiz.pop("alert_flags", None)
        set_step(0)
    if not selected and not notes.strip():
        st.error("Please choose at least one symptom or describe it.")
        return
    flags = scan_free_text(notes)
    if flags and wiz.get("alert_ack_text") != notes:
        wiz["alert_flags"] = flags
        st.rerun()
    wiz.pop("alert_flags", None)
    set_step(2)


def wizard_duration(wiz: dict) -> None:
    units = ["hours", "days"]
    with st.form("wiz_form_2"):
        amount_col, unit_col = st.columns(2)
        amount = amount_col.number_input(
            "How long has this been going on?",
            min_value=1,
            max_value=999,
            value=int(wiz.get("duration_amount", 1)),
            step=1,
        )
        unit = unit_col.radio(
            "Unit",
            units,
            index=units.index(wiz.get("duration_unit", "days")),
            horizontal=True,
        )
        severity = st.slider(
            "Pain or severity",
            min_value=1,
            max_value=10,
            value=int(wiz.get("severity", 3)),
        )
        st.caption("1 = barely noticeable, 5 = hard to ignore, 10 = worst imaginable")
        progression = st.radio(
            "Is it getting better or worse?",
            PROGRESSIONS,
            index=PROGRESSIONS.index(wiz.get("progression", PROGRESSIONS[1])),
            horizontal=True,
        )
        back_col, next_col = st.columns(2)
        back_clicked = back_col.form_submit_button("Back", key="wiz_back_2")
        next_clicked = next_col.form_submit_button(
            "Next", type="primary", key="wiz_next_2"
        )
    if back_clicked or next_clicked:
        wiz.update(
            duration_amount=int(amount),
            duration_unit=unit,
            severity=int(severity),
            progression=progression,
        )
        set_step(1 if back_clicked else 3)


def wizard_red_flags(wiz: dict) -> None:
    st.subheader("Emergency warning signs")
    st.write("Do any of these apply to you **right now**? Tick all that do.")
    checked = [
        flag.key
        for flag in RED_FLAGS
        if st.checkbox(flag.label, key=f"rf_{flag.key}")
    ]
    if checked:
        render_emergency([RED_FLAGS_BY_KEY[key] for key in checked])
        st.caption("Please get help first. You can still view your summary below.")
    back_col, finish_col = st.columns(2)
    if back_col.button("Back", key="wiz_back_3"):
        set_step(2)
    if finish_col.button("See my results", type="primary", key="wiz_finish"):
        finish_wizard(wiz, checked)


def finish_wizard(wiz: dict, red_flag_keys: list[str]) -> None:
    multiplier = 24 if wiz.get("duration_unit", "days") == "days" else 1
    inp = TriageInput(
        region=wiz.get("region", list(SYMPTOMS)[0]),
        symptoms=tuple(wiz.get("symptoms", ())),
        duration_hours=wiz.get("duration_amount", 1) * multiplier,
        severity=int(wiz.get("severity", 3)),
        progression=wiz.get("progression", PROGRESSIONS[1]),
        red_flags=tuple(red_flag_keys),
        notes=wiz.get("notes", ""),
    )
    st.session_state["triage"] = (inp, assess(inp))
    st.session_state["wiz"] = {}
    st.session_state["wiz_step"] = 0
    go_to(VIEW_GUIDANCE)
    st.rerun()


# ------------------------------------------------------------ guidance/export


def view_guidance() -> None:
    st.header("Guidance & Export")
    triage = st.session_state.get("triage")
    if triage is None:
        st.info("You have not done a symptom evaluation yet.")
        st.button(
            "Start a symptom evaluation",
            type="primary",
            key="guidance_start",
            on_click=go_to,
            args=(VIEW_EVALUATION,),
        )
        return

    inp, result = triage
    database = get_db()
    profile = database.get_profile()

    if result.tier is Tier.EMERGENCY:
        render_emergency(result.red_flags)
    else:
        banner(result.headline, result.steps, result.info.color)
        st.caption(f"Care level: {result.info.label}")

    st.markdown("**Why SIGN chose this level**")
    for reason in result.reasons:
        st.markdown(f"- {reason}")
    st.caption("SIGN suggests how quickly to seek care. It does not diagnose.")

    st.divider()
    if result.tier is Tier.EMERGENCY:
        st.info(ai_guidance.EMERGENCY_GUIDANCE)
    else:
        render_guidance_text(inp, result, profile)

    st.divider()
    st.subheader("Appointment Preparation Summary")
    summary = report.build_summary(
        inp,
        result,
        profile=profile,
        weights=database.weight_history(),
        generated=datetime.now(),
    )
    st.download_button(
        "Download summary (.txt)",
        data=summary,
        file_name=f"sign_summary_{date.today().isoformat()}.txt",
        mime="text/plain",
        key="download_summary",
    )
    st.caption("Download and print this summary file (Ctrl+P or Cmd+P) to bring to your appointment.")
    st.button(
        "Start a new symptom evaluation",
        key="guidance_new",
        on_click=go_to,
        args=(VIEW_EVALUATION,),
    )


def render_guidance_text(inp, result, profile) -> None:
    config = ai_guidance.load_config()
    use_ai = False
    if config.enabled:
        use_ai = st.toggle("Use AI-written tips", value=True, key="use_ai")
        st.caption(
            "When this is on, the details of this symptom check plus your "
            f"age and sex are sent to {config.description} to write the tips "
            "below. No name or contact information is sent."
        )

    cache = st.session_state["guidance_cache"]
    cache_key = (
        inp,
        use_ai,
        profile.age if profile else None,
        profile.sex if profile else None,
    )
    guidance = cache.get(cache_key)
    if guidance is None:
        with st.spinner("Preparing your guidance..."):
            guidance = ai_guidance.get_guidance(
                inp, result, profile, config, use_ai
            )
        if not use_ai or guidance.source == "ai":
            cache[cache_key] = guidance
    if guidance.note:
        st.warning(guidance.note)
    st.markdown(guidance.text)


# ------------------------------------------------------------------ directory


def view_directory() -> None:
    st.header("Emergency Directory")
    st.write("Tap a number to call from a phone, or dial it yourself.")
    for helpline in HELPLINES:
        with st.container(border=True):
            info_col, button_col = st.columns([3, 1])
            info_col.markdown(
                f"**{helpline.name}** - {helpline.display}\n\n"
                f"{helpline.description}"
            )
            button_col.link_button(
                call_label(helpline.display) + " now", helpline.tel_url
            )

    st.subheader("Find care near you")
    columns = st.columns(len(FACILITY_SEARCHES))
    for column, (label, query) in zip(columns, FACILITY_SEARCHES):
        column.link_button(f"Find {label}", facility_search_url(query))
    st.caption(
        "These open Google Maps in a new tab. Your browser may ask to share "
        "your location with Google Maps. SIGN does not see or store it."
    )


VIEW_RENDERERS = {
    VIEW_DASHBOARD: view_dashboard,
    VIEW_TRACKER: view_tracker,
    VIEW_EVALUATION: view_evaluation,
    VIEW_GUIDANCE: view_guidance,
    VIEW_DIRECTORY: view_directory,
}


def render_footer_privacy() -> None:
    with st.expander("Privacy and data options"):
        st.caption(
            "Your profile, meals, and weights are saved locally on this computer. "
            "Symptom checks are discarded once the session is closed."
        )
        if st.session_state.get("wipe_done"):
            del st.session_state["wipe_done"]
            st.success("All saved data was deleted.")
        st.checkbox("I understand this cannot be undone", key="wipe_confirm")
        st.button(
            "Delete all my saved data",
            key="wipe_go",
            disabled=not st.session_state.get("wipe_confirm", False),
            on_click=wipe_data,
        )


def main() -> None:
    init_state()
    if not st.session_state["acknowledged"]:
        render_gate()
        return

    render_top_navigation()
    VIEW_RENDERERS[st.session_state["view"]]()
    render_footer_privacy()


main()