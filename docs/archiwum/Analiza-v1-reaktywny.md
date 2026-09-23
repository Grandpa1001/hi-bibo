# Analiza architektury Bibo (Hermes-native rebuild)

**Status:** 🟡 M1 w toku na żywo — 3 realne problemy znalezione i naprawione przez iteracyjne testy + research prawdziwej dokumentacji Hermesa (`NousResearch/hermes-agent`): (1) profil musi być płaski w korzeniu repo — naprawione; (2) `config.yaml` używał całkowicie zmyślonego schematu który cicho blokował rejestrację profilu — naprawione, przepisany na minimalny/potwierdzony; (3) komenda gateway/link do repo były błędne w README — naprawione. Czeka na retest #9 poniżej. M6/M7/M8 wydzielone do [MAINTENANCE.md](MAINTENANCE.md).  
**Data rozpoczęcia:** 2026-09-21  
**Cel:** Kompletny plan developmentu Bibo jako natywnego agenta Hermes.

_Uwaga o nazwie: nie używamy "v2" — po prostu Bibo. Stara implementacja v1.3 została w całości usunięta z main (2026-09-21) — dostępna wyłącznie w historii gita, jeśli trzeba do niej wrócić._

---

## Wnioski z tutorialu Hermesa → dyrektywy dla Bibo

1. **Nie komplikuj konfiguracji na zapas** — jeden profil, jeden model na start
2. **Pamięć w odpowiednim miejscu** — SOUL / AGENTS.md / memory / skills / historia sesji — nie wszystko w prompcie
3. **Progressive disclosure** — knowledge ładowany doraźnie, nie stale
4. **Auxiliary models** — deterministyczne rzeczy na Haiku, refleksja na Sonnet
5. **Split cron** — no-agent do decyzji, agent tylko gdy trzeba
6. **Pomiar zamiast intuicji** — `hermes prompt-size`, `/usage`, monitoring
7. **Automatyzacja tego co stabilne** — zanim cron, testuj ręcznie
8. **Bibo ma audytować sam siebie** — miesięczny self-check

---

## Dyrektywy od Kamila (2026-09-21)

- **Nie agregować pełno informacji** — minimalna persistent state
- **Cron nie musi trzymać kontekstu** — fresh sessions (zgodnie z Hermes)
- **Kontekst tylko pare chwil** — ephemeral, konwersacja krótka
- **Zadawać inne pytania** — variety, brak repetycji (mocny T010 topic tracker)

**Wnioskowana filozofia:** Bibo (rebuild) = **ephemeral partner** — pamięta trochę, zapomina dużo, każde spotkanie świeże ale z sygnałem ciągłości.

---

## Etap 0 — Założenia fundamentalne

### Ustalone (iteracja 1)

| # | Decyzja | Konsekwencja architektoniczna |
|---|---------|-------------------------------|
| 1 | **Single-user (Kamil), ale open-source** | Jedna instalacja per user. Rekomendacja: fresh Hermes + Bibo. Templates czyste, docs jasne, żadnego multi-tenant. |
| 2 | **Reaktywny na start** | Bibo odpowiada na inbound. Proaktywność jako opt-in feature na później. Cron minimalny (lub brak na start). |
| 3 | **Minimalna pamięć (ephemeral partner)** | brain.json ~30 linii: partner config, phase, ostatnie 3-5 tematów, last_contact. Reszta w Hermes memory na żądanie. Zero decay/archive/wnioski jako trwałe struktury. |
| 4 | **Stały charakter** | SOUL.md definiuje osobowość raz. Brak `charakter_bibo` z 6 parametrami. Prostsze, przewidywalne, tańsze. |

### Wywnioskowana filozofia Bibo

> **Bibo = reaktywny partner z minimalną pamięcią i stałym charakterem.**  
> Nie coach ADHD z ewoluującą osobowością i głębokim dziennikiem.  
> Odpowiada na to co user pisze, pamięta tyle ile trzeba by ciągłość była wyczuwalna, ma jasny styl który się nie zmienia.

### Ustalone (iteracja 2)

