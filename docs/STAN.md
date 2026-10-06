# Stan dnia (Bibo)

Bibo pyta raz dziennie, jak się czujesz, jednym stuknięciem, i dopasowuje do tego resztę dnia.
Nic nie diagnozuje: nazywa tryb dnia, nie stan zdrowia.

## Jak używać

- Pierwsza rozmowa dnia: po odpowiedzi Bibo pojawia się siatka 4×4. Wiersz to energia (⚡⚡ → 🌙🌙), kolumna to samopoczucie (😣 → 😄).
- `/stan` pokazuje siatkę w dowolnej chwili. Nowy wpis zastępuje tryb z poprzedniego.
- Po stuknięciu Bibo odpowiada jednym zdaniem i jednym krokiem, potem możesz wybrać słowo (💭) albo pominąć.
  Notatkę dopiszesz wiadomością zaczynającą się od `notatka:`.
- Zignorowana siatka tego dnia nie wraca i nie ma przypomnień.

## Tryb dnia

| Siatka | Tryb | Bibo proponuje | Duże decyzje | Styl |
| --- | --- | --- | --- | --- |
| wysoka energia, przyjemnie | Szczyt | pełny plan | tak | normalny |
| niska energia, przyjemnie | Stabilnie | plan bez nowych tematów | tak, bez pośpiechu | normalny |
| wysoka energia, nieprzyjemnie | Napięcie | 2–3 zadania, najpierw to, co uwiera | odłożyć | krótszy, spokojny |
| niska energia, nieprzyjemnie | Regeneracja | 1–2 drobne domknięcia | nie | krótki, z propozycją przerwy |

Tryb to ćwiartka ostatniego dzisiejszego wpisu. Do kontekstu każdej tury trafiają dwie krótkie linie wytycznych,
tylko dla właściciela i tylko gdy dziś jest wpis.

## Zaangażowanie w tle

Zaangażowania nie pytamy. Bibo zapisuje wyłącznie znaczniki czasu tur (liczba tur, sesje przedzielone przerwą
30 min, czas sesji) oraz liczy karty spraw zakończone tego dnia. Treść rozmów nie jest zapisywana.
Issues z zewnętrznych narzędzi ta instancja nie widzi.

## Wyłączanie i dane

- `{"stan": false}` w `local/bibo_tryby/ustawienia.json` wyłącza siatkę, przechwytywanie i liczenie tur.
- Dane: `local/bibo_tryby/stan.sqlite3` (osobno od `karta.sqlite3`; stare wersje wtyczki go ignorują).
- Dane zostają na instancji. Eksport i usuwanie jedną komendą dojdą w kroku 7.
