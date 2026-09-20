#!/usr/bin/env python3
"""Hi-Bibo breath — context-only pre-run script for the bibo-breath cron.

Wypisuje na stdout kontekst potrzebny agentowi:
- czas, slot decyzji (deterministyczny)
- godziny od ostatniego kontaktu usera
- partner (imię, język, cel)
- stan brain.json (po decay i inkrementacji oddechu)

Skrypt NIE woła Anthropic API. Aktualizuje brain.json nawet przy SILENT,
żeby mózg nie zamarzał w pętli śmierci z T006.
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

    # Auto-migrate brain schema if needed (T011)
    try:
        from migrate_brain import migrate_if_needed
        migrate_result = migrate_if_needed(BRAIN_PATH)
        if migrate_result.get("success") and not migrate_result.get("dry_run"):
            # Reload brain after migration
            with open(BRAIN_PATH, "r", encoding="utf-8") as f:
                brain = json.load(f)
            if migrate_result.get("applied"):
                print(
                    f"NOTICE: Brain migrated: {migrate_result.get('applied')}",
                    file=sys.stderr,
                )
        elif not migrate_result.get("success"):
            print(
                f"WARNING: Migration failed: {migrate_result.get('error')}",
                file=sys.stderr,
            )
    except Exception as exc:
        print(f"WARNING: migrate_brain import failed (skipping): {exc}", file=sys.stderr)

    now = datetime.now().astimezone()
    partner = brain.get("partner") or {}
    name = partner.get("name") or "Bibo"
    language = partner.get("language") or "pl"
    goal = partner.get("goal") or ""

    print("## Aktualny czas")
    print(f"Data: {now.strftime('%Y-%m-%d')} ({now.strftime('%A')})")
    print(f"Godzina: {now.strftime('%H:%M')}")
    print(f"Oddech nr: {int(brain.get('breath_count') or 0) + 1}")
    print()

    print("## Partner")
    print(f"Imię: {name}")
    print(f"Język: {language}")
    print(f"Cel: {goal or '—'}")
    print(f"Faza: {brain.get('phase') or 'adaptation'}")
    print()

    decision = None
    decay = None
    try:
        scripts = os.path.join(BIBO_DIR, "scripts")
        if scripts not in sys.path:
            sys.path.insert(0, scripts)
        from decision import compute_slot, maintain_brain, write_brain, write_decision

        decision = compute_slot(brain, now=now)
        write_decision(decision)
        updated = maintain_brain(brain, decision, now=now)
        decay = updated.pop("_decay", None)
        try:
            write_brain(updated, BRAIN_PATH)
            brain = updated
        except OSError as exc:
            print(f"WARN: cannot thaw brain.json: {exc}", file=sys.stderr)

        print("## Slot decyzji (kod — nie głosuj)")
        print(f"slot: {decision['slot']}")
        print(f"powód: {decision['reason']}")
        print(f"faza: {decision.get('phase')}  |  limit dnia: {decision['cap']}  |  wysłane dziś: {decision['spoken_today']}")
        print("MUST_WRITE → napisz. SILENT → dokładnie [SILENT]. MAY_WRITE → tylko gdy masz wniosek z dowodem.")
        print()

        hours = decision.get("hours_since_user")
        hours_bibo = decision.get("hours_since_bibo")
        print("## Kontakt")
        if hours is None:
            print("Ostatni inbound usera: brak (jeszcze nie pisał albo brak timestampu)")
        else:
            print(f"Ostatni inbound usera: {hours}h temu")
        if hours_bibo is None:
            print("Ostatni outbound Bibo: brak")
        else:
            print(f"Ostatni outbound Bibo: {hours_bibo}h temu")
        if decision.get("failure_24h"):
            print("NIEPOWODZENIE: user milczy >24h po kontakcie. Nie guilt-tripuj. Jeden spokojny sygnał życia, nie śledztwo.")
        print()

        if decay:
            print("## Decay zachowania_biezace")
            print(f"aktywne: {decay.get('active', 0)}  |  waga 0.5 (>48h): {decay.get('halved', 0)}  |  archiwum (>72h): {decay.get('archived', 0)}")
            print("Wpisów z waga 0.5 lub archiwum NIE traktuj jako aktualnego nastroju. Nie blokuj inicjatywy starym „zirytowany”.")
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