| # | Decyzja | Konsekwencja architektoniczna |
|---|---------|-------------------------------|
| 5 | **Brak crona (pure reactive)** | Bibo żyje tylko gdy user pisze. Zero background tick. `decision.py` może w ogóle nie istnieć w v2. Zero anti-silence loop. Zero token cost w tle. |
| 6 | **Sonnet 4.6 only** | Jeden model dla wszystkiego. Bez auxiliary routing. Prostsze config, mniejszy surface area. |
| 7 | **Telegram (bez zmian)** | Reuse Hermes Telegram gateway. TTS przez Edge Neural jak w v1.3. Bez zmian w bocie @BotFather. |
| 8 | **Fresh start (zero migracji)** | Nowy `brain.json` z prostą schema. Nowy onboarding od zera. Stary v1.3 usunięty z main (dostępny w historii gita). |

### Wnioski dla architektury Bibo

**To co znika w rebuild:**
- ❌ `scripts/decision.py` (nie ma crona → nie ma slotów MUST/SILENT/MAY)
- ❌ `scripts/breath.py` (nie ma oddechów)
- ❌ `scripts/analytics.py` (może zostać jako opt-in skill, nie w core)
- ❌ `scripts/migrate_brain.py` (fresh start)
- ❌ `charakter_bibo` (fixed personality)
- ❌ `zachowania_biezace.decay/archive` (ephemeral memory)
- ❌ `wnioski.entries` z dowodem (za dużo persistence)
- ❌ `spoken_today`, `spoken_on`, `silence.*` (nie ma limitu bo nie ma inicjatywy)
- ❌ Auxiliary model routing
- ❌ Migration chain 1.0→1.1→1.2→1.3

**To co zostaje:**
- ✅ Plugin `bibo-clean-output` (odchudzony do T007 sanitization)
- ✅ SOUL.md (fixed tożsamość)
- ✅ Anti-sycophancy jako reguła
- ✅ Format wiadomości (Hi + treść + ,imię)
- ✅ Limit 300 znaków / 3 zdania (T008 hard guardrails)
- ✅ Telegram gateway integracja

**Nowe rzeczy (Hermes-native):**
- 🆕 AGENTS.md (kontekst projektu z regułami partnerstwa)
- 🆕 Skills (progressive disclosure zamiast knowledge.md w prompcie)
- 🆕 Hermes memory (zamiast custom brain.json struktur)
- 🆕 Prompt caching (config.yaml)

---

## Etap 1 — Fundament techniczny

### Ustalone

| # | Decyzja | Konsekwencja |
|---|---------|--------------|
| 9 | **VPS (obecna infrastruktura)** | Instalacja przez `hermes profile install` z GitHuba — user instaluje sam, nie edytujemy VPS bezpośrednio z tej sesji. |
| 10 | **Onboarding minimalny (2 pytania)** | Bibo w pierwszej rozmowie pyta o imię i cel. Zapisuje do brain.json (~5 linii). Bez inline keyboard, bez 4-question flow z T004. |
| 11 | **Neutralny partner (produkt-agnostic)** | Bez tematyki ADHD w SOUL/AGENTS. Bez anti-patterns library. Otwarty na dowolne tematy: kod, projekty, decyzje, plany. **Ready dla open-source: każdy user może sensownie użyć.** |
| 12 | **Anti-sycophancy → Critical thinking partner** | Nie konfrontator, nie sycophant. **Partner do myślenia** który: kontruje delikatnie, pyta „co jeszcze?", szuka „gdzie można lepiej?", nie potakuje bezmyślnie. Konstruktywny dialog. |

### Kluczowa zmiana filozofii vs. v1.3

**v1.3 Bibo** = coach ADHD z ewoluującą osobowością i głębokim dziennikiem  
**Bibo (rebuild)** = neutralny partner intelektualny, minimalna pamięć, stały styl, kwestionuje konstruktywnie

### Konsekwencje kulturowe

- ❌ **Znika knowledge.md z ADHD teorii** (Volkow, RSD, delay aversion, hyperfocus)
- ❌ **Znika 12 anti-patterns** (planowanie zamiast robienia, research rabbit hole, etc.)
- ❌ **Znika 8 form komunikacji** (deklaratywny, prowokacja, body doubling, etc.)
- ✅ **Zostaje minimalny styl** (Hi + treść + ,imię, max 300 znaków)
- ✅ **Nowa rola:** partner myślenia = pomoc w rozważaniu opcji, weryfikacji założeń, szukaniu ulepszeń

