"""Pętla kontroli terminów (§A): co 60 s czyta sprawy.json, wysyła kontrolę
po sprawach, których termin minął. Przeżywa restart — termin jest w pliku.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from . import czat, magazyn

log = logging.getLogger("bibo-tryby")

INTERWAL_S = 60


async def sprawdz(uslugi) -> int:
    """Zwraca liczbę wysłanych kontroli."""
    stan = magazyn.sprawy()
    teraz = magazyn.teraz()
    wyslane = 0
    for sid, sprawa in list(stan.items()):
        if sprawa.get("etap") != "zamknieta" or sprawa.get("kontrola_wyslana"):
            continue
        termin = sprawa.get("kontrola")
        if not termin:
            continue
        try:
            termin_dt = datetime.fromisoformat(termin)
        except ValueError:
            continue
        if termin_dt.astimezone(teraz.tzinfo) > teraz:
            continue
        uid = str(sprawa.get("user") or "")
        if not uid:
            continue
        if await czat.wyslij_kontrole(uid, sid, sprawa, uslugi):
            sprawa["kontrola_wyslana"] = True
            wyslane += 1
    if wyslane:
        magazyn.zapisz_sprawy(stan)
    return wyslane


async def petla(uslugi) -> None:
    while True:
        try:
            await sprawdz(uslugi)
        except Exception:
            log.exception("bibo-tryby: pętla kontroli")
        await asyncio.sleep(INTERWAL_S)
