# Reanaliza Bibo — wrzesień 2026

> Cel tego dokumentu: rozłożyć projekt na małe tematy, sprawdzić każdy
> z nich na **realnym kodzie Hermesa (v0.21.3)** zamiast na założeniach
> i zdecydować, co ma sens. Poprzednia analiza (wersja „reaktywna, bez
> pamięci, neutralna”) leży w [archiwum](archiwum/Analiza-v1-reaktywny.md).

---

## 0. Czego naprawdę chcesz (kryteria sukcesu)

| # | Wymaganie | Jak sprawdzimy, że działa |
|---|-----------|---------------------------|
| 1 | Partner obok, który **kuma ADHD** | Proponuje mały krok zamiast „po prostu zacznij”, nie moralizuje |
| 2 | **Trzyma parametry** (styl, długość, charakter) | Krótkie wiadomości, podpis „bibo”, zero „Super pomysł!” — też po tygodniu |
| 3 | **Zbiera informacje o Tobie** | Po tygodniu `memories/USER.md` opisuje Cię trafnie |
| 4 | **Sam się odzywa**, symuluje rozmowę | 1–3 zaczepki dziennie, nawiązujące do Twoich spraw; odpowiedź ciągnie wątek |
| 5 | **Tani** — limit nie znika po 2–3 wiadomościach | Stały prompt < 5 tys. tokenów; koszt miesięczny w dolarach jednocyfrowych |
| 6 | **Instalacja z paczki**, powtarzalna, także dla innych | Jedno polecenie; reinstalacja nie gubi pamięci |
| 7 | **Panel konfiguracyjny** | Zmiana modelu, kluczy, Telegrama bez edycji YAML |
| 8 | Na serwerze **nic poza nim** | Jeden profil, zero wbudowanych skilli, zero zbędnych narzędzi |

Poprzednia analiza zdecydowała o czymś odwrotnym do punktów 1, 3 i 4
(„neutralny”, „minimalna pamięć”, „zero crona”). To główny rozjazd:
**projekt był optymalizowany pod prostotę, a nie pod to, czego potrzebujesz.**

---

## 1. Diagnoza: dlaczego obecna wersja nie działa

Wszystko poniżej zostało sprawdzone w kodzie i dokumentacji Hermesa oraz
zmierzone `hermes prompt-size` — nie jest zgadywane.

| Problem | Dowód | Skutek |
|---------|-------|--------|
| **`AGENTS.md` nigdy nie trafia do Bibo** | Hermes czyta `AGENTS.md` z *katalogu roboczego* (projektu), nie z profilu. Z profilu ładowany jest tylko `SOUL.md`. Pomiar: `context (AGENTS.md) = 0 B`. | Onboarding, anti-sycophancy, zasady `brain.json`, trigger skilla — martwe. |
| **`brain.json` to fikcja** | Nic w Hermesie go nie czyta ani nie zapisuje; Bibo nie ma narzędzi do plików. | „Pamięć imienia i celu” nie istnieje. |
| **~80 wbudowanych skilli** | Każdy profil dostaje katalog skilli przy tworzeniu i przy każdym `hermes update`. Indeks: **+8,1 KB** w każdym zapytaniu. | „Hermes się zatyka skillami”. |
| **24 narzędzia na Telegramie** | Domyślny zestaw: terminal, przeglądarka, pliki, delegacja, wykonywanie kodu... = **41 KB** schematów JSON w każdym zapytaniu. | Największy stały koszt — płacony przy każdym „cześć”. |
| **Historia rośnie do 256 tys. tokenów** | Rozmowa na Telegramie nie wygasa; domyślny próg kompresji to `threshold_tokens: 256000`. | Każda wiadomość wysyła całą dotychczasową rozmowę. Koszt rośnie z każdym dniem. |
| **„Self-improvement review” po turach** | `auxiliary.background_review` — osobne wywołanie modelu z *całą* rozmową, domyślny limit 120 tys.+ tokenów na przegląd. | Ukryty mnożnik kosztu. |
| **Subskrypcja Claude ≠ limit z planu** | Dokumentacja Hermesa: logowanie Claude przez OAuth działa tylko na **Max** i zużywa **wyłącznie dokupione „extra usage”**, nigdy limitu z planu. Na **Pro nie działa wcale**. | To dokładnie „limit znika po 2–3 wiadomościach”: ~15 tys. tokenów stałego promptu + historia, rozliczane z małej puli dodatkowych kredytów. |

### Pomiar (Telegram, jedna wiadomość, zanim doliczymy historię)

