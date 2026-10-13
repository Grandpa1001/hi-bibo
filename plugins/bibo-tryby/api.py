"""Trasy HTTP wtyczki: front Mini App (static/), /health, /api/stan*.

Zostały tylko /health i /api/stan*; całe API znika razem z Mini App w M1 1.3.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from aiohttp import web

from . import auth
from .telegram import token

log = logging.getLogger("bibo-tryby")
STATIC = Path(__file__).parent / "static"      # miniapp/dist kopiowany przez install.sh / update.sh
WERSJA = "0.5.0"
API_GOTOWE = True


def trasy(app: web.Application) -> None:
    app.router.add_get("/health", health)
    from . import api_stan
    api_stan.trasy(app)
    app.router.add_get("/{sciezka:(?!api/).*}", front)


async def front(request: web.Request) -> web.StreamResponse:
    """Pliki frontu; nieznana ścieżka → index.html. Bez wyjścia poza katalog static/."""
    if not (STATIC / "index.html").is_file():
        raise web.HTTPNotFound()
    sciezka = request.match_info.get("sciezka", "")
    plik = (STATIC / sciezka).resolve() if sciezka else STATIC / "index.html"
    if not plik.is_file() or STATIC.resolve() not in plik.parents:
        plik = STATIC / "index.html"
    naglowki = {"Cache-Control": "no-cache"} if plik.name == "index.html" else \
        {"Cache-Control": "public, max-age=31536000, immutable"} if "assets" in plik.parts else \
        {"Cache-Control": "public, max-age=3600"}
    return web.FileResponse(plik, headers=naglowki)


# --- pomocnicze ---------------------------------------------------------------

KOMUNIKATY = {
    "podpis": "Sesja Telegrama wygasła. Otwórz Mini App jeszcze raz z czatu z Bibo.",
    "uzytkownik": "Ten bot jest prywatny. Odezwij się do właściciela, jeśli powinieneś mieć dostęp.",
    "dane": "Coś się nie zgadza w danych. Spróbuj ponownie.",
    "wylaczone": "Ta funkcja jest wyłączona w ustawieniach tej instancji.",
    "brak_wpisu": "Najpierw wpis na siatce — bez niego nie ma trybu dnia.",
}


class BladApi(Exception):
    def __init__(self, status: int, kod: str, komunikat: str | None = None):
        super().__init__(kod)
        self.status = status
        self.kod = kod
        self.komunikat = komunikat or KOMUNIKATY.get(kod, "")


def _blad(status: int, kod: str, komunikat: str | None = None) -> web.Response:
    return web.json_response({"blad": kod, "komunikat": komunikat or KOMUNIKATY.get(kod, "")}, status=status)


def _uid(request: web.Request) -> str:
    try:
        user = auth.weryfikuj_init_data(request.headers.get("X-Init-Data", ""), token())
        return auth.sprawdz_usera(user)
    except auth.BladAuth as e:
        raise BladApi(403 if str(e) == "uzytkownik" else 401, str(e))


async def _cialo(request: web.Request) -> dict:
    try:
        surowe = await request.read()
    except web.HTTPRequestEntityTooLarge:
        raise BladApi(422, "dane", "Wiadomość jest za długa.")
    if not surowe:
        return {}
    try:
        dane = json.loads(surowe.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise BladApi(422, "dane", "Zła składnia JSON.")
    if not isinstance(dane, dict):
        raise BladApi(422, "dane")
    return dane


# --- middleware --------------------------------------------------------------

@web.middleware
async def bledy(request: web.Request, handler):
    try:
        return await handler(request)
    except BladApi as e:
        return _blad(e.status, e.kod, e.komunikat)
    except web.HTTPRequestEntityTooLarge:
        return _blad(422, "dane", "Wiadomość jest za długa.")


# --- /health -----------------------------------------------------------------

async def health(request: web.Request) -> web.Response:
    return web.json_response({"ok": True, "wersja": WERSJA})
