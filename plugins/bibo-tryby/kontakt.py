"""Wspólna bramka kontaktu: pauza i cisza nocna dla wiadomości, które Bibo inicjuje sam.

Źródła to rzeczywiste pliki, nie pamięć opisowa modelu:
- cisza: `local/bibo_pulse.json` (`quiet_from`, `quiet_to`) — ten sam plik czyta puls;
- pauza: `local/bibo_pauza.json` (`do`: ISO z offsetem) — czyta ją też `scripts/bibo_pulse.py`.
Strefa: `BIBO_STREFA` (jak w bibo-zegar), inaczej ustawienie `strefa`.
"""
from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timedelta, timezone

from . import magazyn

CISZA_OD, CISZA_DO = 22, 8
MAKS_PAUZA_H = 24 * 14


def teraz() -> datetime:
    """Jedyny zegar funkcji kontaktu (w testach podmieniany)."""
    return datetime.now(timezone.utc)


def strefa():
    nazwa = (os.environ.get("BIBO_STREFA") or magazyn.ustawienia().get("strefa") or "Europe/Warsaw").strip()
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo(nazwa)
    except Exception:
        return timezone.utc


def _local():
    return magazyn.hermes_home() / "local"


def cisza_godziny() -> tuple[int, int]:
    try:
        d = json.loads((_local() / "bibo_pulse.json").read_text(encoding="utf-8"))
        return int(d.get("quiet_from", CISZA_OD)), int(d.get("quiet_to", CISZA_DO))
    except (OSError, ValueError, TypeError):
        return CISZA_OD, CISZA_DO


def w_ciszy(dt: datetime) -> bool:
    od, do = cisza_godziny()
    h = dt.astimezone(strefa()).hour
    return (h >= od or h < do) if od > do else (od <= h < do)


def pauza_do() -> datetime | None:
    try:
        d = json.loads((_local() / "bibo_pauza.json").read_text(encoding="utf-8"))
        return datetime.fromisoformat(d["do"]) if d.get("do") else None
    except (OSError, ValueError, KeyError, TypeError):
        return None


def ustaw_pauze(godziny: int, momentu: datetime | None = None) -> datetime:
    do = (momentu or teraz()) + timedelta(hours=godziny)
    _zapisz_pauze(do.astimezone(strefa()).isoformat(timespec="seconds"))
    return do.astimezone(strefa())


def zakoncz_pauze() -> None:
    _zapisz_pauze(None)


def _zapisz_pauze(iso: str | None) -> None:
    k = _local()
    k.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=k, prefix=".bibo_pauza.", suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump({"do": iso}, f)
    os.replace(tmp, k / "bibo_pauza.json")


def powod_blokady(dt: datetime) -> str | None:
    """`pauza` / `cisza` / None — czy wiadomość inicjowana przez Bibo może wyjść w chwili `dt`."""
    p = pauza_do()
    if p and dt < p:
        return "pauza"
    if w_ciszy(dt):
        return "cisza"
    return None