| Wariant | Prompt systemowy | Schematy narzędzi | Razem | ≈ tokeny |
|---------|-----------------:|------------------:|------:|---------:|
| Obecne repo, świeży profil | 8,5 KB | 41,3 KB | **~50 KB** | ~13 tys. |
| Obecne repo po `hermes update` (skille) | 16,8 KB | 41,3 KB | **~58 KB** | ~15 tys. |
| **Nowe MVP (zainstalowane)** | 9,4 KB | 3,4 KB | **~13 KB** | **~3,5–4 tys.** |

Do tego w starej wersji dochodzi historia rosnąca do 256 tys. tokenów;
w nowej jest ucinana i streszczana przy ~16 tys.

---

## 2. Tematy — obecnie vs docelowo

### A. Pakiet i instalacja
- **Obecnie:** `hermes profile install` kopiował *całe repo* (README, PDF, analizy) do profilu; `config.yaml` przez długi czas miał zmyślony schemat.
- **Docelowo:** `distribution.yaml` z listą `distribution_owned` — do profilu trafia tylko `SOUL.md`, `config.yaml`, `scripts/`, znacznik bez skilli, szablon `.env`. Plus `install.sh`, który prowadzi przez Telegram, model, puls i usługę w tle.
- **Dlaczego:** jedno polecenie, bezpieczne do powtarzania — `profile update` nie rusza pamięci, historii ani `.env`.

### B. Model i płatność
- **Obecnie:** Sonnet 4.6 przez subskrypcję (OAuth) → extra usage → szybko pusto.
- **Docelowo:** **klucz API Anthropic** jako ścieżka domyślna; OAuth zostaje jako opcja dla Max + extra usage. Model domyślny: `claude-sonnet-5` ($2/$10 za 1 mln tokenów — tańszy od 4.6 i lepszy), do zmiany jednym poleceniem na `claude-haiku-4-5` ($1/$5). Streszczanie historii zawsze na Haiku.
- **Szacunek kosztu** (nie pomiar — zweryfikuj `hermes insights` po tygodniu): ~30 wiadomości dziennie + 3 zaczepki, prompt ~4 tys. tokenów w większości z cache, historia ≤16 tys. → rząd **kilku dolarów miesięcznie** na Sonnet 5, mniej na Haiku.

### C. Stały prompt (to, co płacisz przy każdej wiadomości)
- **Decyzja:** Telegram i cron dostają **jedno narzędzie: `memory`**. Bez terminala, przeglądarki, plików, skilli, delegacji.
- **Decyzja:** znacznik `.no-bundled-skills` w paczce — Hermes nie dosieje ~80 skilli przy aktualizacjach.
- **Decyzja:** wiedza o ADHD i pytania sokratejskie **wprost w `SOUL.md`** (~1 tys. tokenów), zamiast skilla. Skill wymaga narzędzia `skills` (5 KB schematu w każdym zapytaniu) i dodatkowej tury, żeby go wczytać — przy jednym małym skillu to się nie opłaca.

### D. Historia rozmowy
- **Decyzja:** `compression.threshold_tokens: 16000`, `protect_last_n: 12`, `idle_compact_after_seconds: 3600` (po godzinie ciszy historia jest zwijana przed odpowiedzią), streszczanie na Haiku, `prompt_caching.cache_ttl: 1h`.
- **Efekt:** koszt wiadomości nie rośnie z wiekiem rozmowy. Ciągłość niesie pamięć (punkt E), a nie surowa historia.

### E. Pamięć o Tobie (serce produktu)
- **Obecnie:** `brain.json`, którego nikt nie czyta; zasada „nie zapisuj niczego”.
- **Docelowo:** wbudowana pamięć Hermesa — `USER.md` (profil: kim jesteś, jak u Ciebie wygląda ADHD, co działa) i `MEMORY.md` (obietnice z datami, zauważone wzorce, wątki do podjęcia). Obie są automatycznie wstrzykiwane do promptu każdej sesji, także zaczepek z crona. `SOUL.md` każe zapisywać na bieżąco, bez pytania. Limity lekko podniesione (2,5 tys. + 3 tys. znaków).
- **Mnemosyne?** To lokalna pamięć na SQLite (wyszukiwanie semantyczne, graf wiedzy, konsolidacja). Świetna na później, ale w MVP: dodatkowa zależność, dodatkowe narzędzia w każdym zapytaniu, kolejna rzecz, która może się wysypać. **Decyzja: v0.3**, gdy MVP będzie stabilny i `USER.md` okaże się za mały. Hermes ma to jako `memory.provider` — dołożenie nie wymaga przebudowy.

