from __future__ import annotations

import hashlib
import io
import json
import re
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import pandas as pd
import requests
from flask import Flask, Response, flash, redirect, render_template, request, send_from_directory, url_for

from runq_engine import calculate_dataframe

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR.parent / "data"
CONFIG_PATH = BASE_DIR / "races.json"

app = Flask(__name__)
APP_VERSION = "0.9.0"
app.secret_key = "runq-local"


def normalize_person_name(value: Any) -> str:
    """Return an accent-insensitive technical key for matching/searching names."""
    text = str(value or "").translate(str.maketrans({
        "ł": "l", "Ł": "L", "đ": "d", "Đ": "D",
        "ø": "o", "Ø": "O", "æ": "ae", "Æ": "AE",
        "œ": "oe", "Œ": "OE", "ß": "ss",
    }))
    text = unicodedata.normalize("NFKD", text)
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]", "", text.casefold())


def format_person_name(value: Any) -> str:
    """Format source names as SURNAME Given-name while preserving Polish characters."""
    text = re.sub(r"\s+", " ", str(value or "").strip())
    if not text:
        return ""
    parts = text.split(" ")
    surname = parts[0].upper()
    given_names = " ".join(part.lower().capitalize() for part in parts[1:])
    return f"{surname} {given_names}".strip()


def load_races() -> dict[str, dict[str, Any]]:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def base_params(race: dict[str, Any]) -> list[tuple[str, str | int]]:
    return [
        ("search", 1),
        ("dystans", race["distance_id"]),
        ("dystans", race["distance_id"]),
        ("filter[country]", ""),
        ("filter[city]", ""),
        ("filter[team]", ""),
        ("filter[sex]", ""),
        ("filter[cat]", ""),
    ]


def build_url(race: dict[str, Any], show_columns: list[int] | None = None) -> str:
    params = base_params(race)
    for value in (show_columns or race.get("show_columns", list(range(1, 9)))):
        params.append(("show[]", value))
    params.append(("sort", ""))
    return f"https://live.sts-timing.pl/{race['event_code']}/wyniki.php?{urlencode(params)}"


def race_dir(race_id: str) -> Path:
    path = DATA_DIR / race_id
    for sub in ("source", "raw", "standard", "runq", "metadata"):
        (path / sub).mkdir(parents=True, exist_ok=True)
    return path


def latest_metadata(race_id: str) -> dict[str, Any] | None:
    path = DATA_DIR / race_id / "metadata" / "latest.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def flatten_columns(df: pd.DataFrame) -> pd.DataFrame:
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [" ".join(str(x) for x in col if str(x) != "nan").strip() for col in df.columns]
    else:
        df.columns = [str(col).strip() for col in df.columns]
    return df


def find_results_table(html: bytes) -> pd.DataFrame:
    tables = pd.read_html(io.BytesIO(html), decimal=",", thousands=" ")
    candidates: list[pd.DataFrame] = []
    for table in tables:
        table = flatten_columns(table)
        cols = " | ".join(table.columns).lower()
        if "imię i nazwisko" in cols and "czas netto" in cols:
            candidates.append(table)
    if not candidates:
        detected = [list(flatten_columns(t.copy()).columns) for t in tables]
        raise ValueError(
            "Nie znaleziono tabeli z kolumnami „Imię i nazwisko” i „Czas netto”. "
            f"Wykryte nagłówki: {detected[:3]}"
        )
    return max(candidates, key=len).copy()


def clean_header(text: str) -> str:
    text = re.sub(r"^#+", "", str(text)).strip()
    return re.sub(r"\s+", " ", text)


