[🇬🇧 English](README.md) | 🇵🇱 Polski

# Hi-Bibo 🫧

## Co to jest Hi-Bibo?

Hi-Bibo to autonomiczny AI partner dla osób z ADHD. Nie jest chatbotem, nie jest task managerem. Jest agentem który żyje 24/7, oddycha co godzinę, buduje mentalny model użytkownika i adaptuje swoją komunikację.

**Kluczowe cechy:**
- 🧠 Własna pamięć (`brain.json`) — uczy się KIM jesteś
- ⏰ Cron = budzik — czyta brain, triggeruje gateway
- 🧩 Gateway = mózg — jedyny agent który myśli i pisze
- 🚫 Anty-sycophancy — nie potakuje, stawia lustro
- 📱 Działa przez Telegram — jak wiadomość od partnera
- 🎭 8 form komunikacji — rotuje żeby nie znudzić
- 🫧 Podpis: "Hi ... ,bibo"

## Architektura

```
hi-bibo/
├── brain.json          # Dynamiczny model usera (gitignored, prywatne)
├── brain.template.json # Pusty template (w repo)
├── knowledge.md        # Statyczna baza wiedzy o ADHD
├── prompt.md           # System prompt Bibo (główny plik)
├── scripts/
│   ├── breath.py       # Oddech + slot decyzji
│   ├── decision.py     # Twardy budżet MUST/MAY/SILENT
│   ├── analytics.py    # CLI indeksu jakości (operator)
│   └── test_analytics.py
├── install/
│   ├── setup.py        # Instalator + kreator (imię, cel, język, TTS)
│   ├── SOUL.md
│   └── plugins/bibo-clean-output/
├── README.md           # English (domyślny)
├── README.pl.md        # Ten plik (polski)
├── CHANGELOG.md        # Historia wersji
└── .gitignore
```

**Jak to działa:**
1. Cron co godzinę budzi profil `bibo`
2. `breath.py` podaje czas, brain i **twardy slot** (`MUST_WRITE` / `MAY_WRITE` / `SILENT`)
3. Model pisze treść tylko gdy slot pozwala — plugin egzekwuje `SILENT`
4. Wiadomość idzie na Telegram (tekst + opcjonalna bańka Edge Neural po `/voice tts`)
5. Po rozmowie agent może dodać jeden wniosek z dowodem do `wnioski.entries`

> **Zmiana vs. V0:** Cron nie decyduje OBSERVE / THINK / MESSAGE / WAIT. Jest budzikiem — wysyła zagajenie lub `[SILENT]`. Całą logikę prowadzi gateway.

---

## Issues & Kanban