### F. Proaktywność („sam coś rzuca”)
- **Obecnie:** świadomie brak.
- **Docelowo:** zadanie cron `bibo-pulse` co godzinę + skrypt `scripts/bibo_pulse.py` jako **darmowa bramka** (bez modelu): cisza nocna 22–8, max 3 dziennie, min. 3 h odstępu, nie przeszkadza, gdy piszesz (ostatnie 45 min), losowość 60%. Tylko gdy bramka przepuści, model pisze jedną wiadomość z kontekstem pory dnia i tego, co pamięta. Może też odpowiedzieć `[SILENT]` — wtedy nic nie idzie.
- `--continuity`: puls widzi, co napisał ostatnio → nie powtarza się.
- `cron.mirror_delivery: true`: zaczepka trafia do Twojej rozmowy → odpowiadasz i Bibo wie, do czego się odnosisz. To jest „symulowanie rozmowy”.
- **Odrzucone:** `/heartbeat` — działa w pełnym kontekście sesji, więc każdy tik kosztuje całą historię.
- Ustawienia (godziny, limit, strefa) w `local/bibo_pulse.json` — ten katalog przeżywa aktualizacje.

### G. Osobowość i ADHD
- **Obecnie:** „neutralny partner do myślenia, nie ADHD”.
- **Docelowo:** kumpel, który rozumie ADHD od środka: problem z uruchamianiem, ślepota czasowa, układ nerwowy napędzany zainteresowaniem, hiperfokus, wrażliwość na odrzucenie; narzędzia typu najmniejszy krok, 10 minut, body doubling. Zostaje: anti-sycophancy, krótkie wiadomości, podpis „bibo” (doklejany wtyczką `bibo-podpis`), jedno pytanie naraz, bezpieczeństwo (116 123 / 800 70 2222 / 112).

### H. Panel konfiguracyjny
- **Decyzja: nie budujemy własnego.** Hermes ma `hermes dashboard` (klucze, modele, Telegram/pairing, cron, sesje, pamięć, logi, wiele profili). Na VPS: tunel SSH `ssh -L 9119:127.0.0.1:9119 serwer` → `hermes dashboard --no-open`. Własny panel to miesiące pracy i powierzchnia ataku, a nic nie wnosi na tym etapie.

### I. Telegram
- Bez zmian technicznie (gateway Hermesa), ale: `TELEGRAM_ALLOWED_USERS` (tylko Ty), `TELEGRAM_HOME_CHANNEL` (dokąd idą zaczepki), bez komunikatów „💾 Memory updated” i bez nagłówka „Cron job…”.

### J. Bezpieczeństwo i prywatność
- Bibo nie ma terminala, plików ani przeglądarki → prompt injection z wiadomości nie ma czym zaszkodzić.
- Pamięć o Tobie leży na Twoim serwerze w `memories/`. Paczka nigdy jej nie publikuje (Hermes wyklucza `memories/`, `sessions/`, `.env`, `auth.json`).
- Rozmowa idzie do dostawcy modelu (Anthropic) — warto to napisać w README dla innych użytkowników.

### K. Czy Hermes w ogóle ma sens?
Uczciwie: Bibo potrzebuje ~5% Hermesa. Alternatywą byłby własny bot na ~300 linii (Telegram + API Claude + plik z pamięcią + cron).
- **Za Hermesem:** instalacja z paczki i aktualizacje, gotowa pamięć, kompresja, cache, cron z bramką, panel, fallbacki, `insights`. Tego nie trzeba pisać ani utrzymywać.
- **Przeciw:** domyślne ustawienia są „agent do wszystkiego” i drogie; każda aktualizacja Hermesa może coś zmienić.
- **Werdykt:** zostajemy przy Hermesie, **pod warunkiem**, że paczka twardo wyłącza to, czego nie potrzebujemy (zrobione w `config.yaml`) i mierzymy prompt po każdej aktualizacji (`prompt-size`). Jeśli za 1–2 miesiące Hermes nadal będzie walczył z tym trybem — wtedy własny bot i przeniesienie `SOUL.md` + pamięci (to zwykłe pliki).

### L. Rozszerzalność (biznes i inne dziedziny)
- **Nie teraz.** Kierunek na później: każda dziedzina jako *osobny profil-paczka* (`bibo-biznes`) albo jako mały skill ładowany na żądanie. Zanim to zrobimy — MVP musi realnie działać u Ciebie przez 2–3 tygodnie.

---

## 3. Architektura MVP