def normalize_dataframe(df: pd.DataFrame, race_id: str, race: dict[str, Any]) -> pd.DataFrame:
    df = df.copy()
    df.columns = [clean_header(c) for c in df.columns]
    df = df.dropna(how="all")

    if "Imię i nazwisko" in df.columns:
        df = df[df["Imię i nazwisko"].astype(str).str.strip().str.lower() != "imię i nazwisko"]

    rename = {
        "#": "miejsce_open",
        "Miejsce": "miejsce_open",
        "Numer": "numer_startowy",
        "Imię i nazwisko": "imie_i_nazwisko",
        "Miasto": "miasto",
        "Kraj": "kraj",
        "Team": "team",
        "Płeć": "plec",
        "Miejsce płeć": "miejsce_plec",
        "Kategoria": "kategoria",
        "Czas netto": "czas_netto",
        "Czas brutto": "czas_brutto",
    }
    df = df.rename(columns={c: rename.get(c, c) for c in df.columns})

    for col in list(df.columns):
        if str(col).lower() in {"#numer", "numer"} and "numer_startowy" not in df.columns:
            df = df.rename(columns={col: "numer_startowy"})

    df.insert(0, "race_id", race_id)
    df.insert(1, "nazwa_biegu", race["name"])
    df.insert(2, "rok", race["year"])
    df.insert(3, "rodzaj", race["kind"])
    df.insert(4, "dystans_km", race["distance_m"] / 1000)
    df.insert(5, "data_biegu", race["date"])
    return df.reset_index(drop=True)


def save_runq_files(standard: pd.DataFrame, race_id: str, race: dict[str, Any], folder: Path, stamp: str) -> pd.DataFrame:
    runq = calculate_dataframe(standard, race_id, race)
    version = folder / "runq" / f"runq_{stamp}.csv"
    latest = folder / "runq" / "latest.csv"
    runq.to_csv(version, index=False, encoding="utf-8-sig")
    runq.to_csv(latest, index=False, encoding="utf-8-sig")
    return runq


def import_race(race_id: str) -> dict[str, Any]:
    races = load_races()
    if race_id not in races:
        raise KeyError(f"Nieznany bieg: {race_id}")
    race = races[race_id]

    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) RunQImporter/0.6",
        "Accept-Language": "pl-PL,pl;q=0.9,en;q=0.7",
    })

    show_columns = [int(v) for v in race["show_columns"]]
    url = build_url(race, show_columns)
    now = datetime.now().astimezone()
    stamp = now.strftime("%Y-%m-%d_%H%M%S")
    folder = race_dir(race_id)

    response = session.get(url, timeout=90)
    response.raise_for_status()
    html = response.content
    checksum = hashlib.sha256(html).hexdigest()

    source_version = folder / "source" / f"source_{stamp}.html"
    source_latest = folder / "source" / "latest.html"
    source_version.write_bytes(html)
    source_latest.write_bytes(html)

    raw = find_results_table(html)
    raw_version = folder / "raw" / f"raw_{stamp}.csv"
    raw_latest = folder / "raw" / "latest.csv"
    raw.to_csv(raw_version, index=False, encoding="utf-8-sig")
    raw.to_csv(raw_latest, index=False, encoding="utf-8-sig")

    standard = normalize_dataframe(raw, race_id, race)
    std_version = folder / "standard" / f"standard_{stamp}.csv"
    std_latest = folder / "standard" / "latest.csv"
    standard.to_csv(std_version, index=False, encoding="utf-8-sig")
    standard.to_csv(std_latest, index=False, encoding="utf-8-sig")

    runq = save_runq_files(standard, race_id, race, folder, stamp)

    metadata = {
        "race_id": race_id,
        "name": race["name"],
        "run_name": race["run_name"],
        "kind": race["kind"],
        "year": race["year"],
        "date": race["date"],
        "distance_m": race["distance_m"],
        "event_code": race["event_code"],
        "distance_id": race["distance_id"],
        "show_columns": show_columns,
        "url": url,
        "downloaded_at": now.isoformat(timespec="seconds"),
        "http_status": response.status_code,
        "html_bytes": len(html),
        "sha256": checksum,
        "rows": int(len(standard)),
        "runq_rows": int(len(runq)),
        "columns": list(standard.columns),
        "runq_columns": list(runq.columns),
        "files": {
            "source": str(source_version.relative_to(DATA_DIR)),
            "raw": str(raw_version.relative_to(DATA_DIR)),
            "standard": str(std_version.relative_to(DATA_DIR)),
            "runq": str((folder / "runq" / f"runq_{stamp}.csv").relative_to(DATA_DIR)),
        },
    }

    text = json.dumps(metadata, ensure_ascii=False, indent=2)
    (folder / "metadata" / f"metadata_{stamp}.json").write_text(text, encoding="utf-8")
    (folder / "metadata" / "latest.json").write_text(text, encoding="utf-8")
    return metadata