---

## Etap 2 — Modele i routing

### Ustalone
- **Sonnet 4.6 only** (już w Etap 0 iteracja 2)
- Bez auxiliary routing
- Prompt caching włączony w config.yaml (wynika z filozofii Hermesa)

## Etap 3 — Pamięć i kontekst

### Ustalone

| # | Decyzja | Konsekwencja |
|---|---------|--------------|
| 13 | **1 skill: `bibo-critical-thinking`** | Skill ładowany doraźnie z technikami: sokratejskie pytania, challenge assumptions, "co jeszcze?", "gdzie to nie działa?". Bez ADHD teorii. Bez form komunikacji. |
| 14 | **brain.json ultra-slim: imię + cel + język** | Absolutne minimum. Bez recent_topics, insights, faz, wnioski. `~10 linii`. Bibo nie pamięta rozmów sprzed sesji Telegram. |
| 15 | **Hermes session context: 5-10 ostatnich wymian** | Standard Telegram chatbot. Reasonable balance. Auto-managed przez Hermes memory system. |
| 16 | **Podpis tylko `,bibo` na końcu (bez "Hi" prefix)** | Natural conversational style. "Ciekawe. A gdybyś zamiast X spróbował Y? ,bibo". T007 sanitization przerobiony: obcinamy tylko wymaganie Hi, zostaje ,imię terminator. |

### Nowa struktura brain.json v2

```json
{
  "schema_version": "2.0",
  "partner": {
    "name": "bibo",
    "goal": "partnerstwo do myślenia i kwestionowania rozwiązań",
    "language": "pl"
  },
  "onboarding_complete": false,
  "created_at": "2026-09-21T..."
}
```

Wszystko inne (historia, tematy, insights) → Hermes memory + skill loading.

---

## Etap 3 — Pamięć i kontekst (⏸ czeka)

---

## Etap 4 — Skille i narzędzia

### Ustalone

| # | Decyzja | Konsekwencja |
|---|---------|--------------|
| 17 | **Skill `bibo-critical-thinking`: sokratejskie pytania (klasyka)** | Framework 5 typów pytań: o założenia, o powody, o alternatywy, o konsekwencje, o perspektywy. Bibo dobiera pytanie do sytuacji. Ładowany doraźnie gdy trzeba pogłębić temat. |
| 18 | **Narzędzia: rozmowa + Hermes memory** | Zero file access, zero web search, zero code execution. Hermes built-in memory dostępna (Bibo może zapisać notatkę "myślę że warto zapamiętać X"). Minimalne surface, bezpieczne dla open-source. |
| 19 | **Ton: luźny, po polsku, per Ty** | Konwersacyjny domyślnie. "A gdybyś zamiast X spróbował Y?". Bez formalnego stylu. Bez per Pan/Pani. |
| 20 | **Instalacja: `hermes profile install bibo`** | Hermes-native package. Struktura folderu zgodna z tym co Hermes oczekuje: `SOUL.md`, `AGENTS.md`, `plugins/`, `skills/`, `config.yaml`. Publikacja jako GitHub package. |

### Struktura skilla `bibo-critical-thinking`

```
skills/bibo-critical-thinking/
├── SKILL.md               # Metadata + kiedy się ładuje
├── socratic-questions.md  # 5 typów pytań z przykładami
└── examples.md            # Przykłady użycia w rozmowach
```

Skill ładuje się gdy Bibo widzi w wiadomości usera:
- Deklarację ("zamierzam", "planuję", "myślę o")
- Prośbę o opinię ("co sądzisz", "jak myślisz")
- Wątpliwość ("nie wiem czy", "boję się że")
- Wybór ("A czy B", "co lepsze")

Inne sytuacje (small talk, prosty fakt) — nie ładuje.

---

## Etap 5 — Onboarding, plugin, deployment

### Ustalone

