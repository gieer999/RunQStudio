from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any

import pandas as pd

RUNQ_VERSION = "0.1"
BASE_AGE = 25.0
AGE_FACTOR = 250.0
RUNQ_FACTOR = 1.5
DISTANCE_EXPONENT = 0.06

OUTPUT_COLUMNS = [
    "RaceId", "RunName", "Year", "RaceDate", "Distance", "Place", "Bib",
    "Name", "City", "Country", "Team", "Sex", "SexPlace", "Category",
    "CategoryAge", "Born", "BornSource", "NettoTime", "BruttoTime",
    "TimeSeconds", "TimeHours", "Speed", "Coeff", "RealAge", "SportAge",
    "RunQ", "RunQVersion",
]


def parse_time_to_seconds(value: Any) -> int | None:
    """Convert HH:MM:SS, MM:SS or a pandas time-like value into seconds."""
    if value is None or pd.isna(value):
        return None

    text = str(value).strip()
    if not text:
        return None

    # Pandas can serialize a time as "0 days 02:14:37".
    if "days" in text:
        try:
            return int(pd.to_timedelta(text).total_seconds())
        except ValueError:
            return None

    parts = text.split(":")
    try:
        numbers = [float(part.replace(",", ".")) for part in parts]
    except ValueError:
        return None

    if len(numbers) == 3:
        hours, minutes, seconds = numbers
    elif len(numbers) == 2:
        hours, minutes, seconds = 0.0, numbers[0], numbers[1]
    else:
        return None

    total = round(hours * 3600 + minutes * 60 + seconds)
    return int(total) if total > 0 else None


def normalize_sex(value: Any) -> str | None:
    if value is None or pd.isna(value):
        return None
    text = str(value).strip().upper()
    mapping = {
        "M": "M", "MALE": "M", "MĘŻCZYZNA": "M", "MEZCZYZNA": "M",
        "W": "W", "F": "W", "FEMALE": "W", "K": "W",
        "KOBIETA": "W", "WOMAN": "W",
    }
    return mapping.get(text)


def parse_category(value: Any) -> tuple[str | None, int | None]:
    if value is None or pd.isna(value):
        return None, None
    text = str(value).strip().upper().replace(" ", "")
    match = re.fullmatch(r"([MWFK])(\d{2,3})", text)
    if not match:
        return None, None
    prefix, age_text = match.groups()
    sex = "M" if prefix == "M" else "W"
    return f"{sex}{int(age_text)}", int(age_text)


def parse_birth_date(value: Any, race_year: int, category_age: int) -> tuple[date, str]:
    """
    Priority:
    1. full date -> exact date,
    2. year only -> 31 December of that year,
    3. missing -> 31 December of (race year - category age).
    """
    if value is not None and not pd.isna(value):
        text = str(value).strip()
        if text:
            year_match = re.fullmatch(r"\d{4}", text)
            if year_match:
                return date(int(text), 12, 31), "year"

            parsed = pd.to_datetime(text, dayfirst=True, errors="coerce")
            if not pd.isna(parsed):
                return parsed.date(), "date"

    return date(int(race_year) - int(category_age), 12, 31), "category"


def calculate_coeff(distance_m: float) -> float:
    return (float(distance_m) / 10000.0) ** DISTANCE_EXPONENT


def calculate_real_age(born: date, race_date: date) -> float:
    # Exact Power Query rule used in the reference workbook.
    return (race_date - born).days / 365.0


def calculate_sport_age(real_age: float) -> float:
    if real_age <= BASE_AGE:
        return BASE_AGE
    return BASE_AGE + (real_age - BASE_AGE) / (AGE_FACTOR / real_age)


def calculate_speed(distance_m: float, time_seconds: int) -> float:
    return (float(distance_m) / 1000.0) / (float(time_seconds) / 3600.0)


def calculate_runq(speed: float, sport_age: float, coeff: float) -> float:
    return speed * sport_age * coeff * RUNQ_FACTOR


def _first_existing(df: pd.DataFrame, names: list[str]) -> str | None:
    for name in names:
        if name in df.columns:
            return name
    return None


