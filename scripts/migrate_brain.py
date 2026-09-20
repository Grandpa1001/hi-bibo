#!/usr/bin/env python3
"""Hi-Bibo brain.json migration framework (T011).

Handles schema version upgrades with backup and rollback support.

Usage:
    python3 scripts/migrate_brain.py /path/to/brain.json
    python3 scripts/migrate_brain.py /path/to/brain.json --dry-run
    python3 scripts/migrate_brain.py /path/to/brain.json --check-only
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from datetime import datetime
from typing import Any, Callable, Dict, Optional


CURRENT_SCHEMA_VERSION = "1.3"

# Migration chain: version -> (description, function)
MIGRATIONS: Dict[str, tuple[str, Callable[[Dict[str, Any]], Dict[str, Any]]]] = {}


def register_migration(from_version: str, description: str) -> Callable:
    """Decorator to register a migration function."""
    def decorator(func: Callable) -> Callable:
        MIGRATIONS[from_version] = (description, func)
        return func
    return decorator


@register_migration("1.0", "Add wnioski, setup, silence fields")
def migrate_1_0_to_1_1(brain: Dict[str, Any]) -> Dict[str, Any]:
    """1.0 → 1.1: Add missing top-level structures."""
    if "wnioski" not in brain:
        brain["wnioski"] = {
            "description": "Wnioski Bibo z dowodem — nie vibe",
            "entries": [],
            "last_updated": None,
        }
    if "setup" not in brain:
        brain["setup"] = {
            "complete": False,
            "completed_at": None,
            "installer": None,
        }
    if "silence" not in brain:
        brain["silence"] = {
            "hours_since_user": None,
            "failure_24h": False,
            "failure_at": None,
        }
    return brain


@register_migration("1.1", "Add partner.contact and partner.tts")
def migrate_1_1_to_1_2(brain: Dict[str, Any]) -> Dict[str, Any]:
    """1.1 → 1.2: Extend partner configuration."""
    partner = brain.get("partner", {})
    if "contact" not in partner:
        partner["contact"] = {
            "frequency": "normal",
            "initiative": "balanced",
            "length": "short",
        }
    if "tts" not in partner:
        partner["tts"] = {
            "enabled": True,
            "provider": "edge",
            "voice": "pl-PL-ZofiaNeural",
            "mode": "off",
        }
    brain["partner"] = partner
    return brain


@register_migration("1.2", "Add schema_version, T010/T004/T009 fields, log config, model_requirements")
def migrate_1_2_to_1_3(brain: Dict[str, Any]) -> Dict[str, Any]:
    """1.2 → 1.3: Add schema versioning and new feature fields."""
    # Schema versioning
    if "schema_version" not in brain:
        brain["schema_version"] = "1.3"

    # Log rotation (T002)
    if "log_max_bytes" not in brain:
        brain["log_max_bytes"] = 1_000_000
    if "log_keep_files" not in brain:
        brain["log_keep_files"] = 3

    # Model resilience (T008)
    if "model_requirements" not in brain:
        brain["model_requirements"] = {
            "max_output_chars": 300,
            "max_sentences": 3,
            "temperature": 0.7,
            "notes": "Egzekwowane przez plugin, nie przez model",
        }

    # Topic tracker (T010)
    if "recent_topics" not in brain:
        brain["recent_topics"] = {
            "description": "Ostatnie 5 tematów wiadomości Bibo z timestampem",
            "entries": [],
            "max_entries": 5,
        }

    # Onboarding (T004)
    if "onboarding" not in brain:
        brain["onboarding"] = {
            "description": "Stan procesu onboardingu",
            "complete": False,
            "step": 0,
            "answers": {},
            "started_at": None,
            "completed_at": None,
        }

    # Engagement metrics (T009)
    if "engagement" not in brain:
        brain["engagement"] = {
            "description": "Metryki zaangażowania dla adaptive frequency",
            "response_rate_7d": None,
            "last_calculated": None,
        }

    return brain


def get_schema_version(brain: Dict[str, Any]) -> str:
    """Extract schema version, default to 1.0 if missing."""
    return brain.get("schema_version", "1.0")


def backup_brain(path: str) -> str:
    """Create timestamped backup of brain.json. Returns backup path."""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = f"{path}.backup.{ts}.json"
    shutil.copy2(path, backup_path)
    return backup_path


def load_brain(path: str) -> Dict[str, Any]:
    """Load brain.json safely."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            brain = json.load(f)
        if not isinstance(brain, dict):
            raise ValueError("brain.json root is not an object")
        return brain
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Cannot load {path}: {exc}") from exc


def save_brain(brain: Dict[str, Any], path: str) -> None:
    """Save brain.json with proper formatting."""
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(brain, f, indent=2, ensure_ascii=False)
            f.write("\n")
    except OSError as exc:
        raise RuntimeError(f"Cannot save {path}: {exc}") from exc