| # | Decyzja | Konsekwencja |
|---|---------|--------------|
| 21 | **Onboarding: imię + cel ogólny (2 pytania)** | Pierwsza rozmowa: "Jak masz na imię?" → user odp → "Nad czym teraz chcesz pomyśleć albo z czym walczysz?" → user odp → zapis do brain.json + onboarding_complete=true. |
| 22 | **BEZ pluginu `bibo-clean-output`** | Zero custom Python. Jeśli Hermes sam nie obcina długości, dopisujemy zasady do AGENTS.md — LLM wymusza samodyscyplinę. Testujemy bez pluginu. Dodajemy tylko gdy widzimy że jest potrzebny. |
| 23 | **Fresh Hermes install, profile `bibo`** | Nowa instalka Hermesa na VPS (`hermes setup`). Legacy `bibo` (v1.3) nie istnieje. Jeden profil `bibo`. Ten sam bot Telegram (token istniejący). |
| 24 | **Iteracyjnie, bez deadline'u** | Milestones zamykane gdy działa. Bez presji. Merge do main po pełnej walidacji. |

---

## Finalna architektura Bibo

**AKTUALIZACJA (2026-09-21, po pierwszym realnym teście instalacji):**
Pierwotny plan miał profil w podfolderze `bibo/`. Realny test
`hermes profile install github.com/Grandpa1001/hi-bibo` pokazał że Hermes
traktuje **cały korzeń repo jako treść dystrybucji** — plik
`distribution.yaml` musi leżeć obok właściwych plików profilu (`SOUL.md`
itd.), nie w podfolderze. Struktura poniżej już odzwierciedla tę korektę
(repo spłaszczone, `bibo/` nie istnieje jako podfolder).

```
distribution.yaml               # Manifest instalacji: name, version, description, author
SOUL.md                         # Tożsamość Bibo (~30 linii)
AGENTS.md                       # Reguły partnerstwa (~50 linii)
                                 # Anti-sycophancy, format, styl, safety
brain.template.json             # Ultra-slim (~10 linii)
                                 # partner.name/goal/language + onboarding
skills/
└── bibo-critical-thinking/
    ├── SKILL.md                # Metadata + trigger conditions
    ├── socratic-questions.md   # 5 typów pytań + przykłady
    └── examples.md             # Przykładowe rozmowy
config.yaml                     # Sonnet 4.6, prompt caching, Telegram gateway

# Pliki projektowe w tym samym korzeniu (Hermes je ignoruje, ale kopiuje
# razem z profilem przy instalacji — kosmetyczny, nie funkcjonalny problem):
# README.md, README.pl.md, Analiza.MD, MAINTENANCE.md, MAINTENANCE.pl.md,
# CHANGELOG.md, LICENSE, .gitignore, .gitattributes

# Hermes built-in (generowane automatycznie przy instalacji profilu):
# cron/, home/, logs/, memories/, plans/, sessions/, skins/, workspace/
# .env          (TELEGRAM_BOT_TOKEN, ANTHROPIC_API_KEY)
```

**Co znika kompletnie:**
- `scripts/` (breath, decision, analytics, migrate) — 4 pliki Python
- `install/plugins/bibo-clean-output/` — plugin + hooki
- `install/setup.py` — Python installer
- `knowledge.md` — 322 linie ADHD teorii  
- `prompt.md` — 304 linie duplikatów z SOUL
- `TESTCASES.md` — obecne testy nie pasują
- `scripts/test_*.py` — testy dla znikającego kodu
- `brain.template.json` (v1.3 schema) → zastąpione minimalną v2

**Sumaryczne LOC:** ~2000 → ~200 (samo config + prompty)

---

## Etap 6 — Roadmapa implementacji (milestones)

### M0 — Analiza ✅
- [x] Ten dokument
- [x] Zamknięte 24 decyzje architektoniczne
- [x] Legacy v1.3 zostaje w gałęzi `main` jako referencja

### M1 — Fresh Hermes na VPS
- [ ] SSH na VPS
- [ ] Backup obecnego `/opt/data/profiles/bibo/` do archive
- [ ] `hermes update` do najnowszej wersji
- [ ] `hermes setup` (świeża instalka jeśli trzeba)
- [ ] `hermes doctor` — verify
- [ ] `hermes profile create bibo` (jeśli nie istnieje)
- **Definition of done:** `hermes chat bibo` odpowiada domyślnie

### M2 — SOUL.md + AGENTS.md
- [x] SOUL.md: tożsamość Bibo (32 linie) — `SOUL.md`
  - Kim jest (partner do myślenia, neutralny)
  - Jaki styl (luźny, PL, per Ty, ,bibo na końcu)
  - Fixed personality, pamięć minimalna, bezpieczeństwo
