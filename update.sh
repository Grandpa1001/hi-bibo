#!/usr/bin/env bash
# Bibo — aktualizacja do najnowszej wersji z GitHuba, bez pytań.
#
#   hermes bibo update              (komenda z wtyczki bibo-cli)
#   ./update.sh                     (z katalogu repo)
#   curl -fsSL https://raw.githubusercontent.com/Grandpa1001/hi-bibo/main/update.sh | bash
#
# Nie potrzebuje gita. Podmienia katalog repo na świeżą paczkę `main`, a potem
# wgrywa pliki Bibo do katalogu Hermesa: SOUL.md, scripts/, wtyczki i front Mini App.
# NIE rusza: .env, config.yaml, pamięci, historii, zadań cron, logowania.
# Pierwsza instalacja i zmiana ustawień: ./install.sh
set -euo pipefail

GALAZ="${BIBO_GALAZ:-main}"
PACZKA="${BIBO_PACZKA:-https://github.com/Grandpa1001/hi-bibo/archive/refs/heads/$GALAZ.tar.gz}"
REPO="${BIBO_REPO:-$HOME/hi-bibo}"
H="${HERMES_HOME:-$HOME/.hermes}"

say() { printf '\n\033[1m%s\033[0m\n' "$*"; }

# --- Etap 1: pobranie świeżej paczki i przekazanie sterowania jej skryptowi ----
if [[ "${1:-}" != "--install" ]]; then
  say "Pobieram najnowszą wersję ($GALAZ)"
  tmp="$(mktemp -d)"
  trap 'rm -rf "$tmp"' EXIT
  curl -fsSL "$PACZKA" | tar xz -C "$tmp"
  nowy="$(find "$tmp" -mindepth 1 -maxdepth 1 -type d | head -1)"
  [[ -f "$nowy/update.sh" ]] || { echo "Paczka nie wygląda na repo Bibo — przerywam."; exit 1; }
  rm -rf "$REPO.nowe" && mv "$nowy" "$REPO.nowe"
  rm -rf "$REPO" && mv "$REPO.nowe" "$REPO"
  echo "Repo: $REPO"
  exec bash "$REPO/update.sh" --install
fi

# --- Etap 2: wgranie (uruchamiane już z nowej wersji) --------------------------
cd "$REPO"
command -v hermes >/dev/null || { echo "Nie widzę Hermesa (hermes)."; exit 1; }
[[ -d "$H" ]] || { echo "Brak katalogu Hermesa: $H — najpierw ./install.sh"; exit 1; }
OWNER="$(stat -c '%u:%g' "$H" 2>/dev/null || stat -f '%u:%g' "$H")"
fix_owner() { [[ "$(id -u)" == 0 ]] && chown -R "$OWNER" "$@" || true; }

say "Wgrywam Bibo do $H"
if [[ "$(head -1 "$H/SOUL.md" 2>/dev/null)" == "# Bibo" ]]; then
  cp SOUL.md "$H/SOUL.md"; fix_owner "$H/SOUL.md"; echo "SOUL.md ✓"
else
  echo "SOUL.md: pomijam (to nie jest profil Bibo — uruchom ./install.sh)"
fi
mkdir -p "$H/scripts" "$H/plugins"
cp scripts/*.py "$H/scripts/"; fix_owner "$H/scripts"; echo "scripts/ ✓"

wgraj_wtyczke() {  # nazwa [włącz_jeśli_nowa]
  local n="$1" byla=0
  [[ -d "$H/plugins/$n" ]] && byla=1
  if [[ $byla == 0 && "${2:-}" != "tak" ]]; then return 0; fi
  rm -rf "$H/plugins/$n"
  cp -r "plugins/$n" "$H/plugins/$n"
  if [[ "$n" == "bibo-tryby" && -d miniapp/dist ]]; then
    cp -r miniapp/dist "$H/plugins/$n/static"
  fi
  fix_owner "$H/plugins/$n"
  hermes plugins enable "$n" --no-allow-tool-override >/dev/null 2>&1 || true
  echo "wtyczka $n $(grep -m1 '^version' "plugins/$n/plugin.yaml" | cut -d'"' -f2) ✓"
}
wgraj_wtyczke bibo-podpis tak
wgraj_wtyczke bibo-cli tak
wgraj_wtyczke bibo-tryby          # tylko jeśli tryby są już zainstalowane

if [[ -d "$H/plugins/bibo-tryby" && ! -x "$H/bin/cloudflared" ]] && ! command -v cloudflared >/dev/null; then
  A="$(uname -m | sed 's/x86_64/amd64/;s/aarch64/arm64/')"
  mkdir -p "$H/bin"
  curl -fsSL -o "$H/bin/cloudflared" "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-$A"
  chmod +x "$H/bin/cloudflared"; fix_owner "$H/bin"; echo "cloudflared ✓"
fi

say "Restart Bibo"
if hermes gateway restart; then
  echo "Gateway zrestartowany ✓"
else
  hermes gateway start || echo "Uruchom ręcznie: hermes gateway start"
fi

say "Gotowe 🫧"
echo "  Stan: ./doctor.sh   ·   Tryby w Telegramie: przycisk 🎲 Tryby (po ok. 10 s)"
