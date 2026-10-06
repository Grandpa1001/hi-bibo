"""Podsumowanie tygodnia (FR-9, FR-16): rozkład trybów, rozkład stanów uwagi i po jednym wniosku w każdej części.

Wszystko z danych, które Bibo już ma, bez modelu i bez nowych pytań do usera:
- tryb dnia = ostatni wpis doby; uwaga dnia = najmocniejszy stan zgłoszony tego dnia (hiperfokus > rozproszenie > norma);
- wnioski opisują, co było w danych, a nie dlaczego: nie sugerują przyczyny i znikają, gdy danych jest za mało;
- „domknięcia” to karty spraw zakończone w danym dniu (issues z zewnętrznych narzędzi ta instancja nie widzi);
- raz w tygodniu ISO podsumowanie samo wychodzi po pierwszej okazji (z opóźnieniem, nigdy jako osobne przypomnienie)
  i trafia do Kroniki; `/tydzien` pokazuje je na żądanie, a Mini App to samo okno liczy na żywo.
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta
from pathlib import Path

from . import karta, kontakt, stan, tryb

log = logging.getLogger("bibo-tryby")

MIN_DNI_Z_WPISEM = 2        # poniżej tego podsumowanie nie ma sensu i nie wychodzi
MIN_DOMKNIECIA = 2
MIN_DNI_HIPERFOKUSU = 2
UWAGA_KOLEJNOSC = ("normal", "hypofocus", "hyperfocus")
CZESCI_DNIA = (("rano", range(5, 12)), ("po południu", range(12, 18)), ("wieczorem", range(18, 23)), ("w nocy", None))


def _czesc_dnia(godzina: int) -> str:
    for nazwa, zakres in CZESCI_DNIA:
        if zakres is not None and godzina in zakres:
            return nazwa
    return "w nocy"


def _dni_z_wpisem(dni: list[dict]) -> list[dict]:
    return [d for d in dni if d["cwiartka"]]


def _wniosek_trybow(dni: list[dict], domkniecia_wg_trybu: dict[str, int]) -> str | None:
    """Najpierw „gdzie domknięto najwięcej”, a bez wystarczających danych — po prostu najczęstszy tryb."""
    razem = sum(domkniecia_wg_trybu.values())
    if razem >= MIN_DOMKNIECIA:
        naj = max(domkniecia_wg_trybu.values())
        liderzy = [c for c, n in domkniecia_wg_trybu.items() if n == naj]
        if len(liderzy) == 1:
            return f"Najwięcej zakończonych spraw ({naj} z {razem}) przypadło na tryb {tryb.nazwa(liderzy[0])}."
    z_wpisem = _dni_z_wpisem(dni)
    licz: dict[str, int] = {}
    for d in z_wpisem:
        licz[d["cwiartka"]] = licz.get(d["cwiartka"], 0) + 1
    naj = max(licz.values())
    liderzy = [c for c, n in licz.items() if n == naj]
    if len(liderzy) == 1:
        return f"Najczęstszy tryb tygodnia: {tryb.nazwa(liderzy[0])} ({naj} z {len(z_wpisem)} dni z wpisem)."
    return None


def _wniosek_uwagi(dni: list[dict]) -> str | None:
    """FR-16: o jakiej porze dnia najczęściej zaczynał się hiperfokus (gdy zdarzył się w co najmniej 2 dniach)."""
    starty = [d["start_hiper"] for d in dni if d["start_hiper"] is not None]
    if len(starty) < MIN_DNI_HIPERFOKUSU:
        return None
    licz: dict[str, int] = {}
    for g in starty:
        licz[_czesc_dnia(g)] = licz.get(_czesc_dnia(g), 0) + 1
    naj = max(licz.values())
    liderzy = [c for c, n in licz.items() if n == naj]
    if naj >= 2 and len(liderzy) == 1:
        return f"Hiperfokus zaczynał się najczęściej {liderzy[0]} ({naj} z {len(starty)} dni)."
    return f"Hiperfokus pojawił się w {len(starty)} dniach, o różnych porach."


def zbuduj(w: str, *, koniec: date | None = None, teraz: datetime | None = None, dni: int = 7,
           sciezka: Path | None = None, sciezka_karty: Path | None = None) -> dict | None:
    """Dane podsumowania dla okna `dni` dób kończącego się na `koniec` (domyślnie dziś). None, gdy mniej niż
    MIN_DNI_Z_WPISEM dób miało wpis."""
    teraz = teraz or kontakt.teraz()
    z = kontakt.strefa()
    koniec = koniec or teraz.astimezone(z).date()
    okno = stan.dni_tygodnia(w, koniec, dni=dni, sciezka=sciezka)
    z_wpisem = _dni_z_wpisem(okno)
    if len(z_wpisem) < MIN_DNI_Z_WPISEM:
        return None
    tryby = {c: 0 for c in stan.CWIARTKI}
    uwaga = {u: 0 for u in UWAGA_KOLEJNOSC}
    for d in z_wpisem:
        tryby[d["cwiartka"]] += 1
        uwaga[d["uwaga"]] += 1
    domkniecia = {c: 0 for c in stan.CWIARTKI}
    try:
        dzien_trybu = {d["dzien"]: d["cwiartka"] for d in z_wpisem}
        for k in karta.odczytaj(w, status="zakonczona", sciezka=sciezka_karty):
            c = dzien_trybu.get(datetime.fromisoformat(k["zaktualizowano"]).astimezone(z).date().isoformat())
            if c:
                domkniecia[c] += 1
    except Exception:
        log.debug("bibo-tryby: domknięcia do podsumowania", exc_info=True)
    return {"od": okno[0]["dzien"], "do": okno[-1]["dzien"], "dni_z_wpisem": len(z_wpisem), "dni_bez_wpisu": dni - len(z_wpisem),
            "tryby": tryby, "uwaga": uwaga, "domkniecia": domkniecia,
            "wniosek_trybow": _wniosek_trybow(okno, domkniecia), "wniosek_uwagi": _wniosek_uwagi(okno)}


def _dm(iso: str) -> str:
    return date.fromisoformat(iso).strftime("%d.%m")


def tekst(p: dict) -> str:
    """Wiadomość do czatu: czytelna jako zwykły tekst, bez formatowania, które psuje się w Telegramie."""
    tryby = " · ".join(f"{tryb.nazwa(c)} {p['tryby'][c]}" for c in stan.CWIARTKI if p["tryby"][c])
    uwagi = " · ".join(f"{tryb.FOKUS_NAZWY[u]} {p['uwaga'][u]}" for u in UWAGA_KOLEJNOSC if p["uwaga"][u])
    brak = f" (bez wpisu: {p['dni_bez_wpisu']})" if p["dni_bez_wpisu"] else ""
    linie = [f"Twój tydzień ({_dm(p['od'])}–{_dm(p['do'])})", "", f"Tryby, liczba dni: {tryby}{brak}"]
    if p["wniosek_trybow"]:
        linie.append(p["wniosek_trybow"])
    linie += ["", f"Uwaga, liczba dni: {uwagi}"]
    if p["wniosek_uwagi"]:
        linie.append(p["wniosek_uwagi"])
    linie += ["", "Opieram się wyłącznie na tym, co wpisujesz i potwierdzasz — to nie ocena. Zapisane też w Kronice."]
    return "\n".join(linie)


def do_wyslania(w: str, *, teraz: datetime | None = None, sciezka: Path | None = None,
                sciezka_karty: Path | None = None) -> str | None:
    """Raz na tydzień ISO: podsumowanie 7 pełnych dób do wczoraj, gdy było co najmniej 2 dni z wpisem.
    Zapis w Kronice i „zajęcie” tygodnia następują przed wysyłką, więc awaria wysyłki nie powoduje powtórki.
    Zwraca tekst do wysłania albo None."""
    teraz = teraz or kontakt.teraz()
    dzis = teraz.astimezone(kontakt.strefa()).date()
    rok, tydz, _ = dzis.isocalendar()
    klucz = f"{rok}-W{tydz:02d}"
    if stan.podsumowanie_juz_bylo(w, klucz, sciezka=sciezka):
        return None
    p = zbuduj(w, koniec=dzis - timedelta(days=1), teraz=teraz, sciezka=sciezka, sciezka_karty=sciezka_karty)
    if p is None:
        return None
    t = tekst(p)
    return t if stan.zapisz_podsumowanie_tygodnia(w, klucz, t, json.dumps(p, ensure_ascii=False), teraz=teraz, sciezka=sciezka) else None