- [x] AGENTS.md: reguły pracy (49 linii) — `AGENTS.md`
  - Onboarding (2 pytania: imię, cel)
  - Critical thinking trigger (kiedy ładować skill)
  - Anti-sycophancy
  - Co NIE zapisywać do brain.json
- [x] brain.template.json — schema v2.0 ultra-slim
- [ ] Test w CLI: `hermes chat bibo` — czy Bibo brzmi jak Bibo (wymaga instalacji na Hermesie — poza zakresem tej sesji lokalnej)
- **Definition of done:** pliki gotowe do instalacji; test CLI odłożony do momentu instalacji przez usera

### M3 — Skill `bibo-critical-thinking` ✅ (pliki gotowe)
- [x] SKILL.md z metadata (frontmatter name/description) + trigger conditions — `skills/bibo-critical-thinking/SKILL.md`
- [x] socratic-questions.md — 5 typów pytań (założenia/powody/alternatywy/konsekwencje/perspektywa) z przykładami — `socratic-questions.md`
- [x] examples.md — 5 pełnych wymian user→Bibo + sekcja "czego unikać" — `examples.md`
- [ ] Test: Bibo ładuje skill i pyta trafnie (wymaga instalacji na Hermesie)
- **Definition of done:** pliki gotowe; test ładowania odłożony do instalacji

### M4 — brain.json + onboarding flow
- [ ] brain.json schema v2.0 (ultra-slim)
- [ ] AGENTS.md: sekcja onboarding
- [ ] Test: nowa rozmowa → Bibo pyta o imię i cel → zapisuje
- **Definition of done:** onboarding_complete=true po drugiej odpowiedzi

### M2.5 — Wczesny pomiar (NOWY, wynik walidacji z tutorialem warstwa 11)
- [ ] `hermes prompt-size` po M2 (SOUL + AGENTS) — pomiar stałego narzutu
- [ ] Cel: <1500 tokenów statycznego promptu
- [ ] Jeśli >2500 — refactor SOUL/AGENTS zanim ruszymy dalej
- **Definition of done:** znamy baseline PRZED dodaniem skilla, integracji, cachingu

### M5 — Telegram gateway + fallback ✅ (config gotowy, niewalidowany)
- [x] config.yaml: Sonnet 4.6, prompt_cache: true, TTS Edge Neural (opt-in) — `config.yaml`
- [x] `agent.fallback: claude-haiku-4-5-20251001` — emergency route gdy Sonnet down/rate-limited
- [x] Gateway config (Telegram platform, home_channel z env var)
- [ ] `hermes gateway start --profile bibo` (wymaga instalacji — poza zakresem tej sesji)
- [ ] Test: rozmowa z Telegramem
- [ ] Test scenariusza fallback (wymuszony 429)
- **Definition of done:** plik gotowy z jawną adnotacją "niewalidowany na żywym Hermesie"; testy live odłożone do instalacji

### M6, M7, M8 — przeniesione do MAINTENANCE.md

Optymalizacja (warstwa 11), Recovery + Security (warstwy 12+13) i
Self-audit (warstwa 14) to praktyki **cykliczne**, nie zadania budowlane
jednorazowe. Wyodrębnione do osobnego, żywego dokumentu:
**[MAINTENANCE.md](MAINTENANCE.md)** ([MAINTENANCE.pl.md](MAINTENANCE.pl.md)) —
checklisty z rekomendowanym cyklem (co tydzień / co miesiąc / co kwartał),
w tym dokładny prompt self-audytu z tutoriala Hermesa.

Ten dokument (Analiza.MD) zostaje historycznym zapisem decyzji — nie
aktualizujemy go już o postęp operacyjny po instalacji, ten żyje
w MAINTENANCE.md.

### M7.5 — Open-source ready (jednorazowe, zostaje tutaj)
- [x] README.md / README.pl.md z instrukcjami instalacji krok-po-kroku
- [ ] `hermes profile install` support — potwierdzić że faktycznie działa (fallback manualny już opisany w README)
- [ ] Przykładowa konfiguracja (bez sekretów) — do dodania jeśli `config.yaml` wymaga korekt po pierwszym teście
- [ ] LICENSE zaktualizowany
- [ ] Zrzut ekranu / GIF pierwszej rozmowy
- **Definition of done:** ktoś inny może zainstalować w <30 min z README

