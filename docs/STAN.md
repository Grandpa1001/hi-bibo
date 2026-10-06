# Stan dnia (Bibo)

Bibo pyta raz dziennie, jak się czujesz, jednym stuknięciem, i dopasowuje do tego resztę dnia.
Nic nie diagnozuje: nazywa tryb dnia, nie stan zdrowia.

## Jak używać

- Pierwsza rozmowa dnia: po odpowiedzi Bibo pojawia się siatka 4×4. Wiersz to energia (⚡⚡ → 🌙🌙), kolumna to samopoczucie (😣 → 😄).
- `/stan` pokazuje siatkę w dowolnej chwili. Nowy wpis zastępuje tryb z poprzedniego.
- Po stuknięciu Bibo odpowiada jednym zdaniem i jednym krokiem, potem możesz wybrać słowo (💭) albo pominąć.
  Notatkę dopiszesz wiadomością zaczynającą się od `notatka:`.
- Zignorowana siatka tego dnia nie wraca i nie ma przypomnień.

## Widget w Mini App

Na zakładce „Dziś” w Mini App (przycisk „Bibo” obok pola wiadomości) widget pokazuje dzisiejszy tryb w kolorze ćwiartki, punkt na siatce,
ikonę stanu uwagi i 7 ostatnich dni (kropka = ostatni wpis dnia, przerywana = brak wpisu). Stuknięcie otwiera siatkę
4×4; po wpisie od razu widać reakcję Bibo i opcjonalne chipy uwagi oraz słowa. Wpisy z Mini App mają źródło `widget`.
Tryb zawsze ma nazwę obok koloru. Widget nie pokazuje się, gdy `stan` jest wyłączony albo gdy profil nie ma jednego właściciela.

## Tryb dnia

| Siatka | Tryb | Bibo proponuje | Duże decyzje | Styl |
| --- | --- | --- | --- | --- |
| wysoka energia, przyjemnie | Szczyt | pełny plan | tak | normalny |
| niska energia, przyjemnie | Stabilnie | plan bez nowych tematów | tak, bez pośpiechu | normalny |
| wysoka energia, nieprzyjemnie | Napięcie | 2–3 zadania, najpierw to, co uwiera | odłożyć | krótszy, spokojny |
| niska energia, nieprzyjemnie | Regeneracja | 1–2 drobne domknięcia | nie | krótki, z propozycją przerwy |

Tryb to ćwiartka ostatniego dzisiejszego wpisu. Do kontekstu każdej tury trafiają dwie krótkie linie wytycznych,
tylko dla właściciela i tylko gdy dziś jest wpis.

## Stan uwagi

Uwaga to osobna oś od nastroju. Po stuknięciu w siatkę klawiatura ma jeden rząd: 🌀 Rozproszony · 👌 W normie · 🎯 Hiperfokus.
Bez wyboru zostaje „W normie”. W ciągu dnia: `/fokus` (przyciski) albo `/fokus hiper`, `/fokus rozproszony`, `/fokus norma`.
Zmiana uwagi dodaje nowy wpis z tymi samymi osiami, więc tryb dnia się nie zmienia.

| Stan uwagi | Bibo robi | Bibo nie robi |
| --- | --- | --- |
| Hiperfokus | nie przerywa; co 90 min jedno krótkie przypomnienie o przerwie i wodzie (najwyżej 6 dziennie) | nie dorzuca tematów ani zadań |
| W normie | zachowanie wg trybu dnia | – |
| Rozproszony | pokazuje 1 zadanie, kroki po ok. 15 min; nowe pomysły zapisuje jako „POMYSŁ:” w pamięci | nie pokazuje listy ani kilku opcji |

Przypomnienia wysyła kod (bez modelu) w istniejącej pętli co 60 s i respektują pauzę oraz ciszę nocną: przypomnienie z czasu ciszy
przepada, nie wychodzi po jej końcu. Po wyjściu z hiperfokusu Bibo w jednej wiadomości mówi, co ma zapisane (zakończone sprawy dziś)
i co czeka w karcie. Planu dnia spoza karty ta instancja nie ma, więc go nie zgaduje.

