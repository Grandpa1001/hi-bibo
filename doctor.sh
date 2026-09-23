#!/usr/bin/env bash
# Bibo — diagnostyka. Zbiera stan profilu i gatewaya do jednego raportu,
# który można wkleić do zgłoszenia. NIE wypisuje sekretów (tylko: ustawione / brak).
#
#   ./doctor.sh
set -uo pipefail

PROFILE="bibo"
HERMES_ROOT="${HERMES_HOME:-$HOME/.hermes}"
PROFILE_DIR="$HERMES_ROOT/profiles/$PROFILE"

sec() { printf '\n===== %s =====\n' "$*"; }
run() { printf '$ %s\n' "$*"; out="$("$@" 2>&1)"; printf '%s\n' "$out"; }

sec "Hermes"
run hermes --version
echo "HERMES_HOME=$HERMES_ROOT  user=$(id -un) uid=$(id -u)"

sec "Profile"
run hermes profile list
ls -la "$PROFILE_DIR" 2>&1 | head -30
[[ -e "$HERMES_ROOT/profiles/.deleted/$PROFILE" ]] && echo "UWAGA: istnieje znacznik usunięcia profiles/.deleted/$PROFILE"

sec "Sekrety (.env) — tylko czy ustawione"
bot_ids=()
for f in "$HERMES_ROOT/.env" "$PROFILE_DIR/.env"; do
  echo "-- $f"
  if [[ -r "$f" ]]; then
    for k in TELEGRAM_BOT_TOKEN TELEGRAM_ALLOWED_USERS TELEGRAM_HOME_CHANNEL ANTHROPIC_API_KEY; do
      v="$(grep -E "^$k=" "$f" | tail -1 | cut -d= -f2-)"
      if [[ -n "$v" ]]; then echo "   $k: ustawione"; else echo "   $k: brak"; fi
    done
    tok="$(grep -E '^TELEGRAM_BOT_TOKEN=' "$f" | tail -1 | cut -d= -f2- | cut -d: -f1)"
    [[ -n "$tok" ]] && { echo "   ID bota: $tok"; bot_ids+=("$tok"); }
  else
    echo "   (brak pliku albo brak dostępu)"
  fi
done
if [[ ${#bot_ids[@]} -eq 2 && "${bot_ids[0]}" == "${bot_ids[1]}" ]]; then
  echo "UWAGA: ten sam bot w profilu default i $PROFILE — Telegram pozwala na jeden gateway na bota."
fi

sec "Logowanie do modelu (profil $PROFILE)"
run hermes -p "$PROFILE" auth list
run hermes -p "$PROFILE" config get model

sec "Gateway"
run hermes gateway list
run hermes -p "$PROFILE" gateway status

sec "Cron"
run hermes -p "$PROFILE" cron list --all

sec "Ostatnie błędy gatewaya (profil $PROFILE)"
run hermes -p "$PROFILE" logs gateway -n 40
run hermes -p "$PROFILE" logs errors -n 20

echo
echo "Skopiuj całość powyżej i wklej. Sekrety nie są wypisywane."