def calculate_dataframe(
    df: pd.DataFrame,
    race_id: str,
    race: dict[str, Any],
) -> pd.DataFrame:
    """Create the canonical English RunQ dataset from an STS raw/standard table."""
    source = df.copy()

    columns = {
        "Place": _first_existing(source, ["miejsce_open", "#", "Miejsce", "Place"]),
        "Bib": _first_existing(source, ["numer_startowy", "Numer", "Bib"]),
        "Name": _first_existing(source, ["imie_i_nazwisko", "Imię i nazwisko", "Name"]),
        "City": _first_existing(source, ["miasto", "Miasto", "City"]),
        "Country": _first_existing(source, ["kraj", "Kraj", "Country"]),
        "Team": _first_existing(source, ["team", "Team"]),
        "Sex": _first_existing(source, ["plec", "Płeć", "Sex"]),
        "SexPlace": _first_existing(source, ["miejsce_plec", "Miejsce płeć", "SexPlace"]),
        "Category": _first_existing(source, ["kategoria", "Kategoria", "Category"]),
        "NettoTime": _first_existing(source, ["czas_netto", "Czas netto", "NettoTime"]),
        "BruttoTime": _first_existing(source, ["czas_brutto", "Czas brutto", "BruttoTime"]),
        "BornInput": _first_existing(source, ["born", "Born", "BirthDate", "Rok urodzenia"]),
    }

    required = ["Name", "Sex", "Category", "NettoTime"]
    missing = [name for name in required if columns[name] is None]
    if missing:
        raise ValueError(f"Missing required columns: {', '.join(missing)}")

    race_date = datetime.strptime(race["date"], "%Y-%m-%d").date()
    distance_m = float(race["distance_m"])
    rows: list[dict[str, Any]] = []

    for _, record in source.iterrows():
        sex = normalize_sex(record[columns["Sex"]])
        category, category_age = parse_category(record[columns["Category"]])
        seconds = parse_time_to_seconds(record[columns["NettoTime"]])

        if sex not in {"M", "W"} or category is None or category_age is None or seconds is None:
            continue
        if category[0] != sex:
            continue

        birth_input = record[columns["BornInput"]] if columns["BornInput"] else None
        born, born_source = parse_birth_date(birth_input, int(race["year"]), category_age)
        real_age = calculate_real_age(born, race_date)
        sport_age = calculate_sport_age(real_age)
        speed = calculate_speed(distance_m, seconds)
        coeff = calculate_coeff(distance_m)
        runq = calculate_runq(speed, sport_age, coeff)

        def value(name: str):
            col = columns[name]
            if not col:
                return None
            current = record[col]
            return None if pd.isna(current) else current

        rows.append({
            "RaceId": race_id,
            "RunName": race["run_name"],
            "Year": int(race["year"]),
            "RaceDate": race_date.isoformat(),
            "Distance": distance_m,
            "Place": value("Place"),
            "Bib": value("Bib"),
            "Name": str(record[columns["Name"]]).strip(),
            "City": value("City"),
            "Country": str(value("Country") or "").strip().upper(),
            "Team": value("Team"),
            "Sex": sex,
            "SexPlace": value("SexPlace"),
            "Category": category,
            "CategoryAge": category_age,
            "Born": born.isoformat(),
            "BornSource": born_source,
            "NettoTime": str(record[columns["NettoTime"]]).strip(),
            "BruttoTime": value("BruttoTime"),
            "TimeSeconds": seconds,
            "TimeHours": seconds / 3600.0,
            "Speed": speed,
            "Coeff": coeff,
            "RealAge": real_age,
            "SportAge": sport_age,
            "RunQ": runq,
            "RunQVersion": RUNQ_VERSION,
        })

    result = pd.DataFrame(rows, columns=OUTPUT_COLUMNS)
    if result.empty:
        return result

    numeric = ["Distance", "TimeHours", "Speed", "Coeff", "RealAge", "SportAge", "RunQ"]
    for col in numeric:
        result[col] = pd.to_numeric(result[col], errors="coerce")

    return result.sort_values(["RunQ", "NettoTime"], ascending=[False, True]).reset_index(drop=True)
