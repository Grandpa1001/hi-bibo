"""Kontekst czasu doklejany do każdej tury Bibo (hook `pre_llm_call`).

Bibo ma reagować na „zaraz”, „później”, „jutro” zgodnie z rzeczywistością —
dlatego przed każdą odpowiedzią dostaje jedno zdanie z aktualnym czasem.
Strefę pobieramy z `BIBO_STREFA` (domyślnie Europe/Warsaw).
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

log = logging.getLogger("bibo-zegar")

DNI = ("poniedziałek", "wtorek", "środa", "czwartek", "piątek", "sobota", "niedziela")


def _strefa():
    nazwa = (os.environ.get("BIBO_STREFA") or "Europe/Warsaw").strip()
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo(nazwa)
    except Exception:
        log.warning("bibo-zegar: nie rozpoznano strefy %r — używam czasu lokalnego serwera", nazwa)
        return None


def teraz_tekst(teraz: datetime | None = None) -> str:
    strefa = _strefa()
    t = teraz or datetime.now(tz=timezone.utc)
    t = t.astimezone(strefa) if strefa else t.astimezone()
    return (f"Teraz: {DNI[t.weekday()]} {t:%d.%m.%Y}, {t:%H:%M} "
            f"({t.tzname() or 'czas lokalny'}). "
            "„Zaraz”, „później”, „jutro” odnoś do tego czasu.")


def _przed_tura(**_):
    return {"context": teraz_tekst()}


def register(ctx):
    ctx.register_hook("pre_llm_call", _przed_tura)
