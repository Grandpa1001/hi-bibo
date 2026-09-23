#!/usr/bin/env bash
# Bibo — instalator. Robi z Hermesa na tym serwerze Bibo.
#
#   ./install.sh
#
# Bibo zostaje GŁÓWNYM (domyślnym) profilem Hermesa — bez `-p bibo`.
# Dzięki temu wszystko, co ustawisz w panelu (`hermes dashboard`), przez
# `/login` albo `hermes model`, trafia prosto do Bibo, a jeden gateway
# Hermesa obsługuje jego Telegram.
#
# Najlepiej na osobnej instalacji Hermesa (np. osobny kontener) — Bibo
# odchudza profil domyślny: zostawia jedno narzędzie (pamięć) na Telegramie
# i usuwa wbudowane skille.
#
# Bezpieczny do ponownego uruchomienia (np. po `git pull`): nie rusza pamięci,
# historii, logowania ani tokenów; nie dubluje zadania cron.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
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
# Bez `| head`: zamknięty potok wywala Hermesa (BrokenPipeError) przy pipefail.
hv="$(hermes --version 2>&1 || true)"; echo "${hv%%$'\n'*}"

HOME_DIR="${HERMES_HOME:-$HOME/.hermes}"
ENV_FILE="$HOME_DIR/.env"
mkdir -p "$HOME_DIR/scripts" "$HOME_DIR/backups"
echo "Katalog Hermesa: $HOME_DIR"

# W obrazie Docker Hermesa `hermes` uruchomiony jako root przełącza się na
# użytkownika `hermes`. Wszystko, co ten skrypt zapisze jako root, oddajemy
# właścicielowi katalogu Hermesa — inaczej Hermes nie przeczyta (PermissionError).
OWNER="$(stat -c '%u:%g' "$HOME_DIR" 2>/dev/null || stat -f '%u:%g' "$HOME_DIR")"
fix_owner() { [[ "$(id -u)" == 0 ]] && chown -R "$OWNER" "$@" || true; }

# --- 2. Stary profil `bibo` (z wcześniejszych wersji instalatora) ---------------
OLD="$HOME_DIR/profiles/bibo"
if [[ -d "$OLD" ]]; then
  say "Znaleziono stary profil 'bibo' z poprzedniej wersji instalatora."
  echo "Ma ten sam token Telegrama — dwa miejsca z jednym botem się gryzą."
  if yes "Usunąć go (z kopią jego pamięci)?"; then
    fix_owner "$OLD"
    [[ -d "$OLD/memories" ]] && cp -r "$OLD/memories" "$HOME_DIR/backups/bibo-profil-pamiec-$(date +%Y%m%d-%H%M%S)"
    hermes profile delete bibo -y || true
    hermes profile purge-identity bibo >/dev/null 2>&1 || true
  fi
fi
rm -rf "$HOME_DIR"/profiles/bibo.nieudana-* 2>/dev/null || true

# --- 3. Tożsamość i skrypt pulsu -------------------------------------------------
say "Wgrywam Bibo"
# Kopia tylko nie-Bibowego SOUL.md (oryginał Hermesa) — uninstall.sh go przywraca.
if [[ -f "$HOME_DIR/SOUL.md" ]] && [[ "$(head -1 "$HOME_DIR/SOUL.md")" != "# Bibo" ]]; then
  b="$HOME_DIR/backups/SOUL-$(date +%Y%m%d-%H%M%S).md"
  cp "$HOME_DIR/SOUL.md" "$b"; echo "Poprzedni SOUL.md → $b"