def migrate_brain(
    brain: Dict[str, Any],
    from_version: Optional[str] = None,
    to_version: str = CURRENT_SCHEMA_VERSION,
) -> tuple[Dict[str, Any], list[str]]:
    """Execute migration chain from->to version.

    Returns: (migrated_brain, list_of_applied_migrations)
    """
    from_version = from_version or get_schema_version(brain)
    applied = []

    if from_version == to_version:
        return brain, applied

    # Build chain
    current = from_version
    while current != to_version:
        if current not in MIGRATIONS:
            raise RuntimeError(
                f"No migration from {current} to {to_version}. "
                f"Available: {', '.join(sorted(MIGRATIONS.keys()))}"
            )

        description, migrate_func = MIGRATIONS[current]
        brain = migrate_func(brain)
        applied.append(f"{current} → (next): {description}")

        # Find next version (convention: next is first that has current in its name migration-wise)
        # For now, just increment: 1.0→1.1→1.2→1.3
        next_version = {
            "1.0": "1.1",
            "1.1": "1.2",
            "1.2": "1.3",
        }.get(current)

        if not next_version:
            raise RuntimeError(f"Cannot determine next version after {current}")
        current = next_version

    brain["schema_version"] = to_version
    return brain, applied


def migrate_if_needed(
    brain_path: str,
    target_version: str = CURRENT_SCHEMA_VERSION,
    dry_run: bool = False,
) -> dict:
    """Load brain, migrate if needed, save if not dry-run.

    Returns: dict with keys: success, from_version, to_version, applied, backup_path
    """
    try:
        brain = load_brain(brain_path)
    except RuntimeError as exc:
        return {
            "success": False,
            "error": str(exc),
            "from_version": None,
            "to_version": None,
            "applied": [],
            "backup_path": None,
        }

    from_version = get_schema_version(brain)

    if from_version == target_version:
        return {
            "success": True,
            "message": f"Already at {target_version}, no migration needed",
            "from_version": from_version,
            "to_version": target_version,
            "applied": [],
            "backup_path": None,
        }

    try:
        migrated, applied = migrate_brain(brain, from_version, target_version)
    except RuntimeError as exc:
        return {
            "success": False,
            "error": str(exc),
            "from_version": from_version,
            "to_version": target_version,
            "applied": [],
            "backup_path": None,
        }

    if dry_run:
        return {
            "success": True,
            "message": f"Dry-run: would migrate {from_version} → {target_version}",
            "from_version": from_version,
            "to_version": target_version,
            "applied": applied,
            "backup_path": None,
            "dry_run": True,
        }

    # Create backup before writing
    try:
        backup_path = backup_brain(brain_path)
    except OSError as exc:
        return {
            "success": False,
            "error": f"Backup failed: {exc}",
            "from_version": from_version,
            "to_version": target_version,
            "applied": [],
            "backup_path": None,
        }

    # Write migrated version
    try:
        save_brain(migrated, brain_path)
    except RuntimeError as exc:
        return {
            "success": False,
            "error": f"Save failed: {exc}. Backup at {backup_path}",
            "from_version": from_version,
            "to_version": target_version,
            "applied": [],
            "backup_path": backup_path,
        }

    return {
        "success": True,
        "message": f"Migrated {from_version} → {target_version}",
        "from_version": from_version,
        "to_version": target_version,
        "applied": applied,
        "backup_path": backup_path,
    }


def main(argv: Optional[list[str]] = None) -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="Hi-Bibo brain.json schema migration")
    parser.add_argument("brain_path", help="Path to brain.json")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be migrated without saving",
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Check schema version and exit",
    )
    parser.add_argument(
        "--target-version",
        default=CURRENT_SCHEMA_VERSION,
        help=f"Target schema version (default: {CURRENT_SCHEMA_VERSION})",
    )

    args = parser.parse_args(argv)

    if args.check_only:
        try:
            brain = load_brain(args.brain_path)
            version = get_schema_version(brain)
            print(f"Current schema version: {version}")
            print(f"Target schema version: {args.target_version}")
            if version == args.target_version:
                print("✓ Already at target version")
                return 0
            else:
                print(f"⚠ Upgrade available: {version} → {args.target_version}")
                return 1
        except RuntimeError as exc:
            print(f"✗ Error: {exc}", file=sys.stderr)
            return 1

    result = migrate_if_needed(
        args.brain_path,
        target_version=args.target_version,
        dry_run=args.dry_run,
    )

    if result["success"]:
        print(result.get("message", "Migration completed"))
        for line in result.get("applied", []):
            print(f"  • {line}")
        if result.get("backup_path"):
            print(f"  Backup: {result['backup_path']}")
        return 0
    else:
        print(f"✗ {result.get('error', 'Unknown error')}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
