#!/usr/bin/env bash
# Bibo — wyłączenie. Cofa to, co zrobił ./install.sh, ale NIE kasuje
# Twoich danych: pamięć (memories/), historia rozmów, logowanie i tokeny zostają.
#
#   ./uninstall.sh
#
# Co robi:
#   - usuwa zadanie cron `bibo-pulse` i skrypt scripts/bibo_pulse.py,
#   - przywraca poprzedni SOUL.md z kopii (jeśli była), inaczej usuwa SOUL.md
#     (Hermes wraca do swojej domyślnej osobowości),
#   - restartuje gateway.
# Ustawienia z config.yaml (lekki prompt, kompresja) zostają — są bezpieczne.
set -euo pipefail

HOME_DIR="${HERMES_HOME:-$HOME/.hermes}"
say() { printf '\n\033[1m%s\033[0m\n' "$*"; }
read -r -p "Wyłączyć Bibo na tym Hermesie? Pamięć i historia zostaną. [T/n]: " a
[[ -z "$a" || "$a" =~ ^[TtYy] ]] || exit 1

say "Zadanie cron"
hermes cron remove bibo-pulse 2>/dev/null && echo "bibo-pulse usunięte ✓" || echo "(nie było)"
rm -f "$HOME_DIR/scripts/bibo_pulse.py"

say "Tożsamość"
last="$(ls -t "$HOME_DIR"/backups/SOUL-*.md 2>/dev/null | head -1 || true)"
if [[ -n "$last" ]]; then
  cp "$last" "$HOME_DIR/SOUL.md"; echo "Przywrócono SOUL.md z $last"
else
  rm -f "$HOME_DIR/SOUL.md"; echo "Usunięto SOUL.md (Hermes użyje domyślnej osobowości)"
fi

say "Restart gatewaya"
hermes gateway restart || echo "Zrestartuj ręcznie: hermes gateway restart"

say "Bibo wyłączony ✓"
echo "Pamięć o Tobie: $HOME_DIR/memories/  — ponowna instalacja: ./install.sh"