```
Telegram ──► gateway Hermesa (profil "bibo")
               │  prompt: SOUL.md + USER.md + MEMORY.md + 1 narzędzie (memory)
               │  historia: zwijana przy ~16k tokenów (Haiku)
               ▼
            Claude (Sonnet 5 / Haiku 4.5) ── zapisuje fakty o Tobie ──► memories/

cron "bibo-pulse" (co 1h)
   └─ scripts/bibo_pulse.py  (0 tokenów: cisza nocna, limit, odstęp, czy piszesz)
        ├─ wakeAgent=false → nic
        └─ wakeAgent=true  → jedna wiadomość (albo [SILENT]) → Telegram → Twoja odpowiedź ciągnie wątek
```

Pliki w repo, które trafiają do profilu: `SOUL.md`, `config.yaml`,
`scripts/bibo_pulse.py`, `.no-bundled-skills`, `.env.template`,
`distribution.yaml`. Reszta (README, docs, `install.sh`) zostaje w repo.

---

## 4. Czego świadomie NIE ma w MVP

| Rzecz | Kiedy wraca |
|-------|-------------|
| Mnemosyne / pamięć semantyczna | v0.3 — gdy `USER.md` zacznie być za ciasny |
| Głos (TTS/STT) | v0.3 — Hermes to umie, ale to dodatkowe narzędzie i koszt |
| Dziedziny (biznes itd.) | v0.4 — osobne paczki/skille |
| Własny panel | raczej nigdy — `hermes dashboard` wystarcza |
| Fallback na inny model | gdy padnie pierwszy raz; `hermes fallback` bez zmian w paczce |

---

## 5. Ryzyka i co trzeba sprawdzić na żywo

Wszystko powyżej jest zweryfikowane lokalnie (instalacja z paczki,
rejestracja profilu, pomiar promptu, utworzenie zadania cron, testy
reguł bramki). **Nie da się tego sprawdzić bez prawdziwego bota i klucza:**

1. Czy Bibo faktycznie wywołuje `memory` sam z siebie (na Sonnet 5 powinien; na Haiku sprawdzić).
2. Czy odpowiedź na zaczepkę trafia do tej samej rozmowy (`mirror_delivery`).
3. Czy `[SILENT]` z pulsu nic nie wysyła.
4. Realny koszt po tygodniu: `hermes insights`.
5. Czy `hermes update` na VPS respektuje `.no-bundled-skills` (`hermes skills list` → 0).

## 6. Checklista wdrożenia na VPS

```bash
hermes update                       # Hermes >= 0.21
git clone https://github.com/Grandpa1001/hi-bibo && cd hi-bibo
./install.sh                        # Bibo jako główny profil: Telegram, model, puls, restart gatewaya
hermes prompt-size --platform telegram   # oczekiwane: ~13 KB łącznie
```

Instalator sam usuwa wbudowane skille i proponuje usunięcie starego profilu `bibo`.

---

## 7. Aktualizacja po pierwszym wdrożeniu (Hermes 0.21.4 w Dockerze)

Pierwsze wdrożenie jako osobny profil `bibo` (`hermes profile install`)
wyłożyło się na czterech rzeczach, których nie było widać lokalnie:

| Problem | Przyczyna | Rozwiązanie |
|---------|-----------|-------------|
| `PermissionError` na `.env` | W obrazie Docker `hermes` uruchomiony jako root przełącza się na użytkownika `hermes` (UID 10000); plik zapisany przez root był dla niego nieczytelny | Instalator oddaje każdy zapisany plik właścicielowi katalogu Hermesa |
| Reinstalacja po `profile delete` | Hermes zostawia znacznik `profiles/.deleted/<nazwa>`, którego `profile install` nie czyści | Zniknęło razem z trybem profilu |
| Telegram milczy | Od 0.21.4 jest **jeden wspólny gateway** (profil default) obsługujący wszystkie profile; `-p bibo gateway start` jest odrzucany, a bot profilu nie wystartował | Bibo jest teraz **głównym profilem** |
| Logowanie „nie idzie pod Bibo” | `/login`, panel i `hermes model` konfigurują profil default; logowania OAuth nie da się kopiować między profilami | Jw. — wszystko, co konfigurujesz, trafia do Bibo |

**Decyzja:** Bibo = główny profil Hermesa na osobnej instalacji (kontenerze).
Instalator nie nadpisuje `config.yaml`, tylko ustawia nasze klucze przez
`hermes config set`, więc ustawienia obrazu Docker (np. `api_server`) zostają.
`distribution.yaml` i `config.yaml` w repo zostają jako wzorzec dla kogoś,
kto woli osobny profil.
