#!/usr/bin/env python3
"""Deterministic speak/silent slot for Hi-Bibo (T006).

The LLM does not vote on whether to write. This module owns:
- daily cap from phase (adaptation 1/8, partnership 1/4) and T004 frequency
- anti-silence after 12h, failure flag after 24h
- decay of zachowania_biezace (48h half-weight, 72h archive)
- breath-side brain thaw (count + last_updated even when SILENT)
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

BIBO_DIR = os.environ.get("BIBO_DIR", "/opt/data/hi-bibo")
BRAIN_PATH = os.path.join(BIBO_DIR, "brain.json")
DECISION_PATH = os.path.join(BIBO_DIR, "logs", "decision.json")
ANALYTICS_PATH = os.path.join(BIBO_DIR, "logs", "analytics.jsonl")

SILENCE_PING_H = 12.0
SILENCE_FAIL_H = 24.0
DECAY_HALF_H = 48.0
DECAY_ARCHIVE_H = 72.0

# 24 hourly breaths × ratio. adaptation 1/8 = 3, partnership 1/4 = 6.
PHASE_CAP = {
    "adaptation": 3,
    "adaptacja": 3,
    "partnership": 6,
    "partnerstwo": 6,
    "silence": 1,
    "cisza": 1,
}

FREQUENCY_CAP = {
    "rarely": 1,
    "rzadko": 1,
    "often": 6,
    "często": 6,
    "czesto": 6,
}


def _parse_ts(value: Any) -> Optional[datetime]:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _aware(ts: Optional[datetime], now: datetime) -> Optional[datetime]:
    if ts is None:
        return None
    if ts.tzinfo is None and now.tzinfo is not None:
        return ts.replace(tzinfo=now.tzinfo)
    if ts.tzinfo is not None and now.tzinfo is None:
        return ts.replace(tzinfo=None)
    return ts


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


def phase_of(brain: Dict[str, Any]) -> str:
    return str(brain.get("phase") or "adaptation").lower()


def daily_cap(brain: Dict[str, Any]) -> int:
    """Phase sets the default; T004 frequency is a hard override.

    rarely → 1, often → 6, normal/unset → phase table.
    """
    base = PHASE_CAP.get(phase_of(brain), 3)
    contact = partner_of(brain).get("contact") or {}
    freq = str(contact.get("frequency") or "normal").lower()
    if freq in FREQUENCY_CAP:
        return FREQUENCY_CAP[freq]
    return base


def compute_adaptive_cap(
    brain: Dict[str, Any],
    events: List[Dict[str, Any]],
    now: Optional[datetime] = None,
) -> int:
    """Dynamiczny cap na podstawie response rate z ostatnich 7 dni (T009).

    Returns: cap wiadomości dziennie (1–6)
    """
    from datetime import timedelta

    now = now or datetime.now().astimezone()
    base_cap = daily_cap(brain)

    # Ramp-up: pierwsze 3 dni = max(3, cap)
    breath_count = int(brain.get("breath_count") or 0)
    if breath_count < 72:  # Pierwsze 3 dni (24 * 3 oddechy)
        return min(3, base_cap)

    # Oblicz response rate z ostatnich 7 dni
    window_start = now - timedelta(days=7)
    outbound = [e for e in events if e.get("type") == "outbound" and e.get("ts")]
    inbound = [e for e in events if e.get("type") == "inbound" and e.get("ts")]

    # Filtruj do okna 7-dniowego
    def _in_window(event: Dict[str, Any], start: datetime, end: datetime) -> bool:
        ts = _parse_ts(event.get("ts"))
        if ts is None:
            return False
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=end.tzinfo)
        return start <= ts <= end

    outbound_recent = [e for e in outbound if _in_window(e, window_start, now)]
    inbound_recent = [e for e in inbound if _in_window(e, window_start, now)]

    spoken = [e for e in outbound_recent if not e.get("silent")]

    if not spoken:
        # Brak danych — użyj base cap
        return base_cap

    # Ile user odpowiedział na Bibo wiadomości w oknie 6h
    matched, total, delays = _match_replies(spoken, inbound_recent, window_h=6.0)
    response_rate = matched / len(spoken) if spoken else 0.0

    # Dynamiczny cap (FREQUENCY_CAP nigdy nie jest nadpisywany — to hard override)
    contact = partner_of(brain).get("contact") or {}
    freq = str(contact.get("frequency") or "normal").lower()
    if freq in FREQUENCY_CAP:
        # User override (rarely/often) — nie adaptuj
        return FREQUENCY_CAP[freq]

    # Adaptive logic
    if response_rate > 0.6:
        cap = min(6, base_cap + 1)  # Wysokie zaangażowanie → +1 (max 6)
    elif response_rate >= 0.3:
        cap = base_cap  # Normalne zaangażowanie → base cap
    else:
        cap = max(1, base_cap - 1)  # Niskie zaangażowanie → -1 (min 1)

    # Zapisz metrykę
    brain.setdefault("engagement", {})
    brain["engagement"]["response_rate_7d"] = round(response_rate, 3)
    brain["engagement"]["last_calculated"] = now.isoformat(timespec="seconds")

    return cap


def _newer(left: Optional[datetime], right: Optional[datetime]) -> Optional[datetime]:
    if left is None:
        return right
    if right is None:
        return left
    return left if left >= right else right


def _contacts_from_events(
    events: List[Dict[str, Any]],
    now: datetime,
    day_start: datetime,
) -> Tuple[Optional[datetime], Optional[datetime], int]:
    last_in: Optional[datetime] = None
    last_out: Optional[datetime] = None
    spoken_today = 0
    for event in events:
        ts = _aware(_parse_ts(event.get("ts")), now)
        if ts is None:
            continue
        etype = event.get("type")
        if etype == "inbound":
            last_in = _newer(last_in, ts)
        if etype == "outbound" and not event.get("silent"):
            last_out = _newer(last_out, ts)
            if ts >= day_start:
                spoken_today += 1
    return last_in, last_out, spoken_today


def compute_slot(
    brain: Dict[str, Any],
    now: Optional[datetime] = None,
    events: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    now = now or datetime.now().astimezone()
    events = events if events is not None else _load_events()
    cap = compute_adaptive_cap(brain, events, now)
    breath_count = int(brain.get("breath_count") or 0)
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    phase = phase_of(brain)

    last_in, last_out, spoken_today = _contacts_from_events(events, now, day_start)
    last_in = _newer(last_in, _aware(_parse_ts(brain.get("last_user_contact")), now))
    last_out = _newer(last_out, _aware(_parse_ts(brain.get("last_bibo_message")), now))

    spoken_on = str(brain.get("spoken_on") or "")
    if spoken_on == now.date().isoformat():
        spoken_today = max(spoken_today, int(brain.get("spoken_today") or 0))
    elif last_out is not None and last_out >= day_start and spoken_today == 0:
        spoken_today = 1

    hours_since_user = ((now - last_in).total_seconds() / 3600.0) if last_in else None
    hours_since_bibo = ((now - last_out).total_seconds() / 3600.0) if last_out else None
    failure_24h = hours_since_user is not None and hours_since_user >= SILENCE_FAIL_H

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
    # Night quiet holds anti-silence until morning, but never blocks first breath.
    if breath_count > 0 and slot != "SILENT" and not nocturnal and hour < 7:
        slot, reason = "SILENT", "cisza nocna (7:00) — chyba że user jest nocnym"

    return {
        "slot": slot,
        "reason": reason,
        "cap": cap,
        "phase": phase,
        "spoken_today": spoken_today,
        "hours_since_user": round(hours_since_user, 2) if hours_since_user is not None else None,
        "hours_since_bibo": round(hours_since_bibo, 2) if hours_since_bibo is not None else None,
        "failure_24h": failure_24h,
        "ts": now.isoformat(timespec="seconds"),
    }


def _entry_note(item: Dict[str, Any]) -> str:
    for key in ("note", "text", "claim", "message"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _as_entry(item: Any, fallback_ts: Optional[str]) -> Optional[Dict[str, Any]]:
    if isinstance(item, str):
        if not item.strip():
            return None
        return {"ts": fallback_ts, "note": item.strip(), "weight": 1.0}
    if not isinstance(item, dict):
        return None
    note = _entry_note(item)
    if not note and item.get("data") is None:
        return None
    entry = dict(item)
    if note:
        entry["note"] = note
    if not entry.get("ts"):
        entry["ts"] = fallback_ts
    return entry


def decay_zachowania(brain: Dict[str, Any], now: Optional[datetime] = None) -> Dict[str, int]:
    """Age-out stale mood/feedback so a 4-day-old 'irritated' cannot block forever.

    Mutates brain. Returns counts of halved / archived items.
    """
    now = now or datetime.now().astimezone()
    bucket = brain.get("zachowania_biezace")
    if not isinstance(bucket, dict):
        bucket = {}
        brain["zachowania_biezace"] = bucket

    fallback_ts = bucket.get("last_updated")
    entries_in = list(bucket.get("entries") or [])
    archived = list(bucket.get("archived") or [])
    active: List[Dict[str, Any]] = []
    halved = 0
    archived_n = 0

    for raw in entries_in:
        entry = _as_entry(raw, fallback_ts if isinstance(fallback_ts, str) else None)
        if entry is None:
            continue
        ts = _aware(_parse_ts(entry.get("ts")), now)
        age_h = ((now - ts).total_seconds() / 3600.0) if ts is not None else 0.0
        if age_h >= DECAY_ARCHIVE_H:
            entry["weight"] = 0.0
            entry["archived_at"] = now.isoformat(timespec="seconds")
            archived.append(entry)
            archived_n += 1
        elif age_h >= DECAY_HALF_H:
            entry["weight"] = 0.5
            active.append(entry)
            halved += 1
        else:
            entry["weight"] = 1.0
            active.append(entry)

    data = bucket.get("data")
    data_updated = _aware(_parse_ts(bucket.get("last_updated")), now)
    data_age = ((now - data_updated).total_seconds() / 3600.0) if data_updated else 0.0
    if isinstance(data, dict) and data:
        if data_age >= DECAY_ARCHIVE_H:
            archived_data = list(bucket.get("archived_data") or [])
            archived_data.append(
                {
                    "ts": bucket.get("last_updated"),
                    "archived_at": now.isoformat(timespec="seconds"),
                    "data": data,
                }
            )
            bucket["archived_data"] = archived_data
            bucket["data"] = {}
            bucket["data_weight"] = 0.0
            archived_n += 1
        elif data_age >= DECAY_HALF_H:
            bucket["data_weight"] = 0.5
            halved += 1
        else:
            bucket["data_weight"] = 1.0
    else:
        bucket["data_weight"] = 1.0 if not data else bucket.get("data_weight", 1.0)

    bucket["entries"] = active
    bucket["archived"] = archived
    return {"halved": halved, "archived": archived_n, "active": len(active)}


def maintain_brain(
    brain: Dict[str, Any],
    decision: Dict[str, Any],
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Thaw brain.json on every breath — even SILENT ones.

    Increments breath_count, stamps last_updated, decays feedback, records
    silence hours. This is what breaks the death loop from T006.
    """
    now = now or datetime.now().astimezone()
    updated = json.loads(json.dumps(brain))
    updated["breath_count"] = int(updated.get("breath_count") or 0) + 1
    updated["last_updated"] = now.isoformat(timespec="seconds")
    decay = decay_zachowania(updated, now)
    silence = updated.get("silence")
    if not isinstance(silence, dict):
        silence = {}
        updated["silence"] = silence
    hours = decision.get("hours_since_user")
    silence["hours_since_user"] = hours
    failure = bool(decision.get("failure_24h"))
    silence["failure_24h"] = failure
    if failure:
        if not silence.get("failure_at"):
            silence["failure_at"] = now.isoformat(timespec="seconds")
    else:
        silence["failure_at"] = None
    updated["_decay"] = decay
    return updated


