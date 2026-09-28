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

sec "Tryby (Mini App)"
if hermes plugins list 2>/dev/null | grep -qE '^bibo-tryby([[:space:]]|$)'; then
  echo "wtyczka: enabled"
else
  echo "wtyczka: wyłączona / brak"
fi
if [[ -x "$HERMES_ROOT/bin/cloudflared" ]]; then
  echo "cloudflared: $HERMES_ROOT/bin/cloudflared ✓"
elif command -v cloudflared >/dev/null 2>&1; then
  echo "cloudflared: $(command -v cloudflared) ✓"
else
  echo "cloudflared: brak"
fi
if [[ -f "$HERMES_ROOT/plugins/bibo-tryby/static/index.html" ]]; then
  echo "front (static/index.html): ✓"
else
  echo "front: brak (front Mini App nie został skopiowany — uruchom hermes bibo update)"
fi
port="$(python3 -c "import json;print(json.load(open('$HERMES_ROOT/local/bibo_tryby/ustawienia.json')).get('port',8787))" 2>/dev/null || echo 8787)"
if code="$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$port/health" 2>/dev/null)"; then
  echo "/health (127.0.0.1:$port): $code"
else
  echo "/health (127.0.0.1:$port): brak odpowiedzi"
fi
tun="$(python3 -c "import json;print(json.load(open('$HERMES_ROOT/local/bibo_tryby/stan_tunelu.json'))['url'])" 2>/dev/null || true)"
if [[ -n "$tun" ]]; then
  echo "tunel: $tun"
  if code="$(curl -s -o /dev/null -w '%{http_code}' "$tun/health" 2>/dev/null)"; then
    echo "/health przez tunel: $code"
  fi
else
  echo "tunel: brak zapisu (stan_tunelu.json)"
fi
if pgrep -f "cloudflared tunnel" >/dev/null 2>&1; then
  echo "proces cloudflared: żyje"
else
  echo "proces cloudflared: nie widać"
fi

sec "Ostatnie logi gatewaya"
run hermes logs gateway -n 40
run hermes logs errors -n 20

echo
echo "Skopiuj całość powyżej i wklej. Sekrety nie są wypisywane."