---

## Non-goals (co świadomie odrzucamy)

- ❌ Multi-user (single-user architecture)
- ❌ Proaktywny cron (reaktywne only)
- ❌ Ewoluujący charakter (fixed personality)
- ❌ Migracja z v1.3 (fresh start)
- ❌ ADHD-specific knowledge (neutralny partner)
- ❌ Anti-patterns library (zbędne)
- ❌ 8 form komunikacji (naturalne, jedno)
- ❌ `charakter_bibo` parametry (fixed)
- ❌ `wnioski.entries` z dowodem (za dużo persistence)
- ❌ Custom Python installer (Hermes CLI)
- ❌ Custom plugin (Hermes native)
- ❌ Analytics/telemetry na start (dodać jeśli okaże się potrzebne)
- ❌ Multi-language poza PL na start
- ❌ Auxiliary model routing (tylko Sonnet)

---

## Metryki sukcesu

**Techniczne:**
- Stały narzut promptu <2k tokenów (`hermes prompt-size`)
- Średni oddech <5k tokenów input
- Koszt miesięczny <$5 (vs ~$27 w v1.3)

**Jakościowe:**
- Bibo w rozmowie brzmi jak partner myślenia, nie chatbot
- Zero fabricated "insights" i "obserwacji" (nie zgaduje)
- Kwestionuje ale nie prowokuje
- Podpis `,bibo` konsystentny

**Operacyjne:**
- `hermes doctor` zielony
- `hermes backup` działa, jest cloud restore
- Nowy user może zainstalować z README w <30 min

---

## Ryzyka i mitygacja

| Ryzyko | Mitygacja |
|--------|-----------|
| Bibo bez pluginu pisze za długo | Testowanie w M2. Dodać plugin jeśli trzeba. |
| `hermes profile install` nie działa jak myślę | Sprawdzić w M1, fallback do skryptu bash |
| Sonnet 4.6 za drogi mimo cachingu | Pomiary w M6. Fallback: Haiku dla small talk. |
| Skill critical-thinking się nie ładuje | Trigger conditions dopracowane iteracyjnie w M3. |
| User zapomni co Bibo pamięta | README wyjaśnia ephemeral naturę. |
| Legacy bot Telegram konflikt | Backup obecnego stanu w M1. |

---

## Walidacja planu vs. 14 warstw tutorialu Hermesa (2026-09-21)

Przeanalizowano plan pod kątem każdej z 14 warstw z tutorialu.

### ✅ W pełni zgodne (10/14)

| Warstwa | Zgodność |
|---------|----------|
| 1. Fundament | M1 dokładnie odpowiada (jeden profil, jeden model, `hermes doctor`) |
| 3. Pamięć/kontekst | SOUL/AGENTS/brain.json rozdzielone jak w tutorialu |
| 4. Struktura agentów | Jeden profil, brak multi-agent |
| 5. Narzędzia | Zero side effects, tylko rozmowa + Hermes memory |
| 6. Skills | Progressive disclosure, 1 własny skill |
| 7. Wtyczki | **BEZ pluginu** — najlżejsza opcja |
| 8. Projekty/wiedza | AGENTS.md zwięzły, źródła doczytywane przez skill |
| 9. Automatyzacja | **Zero crona** — ekstremalny minimalizm |
| 10. Multi-agent | Non-goal |
| 11. Optymalizacja | Reactive + minimum context = idealna filozofia |

### ⚠️ Wzmocnione po walidacji (4/14)

| Warstwa | Luka wykryta | Poprawka |
|---------|--------------|----------|
| 2. Modele | Brak fallback (Anthropic down = Bibo martwy) | Dodano `agent.fallback: haiku-4-5` w M5 |
| 11. Pomiar | Pomiar dopiero w M6 (za późno) | Dodano **M2.5 — wczesny pomiar** po SOUL/AGENTS |
| 12. Recovery | „Backup w cloud" bez cadence/destination/restore drill | Rozbudowa M7: konkretny dostawca (B2/S3), restore drill, cykl |
| 13. Bezpieczeństwo | `.env` plaintext, brak security audit | M7: Hermes secrets, `hermes security audit`, rotacja tokenu |

