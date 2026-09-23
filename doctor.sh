#!/usr/bin/env bash
# Bibo — diagnostyka. Zbiera stan profilu i gatewaya do jednego raportu,
# który można wkleić do zgłoszenia. NIE wypisuje sekretów (tylko: ustawione / brak).
#
#   ./doctor.sh
set -uo pipefail

PROFILE="bibo"
HERMES_ROOT="${HERMES_HOME:-$HOME/.hermes}"
PROFILE_DIR="$HERMES_ROOT"   # Bibo = główny profil Hermesa

sec() { printf '\n===== %s =====\n' "$*"; }
run() { printf '$ %s\n' "$*"; out="$("$@" 2>&1)"; printf '%s\n' "$out"; }

sec "Hermes"
run hermes --version
echo "HERMES_HOME=$HERMES_ROOT  user=$(id -un) uid=$(id -u)"

sec "Profile"
run hermes profile list
[[ -d "$HERMES_ROOT/profiles/bibo" ]] && echo "UWAGA: istnieje stary profil profiles/bibo (poprzednia wersja instalatora)"
echo "SOUL.md: $(head -1 "$HERMES_ROOT/SOUL.md" 2>/dev/null)"
ls "$HERMES_ROOT/scripts" 2>&1

sec "Sekrety (.env) — tylko czy ustawione"
bot_ids=()
for f in "$HERMES_ROOT/.env" "$HERMES_ROOT/profiles/bibo/.env"; do
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
  echo "UWAGA: ten sam bot w profilu głównym i starym profilu bibo — usuń stary (./install.sh zaproponuje)."
fi

sec "Logowanie do modelu"
run hermes auth list
run hermes config get model

sec "Gateway"
run hermes gateway list
run hermes gateway status
run hermes prompt-size --platform telegram

sec "Cron"
run hermes cron list --all

sec "Ostatnie logi gatewaya"
run hermes logs gateway -n 40
run hermes logs errors -n 20

echo
echo "Skopiuj całość powyżej i wklej. Sekrety nie są wypisywane."
