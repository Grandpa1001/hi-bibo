"""Wysyłanie do czatu Telegrama: propozycja sprawy, karta wyniku, kontrola,
oraz komentarz Bibo po sprawie (przez `gateway_most.wstrzyknij`).

Wszystkie funkcje wywoływane w pętli usług — nie blokują gatewaya.
"""
from __future__ import annotations

import logging
from pathlib import Path

from . import gateway_most, magazyn
from .telegram import BladTelegrama, EFEKT_KONFETTI

log = logging.getLogger("bibo-tryby")

WERDYKT_ETYKIETY = {"obalona": "💥 WYMÓWKA OBALONA",
                    "czesciowo": "⚖️ WERDYKT: CZĘŚCIOWO",
                    "uniewinniona": "🟢 WYMÓWKA UNIEWINNIONA"}
WERDYKT_KARTA = {"obalona": "obalona.png", "czesciowo": "czesciowo.png", "uniewinniona": "uniewinniona.png"}
WERDYKT_EFEKT = {"obalona": EFEKT_KONFETTI, "czesciowo": None, "uniewinniona": "5104841245755180586"}  # ❤️
ZASOBY = Path(__file__).parent / "zasoby"
STATIC = Path(__file__).parent / "static"


# --- propozycja sprawy -------------------------------------------------------

async def wyslij_propozycje(uid: str, uslugi) -> bool:
    """Wysyła propozycję z przyciskiem Mini App, gdy dziś nie było jeszcze propozycji."""
    if not uslugi.url or not uslugi.bot:
        log.info("bibo-tryby: propozycja pominięta — brak adresu Mini App")
        return False
    kart = magazyn.kartoteka()
    dzis = magazyn.data()
    limit = int(magazyn.ustawienia().get("propozycje_dziennie", 1))
    juz = int((kart.get("propozycje") or {}).get(dzis, 0))
    if juz >= limit:
        return False
    tekst = "🕵️ Brzmi jak klasyczny zator. Otwieramy śledztwo?"
    try:
        await uslugi.bot.wiadomosc_z_aplikacja(uid, tekst, "🔍 Otwieramy", f"{uslugi.url}/#/gry/detektyw")
    except BladTelegrama as e:
        log.warning("bibo-tryby: propozycja nie wysłana: %s", e)
        return False
    kart.setdefault("propozycje", {})[dzis] = juz + 1
    magazyn.zapisz_kartoteke(kart)
    return True


# --- karta wyniku ------------------------------------------------------------

def _plik_karty(werdykt: str) -> str:
    nazwa = WERDYKT_KARTA.get(werdykt, "obalona.png")
    kandydat = STATIC / "karty" / nazwa
    if kandydat.is_file():
        return str(kandydat)
    return str(ZASOBY / "radosc.png")   # awaryjnie: postać z konfetti


def _podpis_karty(numer: int, werdykt: str, krok: str) -> str:
    tytul = f"<b>📁 SPRAWA #{numer:02d} · ZAMKNIĘTA</b>"
    etykieta = WERDYKT_ETYKIETY.get(werdykt, werdykt.upper())
    krok_html = f"👣 <b>{krok}</b>" if krok else ""
    return "\n".join(x for x in (tytul, etykieta, krok_html) if x)


async def wyslij_karte(uid: str, sprawa: dict, uslugi) -> bool:
    if not uslugi.bot:
        return False
    werdykt = sprawa.get("werdykt") or "czesciowo"
    plik = _plik_karty(werdykt)
    podpis = _podpis_karty(int(sprawa.get("numer", 0)), werdykt, sprawa.get("krok", ""))
    try:
        await uslugi.bot.karta(uid, plik, podpis, efekt=WERDYKT_EFEKT.get(werdykt))
        return True
    except BladTelegrama as e:
        log.warning("bibo-tryby: karta wyniku nie wysłana: %s", e)
        return False


# --- komentarz Bibo po sprawie (§C.5) ----------------------------------------

async def powiadom_bibo(uid: str, tekst: str) -> str:
    """Wstrzyknięcie notatki do sesji Bibo. Zwraca `sesja` lub `notatka` (fallback)."""
    if not tekst:
        return "brak"
    sposob = await gateway_most.wstrzyknij(uid, tekst)
    # notatka §C.5 zostaje jako fallback tylko do czasu wstrzyknięcia
    kart = magazyn.kartoteka()
    if kart.get("notatka_dla_bibo") == tekst:
        kart["notatka_dla_bibo"] = None
        magazyn.zapisz_kartoteke(kart)
    return sposob


async def zakoncz_sprawe(uid: str, sprawa: dict, notatka: str, uslugi) -> None:
    """Karta wyniku + komentarz Bibo. Uruchamiane jako task po `api_zamknij`."""
    await wyslij_karte(uid, sprawa, uslugi)
    await powiadom_bibo(uid, notatka)


# --- kontrola po X min (§A) --------------------------------------------------

def _skroc(krok: str, maks: int = 60) -> str:
    krok = krok.strip()
    return krok if len(krok) <= maks else krok[: maks - 1].rstrip() + "…"


async def wyslij_kontrole(uid: str, sid: str, sprawa: dict, uslugi) -> bool:
    if not uslugi.bot or not uslugi.url:
        return False
    numer = int(sprawa.get("numer", 0))
    krok = _skroc(sprawa.get("krok", ""))
    tekst = f"🕵️ Kontrola po sprawie #{numer:02d}: ruszyło z „{krok}”?"
    url = f"{uslugi.url}/#/kontrola/{sid}"
    try:
        await uslugi.bot.wiadomosc_z_aplikacja(uid, tekst, "📁 Otwórz akta", url)
        return True
    except BladTelegrama as e:
        log.warning("bibo-tryby: kontrola nie wysłana: %s", e)
        return False


# --- §C.6: „🐢 Jeszcze nie” --------------------------------------------------

async def zapytaj_co_blokuje(uid: str, sprawa: dict) -> str:
    tekst = (
        "[bibo-tryby · notatka systemowa, nie wiadomość od usera]\n"
        f"Kontrola sprawy #{sprawa.get('numer')}: krok „{sprawa.get('krok', '')}” jeszcze nie ruszył.\n"
        "Zapytaj krótko i bez oceny, co blokuje. Jedno pytanie. Nie proponuj jeszcze rozwiązania."
    )
    return await gateway_most.wstrzyknij(uid, tekst)
