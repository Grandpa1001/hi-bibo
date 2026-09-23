#!/usr/bin/env bash
# Bibo — raport: co wie, ile kosztuje (na wiadomość / dzień / zaczepkę),
# czego się nauczył, jaki ma plan.
#
#   ./raport.sh              # 0 tokenów, tylko lokalne dane
#   ./raport.sh --dni 30     # dłuższe okno zużycia dziennego
#   ./raport.sh --opinia     # + opinia Bibo o Tobie i plan (1 wywołanie modelu)
set -euo pipefail
HOME_DIR="${HERMES_HOME:-$HOME/.hermes}"
exec python3 "$HOME_DIR/scripts/bibo_raport.py" "$@"
