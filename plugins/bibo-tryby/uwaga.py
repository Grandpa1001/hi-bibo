"""Stan uwagi (FR-11, FR-14, FR-15): wybór, powrót z hiperfokusu i przypomnienia o przerwie.

Wszystko deterministyczne i bez modelu: wybór przyciskiem lub `/fokus`, szablonowe podsumowanie
po wyjściu z hiperfokusu i przypomnienie co 90 min wysyłane przez istniejącą pętlę `kontrola.petla`
(bez drugiego harmonogramu). Zachowanie modelu wg stanu uwagi opisuje `tryb.kontekst`.
Przypomnienia respektują wspólną bramkę kontaktu (pauza, cisza): zaległe nie wychodzi po jej końcu.
"""
from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

from . import karta, kontakt, siatka, stan, tryb

log = logging.getLogger("bibo-tryby")

TEKST_PRZERWY = "Minęło 90 minut. Krótka przerwa i łyk wody? Nie przerywam — wrócisz, kiedy będziesz gotowy."
SLOWA_KOMENDY = {"rozproszony": "hypofocus", "rozproszona": "hypofocus", "hipo": "hypofocus", "hipofokus": "hypofocus",
                 "norma": "normal", "normie": "normal", "normalnie": "normal",
                 "hiper": "hyperfocus", "hiperfokus": "hyperfocus"}


def z_argumentu(raw: str) -> str | None:
    t = (raw or "").strip().lower()
    if t.startswith("w "):
        t = t[2:]
    return SLOWA_KOMENDY.get(t)


def podsumowanie_powrotu(w: str, *, teraz: datetime | None = None, sciezka: Path | None = None,
                         sciezka_karty: Path | None = None) -> str:
    """FR-15: jedna wiadomość po hiperfokusie. Mówi tylko to, co Bibo ma zapisane, bez zgadywania."""
    z = stan.zaangazowanie(w, teraz=teraz, sciezka=sciezka, sciezka_karty=sciezka_karty)
    zrobiono = (f"zakończone dziś sprawy: {z['domkniecia']}" if z["domkniecia"]
                else "żadnej zakończonej dziś sprawy w karcie")
    try:
        a = karta.aktywna(w, sciezka_karty)
    except Exception:
        a = None
    czeka = (a and (a["krok"] or a["cel"])) or ""
    czeka = f"Czeka: {czeka}." if czeka else "W karcie nic na Ciebie nie czeka."
    return (f"Witaj z powrotem. Z tego, co mam zapisane — {zrobiono}. {czeka} "
            "Resztę planu dnia sprawdzimy, gdy będziesz gotowy.")


def wybierz(w: str, uwaga: str, *, teraz: datetime | None = None, sciezka: Path | None = None,
            sciezka_karty: Path | None = None) -> str:
    """Ustawia stan uwagi na dziś i zwraca tekst potwierdzenia (dopiero po zapisie).
    Ta sama wartość = bez zmian (bez nowego wpisu). Wyjście z hiperfokusu dokłada podsumowanie powrotu.
    Bez dzisiejszego wpisu rzuca `BladStanu('brak_wpisu')`."""
    teraz = teraz or kontakt.teraz()
    obecny = stan.dzisiejszy(w, teraz=teraz, sciezka=sciezka)
    if obecny is None:
        raise stan.BladStanu("brak_wpisu", "Najpierw wpis na siatce — bez niego nie ma trybu dnia.")
    if obecny["uwaga"] == uwaga:
        return tryb.reakcja_uwagi(uwaga)
    stan.ustaw_uwage(w, uwaga, teraz=teraz, sciezka=sciezka)
    tekst = tryb.reakcja_uwagi(uwaga)
    if obecny["uwaga"] == "hyperfocus":
        tekst += "\n\n" + podsumowanie_powrotu(w, teraz=teraz, sciezka=sciezka, sciezka_karty=sciezka_karty)
    return tekst


async def sprawdz(uslugi, teraz: datetime | None = None, sciezka: Path | None = None) -> int:
    """Wywoływane przez pętlę kontroli. Zwraca liczbę wysłanych przypomnień (0 lub 1)."""
    w = karta.wlasciciel()
    if not w or not siatka.wlaczone() or not getattr(uslugi, "bot", None):
        return 0
    teraz = teraz or kontakt.teraz()
    if not stan.zajmij_przypomnienie(w, wstrzymane=bool(kontakt.powod_blokady(teraz)), teraz=teraz, sciezka=sciezka):
        return 0
    try:
        await uslugi.bot.wywolaj("sendMessage", {"chat_id": w, "text": TEKST_PRZERWY})
        return 1
    except Exception as e:
        log.warning("bibo-tryby: przypomnienie o przerwie nie wysłane: %s", type(e).__name__)   # bez ponawiania
        return 0
