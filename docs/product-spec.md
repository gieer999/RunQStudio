# RunQStudio — specyfikacja produktu

## 1. Cel produktu

RunQStudio ma umożliwiać tworzenie sprawiedliwego i motywującego rankingu biegaczy masters 40+.

System ma łączyć wyniki z różnych zawodów i dystansów, normalizować je oraz obliczać porównywalny wynik RunQ.

## 2. Problem

Standardowe rankingi biegowe mają kilka ograniczeń:

- porównują głównie wynik bezwzględny,
- słabo uwzględniają wiek,
- utrudniają porównanie różnych dystansów,
- nie pokazują szerszego kontekstu jakości wyniku,
- są rozproszone pomiędzy wieloma organizatorami.

## 3. Użytkownicy

### Główni użytkownicy

- biegacze masters 40+,
- organizatorzy zawodów,
- kluby biegowe,
- osoby analizujące wyniki.

### Potrzeby użytkowników

- sprawdzenie własnego wyniku RunQ,
- porównanie z innymi zawodnikami,
- ranking dla konkretnych zawodów,
- ranking sezonowy,
- historia wyników,
- informacja o jakości wyniku.

## 4. Zakres pierwszej wersji

Pierwsza wersja obejmuje:

- import wyników z STS Timing,
- konfigurację wielu zawodów,
- archiwizację strony źródłowej,
- zapis danych surowych,
- standaryzację danych,
- podgląd importu,
- przygotowanie danych do obliczeń RunQ.

## 5. Źródła danych

### STS Timing

Aktualnie obsługiwane zawody:

- PW2021–PW2026,
- MW2021–MW2025.

Szczególny przypadek:

- PW2021 znajduje się w wydarzeniu MW2021 jako dystans 3.

## 6. Archiwizacja importu

Każdy import powinien tworzyć niezależny katalog zawierający:

```text
source.html
raw.csv
standard.csv
metadata.json

```

### Cel archiwizacji

- możliwość odtworzenia importu,
- ochrona przed zmianą strony źródłowej,
- możliwość ponownej normalizacji,
- audyt pochodzenia danych.

## 7. Model danych zawodnika

Minimalny rekord wyniku powinien zawierać:

- identyfikator zawodów,
- rok zawodów,
- dystans,
- miejsce,
- imię,
- nazwisko,
- płeć,
- kraj,
- klub,
- kategoria,
- rok urodzenia,
- czas netto,
- czas brutto,
- czas używany do RunQ,
- adres źródłowy.

### Reguły jakości danych

- rok urodzenia może być nieznany,
- czas brutto powinien być przechowywany zawsze,
- czas netto jest preferowany do obliczeń,
- brak opcjonalnego pola nie zatrzymuje importu,
- błędne rekordy powinny być raportowane.

## 8. RunQ

RunQ jest wynikiem normalizującym rezultat zawodnika z uwzględnieniem między innymi:

- wieku,
- prędkości,
- dystansu,
- płci,
- jakości wyniku.

Ostateczna formuła pozostaje przedmiotem dalszych testów.

## 9. Rankingi

Planowane rankingi:

- ranking pojedynczych zawodów,
- ranking open,
- ranking masters 40+,
- ranking kobiet,
- ranking mężczyzn,
- ranking roczny,
- ranking według dystansu,
- profil zawodnika.

## 10. Wymagania techniczne

- importer musi być konfigurowalny,
- reguły biznesowe powinny być oddzielone od kodu pobierającego dane,
- import powinien być powtarzalny,
- dane powinny być możliwe do przeliczenia ponownie,
- system powinien przechowywać wersję reguł,
- aplikacja powinna działać lokalnie przed wdrożeniem online.

## 11. Otwarte pytania

- jaka będzie docelowa formuła RunQ,
- jak uwzględniać różne dystanse,
- czy stosować limity maksymalnego wyniku,
- jak traktować brak roku urodzenia,
- jak identyfikować tę samą osobę w różnych zawodach,
- jak obsłużyć korekty wyników,
- jak prezentować progi jakości,
- czy tworzyć ranking tylko 40+, czy również open,
- jak często odświeżać dane,
- jakie źródło będzie kolejne po STS Timing.

## 12. Najbliższe prace

1. przenieść aktualny importer do repozytorium,
2. uporządkować strukturę kodu,
3. opisać format `standard.csv`,
4. dodać walidację danych,
5. przygotować pierwszą wersję formuły RunQ,
6. zbudować tabelę rankingu,
7. dodać testy dla importu i obliczeń.