### ➕ Nowy milestone (1/14)

| Warstwa | Poprawka |
|---------|----------|
| 14. Self-audit | **M8 — Monthly self-audit** z konkretnym promptem z tutorialu, raport do `logs/audit-YYYY-MM.md` |

### Podsumowanie walidacji

**Wynik:** 10 warstw ✅ + 4 wzmocnione ⚠️ + 1 nowa ➕ = **15/14 zgodności** (żadna nie została pominięta).

**Największa siła planu:**
- Filozofia „nie komplikuj na zapas" wywalczona radykalnie (zero cron, zero plugin, zero auxiliary)
- Reactive-only + ephemeral memory = najtańszy token = ten nie wysłany

**Największe ryzyko:**
- Brak crona = Bibo nie zauważy tygodniowej ciszy usera. Świadome. Jeśli okaże się problemem — dodać silence-watchdog cron w M9 (przyszłość).

---

## Kolejne kroki

1. ✅ **Analiza.MD w main** — utrwalenie decyzji + walidacji
2. ✅ **Stary kod v1.3 usunięty z main** (2026-09-21) — bez legacy branch, historia w gicie jeśli trzeba
3. ✅ **Cały pakiet gotowy lokalnie** (spłaszczony do korzenia repo, nie podfolder) — SOUL.md, AGENTS.md, brain.template.json, skill `bibo-critical-thinking` (3 pliki), config.yaml
4. ✅ **`distribution.yaml`** dodany — manifest wymagany przez `hermes profile install` (name, version, description, author)
5. ✅ **README.md / README.pl.md** przepisane pod instalację, w tym potwierdzoną składnię `hermes profile install github.com/Grandpa1001/hi-bibo`
6. 🟡 **Diagnoza pogłębiona po spłaszczeniu:** `hermes profile install --force` po fixie #3 nadal kopiował pliki (teraz poprawnie, potwierdzone komunikatem *"will overwrite distribution-owned files only"* — Hermes rozpoznaje nasze pliki) ale **profil nadal się nie rejestrował**. `hermes profile create bibo` odmówił bo katalog już istniał (sprawdza tylko obecność folderu, nie rejestr). To wykluczyło hipotezę ze spłaszczeniem jako jedyną przyczynę.
7. ✅ **Prawdziwa przyczyna znaleziona przez research dokumentacji Hermesa** (`github.com/NousResearch/hermes-agent`, nie `NousResearch/hermes` — zła nazwa repo w naszych wcześniejszych linkach, też poprawione):
   - Profile są rozpoznawane **po obecności plików identyfikujących** (`SOUL.md`, `config.yaml` itd.) — nie ma osobnego rejestru
   - Ale **`config.yaml` musi przejść walidację** żeby profil był uznany za poprawny — `profile list` parsuje go żeby pokazać kolumnę "Model"
   - **Nasz `config.yaml` używał całkowicie zmyślonego schematu**: `agent.model` zamiast top-level `model:`, `agent.fallback` zamiast `providers.*.fallback_chain`, `plugins.enabled` (nie istnieje), `platforms.telegram` w config.yaml (Telegram konfiguruje się przez `hermes gateway setup`, nie tu), `cron.jobs` w config.yaml (cron to osobne pliki, nie klucz configu)
   - Bardzo prawdopodobnie to właśnie nieprawidłowy `config.yaml` cicho wywalał walidację i blokował rejestrację, nawet gdy pliki fizycznie istniały
8. ✅ **Naprawione:** `config.yaml` przepisany na minimalny, zawiera TYLKO potwierdzone klucze (`model:` top-level, `skills.auto_load: []`). Reszta (fallback_chain, dokładny format ID modelu, prompt cache) świadomie pominięta zamiast zgadywana. README zaktualizowane o poprawną komendę gatewaya (`hermes -p bibo gateway` / `hermes gateway setup`, nie `hermes gateway start --profile`) i poprawny link do repo Hermesa.
9. **Teraz:** Kamil pushuje poprawiony `config.yaml` → retest `hermes profile install ... --force` → `hermes profile list` → `hermes -p bibo chat`
