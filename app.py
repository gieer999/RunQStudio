from __future__ import annotations

import hashlib
import io
import json
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
