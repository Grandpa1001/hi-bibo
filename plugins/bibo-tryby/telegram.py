"""Minimalny klient Bot API (HTTPS, token z `.env`).

Wysyłamy bezpośrednio, nie przez adapter Hermesa: wysyłanie nie koliduje
z pollingiem, a nie dotykamy prywatnych obiektów gatewaya.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path

import aiohttp

log = logging.getLogger("bibo-tryby")


def token() -> str:
    return os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()


class BladTelegrama(Exception):
    """Odpowiedź Bot API z `ok: false`. `kod` = error_code (brak → nieznany)."""

    def __init__(self, komunikat: str = "", kod: int | None = None):
        super().__init__(komunikat)
        self.kod = kod


class BotApi:
    def __init__(self, session: aiohttp.ClientSession):
        self._s = session

    async def wywolaj(self, metoda: str, dane: dict | None = None, pliki: dict | None = None) -> dict:
        url = f"https://api.telegram.org/bot{token()}/{metoda}"
        if pliki:
            form = aiohttp.FormData()
            for k, v in (dane or {}).items():
                form.add_field(k, v if isinstance(v, str) else json.dumps(v, ensure_ascii=False))
            for k, sciezka in pliki.items():
                form.add_field(k, Path(sciezka).read_bytes(), filename=Path(sciezka).name)
            req = self._s.post(url, data=form)
        else:
            req = self._s.post(url, json=dane or {})
        async with req as r:
            odp = await r.json(content_type=None)
        if not odp.get("ok"):
            # Nie logujemy URL-a — zawiera token.
            raise BladTelegrama(f"{metoda}: {odp.get('error_code')} {odp.get('description')}", odp.get("error_code"))
        return odp["result"]

    async def zresetuj_menu(self) -> None:
        """Przycisk menu czatów prywatnych z powrotem na domyślny (zdejmuje dawny przycisk Mini App)."""
        await self.wywolaj("setChatMenuButton", {"menu_button": {"type": "default"}})
