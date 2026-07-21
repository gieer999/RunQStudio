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