fi
cp "$REPO/SOUL.md" "$HOME_DIR/SOUL.md"
cp "$REPO"/scripts/*.py "$HOME_DIR/scripts/"
cp "$REPO/.no-bundled-skills" "$HOME_DIR/.no-bundled-skills"
fix_owner "$HOME_DIR/SOUL.md" "$HOME_DIR/scripts" "$HOME_DIR/.no-bundled-skills" "$HOME_DIR/backups"
echo "SOUL.md, scripts/ (puls, raport) ✓"

# Podpis "bibo" dokleja wtyczka (hook transform_llm_output), nie model.
mkdir -p "$HOME_DIR/plugins"
rm -rf "$HOME_DIR/plugins/bibo-podpis"
cp -r "$REPO/plugins/bibo-podpis" "$HOME_DIR/plugins/bibo-podpis"
fix_owner "$HOME_DIR/plugins"
hermes plugins enable bibo-podpis --no-allow-tool-override >/dev/null 2>&1 \
  && echo "Wtyczka podpisu (bibo-podpis) ✓" \
  || echo "UWAGA: włącz wtyczkę ręcznie: hermes plugins enable bibo-podpis"

# Wbudowane skille Hermesa (~80) puchną w każdym zapytaniu. Usuwamy tylko
# niezmienione; znacznik .no-bundled-skills blokuje ich powrót przy update.
hermes skills opt-out --remove -y >/dev/null 2>&1 || true
echo "Wbudowane skille usunięte ✓"

# --- 4. Ustawienia (tylko nasze klucze; reszta config.yaml zostaje) ------------
# Uzasadnienie każdej wartości: config.yaml w repo i docs/REANALIZA.md.
say "Ustawienia (lekki prompt, pamięć, puls)"
settings=(
  "platform_toolsets.telegram=[memory]"
  "platform_toolsets.cron=[memory]"
  "memory.memory_enabled=true"
  "memory.user_profile_enabled=true"
  "memory.memory_char_limit=3000"
  "memory.user_char_limit=2500"
  "compression.enabled=true"
  "compression.threshold_tokens=16000"
  "compression.protect_last_n=12"
  "compression.idle_compact_after_seconds=3600"
  "prompt_caching.cache_ttl=1h"
  "auxiliary.compression.provider=anthropic"
  "auxiliary.compression.model=claude-haiku-4-5"
  "auxiliary.background_review.enabled=false"
  "curator.enabled=false"
  "display.memory_notifications=off"
  "cron.mirror_delivery=true"
  "cron.wrap_response=false"
  # Wiadomość w jednym kawałku — podpis doklejany na końcu musi trafić do wysłanej treści.
  "streaming.enabled=false"
)
for kv in "${settings[@]}"; do
  hermes config set "${kv%%=*}" "${kv#*=}" >/dev/null
done
echo "${#settings[@]} ustawień ✓"

# Niski poziom rozumowania — do rozmowy wystarczy, szybciej i taniej. Tylko gdy
# nieustawiony (nie nadpisujemy Twojego wyboru). --force: gateway czyta ten
# klucz, ale `config set` nie ma go na liście znanych i ostrzega bez potrzeby.
effort="$(hermes config get agent.reasoning_effort 2>/dev/null || true)"
if [[ -z "$effort" || "$effort" == "None" || "$effort" == "null" ]]; then
  hermes config set --force agent.reasoning_effort low >/dev/null 2>&1 || true
  effort="low"
fi
echo "Poziom rozumowania: $effort"

# --- 5. Telegram ---------------------------------------------------------------
touch "$ENV_FILE"; chmod 600 "$ENV_FILE"; fix_owner "$ENV_FILE"
get_env() { grep -E "^$1=" "$ENV_FILE" | tail -1 | cut -d= -f2- || true; }
set_env() {
  local key="$1" val="$2" tmp
  tmp="$(mktemp)"
  grep -vE "^${key}=" "$ENV_FILE" > "$tmp" || true
  printf '%s=%s\n' "$key" "$val" >> "$tmp"
  mv "$tmp" "$ENV_FILE"; chmod 600 "$ENV_FILE"; fix_owner "$ENV_FILE"
}

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

# --- 6. Model ----------------------------------------------------------------
say "Model (Claude)"
has_auth() {
  [[ -n "$(get_env ANTHROPIC_API_KEY)" ]] && return 0
  local out; out="$(hermes auth list 2>/dev/null || true)"
  [[ "$out" == *"anthropic ("* ]]
}
if has_auth; then
  echo "Logowanie Anthropic: jest ✓  (zmiana: hermes model)"
else
  cat <<'TXT'
  1) Logowanie kontem Claude — kreator `hermes model` (to samo co /login):
     logujesz się i wybierasz model. Wg dokumentacji Hermesa rozlicza się
     z dokupionego "extra usage" na Claude Max, nie z limitu planu.
  2) Klucz API Anthropic — płacisz za tokeny (console.anthropic.com).
TXT
  if [[ "$(ask 'Wybierz' 1)" == "2" ]]; then
    set_env ANTHROPIC_API_KEY "$(asks 'ANTHROPIC_API_KEY')"
  else
    echo "W kreatorze: Anthropic → logowanie kontem → model"
    echo "(polecany claude-sonnet-5, tańszy claude-haiku-4-5)."
    hermes model || true
  fi
  if ! has_auth; then
    say "UWAGA: logowanie się nie zapisało — Bibo nie będzie miał czym odpowiadać."
    echo "Spróbuj: hermes auth add anthropic --type oauth --no-browser"
    echo "(otwórz link na komputerze, zaloguj się, wklej kod) i uruchom ./install.sh ponownie."
  fi
fi
model_now="$(hermes config get model.default 2>/dev/null || true)"
if [[ -z "$model_now" || "$model_now" == "None" || "$model_now" == "null" ]]; then
  hermes config set model.provider anthropic >/dev/null
  hermes config set model.default claude-sonnet-5 >/dev/null
  model_now="claude-sonnet-5"
fi
echo "Model: $model_now"

# --- 7. Proaktywny puls -----------------------------------------------------------
say "Proaktywne wiadomości"
jobs_out="$(hermes cron list --all 2>/dev/null || true)"
if [[ "$jobs_out" == *"$JOB_NAME"* ]]; then
  echo "Zadanie '$JOB_NAME' już istnieje ✓"
elif yes "Czy Bibo ma się odzywać sam z siebie (max 3x dziennie, 8–22)?"; then
  hermes cron create "every 1h" "$PULSE_PROMPT" \
    --name "$JOB_NAME" --script bibo_pulse.py --deliver telegram \
    --failure-deliver local --continuity
  echo "Godziny, limit i strefę zmienisz w: $HOME_DIR/local/bibo_pulse.json"
fi

# Dzienne zdjęcie licznika zużycia — bez modelu (0 tokenów), nic nie wysyła.
# Z różnic między dniami ./raport.sh liczy zużycie na dzień.
if [[ "$jobs_out" == *"bibo-usage"* ]]; then
  echo "Zadanie 'bibo-usage' już istnieje ✓"
else
  hermes cron create "55 23 * * *" --name bibo-usage --no-agent \
    --script bibo_usage_snapshot.py --deliver local >/dev/null \
    && echo "Dzienny licznik zużycia (bibo-usage, 23:55, 0 tokenów) ✓"
fi

# --- 8. Gateway -----------------------------------------------------------------
say "Uruchamiam Bibo"
if hermes gateway restart; then
  echo "Gateway zrestartowany ✓"
else
  hermes gateway start \
    || { hermes gateway install && hermes gateway start; } \
    || echo "Nie udało się w tle — uruchom ręcznie: hermes gateway run"
fi

say "Gotowe 🫧"
cat <<TXT
  • Napisz do swojego bota na Telegramie — Bibo sam Cię pozna.
  • Stan:                 ./doctor.sh
  • Koszt promptu:        hermes prompt-size --platform telegram   (~13 KB)
  • Zużycie:              hermes insights
  • Panel konfiguracji:   hermes dashboard
      (na serwerze: ssh -L 9119:127.0.0.1:9119 <serwer>, potem
       'hermes dashboard --no-open' i otwórz http://127.0.0.1:9119)
TXT
