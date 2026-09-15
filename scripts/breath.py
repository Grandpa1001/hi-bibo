#!/usr/bin/env python3
"""Hi-Bibo breath — context-only pre-run script for the bibo-breath cron.

Wypisuje na stdout kontekst potrzebny agentowi Bibo w oddechu:
- aktualny czas / numer oddechu
- stan brain.json

Skrypt NIE woła Anthropic API. To robi hermes-agent uruchamiany przez
cron job z ``no_agent: false``. Agent dziedziczy uwierzytelnianie gatewaya.
"""

import json
import os
import sys
from datetime import datetime

BIBO_DIR = "/opt/data/hi-bibo"
BRAIN_PATH = os.path.join(BIBO_DIR, "brain.json")


def main() -> None:
    try:
        with open(BRAIN_PATH, "r", encoding="utf-8") as f:
            brain = json.load(f)
    except (OSError, ValueError) as exc:
        print(f"ERROR: cannot load brain.json: {exc}", file=sys.stderr)
        sys.exit(1)

    now = datetime.now()
    print("## Aktualny czas")
    print(f"Data: {now.strftime('%Y-%m-%d')} ({now.strftime('%A')})")
    print(f"Godzina: {now.strftime('%H:%M')}")
    print(f"Oddech nr: {brain.get('breath_count', 0) + 1}")
    print()

    print("## Stan brain.json")
    print("```json")
    print(json.dumps(brain, indent=2, ensure_ascii=False))
    print("```")


if __name__ == "__main__":
    main()
