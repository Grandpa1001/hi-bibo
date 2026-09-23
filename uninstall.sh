#!/usr/bin/env bash
# Bibo — sprzątanie. Zatrzymuje Bibo i usuwa profil `bibo` razem z jego
# cronem, pamięcią, historią i .env. Inne profile Hermesa zostają nietknięte.
#
#   ./uninstall.sh        # pyta o potwierdzenie, proponuje kopię pamięci
#   ./uninstall.sh -y     # bez pytań, z kopią pamięci
#
# Potem można od zera: ./install.sh "$PWD"
set -euo pipefail

PROFILE="bibo"
PROFILE_DIR="${HERMES_HOME:-$HOME/.hermes}/profiles/$PROFILE"
AUTO="${1:-}"

say() { printf '\n\033[1m%s\033[0m\n' "$*"; }
yes() { [[ "$AUTO" == "-y" ]] && return 0; local a; read -r -p "$1 [T/n]: " a; [[ -z "$a" || "$a" =~ ^[TtYy] ]]; }

if [[ ! -d "$PROFILE_DIR" ]]; then
  echo "Brak profilu '$PROFILE' ($PROFILE_DIR) — nie ma czego sprzątać."
  exit 0
fi

say "Usuwam profil '$PROFILE' z: $PROFILE_DIR"
yes "Na pewno? Zniknie cron, historia rozmów, pamięć i .env tego profilu" || exit 1

# Pliki zapisane przez root (np. przez starą wersję install.sh) blokują
# Hermesa w Dockerze — oddajemy cały profil właścicielowi katalogu profili.
if [[ "$(id -u)" == 0 ]]; then
  owner="$(stat -c '%u:%g' "$(dirname "$PROFILE_DIR")" 2>/dev/null || stat -f '%u:%g' "$(dirname "$PROFILE_DIR")")"
  chown -R "$owner" "$PROFILE_DIR"
fi

if [[ -d "$PROFILE_DIR/memories" ]] && yes "Zrobić kopię tego, co Bibo o Tobie wie (memories/)?"; then
  backup="$HOME/bibo-pamiec-$(date +%Y%m%d-%H%M%S)"
  cp -r "$PROFILE_DIR/memories" "$backup"
  echo "Kopia: $backup  (po reinstalacji wrzuć pliki do $PROFILE_DIR/memories/)"
fi

say "Zatrzymuję Bibo"
hermes -p "$PROFILE" gateway stop 2>/dev/null || echo "(gateway nie działał)"

say "Usuwam profil"
# Delete potrafi zakończyć się błędem "identity settlement is still pending"
# mimo usunięcia katalogu — wtedy dokańczamy purge-identity.
hermes profile delete "$PROFILE" -y || true
hermes profile purge-identity "$PROFILE" >/dev/null 2>&1 || true
if [[ -d "$PROFILE_DIR" ]]; then
  echo "Katalog profilu nadal istnieje: $PROFILE_DIR — sprawdź komunikaty wyżej."
  exit 1
fi

say "Posprzątane ✓"
echo "Instalacja od zera: ./install.sh \"\$PWD\""
