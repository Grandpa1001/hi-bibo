#!/usr/bin/env python3
"""Hi-Bibo breath — context-only pre-run script for the bibo-breath cron.

Wypisuje na stdout kontekst potrzebny agentowi:
- czas, slot decyzji (deterministyczny)
- partner (imię, język, cel)
- stan brain.json

Skrypt NIE woła Anthropic API.
"""

import json
import os
import sys
from datetime import datetime

BIBO_DIR = os.environ.get("BIBO_DIR", "/opt/data/hi-bibo")
BRAIN_PATH = os.path.join(BIBO_DIR, "brain.json")


def main() -> None:
    try:
        with open(BRAIN_PATH, "r", encoding="utf-8") as f:
            brain = json.load(f)
    except (OSError, ValueError) as exc:
        print(f"ERROR: cannot load brain.json: {exc}", file=sys.stderr)
        sys.exit(1)

    now = datetime.now()
    partner = brain.get("partner") or {}
    name = partner.get("name") or "Bibo"
    language = partner.get("language") or "pl"
    goal = partner.get("goal") or ""

    print("## Aktualny czas")
    print(f"Data: {now.strftime('%Y-%m-%d')} ({now.strftime('%A')})")
    print(f"Godzina: {now.strftime('%H:%M')}")
    print(f"Oddech nr: {brain.get('breath_count', 0) + 1}")
    print()

    print("## Partner")
    print(f"Imię: {name}")
    print(f"Język: {language}")
    print(f"Cel: {goal or '—'}")
    print()

    decision = None
    try:
        scripts = os.path.join(BIBO_DIR, "scripts")
        if scripts not in sys.path:
            sys.path.insert(0, scripts)
        from decision import compute_slot, write_decision

        decision = compute_slot(brain)
        write_decision(decision)
        print("## Slot decyzji (kod — nie głosuj)")
        print(f"slot: {decision['slot']}")
        print(f"powód: {decision['reason']}")
        print(f"limit dnia: {decision['cap']}  |  wysłane dziś: {decision['spoken_today']}")
        print("MUST_WRITE → napisz. SILENT → dokładnie [SILENT]. MAY_WRITE → tylko gdy masz wniosek z dowodem.")
        print()
    except Exception as exc:
        print(f"WARN: decision slot failed: {exc}", file=sys.stderr)

    print("## Stan brain.json")
    print("```json")
    print(json.dumps(brain, indent=2, ensure_ascii=False))
    print("```")

    try:
        from analytics import emit_breath

        extra = {"decision": (decision or {}).get("slot")} if decision else None
        emit_breath(brain, extra=extra)
    except Exception as exc:
        print(f"WARN: analytics emit failed: {exc}", file=sys.stderr)


if __name__ == "__main__":
    main()
