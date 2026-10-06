"""API widgetu stanu dnia w Mini App (FR-8): odczyt dnia i tygodnia, wpis z siatki, doprecyzowanie, uwaga.

Tylko dla właściciela profilu (jedyne id w TELEGRAM_ALLOWED_USERS), tak samo jak stan w czacie.
Wpisy z Mini App mają źródło `widget`. Odczyt to jedno krótkie zapytanie na dzień i jedno na tydzień;
nic nie dotyka modelu. Reakcja na wpis to ten sam szablon co w czacie (`tryb.reakcja`).
"""
from __future__ import annotations

import logging

from aiohttp import web

from . import karta, podsumowanie, siatka, stan, tryb, uwaga
from .api import BladApi, _cialo, _uid

log = logging.getLogger("bibo-tryby")


def trasy(app: web.Application) -> None:
    app.router.add_get("/api/stan", api_stan)
    app.router.add_post("/api/stan", api_wpis)
    app.router.add_post("/api/stan/doprecyzuj", api_doprecyz)
    app.router.add_post("/api/stan/uwaga", api_uwaga)


def _wlasciciel(request: web.Request) -> str:
    uid = _uid(request)
    if karta.wlasciciel() != uid:
        raise BladApi(403, "uzytkownik")
    if not siatka.wlaczone():
        raise BladApi(409, "wylaczone", "Stan dnia jest wyłączony w tej instancji.")
    return uid


def _blad_stanu(e: stan.BladStanu) -> BladApi:
    return BladApi(409 if e.kod == "brak_wpisu" else 422, e.kod if e.kod == "brak_wpisu" else "dane", e.komunikat)


def _dzis(w: str) -> dict | None:
    r = stan.dzisiejszy(w)
    if not r:
        return None
    return {"cwiartka": r["cwiartka"], "nazwa": tryb.nazwa(r["cwiartka"]), "energia": r["energia"],
            "przyjemnosc": r["przyjemnosc"], "uwaga": r["uwaga"], "slowo": r["slowo"],
            "slowa": list(stan.SLOWA[r["cwiartka"]])}


def _widok(w: str, **dodatek) -> dict:
    return {"wlaczone": True, "dzis": _dzis(w), "tydzien": stan.tydzien(w), **dodatek}


def _tydzien(w: str) -> dict | None:
    """Podsumowanie ostatnich 7 dni do karty „Twój tydzień” (bez domknięć; None, gdy za mało wpisów lub błąd)."""
    try:
        p = podsumowanie.zbuduj(w)
    except Exception:
        log.debug("bibo-tryby: podsumowanie w API", exc_info=True)
        return None
    return {k: p[k] for k in ("od", "do", "dni_z_wpisem", "dni_bez_wpisu", "tryby", "uwaga", "wniosek_trybow", "wniosek_uwagi")} if p else None


async def api_stan(request: web.Request) -> web.Response:
    uid = _uid(request)
    if karta.wlasciciel() != uid or not siatka.wlaczone():
        return web.json_response({"wlaczone": False})   # widget po prostu się nie pokazuje
    return web.json_response(_widok(uid, podsumowanie=_tydzien(uid)))


async def api_wpis(request: web.Request) -> web.Response:
    w = _wlasciciel(request)
    d = await _cialo(request)
    try:
        r = stan.zapisz_wpis(w, d.get("energia"), d.get("przyjemnosc"), uwaga=d.get("uwaga", "normal"), zrodlo="widget")
    except stan.BladStanu as e:
        raise _blad_stanu(e)
    try:
        a = karta.aktywna(w)
    except Exception:
        a = None
    return web.json_response(_widok(w, reakcja=tryb.reakcja(r["cwiartka"], a and a["krok"])))


async def api_doprecyz(request: web.Request) -> web.Response:
    w = _wlasciciel(request)
    d = await _cialo(request)
    try:
        stan.doprecyzuj(w, slowo=d.get("slowo"), notatka=d.get("notatka"))
    except stan.BladStanu as e:
        raise _blad_stanu(e)
    return web.json_response(_widok(w))


async def api_uwaga(request: web.Request) -> web.Response:
    w = _wlasciciel(request)
    d = await _cialo(request)
    try:
        tekst = uwaga.wybierz(w, d.get("uwaga"))
    except stan.BladStanu as e:
        raise _blad_stanu(e)
    return web.json_response(_widok(w, komunikat=tekst))