def dashboard_rows() -> list[dict[str, Any]]:
    rows = []
    for race_id, race in load_races().items():
        meta = latest_metadata(race_id)
        rows.append({
            "race_id": race_id,
            **race,
            "distance_km": race["distance_m"] / 1000,
            "url": build_url(race),
            "status": "Pobrano" if meta else "Niepobrano",
            "rows": meta.get("rows") if meta else None,
            "runq_rows": meta.get("runq_rows") if meta else None,
            "downloaded_at": meta.get("downloaded_at") if meta else None,
            "sha256_short": meta.get("sha256", "")[:12] if meta else None,
        })
    return sorted(rows, key=lambda x: (x["kind"], x["year"]))


def load_all_runq() -> pd.DataFrame:
    frames = []
    for race_id in load_races():
        path = DATA_DIR / race_id / "runq" / "latest.csv"
        if path.exists():
            frame = pd.read_csv(path)
            frames.append(frame)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def filter_rankings(df: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    defaults = {
        "year": request.args.get("year", ""),
        "distance": request.args.get("distance", ""),
        "sex": request.args.get("sex", "M"),
        "age": request.args.get("age", ""),
        "country": request.args.get("country", "POL"),
        "name": request.args.get("name", "").strip(),
        "limit": request.args.get("limit", "100"),
    }

    filtered = df.copy()
    if defaults["year"]:
        filtered = filtered[filtered["Year"] == int(defaults["year"])]
    if defaults["distance"]:
        filtered = filtered[filtered["Distance"] == float(defaults["distance"])]
    if defaults["sex"]:
        filtered = filtered[filtered["Sex"] == defaults["sex"]]
    if defaults["age"] == "under40":
        filtered = filtered[pd.to_numeric(filtered["CategoryAge"], errors="coerce") < 40]
    elif defaults["age"] == "40plus":
        filtered = filtered[pd.to_numeric(filtered["CategoryAge"], errors="coerce") >= 40]
    if defaults["country"]:
        filtered = filtered[filtered["Country"].fillna("").str.upper() == defaults["country"].upper()]
    if defaults["name"]:
        search_key = normalize_person_name(defaults["name"])
        name_keys = filtered["Name"].fillna("").map(normalize_person_name)
        filtered = filtered[name_keys.str.contains(search_key, regex=False)]

    filtered = filtered.sort_values(["RunQ", "NettoTime"], ascending=[False, True]).reset_index(drop=True)

    # Temporary athlete identity for the ranking view: one best result per person.
    # Runner Engine will later replace this key with a persistent RunnerID.
    normalized_name = filtered["Name"].fillna("").map(normalize_person_name)
    athlete_key = (
        normalized_name
        + "|" + filtered["Sex"].fillna("").astype(str).str.upper()
        + "|" + filtered["Country"].fillna("").astype(str).str.upper()
    )
    filtered = (
        filtered.assign(_AthleteKey=athlete_key)
        .drop_duplicates(subset="_AthleteKey", keep="first")
        .drop(columns="_AthleteKey")
        .reset_index(drop=True)
    )
    filtered.insert(0, "Rank", range(1, len(filtered) + 1))

    try:
        limit = max(1, min(int(defaults["limit"]), 5000))
    except ValueError:
        limit = 100
        defaults["limit"] = "100"

    options = {
        "years": sorted(df["Year"].dropna().astype(int).unique().tolist(), reverse=True),
        "distances": sorted(df["Distance"].dropna().astype(float).unique().tolist()),
        "sexes": sorted(df["Sex"].dropna().astype(str).unique().tolist()),
        "countries": sorted(x for x in df["Country"].dropna().astype(str).unique().tolist() if x),
    }
    return filtered.head(limit), {"filters": defaults, **options, "total_filtered": len(filtered)}


def ranking_display(df: pd.DataFrame) -> pd.DataFrame:
    """Build the public ranking view without exposing technical engine fields."""
    races = load_races()
    race_names = {
        race_id: ("Warsaw Half Marathon" if race["kind"] == "Półmaraton" else "Warsaw Marathon")
        for race_id, race in races.items()
    }

    display = pd.DataFrame({
        "Rank": df["Rank"],
        "Name": df["Name"].map(format_person_name),
        "Country": df["Country"].fillna(""),
        "RunQ": pd.to_numeric(df["RunQ"], errors="coerce"),
        "Category": df["Category"].fillna(""),
        "Time": df["NettoTime"],
        "Race": df["RaceId"].map(race_names).fillna(df["RunName"]),
        "Date": pd.to_datetime(df["RaceDate"], errors="coerce").dt.strftime("%d.%m.%Y"),
    })
    return display


@app.get("/")
def index():
    return render_template("index.html", races=dashboard_rows(), app_version=APP_VERSION)


@app.post("/import/<race_id>")
def import_one(race_id: str):
    try:
        meta = import_race(race_id)
        flash(
            f"{race_id.upper()}: pobrano {meta['rows']} wyników; "
            f"obliczono RunQ dla {meta['runq_rows']} rekordów.",
            "success",
        )
    except Exception as exc:
        flash(f"{race_id.upper()}: błąd — {exc}", "error")
    return redirect(url_for("index"))


@app.post("/import-all")
def import_all():
    ok, errors = 0, []
    for race_id in load_races():
        try:
            import_race(race_id)
            ok += 1
        except Exception as exc:
            errors.append(f"{race_id.upper()}: {exc}")
    flash(f"Pobrano poprawnie: {ok}. Błędy: {len(errors)}.", "success" if not errors else "error")
    for error in errors[:5]:
        flash(error, "error")
    return redirect(url_for("index"))


@app.get("/rankings")
def rankings():
    df = load_all_runq()
    if df.empty:
        flash("Najpierw pobierz co najmniej jedną edycję.", "error")
        return redirect(url_for("index"))

    rows, context = filter_rankings(df)
    display = ranking_display(rows)
    return render_template(
        "rankings.html",
        rows=display.to_dict(orient="records"),
        columns=list(display.columns),
        **context,
    )


@app.get("/rankings.csv")
def rankings_csv():
    df = load_all_runq()
    if df.empty:
        return "No RunQ data", 404
    rows, _ = filter_rankings(df)
    output = ranking_display(rows).to_csv(index=False, encoding="utf-8-sig")
    return Response(
        output.encode("utf-8-sig"),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=runq_ranking.csv"},
    )


@app.get("/preview/<race_id>")
def preview(race_id: str):
    races = load_races()
    if race_id not in races:
        return "Nieznany bieg", 404
    csv_path = DATA_DIR / race_id / "standard" / "latest.csv"
    if not csv_path.exists():
        flash("Najpierw pobierz dane tego biegu.", "error")
        return redirect(url_for("index"))
    df = pd.read_csv(csv_path, nrows=200)
    return render_template(
        "preview.html",
        race_id=race_id,
        race=races[race_id],
        columns=list(df.columns),
        rows=df.fillna("").to_dict(orient="records"),
        total=latest_metadata(race_id).get("rows", len(df)),
    )


@app.get("/files/<race_id>/<kind>/<path:filename>")
def files(race_id: str, kind: str, filename: str):
    allowed = {"source", "raw", "standard", "runq", "metadata"}
    if kind not in allowed:
        return "Niedozwolony katalog", 403
    return send_from_directory(DATA_DIR / race_id / kind, filename, as_attachment=True)


if __name__ == "__main__":
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    print(f"RunQ Studio v{APP_VERSION}: http://127.0.0.1:5001")
    app.run(host="127.0.0.1", port=5001, debug=False)
n
import re
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import pandas as pd
import requests
from flask import Flask, flash, redirect, render_template, request, send_from_directory, url_for

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
CONFIG_PATH = BASE_DIR / "races.json"

app = Flask(__name__)
app.secret_key = "runq-local-v05"


def load_races() -> dict[str, dict[str, Any]]:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def base_params(race: dict[str, Any]) -> list[tuple[str, str | int]]:
    # STS generuje adres z parametrem dystans powtórzonym dwa razy.
    # Zachowujemy dokładnie ten układ, zamiast upraszczać adres.
    return [
        ("search", 1),
        ("dystans", race["distance_id"]),
        ("dystans", race["distance_id"]),
        ("filter[country]", ""),
        ("filter[city]", ""),
        ("filter[team]", ""),
        ("filter[sex]", ""),
        ("filter[cat]", ""),
    ]


def build_url(race: dict[str, Any], show_columns: list[int] | None = None) -> str:
    params = base_params(race)
    for value in (show_columns or race.get("show_columns", list(range(1, 9)))):
        params.append(("show[]", value))
    params.append(("sort", ""))
    return f"https://live.sts-timing.pl/{race['event_code']}/wyniki.php?{urlencode(params)}"


def race_dir(race_id: str) -> Path:
    path = DATA_DIR / race_id
    for sub in ("source", "raw", "standard", "metadata"):
        (path / sub).mkdir(parents=True, exist_ok=True)
    return path


def latest_metadata(race_id: str) -> dict[str, Any] | None:
    path = DATA_DIR / race_id / "metadata" / "latest.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def flatten_columns(df: pd.DataFrame) -> pd.DataFrame:
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [" ".join(str(x) for x in col if str(x) != "nan").strip() for col in df.columns]
    else:
        df.columns = [str(col).strip() for col in df.columns]
    return df


def find_results_table(html: bytes) -> pd.DataFrame:
    tables = pd.read_html(io.BytesIO(html), decimal=",", thousands=" ")
    candidates: list[pd.DataFrame] = []
    for table in tables:
        table = flatten_columns(table)
        cols = " | ".join(table.columns).lower()
        if "imię i nazwisko" in cols and "czas netto" in cols:
            candidates.append(table)
    if not candidates:
        detected = [list(flatten_columns(t.copy()).columns) for t in tables]
        raise ValueError(
            "Nie znaleziono tabeli z kolumnami „Imię i nazwisko” i „Czas netto”. "
            f"Wykryte nagłówki: {detected[:3]}"
        )
    return max(candidates, key=len).copy()


def clean_header(text: str) -> str:
    text = re.sub(r"^#+", "", str(text)).strip()
    return re.sub(r"\s+", " ", text)


def normalize_dataframe(df: pd.DataFrame, race_id: str, race: dict[str, Any]) -> pd.DataFrame:
    df = df.copy()
    df.columns = [clean_header(c) for c in df.columns]
    df = df.dropna(how="all")

    # Usuń wiersze powtarzające nagłówek, jeśli STS je wstawił.
    if "Imię i nazwisko" in df.columns:
        df = df[df["Imię i nazwisko"].astype(str).str.strip().str.lower() != "imię i nazwisko"]

    rename = {
        "#": "miejsce_open",
        "Miejsce": "miejsce_open",
        "Numer": "numer_startowy",
        "Imię i nazwisko": "imie_i_nazwisko",
        "Miasto": "miasto",
        "Kraj": "kraj",
        "Team": "team",
        "Płeć": "plec",
        "Miejsce płeć": "miejsce_plec",
        "Kategoria": "kategoria",
        "Czas netto": "czas_netto",
        "Czas brutto": "czas_brutto",
    }
    df = df.rename(columns={c: rename.get(c, c) for c in df.columns})

    # Czasem pierwsza kolumna po odczycie ma nazwę np. „#Numer”.
    for col in list(df.columns):
        if str(col).lower() in {"#numer", "numer"} and "numer_startowy" not in df.columns:
            df = df.rename(columns={col: "numer_startowy"})

    df.insert(0, "race_id", race_id)
    df.insert(1, "nazwa_biegu", race["name"])
    df.insert(2, "rok", race["year"])
    df.insert(3, "rodzaj", race["kind"])
    df.insert(4, "dystans_km", race["distance_km"])
    return df.reset_index(drop=True)


def import_race(race_id: str) -> dict[str, Any]:
    races = load_races()
    if race_id not in races:
        raise KeyError(f"Nieznany bieg: {race_id}")
    race = races[race_id]
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) RunQImporter/0.5",
        "Accept-Language": "pl-PL,pl;q=0.9,en;q=0.7",
    })
    # STS ma stałe numery kolumn czasu dla tych dwóch typów imprez:
    # półmaraton 13/14, maraton 18/19. Używamy jawnej konfiguracji
    # i nie próbujemy już automatycznie odgadywać pól formularza.
    show_columns = [int(v) for v in race["show_columns"]]
    url = build_url(race, show_columns)
    now = datetime.now().astimezone()
    stamp = now.strftime("%Y-%m-%d_%H%M%S")
    folder = race_dir(race_id)

    response = session.get(url, timeout=90)
    response.raise_for_status()
    html = response.content
    checksum = hashlib.sha256(html).hexdigest()

    source_version = folder / "source" / f"source_{stamp}.html"
    source_latest = folder / "source" / "latest.html"
    source_version.write_bytes(html)
    source_latest.write_bytes(html)

    raw = find_results_table(html)
    raw_version = folder / "raw" / f"raw_{stamp}.csv"
    raw_latest = folder / "raw" / "latest.csv"
    raw.to_csv(raw_version, index=False, encoding="utf-8-sig")
    raw.to_csv(raw_latest, index=False, encoding="utf-8-sig")

    standard = normalize_dataframe(raw, race_id, race)
    std_version = folder / "standard" / f"standard_{stamp}.csv"
    std_latest = folder / "standard" / "latest.csv"
    standard.to_csv(std_version, index=False, encoding="utf-8-sig")
    standard.to_csv(std_latest, index=False, encoding="utf-8-sig")

    metadata = {
        "race_id": race_id,
        "name": race["name"],
        "kind": race["kind"],
        "year": race["year"],
        "distance_km": race["distance_km"],
        "event_code": race["event_code"],
        "distance_id": race["distance_id"],
        "show_columns": show_columns,
        "url": url,
        "downloaded_at": now.isoformat(timespec="seconds"),
        "http_status": response.status_code,
        "html_bytes": len(html),
        "sha256": checksum,
        "rows": int(len(standard)),
        "columns": list(standard.columns),
        "files": {
            "source": str(source_version.relative_to(BASE_DIR)),
            "raw": str(raw_version.relative_to(BASE_DIR)),
            "standard": str(std_version.relative_to(BASE_DIR)),
        },
    }
    meta_version = folder / "metadata" / f"metadata_{stamp}.json"
    meta_latest = folder / "metadata" / "latest.json"
    text = json.dumps(metadata, ensure_ascii=False, indent=2)
    meta_version.write_text(text, encoding="utf-8")
    meta_latest.write_text(text, encoding="utf-8")
    return metadata


