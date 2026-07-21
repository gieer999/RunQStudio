# Changelog

Wszystkie istotne zmiany w projekcie RunQStudio będą dokumentowane w tym pliku.

Format jest inspirowany Keep a Changelog.

## Unreleased

### Added

- repozytorium projektu RunQStudio,
- podstawowa dokumentacja projektu,
- opis aktualnego zakresu importera STS Timing,
- struktura katalogu dokumentacji.

## 0.5.0

### Added

- import wyników z STS Timing,
- obsługa PW2021–PW2026,
- obsługa MW2021–MW2025,
- archiwizacja HTML,
- generowanie `raw.csv`,
- generowanie `standard.csv`,
- generowanie `metadata.json`,
- podgląd danych i statusów importu.

### Changed

- czas netto jest używany jako podstawowy czas RunQ, jeśli jest dostępny,
- czas brutto jest zawsze przechowywany,
- rok urodzenia jest polem opcjonalnym.

### Fixed

- poprawne mapowanie kolumn czasu dla półmaratonów,
- poprawne mapowanie kolumn czasu dla maratonów,
- obsługa specjalnej edycji PW2021.
