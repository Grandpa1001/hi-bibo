#!/usr/bin/env bash
# Bibo — aktualizacja do najnowszej wersji z GitHuba, bez pytań.
#
#   hermes bibo update [--force]    (komenda z wtyczki bibo-cli)
#   ./update.sh [--force]           (z katalogu repo)
#   curl -fsSL https://raw.githubusercontent.com/Grandpa1001/hi-bibo/main/update.sh | bash
#
# Nie potrzebuje gita. Sprawdza numer najnowszego commita na GitHubie — jeśli to
# ta sama wersja, co wgrana, kończy bez pobierania. W przeciwnym razie pobiera
# paczkę, wgrywa z niej pliki Bibo do katalogu Hermesa (SOUL.md, scripts/, wtyczki,
# front Mini App) i restartuje Bibo. Kopię repo (~/hi-bibo) odświeża, jeśli może.
# NIE rusza: .env, config.yaml, pamięci, historii, zadań cron, logowania.
# Pierwsza instalacja i zmiana ustawień: ./install.sh
set -euo pipefail

GALAZ="${BIBO_GALAZ:-main}"
GH="Grandpa1001/hi-bibo"
REPO="${BIBO_REPO:-$HOME/hi-bibo}"
H="${HERMES_HOME:-$HOME/.hermes}"
WERSJA_PLIK="$H/local/bibo_wersja"

say() { printf '\n\033[1m%s\033[0m\n' "$*"; }
[[ -d "$H" ]] || { echo "Brak katalogu Hermesa: $H — najpierw ./install.sh"; exit 1; }
# W obrazie Docker `hermes` działa jako użytkownik `hermes`; to, co zapisze root,
# oddajemy właścicielowi katalogu Hermesa (inaczej kolejna aktualizacja nie ma uprawnień).
OWNER="$(stat -c '%u:%g' "$H" 2>/dev/null || stat -f '%u:%g' "$H")"
fix_owner() { [[ "$(id -u)" == 0 ]] && chown -R "$OWNER" "$@" || true; }

# --- Etap 1: czy jest coś nowego? pobranie paczki --------------------------------
if [[ "${1:-}" != "--install" ]]; then
  WYMUS=0; [[ "${1:-}" == "--force" ]] && WYMUS=1
  sha="$(curl -fsSL -H 'Accept: application/vnd.github.sha' \
          "https://api.github.com/repos/$GH/commits/$GALAZ" 2>/dev/null || true)"
  [[ "$sha" =~ ^[0-9a-f]{40}$ ]] || sha=""
  obecna="$(cat "$WERSJA_PLIK" 2>/dev/null || true)"
  if [[ -n "$sha" && "$sha" == "$obecna" && $WYMUS == 0 && -z "${BIBO_PACZKA:-}" ]]; then
    say "Bibo jest aktualny (${sha:0:7}) — nic nie pobieram."
    echo "Wymuszenie ponownego wgrania: hermes bibo update --force"
    exit 0
  fi

  say "Pobieram nową wersję (${sha:0:7}${sha:+ · }$GALAZ)"
  paczka="${BIBO_PACZKA:-https://github.com/$GH/archive/${sha:-refs/heads/$GALAZ}.tar.gz}"
  tmp="$(mktemp -d)"
  curl -fsSL "$paczka" | tar xz -C "$tmp"
  zrodlo="$(find "$tmp" -mindepth 1 -maxdepth 1 -type d | head -1)"
  [[ -f "$zrodlo/update.sh" ]] || { rm -rf "$tmp"; echo "Paczka nie wygląda na repo Bibo — przerywam."; exit 1; }
  # Dalej prowadzi skrypt z NOWEJ wersji (etap 2 sprząta katalog tymczasowy).
  BIBO_SHA="$sha" BIBO_TMP="$tmp" exec bash "$zrodlo/update.sh" --install "$zrodlo"
fi

# --- Etap 2: wgranie z pobranej paczki (uruchamiane już z nowej wersji) ----------
ZRODLO="${2:-$REPO}"
[[ -n "${BIBO_TMP:-}" ]] && trap 'rm -rf "$BIBO_TMP"' EXIT
cd "$ZRODLO"
command -v hermes >/dev/null || { echo "Nie widzę Hermesa (hermes)."; exit 1; }

say "Wgrywam Bibo do $H"
if [[ "$(head -1 "$H/SOUL.md" 2>/dev/null)" == "# Bibo" ]]; then
  cp SOUL.md "$H/SOUL.md"; fix_owner "$H/SOUL.md"; echo "SOUL.md ✓"
else
  echo "SOUL.md: pomijam (to nie jest profil Bibo — uruchom ./install.sh)"
fi
mkdir -p "$H/scripts" "$H/plugins" "$H/local"
cp scripts/*.py "$H/scripts/"; fix_owner "$H/scripts"; echo "scripts/ ✓"

wgraj_wtyczke() {  # nazwa [tak = zainstaluj także, gdy jej jeszcze nie ma]
  local n="$1"
  [[ -d "$H/plugins/$n" || "${2:-}" == "tak" ]] || return 0
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

# Kopia repo (install.sh, doctor.sh...) — odświeżana tylko, gdy mamy do niej prawo.
if [[ "$ZRODLO" != "$REPO" ]]; then
  obcy=""
  [[ -e "$REPO" && "$(id -u)" != 0 ]] && obcy="$(find "$REPO" ! -user "$(id -u)" -print -quit 2>/dev/null || true)"
  # Zamiana bez ryzyka połowicznego usunięcia: nowa kopia obok → podmiana → sprzątanie.
  nowe="$REPO.nowe.$$" stare="$REPO.stare.$$"
  if [[ -z "$obcy" ]] && cp -R "$ZRODLO" "$nowe" 2>/dev/null \
     && { [[ ! -e "$REPO" ]] || mv "$REPO" "$stare" 2>/dev/null; } \
     && { mv "$nowe" "$REPO" 2>/dev/null || { [[ -e "$stare" ]] && mv "$stare" "$REPO"; false; }; }; then
    rm -rf "$stare" 2>/dev/null || true
    fix_owner "$REPO"; echo "repo $REPO ✓"
  else
    rm -rf "$nowe" 2>/dev/null || true
    echo "repo $REPO: pomijam (brak uprawnień — Bibo i tak jest zaktualizowany)."
    echo "  Jednorazowo jako root: chown -R $OWNER $REPO"
  fi
fi

[[ -n "${BIBO_SHA:-}" ]] && { echo "$BIBO_SHA" > "$WERSJA_PLIK"; fix_owner "$WERSJA_PLIK"; }

say "Restart Bibo"
if hermes gateway restart; then
  echo "Gateway zrestartowany ✓"
else
  hermes gateway start || echo "Uruchom ręcznie: hermes gateway start"
fi

say "Gotowe 🫧 ${BIBO_SHA:+(wersja ${BIBO_SHA:0:7})}"
echo "  Tryby w Telegramie: przycisk 🎲 Tryby (po ok. 10 s)"
