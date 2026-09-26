"""Wątek usług: własna pętla asyncio z serwerem API, tunelem i klientem Bot API.

Pętla gatewaya Hermesa nie jest tu używana — awaria usług nie wpływa na Bibo.
"""
from __future__ import annotations

import asyncio
import logging
import os
import threading
import time

import aiohttp
from aiohttp import web

from . import magazyn, wystawienie
from .telegram import BotApi, BladTelegrama

log = logging.getLogger("bibo-tryby")

NAZWA_WATKU = "bibo-tryby-uslugi"


class Uslugi:
    def __init__(self):
        self.ust = magazyn.ustawienia()
        self.port = int(self.ust["port"])
        self.petla: asyncio.AbstractEventLoop | None = None
        self.http: aiohttp.ClientSession | None = None
        self.bot: BotApi | None = None
        self.url: str | None = None
        self.wystawienie = None
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
        app = web.Application(client_max_size=4096, middlewares=[_naglowki])
        app["uslugi"] = self
        from . import api
        api.trasy(app)
        runner = web.AppRunner(app, access_log=None)
        await runner.setup()
        try:
            await web.TCPSite(runner, "127.0.0.1", self.port).start()
        except OSError as e:
            log.warning("bibo-tryby: port %s zajęty (%s) — usługi nie startują", self.port, e)
            await self.http.close()
            return
        log.info("bibo-tryby: API na 127.0.0.1:%s", self.port)
        self.wystawienie = wystawienie.utworz(self.ust)
        await self.wystawienie.uruchom(self._nowy_adres)   # QuickTunnel: działa do końca procesu
        await asyncio.Event().wait()

    async def _nowy_adres(self, url: str) -> None:
        self.url = url
        magazyn.zapisz("stan_tunelu.json", {"url": url, "od": time.strftime("%Y-%m-%dT%H:%M:%S%z")})
        from .api import API_GOTOWE
        menu = url if API_GOTOWE else f"{url}/?mock=1"
        try:
            await self.bot.ustaw_menu(menu)
            log.info("bibo-tryby: przycisk menu → %s", menu)
        except BladTelegrama as e:
            log.warning("bibo-tryby: nie ustawiono przycisku menu: %s", e)

    # --- pomocnicze dla hooków (wywoływane z innych wątków) ------------------
    def zleć(self, coro) -> None:
        if self.petla and self.petla.is_running():
            asyncio.run_coroutine_threadsafe(coro, self.petla)
        else:
            coro.close()


@web.middleware
async def _naglowki(request, handler):
    resp = await handler(request)
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("Referrer-Policy", "no-referrer")
    return resp


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
