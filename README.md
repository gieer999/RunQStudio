# RunQStudio

RunQStudio to aplikacja rozwijająca uniwersalny ranking wyników biegowych, ze szczególnym uwzględnieniem zawodników masters.

System importuje wyniki zawodów, normalizuje dane, oblicza wynik RunQ i tworzy rankingi umożliwiające porównywanie zawodników w różnym wieku oraz na różnych dystansach.

## Aktualny etap

Wersja 0.9.0 jest działającym lokalnie pilotem obejmującym:

- import wyników z STS Timing,
- zapis danych źródłowych i przetworzonych,
- standaryzację wyników,
- obliczanie RunQ,
- ranking ogólny i masters,
- filtrowanie według roku, dystansu, płci, kraju i kategorii,
- usuwanie duplikatów zawodników poprzez zachowanie ich najlepszego wyniku RunQ.

Aktualny pilotaż obejmuje Półmaraton Warszawski i Maraton Warszawski.

Pełna lista obsługiwanych edycji oraz ich konfiguracja znajduje się w pliku `races.json`.

## Struktura projektu

```text
app.py              główna aplikacja RunQ Studio
races.json          konfiguracja obsługiwanych biegów
templates/          szablony interfejsu
static/             arkusze stylów i zasoby interfejsu
docs/               dokumentacja i specyfikacja projektu
data/               dane lokalne, niewysyłane do repozytorium
requirements.txt    wymagane biblioteki Pythona
start.bat           uruchomienie aplikacji w Windows
README.md           opis projektu
CHANGELOG.md        historia zmian
ROADMAP.md          plan dalszego rozwoju
```

Katalog `data/` pozostaje lokalny i jest wykluczony z repozytorium przez `.gitignore`.

## Przepływ danych

```text
STS Timing
→ source.html
→ raw.csv
→ standard.csv
→ runq.csv
→ ranking
```

## Główne zasady

- specyfikacja biznesowa jest ważniejsza niż konkretna implementacja,
- dane źródłowe powinny być archiwizowane lokalnie,
- import powinien być powtarzalny,
- brak pola opcjonalnego nie może zatrzymywać całego importu,
- czas netto jest preferowany, a czas brutto przechowywany,
- nazwy zawodników są normalizowane technicznie bez zmiany sposobu ich wyświetlania,
- silnik RunQ powinien być rozwijany niezależnie od źródła danych.

## Uruchomienie

W systemie Windows uruchom:

```text
start.bat
```

Można również uruchomić aplikację ręcznie:

```bash
python -m pip install -r requirements.txt
python app.py
```

## Status

RunQStudio jest w aktywnej fazie rozwoju.

Aktualna wersja:

```text
v0.9.0
```
