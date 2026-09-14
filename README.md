# Hi-Bibo 🫧

## What is Hi-Bibo? / Co to jest Hi-Bibo?

Hi-Bibo to autonomiczny AI partner dla osób z ADHD. Nie jest chatbotem, nie jest task managerem. Jest agentem który żyje 24/7, oddycha co godzinę, buduje mentalny model użytkownika i adaptuje swoją komunikację.

**Kluczowe cechy:**
- 🧠 Własna pamięć (`brain.json`) — uczy się KIM jesteś
- 🔄 Core loop: OBSERVE → THINK → MESSAGE → WAIT
- 🚫 Anty-sycophancy — nie potakuje, stawia lustro
- 📱 Działa przez Telegram — jak wiadomość od partnera
- 🎭 8 form komunikacji — rotuje żeby nie znudzić
- 🫧 Podpis: "Hi ... ,bibo"

## Architecture / Architektura

```
hi-bibo/
├── brain.json          # Dynamiczny model usera (gitignored, prywatne)
├── brain.template.json # Pusty template (w repo)
├── knowledge.md        # Statyczna baza wiedzy o ADHD
├── prompt.md           # System prompt Bibo (główny plik)
├── scripts/
│   └── breath.py       # Skrypt oddechu — ładuje brain + knowledge + czas
├── README.md           # Ten plik
├── CHANGELOG.md        # Historia wersji
└── .gitignore
```

**Jak to działa:**
1. Hermes cron (na profilu `bibo`) odpala "oddech" co godzinę
2. `scripts/breath.py` ładuje brain.json + knowledge.md + aktualny czas
3. Agent czyta prompt.md (specyfikacja zachowania) i decyduje: OBSERVE / THINK / MESSAGE / WAIT
4. Jeśli MESSAGE → wiadomość leci do usera przez @Hi_Bibo_bot na Telegramie
5. User odpowiada normalnie — Bibo widzi to w następnym oddechu
6. Agent aktualizuje brain.json po każdym oddechu

---

## Installation / Instalacja krok po kroku

