"""SQLite persistence for SIGN. Weights are stored in kilograms.

Tables follow the project spec: user_profile, calorie_log and weight_log.
(user_profile also has a target_weight column so the profile can store the
target weight the spec asks for.)
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path
from typing import Iterator

from sign.metabolic import Profile, ValidationError, validate_weight_kg

SCHEMA = """
CREATE TABLE IF NOT EXISTS user_profile (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    age INTEGER NOT NULL,
    sex TEXT NOT NULL,
    height REAL NOT NULL,
    current_weight REAL NOT NULL,
    target_weight REAL,
    activity_level TEXT NOT NULL,
    goal TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS calorie_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    meal_name TEXT NOT NULL,
    calories INTEGER NOT NULL,
    protein REAL NOT NULL DEFAULT 0,
    carbs REAL NOT NULL DEFAULT 0,
    fats REAL NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS weight_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    weight REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_calorie_date ON calorie_log (date);
CREATE INDEX IF NOT EXISTS idx_weight_date ON weight_log (date);
"""

MAX_MEAL_CALORIES = 10000


def _iso(value: date | datetime | str) -> str:
    """Normalize a date, datetime or ISO string to 'YYYY-MM-DD'."""
    if isinstance(value, datetime):
        value = value.date()
    if isinstance(value, date):
        return value.isoformat()
    return date.fromisoformat(str(value)).isoformat()


class Database:
    """Small wrapper around a SQLite file."""

    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self._connection() as conn:
            conn.executescript(SCHEMA)

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        try:
            with conn:  # commits on success, rolls back on error
                yield conn
        finally:
            conn.close()

    # ------------------------------------------------------------ profile

    def save_profile(self, profile: Profile) -> None:
        with self._connection() as conn:
            conn.execute(
                """
                INSERT INTO user_profile
                    (id, age, sex, height, current_weight, target_weight,
                     activity_level, goal)
                VALUES (1, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    age = excluded.age,
                    sex = excluded.sex,
                    height = excluded.height,
                    current_weight = excluded.current_weight,
                    target_weight = excluded.target_weight,
                    activity_level = excluded.activity_level,
                    goal = excluded.goal
                """,
                (
                    profile.age,
                    profile.sex,
                    profile.height_cm,
                    profile.weight_kg,
                    profile.target_weight_kg,
                    profile.activity_level,
                    profile.goal,
                ),
            )

    def get_profile(self) -> Profile | None:
        with self._connection() as conn:
            row = conn.execute(
                "SELECT * FROM user_profile WHERE id = 1"
            ).fetchone()
        if row is None:
            return None
        return Profile(
            age=row["age"],
            sex=row["sex"],
            height_cm=row["height"],
            weight_kg=row["current_weight"],
            activity_level=row["activity_level"],
            goal=row["goal"],
            target_weight_kg=row["target_weight"],
        )

    # -------------------------------------------------------------- meals

    def add_meal(
        self,
        day: date | datetime | str,
        meal_name: str,
        calories: int,
        protein: float = 0.0,
        carbs: float = 0.0,
        fats: float = 0.0,
    ) -> int:
        name = (meal_name or "").strip()
        if not name:
            raise ValidationError("Please enter a meal or food name.")
        if not 0 <= calories <= MAX_MEAL_CALORIES:
            raise ValidationError(
                f"Calories must be between 0 and {MAX_MEAL_CALORIES:,}."
            )
        if min(protein, carbs, fats) < 0:
            raise ValidationError("Macros cannot be negative.")
        with self._connection() as conn:
            cursor = conn.execute(
                "INSERT INTO calorie_log "
                "(date, meal_name, calories, protein, carbs, fats) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (_iso(day), name, int(calories), protein, carbs, fats),
            )
            return int(cursor.lastrowid)

    def delete_meal(self, meal_id: int) -> None:
        with self._connection() as conn:
            conn.execute("DELETE FROM calorie_log WHERE id = ?", (meal_id,))

    def meals_on(self, day: date | datetime | str) -> list[dict]:
        with self._connection() as conn:
            rows = conn.execute(
                "SELECT * FROM calorie_log WHERE date = ? ORDER BY id",
                (_iso(day),),
            ).fetchall()
        return [dict(row) for row in rows]

    def daily_totals(self, day: date | datetime | str) -> dict:
        with self._connection() as conn:
            row = conn.execute(
                "SELECT COALESCE(SUM(calories), 0) AS calories, "
                "COALESCE(SUM(protein), 0) AS protein, "
                "COALESCE(SUM(carbs), 0) AS carbs, "
                "COALESCE(SUM(fats), 0) AS fats "
                "FROM calorie_log WHERE date = ?",
                (_iso(day),),
            ).fetchone()
        return {
            "calories": int(row["calories"]),
            "protein": float(row["protein"]),
            "carbs": float(row["carbs"]),
            "fats": float(row["fats"]),
        }

    # ------------------------------------------------------------ weights

    def log_weight(self, day: date | datetime | str, weight_kg: float) -> None:
        """Add a weight entry and keep the profile's current weight in sync.

        The profile always shows the weight from the newest dated entry, so
        back-dating an old entry does not overwrite today's weight.
        """
        validate_weight_kg(weight_kg)
        with self._connection() as conn:
            conn.execute(
                "INSERT INTO weight_log (date, weight) VALUES (?, ?)",
                (_iso(day), weight_kg),
            )
            conn.execute(
                "UPDATE user_profile SET current_weight = ("
                "SELECT weight FROM weight_log "
                "ORDER BY date DESC, id DESC LIMIT 1) WHERE id = 1"
            )

    def weight_history(self) -> list[tuple[str, float]]:
        """All (date, kg) entries, oldest first."""
        with self._connection() as conn:
            rows = conn.execute(
                "SELECT date, weight FROM weight_log ORDER BY date, id"
            ).fetchall()
        return [(row["date"], row["weight"]) for row in rows]

    def latest_weight(self) -> tuple[str, float] | None:
        with self._connection() as conn:
            row = conn.execute(
                "SELECT date, weight FROM weight_log "
                "ORDER BY date DESC, id DESC LIMIT 1"
            ).fetchone()
        return (row["date"], row["weight"]) if row else None

    # ------------------------------------------------------------ privacy

    def clear_all(self) -> None:
        """Delete every saved profile, meal and weight entry."""
        with self._connection() as conn:
            conn.execute("DELETE FROM user_profile")
            conn.execute("DELETE FROM calorie_log")
            conn.execute("DELETE FROM weight_log")
