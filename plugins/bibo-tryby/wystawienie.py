"""Skąd bierze się publiczny adres HTTPS Mini App.

Jedna implementacja: Cloudflare quick tunnel (`cloudflared`, bez konta i domeny).
Obejście: `url_staly` w ustawieniach — wtedy nic nie uruchamiamy.
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import shutil
from typing import Awaitable, Callable

from . import magazyn

log = logging.getLogger("bibo-tryby")

ADRES = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")
NaAdres = Callable[[str], Awaitable[None]]


def sciezka_cloudflared() -> str | None:
    lokalny = magazyn.hermes_home() / "bin" / "cloudflared"
    if lokalny.is_file() and os.access(lokalny, os.X_OK):
        return str(lokalny)
    return shutil.which("cloudflared")


class StalyAdres:
    def __init__(self, url: str):
        self.url = url.rstrip("/")

    async def uruchom(self, na_adres: NaAdres) -> None:
        await na_adres(self.url)

    async def zatrzymaj(self) -> None:
        pass


class QuickTunnel:
    """Nadzoruje proces `cloudflared`: restart z backoffem, adres z wyjścia procesu."""

    def __init__(self, port: int):
        self.port = port
        self.url: str | None = None
        self._proc: asyncio.subprocess.Process | None = None
        self._stop = False

    async def uruchom(self, na_adres: NaAdres) -> None:
        exe = sciezka_cloudflared()
        if not exe:
            log.warning("bibo-tryby: brak cloudflared (%s/bin/cloudflared) — Mini App niedostępna",
                        magazyn.hermes_home())
            return
        opoznienie = 5
        while not self._stop:
            self._proc = await asyncio.create_subprocess_exec(
                exe, "tunnel", "--no-autoupdate", "--url", f"http://127.0.0.1:{self.port}",
                stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE,
                start_new_session=True)
            log.info("bibo-tryby: cloudflared uruchomiony (pid %s)", self._proc.pid)
            assert self._proc.stderr
            async for linia in self._proc.stderr:
                m = ADRES.search(linia.decode(errors="replace"))
                if m and m.group(0) != self.url:
                    self.url = m.group(0)
                    opoznienie = 5
                    log.info("bibo-tryby: adres tunelu %s", self.url)
                    try:
                        await na_adres(self.url)
                    except Exception:
                        log.exception("bibo-tryby: obsługa nowego adresu nie powiodła się")
            kod = await self._proc.wait()
            if self._stop:
                break
            log.warning("bibo-tryby: cloudflared zakończył się (%s), restart za %ss", kod, opoznienie)
            self.url = None
            await asyncio.sleep(opoznienie)
            opoznienie = min(opoznienie * 2, 300)

    async def zatrzymaj(self) -> None:
        self._stop = True
        if self._proc and self._proc.returncode is None:
            self._proc.terminate()


def utworz(ust: dict):
    if ust.get("url_staly"):
        return StalyAdres(ust["url_staly"])
    return QuickTunnel(int(ust["port"]))
