"""Pętla terminów: co 60 s obsługuje check-iny karty sprawy (`checkin.sprawdz`) i przypomnienia
o przerwie w hiperfokusie (`uwaga.sprawdz`). Przeżywa restart — terminy są w plikach.
Obie ścieżki respektują bramkę kontaktu (pauza, cisza): zaległa wiadomość nie
wychodzi po jej zakończeniu, tylko jest pomijana.
"""
from __future__ import annotations

import asyncio
import logging

from . import checkin, uwaga

log = logging.getLogger("bibo-tryby")

INTERWAL_S = 60


async def petla(uslugi) -> None:
    while True:
        try:
            await checkin.sprawdz(uslugi)
        except Exception:
            log.exception("bibo-tryby: pętla check-inów")
        try:
            await uwaga.sprawdz(uslugi)
        except Exception:
            log.exception("bibo-tryby: pętla przypomnień uwagi")
        await asyncio.sleep(INTERWAL_S)
