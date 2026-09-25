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

EFEKT_KONFETTI = "5046509860389126442"   # 🎉 (message_effect_id, tylko czaty prywatne)


def token() -> str:
    return os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()


class BladTelegrama(Exception):
    pass


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
            raise BladTelegrama(f"{metoda}: {odp.get('error_code')} {odp.get('description')}")
        return odp["result"]

    async def ustaw_menu(self, url: str, tekst: str = "🎲 Tryby") -> None:
        """Przycisk menu dla wszystkich czatów prywatnych bota."""
        await self.wywolaj("setChatMenuButton", {
            "menu_button": {"type": "web_app", "text": tekst, "web_app": {"url": url}}})

    async def menu(self) -> dict:
        return await self.wywolaj("getChatMenuButton", {})

    async def wiadomosc_z_aplikacja(self, chat_id: str, tekst: str, przycisk: str, url: str,
                                    styl: str | None = "success") -> dict:
        btn = {"text": przycisk, "web_app": {"url": url}}
        if styl:
            btn["style"] = styl
        dane = {"chat_id": chat_id, "text": tekst, "parse_mode": "HTML",
                "reply_markup": {"inline_keyboard": [[btn]]}}
        try:
            return await self.wywolaj("sendMessage", dane)
        except BladTelegrama as e:
            if styl and "style" in str(e).lower():
                btn.pop("style", None)
                return await self.wywolaj("sendMessage", dane)
            raise

    async def karta(self, chat_id: str, zdjecie: str, podpis: str, efekt: str | None = EFEKT_KONFETTI) -> dict:
        dane = {"chat_id": chat_id, "caption": podpis, "parse_mode": "HTML"}
        if efekt:
            dane["message_effect_id"] = efekt
        try:
            return await self.wywolaj("sendPhoto", dane, pliki={"photo": zdjecie})
        except BladTelegrama as e:
            if efekt and "effect" in str(e).lower():
                dane.pop("message_effect_id", None)
                return await self.wywolaj("sendPhoto", dane, pliki={"photo": zdjecie})
            raise
