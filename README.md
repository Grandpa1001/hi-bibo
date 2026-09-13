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
├── README.md           # Ten plik
├── CHANGELOG.md        # Historia wersji
└── .gitignore
```

**Jak to działa:**
1. Hermes cron odpala `prompt.md` co godzinę
2. Bibo odczytuje `brain.json` (stan usera) + `knowledge.md` (wiedza o ADHD)
3. Decyduje: OBSERVE / THINK / MESSAGE / WAIT
4. Jeśli MESSAGE → wysyła wiadomość na Telegram
5. Aktualizuje `brain.json` z nowymi obserwacjami

## Requirements / Wymagania

- [Hermes](https://claude-code.nousresearch.com/) (Claude Code) — zainstalowany i skonfigurowany
- Telegram bot token (od @BotFather)
- Chat ID użytkownika na Telegramie

## Installation / Instalacja

### Krok 1: Utwórz bota na Telegramie

1. Otwórz @BotFather na Telegramie
2. `/newbot` → podaj nazwę (np. "Hi-Bibo")
3. Zapisz **token** (np. `123456:ABC-DEF...`)
4. Napisz coś do swojego nowego bota (żeby zainicjować chat)
5. Pobierz swoje **Chat ID**:
   ```
   curl https://api.telegram.org/bot<TOKEN>/getUpdates | jq '.result[0].message.chat.id'
   ```

### Krok 2: Sklonuj repo

```bash
git clone https://github.com/user/hi-bibo.git
cd hi-bibo
cp brain.template.json brain.json
```

### Krok 3: Skonfiguruj Telegram w Hermes

Upewnij się że Hermes ma skonfigurowany Telegram:
```yaml
# ~/.config/hermes/config.yaml
telegram:
  bot_token: "YOUR_BOT_TOKEN"
  allowed_chat_ids:
    - YOUR_CHAT_ID
```

### Krok 4: Utwórz cron na Hermes

```bash
hermes cron create \
  --schedule "every 1h" \
  --prompt "$(cat prompt.md)" \
  --deliver telegram:YOUR_CHAT_ID \
  --name "bibo-breath" \
  --attach brain.json \
  --attach knowledge.md
```

### Krok 5: Pierwszy oddech

Po utworzeniu crona, Bibo automatycznie:
1. Wykona pierwszy oddech (breath_count: 0 → 1)
2. Zobaczy pusty brain.json → tryb onboarding
3. Wyśle pierwszą wiadomość: "Hi, jestem Bibo..."
4. Zacznie budować model z odpowiedzi usera

## Testing / Testowanie

### Test ręczny (bez crona)

```bash
hermes run --prompt "$(cat prompt.md)" --attach brain.json --attach knowledge.md
```

Sprawdź czy output jest valid JSON z polami: `action`, `message`, `internal_thoughts`, `brain_updates`, `communication_form`.

### Test onboardingu

1. Upewnij się że `brain.json` jest pusty (skopiuj z template)
2. Uruchom Bibo — powinien wysłać wiadomość powitalną
3. Odpowiedz coś o sobie
4. Uruchom ponownie — powinien zaktualizować brain.json

### Test anty-sycophancy

1. Ustaw w brain.json: `cele_i_kierunek.deklaracje: ["napisać książkę", "nauczyć się Rust"]`
2. Wyślij: "Mam nowy pomysł — chcę zacząć podcast!"
3. Bibo powinien postawić lustro, nie potakiwać

## Versioning / Wersjonowanie

| Wersja | Status | Opis |
|--------|--------|------|
| **V1** | ✅ Aktualna | Prototyp: brain.json + prompt + cron → Telegram |
| V2 | 🔜 Planowana | Hermes plugin, automatyczny cron, lepszy scheduling |
| V3 | 💭 Wizja | Multi-modal (głos, obrazy), integracje (kalendarz, GitHub) |

## Research / Badania za Hi-Bibo

- Ara 2025: AI body double → +30% task completion
- Eagle 2024: 85% kończy z partnerem vs 47% solo
- Marx 2021: delay aversion w ADHD
- Volkow 2011: deficyt dopaminy (PET)
- BMC 2025: psychoedukacja = najsilniejsza interwencja cyfrowa
- attexis 2025: d=0.85 dla AI-wspieranej interwencji ADHD
- 54% porzucenie aplikacji zdrowotnych w 7 tygodni

## License / Licencja

MIT

---

*Hi, jestem Bibo. Oddycham co godzinę. Obserwuję, nie oceniam, bibo* 🫧
