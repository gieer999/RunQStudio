# RunQStudio

RunQStudio to projekt rozwijający ranking biegaczy masters 40+.

Celem projektu jest stworzenie systemu, który:

- importuje wyniki zawodów z różnych źródeł,
- normalizuje dane,
- oblicza wynik RunQ,
- tworzy rankingi ogólne i masters,
- archiwizuje źródła danych,
- umożliwia rozwój reguł niezależnie od konkretnej technologii.

## Aktualny etap

Pierwsza działająca wersja importuje wyniki z STS Timing dla wybranych edycji:

- Półmaraton Warszawski 2021–2026,
- Maraton Warszawski 2021–2025.

Importer zapisuje:

- stronę źródłową,
- dane surowe,
- dane ustandaryzowane,
- metadane importu.

## Struktura projektu

```text
docs/              dokumentacja i specyfikacja
data/              dane źródłowe i przetworzone
src/               kod aplikacji
tests/             testy
README.md          opis projektu
CHANGELOG.md       historia zmian

```

## Główne zasady

- specyfikacja biznesowa jest ważniejsza niż konkretna implementacja,
- dane źródłowe powinny być archiwizowane,
- import powinien być powtarzalny,
- brak pola opcjonalnego nie może zatrzymywać całego importu,
- czas netto jest preferowany, a czas brutto przechowywany zawsze,
- rok urodzenia może początkowo pozostać nieznany.

## Status

Projekt jest w aktywnej fazie prototypowania.
