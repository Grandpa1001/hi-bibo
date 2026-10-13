"""Wątek usług: własna pętla asyncio z klientem Bot API i pętlą terminów (`kontrola`).

Pętla gatewaya Hermesa nie jest tu używana — awaria usług nie wpływa na Bibo.
Nie ma serwera HTTP ani tunelu (usunięte w M1 1.3).
"""
from __future__ import annotations

import asyncio
import logging
import os
import threading
import time

import aiohttp

from . import kontrola, magazyn
from .telegram import BotApi, BladTelegrama

log = logging.getLogger("bibo-tryby")

NAZWA_WATKU = "bibo-tryby-uslugi"
ZNACZNIK_MENU = "menu_zresetowane.json"


class Uslugi:
    def __init__(self):
        self.ust = magazyn.ustawienia()
        self.petla: asyncio.AbstractEventLoop | None = None
        self.http: aiohttp.ClientSession | None = None
        self.bot: BotApi | None = None
        self.start = time.time()

    # --- cykl życia ---------------------------------------------------------
    def uruchom_w_watku(self) -> None:
        threading.Thread(target=self._watek, name=NAZWA_WATKU, daemon=True).start()

    def _watek(self) -> None:
        self.petla = asyncio.new_event_loop()
        asyncio.set_event_loop(self.petla)
        try:
            self.petla.run_until_complete(self._main())
        except Exception:
            log.exception("bibo-tryby: wątek usług zakończył się błędem")

    async def _main(self) -> None:
        self.http = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30))
        self.bot = BotApi(self.http)
        await self._zresetuj_menu()
        self._kontrola = asyncio.create_task(kontrola.petla(self))
        await asyncio.Event().wait()

    async def _zresetuj_menu(self) -> None:
        """Raz: po Mini App w Telegramie został przycisk „Bibo” z martwym adresem — wracamy do domyślnego menu."""
        if magazyn.czytaj(ZNACZNIK_MENU):
            return
        try:
            await self.bot.zresetuj_menu()
            magazyn.zapisz(ZNACZNIK_MENU, {"od": time.strftime("%Y-%m-%dT%H:%M:%S%z")})
            log.info("bibo-tryby: przycisk menu Mini App usunięty")
        except BladTelegrama as e:
            log.warning("bibo-tryby: nie zresetowano przycisku menu (spróbuję przy następnym starcie): %s", e)

    # --- pomocnicze dla hooków (wywoływane z innych wątków) ------------------
    def zleć(self, coro) -> None:
        if self.petla and self.petla.is_running():
            asyncio.run_coroutine_threadsafe(coro, self.petla)
        else:
            coro.close()


# --- start tylko w procesie gatewaya ----------------------------------------
_uslugi: Uslugi | None = None
_start_blokada = threading.Lock()


def aktywne() -> Uslugi | None:
    return _uslugi


def _jestem_gatewayem() -> bool:
    """Marker `_HERMES_GATEWAY` dziedziczą procesy potomne, więc wymagamy też
    własności pliku PID działającego gatewaya (tak robi sam Hermes)."""
    if os.environ.get("_HERMES_GATEWAY") != "1":
        return False
    try:
        from gateway.status import get_running_pid
        return get_running_pid(cleanup_stale=False) == os.getpid()
    except Exception:
        return False


def uruchom_gdy_gateway(limit_s: int = 180) -> None:
    """Czeka w tle, aż ten proces zostanie potwierdzony jako gateway, i startuje usługi raz."""
    if os.environ.get("_HERMES_GATEWAY") != "1":
        return
    if any(t.name in (NAZWA_WATKU, NAZWA_WATKU + "-start") for t in threading.enumerate()):
        return

    def czekaj():
        global _uslugi
        koniec = time.time() + limit_s
        while time.time() < koniec:
            if _jestem_gatewayem():
                with _start_blokada:
                    if _uslugi is None:
                        _uslugi = Uslugi()
                        _uslugi.uruchom_w_watku()
                return
            time.sleep(2)
        log.info("bibo-tryby: to nie jest proces gatewaya — usługi nie startują")

    threading.Thread(target=czekaj, name=NAZWA_WATKU + "-start", daemon=True).start()
