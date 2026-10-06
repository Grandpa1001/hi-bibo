"""Pętla kontroli terminów (§A): co 60 s czyta sprawy.json, wysyła kontrolę
po sprawach, których termin minął. Przeżywa restart — termin jest w pliku.
Ta sama pętla obsługuje też check-iny karty sprawy (`checkin.sprawdz`) i przypomnienia
o przerwie w hiperfokusie (`uwaga.sprawdz`); kontrola
minigry i check-in dotyczą różnych rekordów, więc nic nie jest obsługiwane dwa razy.
Obie ścieżki respektują bramkę kontaktu (pauza, cisza): zaległa wiadomość nie
wychodzi po jej zakończeniu, tylko jest pomijana.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from . import checkin, czat, kontakt, magazyn, uwaga

log = logging.getLogger("bibo-tryby")

INTERWAL_S = 60


async def sprawdz(uslugi) -> int:
    """Zwraca liczbę wysłanych kontroli."""
    stan = magazyn.sprawy()
    teraz = magazyn.teraz()
    wyslane = 0
    pominiete = False
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
        if kontakt.powod_blokady(magazyn.teraz()):
            sprawa["kontrola_wyslana"] = True   # pauza/cisza: pomijamy, nie odkładamy na później
            pominiete = True
            continue
        if await czat.wyslij_kontrole(uid, sid, sprawa, uslugi):
            sprawa["kontrola_wyslana"] = True
            wyslane += 1
    if wyslane or pominiete:
        magazyn.zapisz_sprawy(stan)
    return wyslane


async def petla(uslugi) -> None:
    while True:
        try:
            await sprawdz(uslugi)
        except Exception:
            log.exception("bibo-tryby: pętla kontroli")
        try:
            await checkin.sprawdz(uslugi)
        except Exception:
            log.exception("bibo-tryby: pętla check-inów")
        try:
            await uwaga.sprawdz(uslugi)
        except Exception:
            log.exception("bibo-tryby: pętla przypomnień uwagi")
        await asyncio.sleep(INTERWAL_S)