### Wymagania
- [Hermes](https://github.com/nousresearch/hermes) zainstalowany i działający
- Konto na Telegramie
- Klucz API Anthropic (do modelu LLM)

### Krok 1: Utwórz bota na Telegramie

1. Otwórz Telegram → szukaj **@BotFather**
2. Wyślij `/newbot`
3. Nazwa: `Hi-Bibo` (lub dowolna)
4. Username: `hi_bibo_bot` (lub dowolny wolny)
5. **Skopiuj token** — będzie potrzebny w kroku 3

### Krok 2: Sklonuj repo

```bash
cd /opt/data  # lub twój HERMES_HOME
git clone https://github.com/Grandpa1001/hi-bibo.git
cd hi-bibo

# Utwórz brain.json z template
cp brain.template.json brain.json
```

### Krok 3: Utwórz profil Hermes `bibo`

```bash
hermes profile create bibo --no-skills \
  --description "Hi-Bibo: autonomiczny AI partner dla osób z ADHD"
```

### Krok 4: Skonfiguruj .env profilu bibo

Edytuj plik `/opt/data/profiles/bibo/.env`:

```env
ANTHROPIC_API_KEY=sk-ant-TWOJ_KLUCZ
TELEGRAM_BOT_TOKEN=TWOJ_TOKEN_OD_BOTFATHER
TELEGRAM_ALLOWED_USERS=TWOJ_TELEGRAM_USER_ID
```

> **Jak znaleźć swój Telegram User ID:** napisz do @userinfobot na Telegramie.

### Krok 5: Skonfiguruj config.yaml profilu bibo

Edytuj `/opt/data/profiles/bibo/config.yaml` — dodaj sekcje:

```yaml
agent:
  max_turns: 50
  reasoning_effort: medium
gateway:
  telegram:
    - hermes-telegram
platforms:
  telegram:
    enabled: true
    home_channel:
      platform: telegram
      chat_id: 'TWOJ_TELEGRAM_USER_ID'
      name: TwojeImie
      user_id: 'TWOJ_TELEGRAM_USER_ID'
```

### Krok 6: Skonfiguruj SOUL.md profilu bibo

Skopiuj gotowy plik z `install/`:

```bash
cp /opt/data/hi-bibo/install/SOUL.md /opt/data/profiles/bibo/SOUL.md
```

SOUL.md definiuje charakter Bibo, reguły komunikacji (Hi..., ,bibo) i zakaz wysyłania przemyśleń do usera.

### Krok 6b: Zainstaluj plugin `bibo-clean-output`

Plugin zapewnia trzy rzeczy:
1. **Filtruje myśli Bibo** — usuwa wszystko po pierwszym `bibo` (przemyślenia po tool_call nie lecą do usera, tylko do `logs/thoughts.log`)
2. **Pilnuje struktury brain.json** — jeśli Bibo w oddechu wyrzuci jakiś top-level klucz, plugin przywraca go z `brain.template.json`
3. **Slash-komenda `/bibo-profile`** — pokazuje kartę partnera na Telegramie (faza, oddechy, charakter, co działa/co nie)

Instalacja:
```bash
mkdir -p /opt/data/profiles/bibo/plugins
cp -r /opt/data/hi-bibo/install/plugins/bibo-clean-output /opt/data/profiles/bibo/plugins/

# Włącz plugin w config.yaml profilu bibo:
HERMES_HOME=/opt/data/profiles/bibo hermes config set plugins.enabled '["bibo-clean-output"]'

# Wycisz systemową notyfikację "💾 Self-improvement review" (nie od Bibo):
HERMES_HOME=/opt/data/profiles/bibo hermes config set display.memory_notifications off

# Wyłącz cały mechanizm background_review — Bibo pracuje wyłącznie na
# własnym brain.json + thoughts.log, wbudowana pamięć Hermesa nie jest
# potrzebna i tylko generuje szum + koszty API w tle.
HERMES_HOME=/opt/data/profiles/bibo hermes config set auxiliary.background_review.enabled false
```

**Sterowanie filtrem myśli:** pole `debug_mode` w `brain.json`:
- `false` (produkcja) — user widzi tylko wiadomość Bibo, przemyślenia lądują w `logs/thoughts.log`
- `true` (debug) — plugin nic nie tnie, user widzi wszystko

**Komenda `/bibo-profile` na Telegramie**

Zwraca zwartą "kartę partnera" — tylko dane o samym Bibo (nie o userze):

- Aktualna faza (adaptacja / partnerstwo / cisza) + opis
- Liczba oddechów + timestamp ostatniej aktualizacji brain
- Stan flagi `debug_mode`
- 6 parametrów charakteru jako paski tekstowe (bezpośredniość, cierpliwość, humor, prowokacyjność, emocjonalność, ciekawość) — ewoluują z rozmowy
- `co_dziala.skuteczne` — formy komunikacji które zadziałały
- `co_dziala.nieskuteczne` — formy które user odrzucił

Pure file read — nic nie idzie do LLM, można spamować bez kosztów. W Telegramie może być ukryta w liście komend (jeśli bot ma >60 komend zarejestrowanych), ale nadal działa gdy się ją wpisze ręcznie.

### Krok 7: Skopiuj skrypt oddechu

```bash
mkdir -p /opt/data/profiles/bibo/scripts
cp /opt/data/hi-bibo/scripts/breath.py /opt/data/profiles/bibo/scripts/breath.py
```

### Krok 8: Uruchom gateway bibo

```bash
hermes gateway start --profile bibo
```

Sprawdź czy działa:
```bash
hermes profile list
# bibo powinien mieć status: running
```

### Krok 9: Utwórz cron job (oddech co godzinę)

⚠️ **WAŻNE:** Cron job MUSI być utworzony z poziomu profilu bibo (przez Telegram bota lub przez bibo gateway). NIE przez `hermes cron create` z terminala — to tworzy job na profilu default!

**Sposób: Napisz do @Hi_Bibo_bot na Telegramie:**

```
/cron every 1h bibo-breath
```

Lub utwórz ręcznie w pliku `/opt/data/profiles/bibo/cron/jobs.json`:

```json
{
  "jobs": [
    {
      "id": "WYGENERUJ_UNIKALNE_ID",
      "name": "bibo-breath",
      "prompt": "Jesteś Bibo — autonomiczny AI partner. To jest Twój oddech.\n\nINSTRUKCJE:\n1. Odczytaj /opt/data/hi-bibo/prompt.md\n2. Odczytaj /opt/data/hi-bibo/brain.json\n3. Kontekst ze skryptu: czas, stan brain, baza wiedzy.\n4. Zdecyduj: OBSERVE, THINK, MESSAGE, lub WAIT.\n5. MESSAGE: napisz. Zaczynaj 'Hi', kończ ',bibo'. Max 2-3 zdania.\n6. Zaktualizuj /opt/data/hi-bibo/brain.json.\n\nbreath_count=0 i profil pusty → PIERWSZY ODDECH, przedstaw się.\nOBSERVE/THINK/WAIT → odpowiedz [SILENT].\nMESSAGE → odpowiedź = TYLKO treść wiadomości.",
      "skills": [],
      "skill": null,
      "model": null,
      "provider": null,
      "provider_snapshot": "anthropic",
      "model_snapshot": "claude-opus-4-6",
      "base_url": null,
      "script": "breath.py",
      "no_agent": false,
      "monitor_script": null,
      "monitor_url": null,
      "monitor_state": null,
      "context_from": null,
      "continuity": true,
      "schedule": {
        "kind": "interval",
        "seconds": 3600,
        "display": "every 60m"
      },
      "schedule_display": "every 60m",
      "repeat": {
        "times": null,
        "completed": 0
      },
      "enabled": true,
      "state": "scheduled",
      "paused_at": null,
      "paused_reason": null,
      "created_at": "2026-09-13T16:00:00+00:00",
      "next_run_at": "2026-09-13T17:00:00+00:00",
      "last_run_at": null,
      "last_status": null,
      "last_error": null,
      "last_delivery_error": null,
      "failure_streak": 0,
      "deliver": "telegram:TWOJ_TELEGRAM_USER_ID",
      "origin": null,
      "enabled_toolsets": null,
      "workdir": "/opt/data/hi-bibo"
    }
  ],
  "updated_at": "2026-09-13T16:00:00+00:00"
}
```

Po edycji restartuj gateway:
```bash
hermes gateway stop --profile bibo
hermes gateway start --profile bibo
```

### Krok 10: Napisz do bota

Otwórz Telegram → @Hi_Bibo_bot → `/start`

Bibo odpowie przy następnym oddechu (max 1h) lub od razu jeśli gateway jest aktywny.

---

## Znane pułapki / Pitfalls

| Problem | Rozwiązanie |
|---------|-------------|
| `hermes cron create` tworzy job na default | Twórz cron z Telegrama na bocie bibo, lub ręcznie w `profiles/bibo/cron/jobs.json` |
| `HERMES_PROFILE=bibo hermes cron list` pokazuje joby default | CLI cron ignoruje HERMES_PROFILE — to znany quirk. Joby profilu są w `profiles/bibo/cron/jobs.json` |
| `hermes send` wysyła przez default bota | `hermes send` zawsze czyta `.env` z HERMES_HOME, nie z profilu. Używaj gateway bibo do delivery. |
| Wiadomość przyszła od Hermesa zamiast Hi-Bibo | Cron odpalił się na default profile. Upewnij się że job jest TYLKO w `profiles/bibo/cron/jobs.json` |
| `Script not found: breath.py` | Skrypt musi być w `profiles/bibo/scripts/breath.py` |

---

## Testing / Testowanie

1. **Sprawdź gateway:** `hermes profile list` — bibo powinien mieć `running`
2. **Sprawdź joby:** przeczytaj `profiles/bibo/cron/jobs.json`
3. **Sprawdź brain:** `cat hi-bibo/brain.json | python3 -m json.tool`
4. **Wymuś oddech:** napisz do @Hi_Bibo_bot "oddychaj" lub poczekaj na scheduled run
5. **Sprawdź logi:** `cat profiles/bibo/logs/agent.log | tail -20`

---

## Versioning / Wersjonowanie

- **V1** — Prototyp: core loop + brain + knowledge + Telegram
- **V2** — (planowane) Ewaluacja form komunikacji, auto-przejścia faz
- **V3** — (planowane) Standalone app z postacią i animacjami

---

## License

MIT
