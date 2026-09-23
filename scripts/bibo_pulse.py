#!/usr/bin/env python3
"""Bibo pulse — darmowa bramka przed proaktywną wiadomością.

Uruchamiany przez cron Hermesa co godzinę (`--script bibo_pulse.py`).
Decyduje BEZ modelu, czy Bibo ma się teraz odezwać:
  - cisza nocna, dzienny limit, minimalny odstęp między zaczepkami,
  - nie przeszkadza, gdy user właśnie pisze (ostatnia wiadomość < N min),
  - odrobina losowości, żeby nie było jak w zegarku.

Ostatnia linia stdout to {"wakeAgent": true|false} — przy false Hermes
nie wywołuje modelu w ogóle (0 tokenów). Przy true reszta stdout trafia
do promptu zadania jako kontekst (pora dnia, rodzaj impulsu).

Ustawienia usera: <profil>/local/bibo_pulse.json (katalog `local/` nie jest
nadpisywany przez `hermes profile update`). Brak pliku = wartości domyślne.
"""
from __future__ import annotations

import json
import random
import sqlite3
import sys
import time
from datetime import datetime
from pathlib import Path

PROFILE = Path(__file__).resolve().parent.parent
STATE_FILE = PROFILE / "local" / "bibo_pulse_state.json"
SETTINGS_FILE = PROFILE / "local" / "bibo_pulse.json"

DEFAULTS = {
    "enabled": True,
    "timezone": "Europe/Warsaw",
    "quiet_from": 22,           # od tej godziny cisza...
    "quiet_to": 8,              # ...do tej
    "max_per_day": 3,
    "min_gap_hours": 3,
    "skip_if_user_active_min": 45,
    "chance": 0.6,              # szansa odezwania się w "dozwolonej" godzinie
    "platform": "telegram",
}

SLOTS = [
    (8, 11, "poranny start", "Pomóż wybrać JEDNĄ rzecz na dziś albo nawiąż do obietnicy z pamięci."),
    (11, 15, "środek dnia", "Lekki check: jak idzie ta jedna rzecz? Zaproponuj mały krok albo body doubling."),
    (15, 19, "popołudnie", "Energia zwykle siada — zapytaj o stan, pomóż domknąć albo świadomie odpuścić."),
    (19, 22, "wieczór", "Krótka refleksja: co dziś wyszło (konkret, bez oceniania), co na jutro."),
]


def load_json(path: Path, default: dict) -> dict:
    try:
        return {**default, **json.loads(path.read_text(encoding="utf-8"))}
    except (OSError, ValueError):
        return dict(default)


def now_local(tz_name: str) -> datetime:
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo(tz_name))
    except Exception:
        return datetime.now()


def last_user_message_ts(platform: str) -> float | None:
    """Czas ostatniej wiadomości usera z danej platformy (read-only, fail-safe)."""
    db = PROFILE / "state.db"
    if not db.exists():
        return None
    try:
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=2)
        row = con.execute(
            "SELECT MAX(m.timestamp) FROM messages m JOIN sessions s ON s.id = m.session_id "
            "WHERE m.role = 'user' AND s.source = ?",
            (platform,),
        ).fetchone()
        con.close()
        return float(row[0]) if row and row[0] else None
    except sqlite3.Error:
        return None


def in_quiet_hours(hour: int, q_from: int, q_to: int) -> bool:
    if q_from > q_to:  # przez północ, np. 22 -> 8
        return hour >= q_from or hour < q_to
    return q_from <= hour < q_to


def decide(cfg: dict, state: dict, now: datetime, last_user: float | None, rnd: float) -> tuple[bool, str]:
    today = now.date().isoformat()
    if state.get("date") != today:
        state.update(date=today, count=0)
    if not cfg["enabled"]:
        return False, "wyłączone w ustawieniach"
    if in_quiet_hours(now.hour, cfg["quiet_from"], cfg["quiet_to"]):
        return False, "cisza nocna"
    if state["count"] >= cfg["max_per_day"]:
        return False, "dzienny limit"
    ts = now.timestamp()
    if ts - state.get("last_ts", 0) < cfg["min_gap_hours"] * 3600:
        return False, "za krótko od ostatniej zaczepki"
    if last_user and ts - last_user < cfg["skip_if_user_active_min"] * 60:
        return False, "user właśnie rozmawia"
    if rnd > cfg["chance"]:
        return False, "losowo pominięte"
    return True, "ok"


def build_context(now: datetime, last_user: float | None) -> str:
    slot = next(((name, hint) for a, b, name, hint in SLOTS if a <= now.hour < b), ("dzień", "Krótka zaczepka."))
    day = ["poniedziałek", "wtorek", "środa", "czwartek", "piątek", "sobota", "niedziela"][now.weekday()]
    lines = [
        f"Teraz: {day} {now:%H:%M} ({slot[0]}).",
        f"Rodzaj impulsu: {slot[1]}",
    ]
    if last_user:
        hours = (now.timestamp() - last_user) / 3600
        lines.append(f"User ostatnio pisał {hours:.0f} h temu.")
        if hours > 24:
            lines.append("Dawno cisza — zagadaj ciepło, bez wyrzutów i bez „dlaczego nie piszesz”.")
    else:
        lines.append("Brak historii rozmowy — jeśli nie znasz usera, zaproś go do rozmowy.")
    return "\n".join(lines)


def main() -> int:
    cfg = load_json(SETTINGS_FILE, DEFAULTS)
    state = load_json(STATE_FILE, {"date": "", "count": 0, "last_ts": 0})
    now = now_local(cfg["timezone"])
    last_user = last_user_message_ts(cfg["platform"])

    wake, reason = decide(cfg, state, now, last_user, random.random())
    if wake:
        state["count"] += 1
        state["last_ts"] = now.timestamp()
        print(build_context(now, last_user))
    else:
        print(f"pominięte: {reason}", file=sys.stderr)

    try:
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        STATE_FILE.write_text(json.dumps(state), encoding="utf-8")
    except OSError:
        pass
    print(json.dumps({"wakeAgent": wake}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