def stamp_last_user_contact(brain: Dict[str, Any], now: Optional[datetime] = None) -> Dict[str, Any]:
    now = now or datetime.now().astimezone()
    brain["last_user_contact"] = now.isoformat(timespec="seconds")
    silence = brain.get("silence")
    if isinstance(silence, dict):
        silence["hours_since_user"] = 0.0
        silence["failure_24h"] = False
        silence["failure_at"] = None
    return brain


def stamp_last_bibo_message(brain: Dict[str, Any], now: Optional[datetime] = None) -> Dict[str, Any]:
    now = now or datetime.now().astimezone()
    brain["last_bibo_message"] = now.isoformat(timespec="seconds")
    day = now.date().isoformat()
    if str(brain.get("spoken_on") or "") != day:
        brain["spoken_on"] = day
        brain["spoken_today"] = 1
    else:
        brain["spoken_today"] = int(brain.get("spoken_today") or 0) + 1
    return brain


def write_json(path: str, payload: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False)
        fh.write("\n")


def write_brain(brain: Dict[str, Any], path: str = BRAIN_PATH) -> None:
    clean = dict(brain)
    clean.pop("_decay", None)
    write_json(path, clean)


def write_decision(decision: Dict[str, Any], path: str = DECISION_PATH) -> None:
    try:
        write_json(path, decision)
    except OSError:
        return


def load_decision(path: str = DECISION_PATH) -> Optional[Dict[str, Any]]:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else None
    except (OSError, ValueError):
        return None