- 📋 **Issues:** [github.com/Grandpa1001/hi-bibo/issues](https://github.com/Grandpa1001/hi-bibo/issues)
- 📊 **Project board:** [github.com/users/Grandpa1001/projects/1](https://github.com/users/Grandpa1001/projects/1)

---

## Instalacja

### Wymagania
- [Hermes Agent](https://github.com/nousresearch/hermes) w PATH
- Konto Telegram + token od [@BotFather](https://t.me/BotFather)
- Twoje Telegram user ID (napisz do [@userinfobot](https://t.me/userinfobot))
- Auth modelu w Hermesie (Anthropic API key albo OAuth)
- `ffmpeg` — bez niego Edge TTS idzie jako plik, nie bańka głosowa (`brew install ffmpeg` / `sudo apt install ffmpeg`)

### 1. Sklonuj paczkę

```bash
cd /opt/data   # albo katalog, z którego Hermes widzi workdir
git clone https://github.com/Grandpa1001/hi-bibo.git
cd hi-bibo
```

### 2. Odpal kreator

```bash
python3 install/setup.py
```

Kreator zapyta po kolei:
1. **Język** — pl / en
2. **Imię partnera** — 3 losowe propozycje (Mira, Nox, Olek, …) albo własne
3. **Cel relacji** — jeden kontrakt, np. „dowozić sprint, bez nowych projektów”
4. **Częstość** — rzadko / normalnie / często (to jest twardy budżet, nie prompt)
5. **TTS** — Edge Neural (`Zofia` / `Marek` po polsku, `Aria` / `Andrew` po angielsku). To nie jest wbudowany głos Telegrama.
6. **Token bota** i **Twoje user ID**

Skrypt sam: tworzy profil `bibo`, kopiuje SOUL + plugin + skrypty, wpisuje `.env`, stawia TTS/STT w `config.yaml`, cron oddechu, `brain.json` i startuje gateway.

Bez pytań (CI / powtórka):

```bash
python3 install/setup.py --yes --language pl --name Mira \
  --goal "dowozić sprint" --frequency normal --tts zofia \
  --telegram-token 'TOKEN' --telegram-user-id '123456'
```

### 3. Telegram — pierwsze 30 sekund

Otwórz bota → `/start`, potem:

| Komenda | Co robi |
|---|---|
| `/bibo-setup` | Kreator w czacie (imię, cel, język, TTS, częstość). Działa bez LLM. |
| `/voice tts` | Odpowiedzi jako **bańka głosowa** z Edge Neural (nie TTS Telegrama) |
| `/bibo-profile` | Karta partnera |
| `/bibo-analytics` | Indeks czy Bibo działa lepiej |

`/bibo-setup losuj` podrzuca nowe imiona.

### Co jest deterministyczne po instalacji

- **Kiedy pisać** liczy `scripts/decision.py` (limit dnia, anty-cisza 12h, cisza nocna). Model nie głosuje.
- Slot `SILENT` plugin **wymusza** — LLM nie przebije budżetu.
- **Wnioski** idą do `brain.json → wnioski.entries` tylko z dowodem.
- TTS z paczki: `edge` + głos narodowy + Whisper `small` do STT (lepszy polski niż `base`).

Stara instalacja ręczna (10 kroków) jest zastąpiona tym skryptem. Jeśli coś padnie, `install/setup.py` jest listą tych samych operacji.

## Znane pułapki

| Problem | Rozwiązanie |
|---------|-------------|
| `hermes cron create` tworzy job na default | Twórz cron z Telegrama na bocie bibo, lub ręcznie w `profiles/bibo/cron/jobs.json` |
| `HERMES_PROFILE=bibo hermes cron list` pokazuje joby default | CLI cron ignoruje HERMES_PROFILE — to znany quirk. Joby profilu są w `profiles/bibo/cron/jobs.json` |
| `hermes send` wysyła przez default bota | `hermes send` zawsze czyta `.env` z HERMES_HOME, nie z profilu. Używaj gateway bibo do delivery. |
| Wiadomość przyszła od Hermesa zamiast Hi-Bibo | Cron odpalił się na default profile. Upewnij się że job jest TYLKO w `profiles/bibo/cron/jobs.json` |
| `Script not found: breath.py` | Skrypt musi być w `profiles/bibo/scripts/breath.py` |
| Cron `state=error`, `Failed to compute next run` | Schedule ma `"seconds": N` zamiast `"minutes": N`. Hermes cron dla `kind: interval` czyta tylko `minutes`. |
| Cron pisze `401 API key is invalid` w `breath.py` | Job ma `no_agent: true` — skrypt próbuje sam wołać Anthropic. Zmień na `no_agent: false`, żeby to hermes-agent wołał LLM (dziedziczy OAuth z gatewaya). |
| Co godzinę dostajesz `bibo` samo bez treści | Bibo poprawnie zwraca `[SILENT]` gdy nic do powiedzenia, ale pluginy filtrujące myśli mogą go zamieniać na `bibo`. Fix: plugin `bibo-clean-output` musi przepuszczać `[SILENT]` niezmienione. |
| Wiadomość od Hermesa "💾 Self-improvement review: ..." | Wbudowany `background_review` w Hermesie działa równolegle do brain.json Bibo. Wyłącz: `hermes config set auxiliary.background_review.enabled false` w profilu bibo. |
| Głos brzmi jak tani TTS Telegrama | To nie Edge. W kreatorze wybierz Zofia/Marek, zainstaluj `ffmpeg`, na czacie `/voice tts`. |

---

## Testowanie

1. **Sprawdź gateway:** `hermes profile list` — bibo powinien mieć `running`
2. **Sprawdź joby:** przeczytaj `profiles/bibo/cron/jobs.json`
3. **Sprawdź brain:** `cat hi-bibo/brain.json | python3 -m json.tool`
4. **Wymuś oddech:** napisz do @Hi_Bibo_bot "oddychaj" lub poczekaj na scheduled run
5. **Sprawdź logi:** `cat profiles/bibo/logs/agent.log | tail -20`

---

## Analityka jakości

Bez szeregu czasowego nie da się powiedzieć, czy zmiana promptu/crona „poprawiła Bibo”. `brain.json` to tylko stan bieżący.

Warstwa analityki:
- `scripts/breath.py` zapisuje snapshot mózgu przy każdym oddechu
- plugin zapisuje inbound/outbound (długość, hash, flagi higieny — **bez treści wiadomości**)
- plik: `$BIBO_DIR/logs/analytics.jsonl` (gitignored)

```bash
# z maszyny, na której żyje Bibo
BIBO_DIR=/opt/data/hi-bibo python3 /opt/data/hi-bibo/scripts/analytics.py report
BIBO_DIR=/opt/data/hi-bibo python3 /opt/data/hi-bibo/scripts/analytics.py report --json --days 7

# na Telegramie (plugin ≥ 1.2)
/bibo-analytics
/bibo-analytics 14
```

**Indeks 0–100** (proxy, nie klinika), wagi:
| Składowa | Waga | Co mierzy |
|---|---|---|
| Reply rate 6h | 35% | Czy user odpowiada na wiadomości Bibo |
| Obecność | 25% | Czy Bibo odzywa się, gdy user milczy >12h |
| Uczenie | 20% | Średnie `confidence` bucketów w brain.json |
| Higiena | 20% | Brak guilt-tripu, sycophancy, ścian tekstu, przecieków myśli |

Raport porównuje **bieżące N dni z poprzednimi N dni**. Werdykt `rosnie` / `spada` / `stabilne` wymaga ruchu o ≥5 pkt. Za mało zdarzeń → indeks jest `null`, nie zgadujemy.

Bibo **nie** ładuje tego raportu do kontekstu — inaczej zacząłby optymalizować metrykę zamiast relację.

---

## Wersjonowanie

- **V1** — Prototyp: cron-budzik + brain + gateway + Telegram
- **V2** — (planowane) Ewaluacja form komunikacji, auto-przejścia faz, standalone app

---

## License

MIT
