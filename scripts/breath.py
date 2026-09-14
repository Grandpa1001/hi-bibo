#!/usr/bin/env python3
"""Hi-Bibo breath — context-only pre-run script for a hermes-agent cron.

Wypisuje na stdout kontekst potrzebny agentowi Bibo w danym oddechu:
- aktualny czas / numer oddechu
- stan brain.json
- bazę wiedzy (knowledge.md)

Skrypt NIE woła Anthropic API. To robi hermes-agent uruchamiany przez
cron job z ``no_agent: false``. Dzięki temu skrypt nie potrzebuje
własnego klucza API — agent dziedziczy uwierzytelnianie gatewaya, w
tym OAuth setup-tokens (sk-ant-oat*), które nie działają jako zwykły
x-api-key.

Jak jest osadzony w cronie: cron uruchamia hermes-agenta z prompt.md
Bibo, wypycha stdout tego skryptu jako "Script Output" w prompcie
agenta, i pozwala agentowi podjąć decyzję OBSERVE/THINK/MESSAGE/WAIT
oraz zaktualizować brain.json przez normalne narzędzia.
"""

import json
import os
import sys
from datetime import datetime

BIBO_DIR = "/opt/data/hi-bibo"
BRAIN_PATH = os.path.join(BIBO_DIR, "brain.json")
KNOWLEDGE_PATH = os.path.join(BIBO_DIR, "knowledge.md")


def main() -> None:
    try:
        with open(BRAIN_PATH, "r", encoding="utf-8") as f:
            brain = json.load(f)
    except (OSError, ValueError) as exc:
        print(f"ERROR: cannot load brain.json: {exc}", file=sys.stderr)
        sys.exit(1)

    try:
        with open(KNOWLEDGE_PATH, "r", encoding="utf-8") as f:
            knowledge = f.read()
    except OSError as exc:
        print(f"ERROR: cannot load knowledge.md: {exc}", file=sys.stderr)
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
    print()

    print("## Baza wiedzy")
    print(knowledge)


if __name__ == "__main__":
    main()
