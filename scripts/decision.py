#!/usr/bin/env python3
"""Deterministic speak/silent slot for Hi-Bibo.

The LLM does not vote on whether to write. This module owns the budget:
first breath, daily cap from installer prefs, anti-silence after 12h.
The model only writes the message when the slot is MUST_WRITE or MAY_WRITE.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

BIBO_DIR = os.environ.get("BIBO_DIR", "/opt/data/hi-bibo")
DECISION_PATH = os.path.join(BIBO_DIR, "logs", "decision.json")
ANALYTICS_PATH = os.path.join(BIBO_DIR, "logs", "analytics.jsonl")

SILENCE_PING_H = 12.0
DAILY_CAP = {
    "rarely": 1,
    "rzadko": 1,
    "normal": 3,
    "normalnie": 3,
    "often": 6,
    "często": 6,
    "czesto": 6,
}


def _parse_ts(value: Any) -> Optional[datetime]:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _load_events(path: str = ANALYTICS_PATH) -> List[Dict[str, Any]]:
    if not os.path.isfile(path):
        return []
    events: List[Dict[str, Any]] = []
    try:
        with open(path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    item = json.loads(line)
                except ValueError:
                    continue
                if isinstance(item, dict):
                    events.append(item)
    except OSError:
        return []
    return events


def partner_of(brain: Dict[str, Any]) -> Dict[str, Any]:
    partner = brain.get("partner")
    return partner if isinstance(partner, dict) else {}


def daily_cap(brain: Dict[str, Any]) -> int:
    contact = partner_of(brain).get("contact") or {}
    freq = str(contact.get("frequency") or "normal").lower()
    return DAILY_CAP.get(freq, 3)


def compute_slot(
    brain: Dict[str, Any],
    now: Optional[datetime] = None,
    events: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    now = now or datetime.now().astimezone()
    events = events if events is not None else _load_events()
    cap = daily_cap(brain)
    breath_count = int(brain.get("breath_count") or 0)
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    spoken_today = 0
    last_in: Optional[datetime] = None
    last_out: Optional[datetime] = None
    for event in events:
        ts = _parse_ts(event.get("ts"))
        if ts is None:
            continue
        if ts.tzinfo is None and now.tzinfo is not None:
            ts = ts.replace(tzinfo=now.tzinfo)
        etype = event.get("type")
        if etype == "inbound":
            last_in = ts if last_in is None or ts > last_in else last_in
        if etype == "outbound" and not event.get("silent"):
            last_out = ts if last_out is None or ts > last_out else last_out
            if ts >= day_start:
                spoken_today += 1

    hours_since_user = ((now - last_in).total_seconds() / 3600.0) if last_in else None
    hours_since_bibo = ((now - last_out).total_seconds() / 3600.0) if last_out else None

    slot = "MAY_WRITE"
    reason = "budżet otwarty — model decyduje o treści"

    if breath_count == 0:
        slot, reason = "MUST_WRITE", "pierwszy oddech — przedstaw się i zaproś do celu"
    elif spoken_today >= cap:
        slot, reason = "SILENT", f"dzienny limit {cap} wiadomości wyczerpany"
    elif hours_since_user is not None and hours_since_user >= SILENCE_PING_H:
        if hours_since_bibo is None or hours_since_bibo >= SILENCE_PING_H:
            slot, reason = "MUST_WRITE", f"user milczy {hours_since_user:.1f}h — anty-cisza"
    elif hours_since_user is None and breath_count >= 2 and spoken_today == 0:
        slot, reason = "MUST_WRITE", "brak jeszcze żadnej wiadomości do usera dziś"

    hour = now.hour
    nawyki = (brain.get("nawyki") or {}).get("data") or {}
    nocturnal = bool(nawyki.get("aktywny_w_nocy"))
    if slot != "SILENT" and not nocturnal and hour < 7:
        slot, reason = "SILENT", "cisza nocna (7:00) — chyba że user jest nocnym"

    return {
        "slot": slot,
        "reason": reason,
        "cap": cap,
        "spoken_today": spoken_today,
        "hours_since_user": round(hours_since_user, 2) if hours_since_user is not None else None,
        "hours_since_bibo": round(hours_since_bibo, 2) if hours_since_bibo is not None else None,
        "ts": now.isoformat(timespec="seconds"),
    }


def write_decision(decision: Dict[str, Any], path: str = DECISION_PATH) -> None:
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(decision, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
    except OSError:
        return


def load_decision(path: str = DECISION_PATH) -> Optional[Dict[str, Any]]:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else None
    except (OSError, ValueError):
        return None
