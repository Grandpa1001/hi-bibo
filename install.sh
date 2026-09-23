#!/usr/bin/env bash
# Bibo — instalator jednym poleceniem.
#
#   ./install.sh                  # instaluje z GitHuba
#   ./install.sh /ścieżka/do/repo # instaluje z lokalnego katalogu (development)
#
# Bezpieczny do ponownego uruchomienia: aktualizuje profil, nie ruszając
# Twojej pamięci, historii ani sekretów, i nie dubluje zadania cron.
set -euo pipefail

SOURCE="${1:-github.com/Grandpa1001/hi-bibo}"
PROFILE="bibo"
JOB_NAME="bibo-pulse"
PULSE_PROMPT="Odezwij się do usera sam z siebie, zgodnie z sekcją 'Gdy odzywasz się sam' w Twojej tożsamości. Kontekst chwili (pora dnia, rodzaj impulsu) masz poniżej. Opieraj się na tym, co wiesz o userze z pamięci. Jedna krótka wiadomość albo dokładnie [SILENT]."

say()  { printf '\n\033[1m%s\033[0m\n' "$*"; }
ask()  { local q="$1" def="${2:-}" a; read -r -p "$q${def:+ [$def]}: " a; echo "${a:-$def}"; }
asks() { local a; read -r -s -p "$1: " a; echo >&2; echo "$a"; }
yes()  { local a; read -r -p "$1 [T/n]: " a; [[ -z "$a" || "$a" =~ ^[TtYy] ]]; }

# --- 1. Hermes ----------------------------------------------------------------
if ! command -v hermes >/dev/null 2>&1; then
  say "Nie widzę Hermesa. Zainstaluj go najpierw (oficjalny instalator):"
  echo "  curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash -s -- --no-skills"
  exit 1
fi
# Bez `| head`: zamknięty potok wywala Hermesa (BrokenPipeError) i przy pipefail
# zatrzymuje skrypt. Najpierw bierzemy całe wyjście, potem pierwszą linię.
hv="$(hermes --version 2>&1 || true)"; echo "${hv%%$'\n'*}"

# --- 2. Profil ----------------------------------------------------------------
if hermes profile show "$PROFILE" >/dev/null 2>&1; then
  say "Profil '$PROFILE' istnieje — aktualizuję (pamięć, historia i .env zostają)."
  hermes profile update "$PROFILE" --force-config -y
else
  say "Instaluję profil '$PROFILE' z: $SOURCE"
  hermes profile install "$SOURCE" --name "$PROFILE" --alias -y
fi

ENV_FILE="$(hermes -p "$PROFILE" config env-path)"
touch "$ENV_FILE"; chmod 600 "$ENV_FILE"

get_env() { grep -E "^$1=" "$ENV_FILE" | tail -1 | cut -d= -f2- || true; }
set_env() {
  local key="$1" val="$2" tmp
  tmp="$(mktemp)"
  grep -vE "^${key}=" "$ENV_FILE" > "$tmp" || true
  printf '%s=%s\n' "$key" "$val" >> "$tmp"
  mv "$tmp" "$ENV_FILE"; chmod 600 "$ENV_FILE"
}

# --- 3. Telegram --------------------------------------------------------------
say "Telegram"
if [[ -z "$(get_env TELEGRAM_BOT_TOKEN)" ]]; then
  echo "Utwórz bota u @BotFather (/newbot) i wklej token."
  set_env TELEGRAM_BOT_TOKEN "$(asks 'Token bota')"
else
  echo "Token bota: ustawiony ✓"
fi
if [[ -z "$(get_env TELEGRAM_ALLOWED_USERS)" ]]; then
  echo "Twoje user ID podaje @userinfobot."
  uid="$(ask 'Twoje Telegram user ID')"
  set_env TELEGRAM_ALLOWED_USERS "$uid"
  set_env TELEGRAM_HOME_CHANNEL "$uid"
else
  echo "User ID: ustawione ✓"
fi

# --- 4. Model -----------------------------------------------------------------
say "Model (Claude)"
if [[ -z "$(get_env ANTHROPIC_API_KEY)" ]]; then
  cat <<'TXT'
  1) Klucz API Anthropic  — zalecane. Płacisz za tokeny; przy tym profilu
     to zwykle kilka dolarów miesięcznie. console.anthropic.com → API keys.
  2) Logowanie subskrypcją Claude (OAuth) — działa TYLKO na Claude Max
     i zużywa wyłącznie dokupione "extra usage", nie limit z planu.
     Na Claude Pro nie działa wcale.
TXT
  if [[ "$(ask 'Wybierz' 1)" == "2" ]]; then
    hermes -p "$PROFILE" auth add anthropic
  else
    set_env ANTHROPIC_API_KEY "$(asks 'ANTHROPIC_API_KEY')"
  fi
else
  echo "ANTHROPIC_API_KEY: ustawiony ✓"
fi

# --- 5. Proaktywny puls -------------------------------------------------------
say "Proaktywne wiadomości"
jobs_out="$(hermes -p "$PROFILE" cron list --all 2>/dev/null || true)"
if [[ "$jobs_out" == *"$JOB_NAME"* ]]; then
  echo "Zadanie '$JOB_NAME' już istnieje ✓"
elif yes "Czy Bibo ma się odzywać sam z siebie (max 3x dziennie, 8–22)?"; then
  hermes -p "$PROFILE" cron create "every 1h" "$PULSE_PROMPT" \
    --name "$JOB_NAME" --script bibo_pulse.py --deliver telegram \
    --failure-deliver local --continuity
  echo "Godziny, limit i strefę zmienisz w: $(dirname "$ENV_FILE")/local/bibo_pulse.json"
fi

# --- 6. Gateway ---------------------------------------------------------------
say "Uruchomienie"
if yes "Zainstalować Bibo jako usługę w tle (startuje sam po restarcie)?"; then
  hermes -p "$PROFILE" gateway install && hermes -p "$PROFILE" gateway start \
    || echo "Nie udało się jako usługa — uruchom ręcznie: hermes -p $PROFILE gateway run"
else
  echo "Uruchom ręcznie: hermes -p $PROFILE gateway run"
fi

say "Gotowe 🫧"
cat <<TXT
  • Napisz do swojego bota na Telegramie — Bibo sam Cię pozna.
  • Test w terminalu:      $PROFILE chat
  • Koszt promptu:         hermes -p $PROFILE prompt-size --platform telegram
  • Zużycie:               hermes -p $PROFILE insights
  • Panel konfiguracji:    hermes dashboard
      (na serwerze: ssh -L 9119:127.0.0.1:9119 <serwer>, potem
       'hermes dashboard --no-open' i otwórz http://127.0.0.1:9119)
TXT