def dashboard_rows() -> list[dict[str, Any]]:
    rows = []
    for race_id, race in load_races().items():
        meta = latest_metadata(race_id)
        rows.append({
            "race_id": race_id,
            **race,
            "url": build_url(race),
            "status": "Pobrano" if meta else "Niepobrano",
            "rows": meta.get("rows") if meta else None,
            "downloaded_at": meta.get("downloaded_at") if meta else None,
            "sha256_short": meta.get("sha256", "")[:12] if meta else None,
        })
    return sorted(rows, key=lambda x: (x["kind"], x["year"]))


@app.get("/")
def index():
    return render_template("index.html", races=dashboard_rows())


@app.post("/import/<race_id>")
def import_one(race_id: str):
    try:
        meta = import_race(race_id)
        flash(f"{race_id.upper()}: pobrano {meta['rows']} wyników.", "success")
    except Exception as exc:  # komunikat ma być widoczny w prototypie
        flash(f"{race_id.upper()}: błąd — {exc}", "error")
    return redirect(url_for("index"))


@app.post("/import-all")
def import_all():
    ok, errors = 0, []
    for race_id in load_races():
        try:
            import_race(race_id)
            ok += 1
        except Exception as exc:
            errors.append(f"{race_id.upper()}: {exc}")
    flash(f"Pobrano poprawnie: {ok}. Błędy: {len(errors)}.", "success" if not errors else "error")
    for error in errors[:5]:
        flash(error, "error")
    return redirect(url_for("index"))


@app.get("/preview/<race_id>")
def preview(race_id: str):
    races = load_races()
    if race_id not in races:
        return "Nieznany bieg", 404
    csv_path = DATA_DIR / race_id / "standard" / "latest.csv"
    if not csv_path.exists():
        flash("Najpierw pobierz dane tego biegu.", "error")
        return redirect(url_for("index"))
    df = pd.read_csv(csv_path, nrows=200)
    return render_template(
        "preview.html",
        race_id=race_id,
        race=races[race_id],
        columns=list(df.columns),
        rows=df.fillna("").to_dict(orient="records"),
        total=latest_metadata(race_id).get("rows", len(df)),
    )


@app.get("/files/<race_id>/<kind>/<path:filename>")
def files(race_id: str, kind: str, filename: str):
    allowed = {"source", "raw", "standard", "metadata"}
    if kind not in allowed:
        return "Niedozwolony katalog", 403
    return send_from_directory(DATA_DIR / race_id / kind, filename, as_attachment=True)


if __name__ == "__main__":
    DATA_DIR.mkdir(exist_ok=True)
    print("RunQ Studio v0.5: http://127.0.0.1:5001")
    app.run(host="127.0.0.1", port=5001, debug=False)
