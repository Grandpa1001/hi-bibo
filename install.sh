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
# Ścieżki liczymy sami, bez `hermes -p bibo ...`: Hermes przy starcie czyta
# .env profilu i wywala się, jeśli ten plik jest nieczytelny (patrz fix_owner).
HERMES_ROOT="${HERMES_HOME:-$HOME/.hermes}"
PROFILE_DIR="$HERMES_ROOT/profiles/$PROFILE"
TOMBSTONE="$HERMES_ROOT/profiles/.deleted/$PROFILE"
ENV_FILE="$PROFILE_DIR/.env"

# Po `hermes profile delete` zostaje znacznik profiles/.deleted/<nazwa>.
# `profile install` go nie czyści i odmawia zapisu ("Named profile home does
# not exist"); czyści go tylko `profile create`. Resztki nieudanej instalacji
# odsuwamy na bok (nic nie kasujemy), tworzymy pusty profil i instalujemy
# paczkę na nim.
if [[ -e "$TOMBSTONE" ]]; then
  say "Wykryto ślad po usuniętym profilu '$PROFILE' — przygotowuję czysty profil."
  if [[ -e "$PROFILE_DIR" ]]; then
    aside="$PROFILE_DIR.nieudana-$(date +%Y%m%d-%H%M%S)"
    mv "$PROFILE_DIR" "$aside"
    echo "Resztki poprzedniej próby przeniesione do: $aside"
  fi
  hermes profile create "$PROFILE" --no-skills
fi

if grep -qs '^source:' "$PROFILE_DIR/distribution.yaml"; then
  say "Profil '$PROFILE' istnieje — aktualizuję (pamięć, historia i .env zostają)."
  hermes profile update "$PROFILE" --force-config -y
else
  # Nowy profil, pusty profil z `profile create` albo resztki nieudanej instalacji.
  say "Instaluję profil '$PROFILE' z: $SOURCE"
  force=(); [[ -e "$PROFILE_DIR" ]] && force=(--force)
  hermes profile install "$SOURCE" --name "$PROFILE" --alias -y ${force[@]+"${force[@]}"}
fi

# W obrazie Docker Hermesa `hermes` uruchomiony jako root przełącza się na
# użytkownika `hermes` (UID 10000). Plik, który ten skrypt zapisze jako root,
# byłby dla Hermesa nieczytelny (PermissionError). Oddajemy go właścicielowi
# katalogu profilu — ZANIM jakiekolwiek `hermes -p bibo` go przeczyta.
fix_owner() {
  [[ "$(id -u)" == 0 ]] || return 0
  local owner
  owner="$(stat -c '%u:%g' "$PROFILE_DIR" 2>/dev/null || stat -f '%u:%g' "$PROFILE_DIR")"
  chown "$owner" "$1"
}

touch "$ENV_FILE"; chmod 600 "$ENV_FILE"; fix_owner "$ENV_FILE"

get_env() { grep -E "^$1=" "$ENV_FILE" | tail -1 | cut -d= -f2- || true; }
set_env() {
  local key="$1" val="$2" tmp
  tmp="$(mktemp)"
  grep -vE "^${key}=" "$ENV_FILE" > "$tmp" || true
  printf '%s=%s\n' "$key" "$val" >> "$tmp"
  mv "$tmp" "$ENV_FILE"; chmod 600 "$ENV_FILE"; fix_owner "$ENV_FILE"
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
auth_out="$(hermes -p "$PROFILE" auth list 2>/dev/null || true)"
if [[ -z "$(get_env ANTHROPIC_API_KEY)" && "$auth_out" == *"anthropic ("* ]]; then
  echo "Konto Anthropic w profilu: zalogowane ✓ (zmiana: hermes -p $PROFILE model)"
elif [[ -z "$(get_env ANTHROPIC_API_KEY)" ]]; then
  cat <<'TXT'
  1) Klucz API Anthropic — płacisz za tokeny (console.anthropic.com → API keys).
     Przy tym profilu zwykle kilka dolarów miesięcznie; ustaw tam limit wydatków.
  2) Logowanie kontem Claude (OAuth) — ten sam kreator co /login i `hermes model`:
     logujesz się i wybierasz model. Uwaga na rozliczenie (dokumentacja Hermesa):
     wymaga Claude Max i zużywa TYLKO dokupione "extra usage", nie limit
     z planu. Logowanie z innego profilu się nie przenosi — trzeba je
     zrobić raz dla profilu bibo.
TXT
  if [[ "$(ask 'Wybierz' 1)" == "2" ]]; then
    echo "W kreatorze wybierz Anthropic → logowanie kontem, potem model"
    echo "(polecany claude-sonnet-5 albo tańszy claude-haiku-4-5)."
    hermes -p "$PROFILE" model
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
if yes "Uruchomić Bibo w tle (sam wstaje po restarcie)?"; then
  # W kontenerze Docker Hermesa `gateway start` rejestruje usługę s6 (przeżywa
  # restart kontenera). Na zwykłym serwerze start bez install się nie uda —
  # wtedy instalujemy usługę systemd/launchd i startujemy.
  hermes -p "$PROFILE" gateway start \
    || { hermes -p "$PROFILE" gateway install && hermes -p "$PROFILE" gateway start; } \
    || echo "Nie udało się w tle — uruchom ręcznie: hermes -p $PROFILE gateway run"
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