## Wykrywanie gorszego dnia i uwagi

Bibo sam zauważa sygnały, ale **niczego nie zmienia bez Twojego „Tak”**. Zbiera je prostymi regułami w kodzie
(bez modelu i bez zapisu treści; zapisuje tylko rodzaj sygnału i długość wiadomości):

| Pytanie | Sygnały (suma wag ≥ 2) |
| --- | --- |
| „Gorszy dzień?” | wyraźna fraza typu „nie mam siły” (sama wystarcza) · pisanie po 23:00 · wiadomości wyraźnie krótsze niż zwykle |
| „Jesteś w hiperfokusie?” | rozmowa z Bibo ciągnąca się ponad 3 h bez przerwy (sama wystarcza) · pora po 23:00 |
| „Rozproszony dzień?” | co najmniej 4 krótkie sesje dziś (średnio poniżej 10 min) **i** co najmniej 2 odłożone dziś karty |

Pytanie pada po turze, z przyciskami ✅ Tak / ❌ Nie. Najwyżej raz dziennie o dany cel, najwyżej dwa pytania dziennie, jedno
naraz. O uwagę nie pytamy bez dzisiejszego wpisu. „Tak” na gorszy dzień obniża tylko przyjemność (energia zostaje, jak ją
zadeklarowałeś); „Nie” niczego nie zmienia i trafia tylko do licznika fałszywych alarmów.
Bibo widzi tylko czas w rozmowie z nim i swoje karty, więc „długa sesja” i „porzucone zadania” to przybliżenia.

**Po przerwie.** Po 2 pominiętych dniach (ostatni wpis 3 doby temu) pierwsza rozmowa dnia zaczyna się jednym pytaniem
z oszacowaniem Bibo (najczęstszy tryb z ostatniego tygodnia) zamiast siatki. „Tak” zapisuje wpis ze źródłem
`inferred_confirmed`, „Nie” pokazuje siatkę. Raz na przerwę, bez przypomnień.

**Wsparcie.** Po 5 dniach z rzędu w Regeneracji albo przy 3 potwierdzonych gorszych dniach w tygodniu Bibo raz (najwyżej co
14 dni) łagodnie podpowiada rozmowę z bliską osobą lub specjalistą. Bez diagnozy.

## Kryzys

Gdy napiszesz o myślach samobójczych albo samookaleczeniu, Bibo od razu wysyła numery pomocy (**116 123**, Kryzysowy
Telefon Zaufania, i **112** w bezpośrednim zagrożeniu) i przerywa planowanie: do końca doby nie ma siatki, pytań o stan
ani przypomnień, a Bibo odpowiada krótko i ciepło. Działa to w kodzie, także gdy `stan` jest wyłączony. Treść tych
wiadomości nie jest nigdzie zapisywana. Wzorce są szerokie celowo: lepiej raz niepotrzebnie podać numer niż przeoczyć
prawdziwy kryzys.

## Zaangażowanie w tle

Zaangażowania nie pytamy. Bibo zapisuje wyłącznie znaczniki czasu tur (liczba tur, sesje przedzielone przerwą
30 min, czas sesji) oraz liczy karty spraw zakończone tego dnia. Treść rozmów nie jest zapisywana.
Issues z zewnętrznych narzędzi ta instancja nie widzi.

## Wyłączanie i dane

- `{"stan": false}` w `local/bibo_tryby/ustawienia.json` wyłącza siatkę, przechwytywanie i liczenie tur.
- Dane: `local/bibo_tryby/stan.sqlite3` (osobno od `karta.sqlite3`; stare wersje wtyczki go ignorują).
- Dane zostają na instancji. Eksport i usuwanie jedną komendą dojdą w kroku 7.
