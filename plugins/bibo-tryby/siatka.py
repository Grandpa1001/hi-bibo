"""Siatka stanu dnia w rozmowie (FR-1, FR-2, FR-7): klawiatura Telegrama, rozpoznanie stuknięcia, zapis.

Wszystko deterministyczne i bez modelu: stuknięcie w pole siatki to zwykły tekst wiadomości
(jak przyciski check-inu karty), który rozpoznajemy w `pre_gateway_dispatch`, zapisujemy
i odpowiadamy sami. Dzięki temu check-in nie kosztuje tokenów ani nie zależy od tego,
czy model poprawnie wywoła narzędzie. Potwierdzenie wychodzi dopiero po zapisie.

Siatka 4×4 bez pola środkowego: wiersz = energia (⚡⚡ → 🌙🌙), kolumna = samopoczucie
(😣 → 😄), czyli osie −2, −1, 1, 2. Dzięki temu każde pole ma jednoznaczną ćwiartkę.
Słowa z FR-2 mają prefiks 💭, a „Pomiń” prefiks ⏩, żeby zwykła wiadomość usera
(np. „zmęczony”) nigdy nie została wzięta za odpowiedź na klawiaturę.
"""
from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

from . import karta, magazyn, stan, sygnaly, tryb, uwaga

log = logging.getLogger("bibo-tryby")

ENERGIA = {2: "⚡⚡", 1: "⚡", -1: "🌙", -2: "🌙🌙"}
PRZYJEMNOSC = {-2: "😣", -1: "🙁", 1: "🙂", 2: "😄"}
PRZYCISK_POMIN = "⏩ Pomiń"
PREFIKS_SLOWA = "💭 "
PREFIKS_NOTATKI = "notatka:"
FOKUS = {"🌀 Rozproszony": "hypofocus", "👌 W normie": "normal", "🎯 Hiperfokus": "hyperfocus"}

WIERSZE = (2, 1, -1, -2)
KOLUMNY = (-2, -1, 1, 2)
POLA = {f"{ENERGIA[e]} {PRZYJEMNOSC[p]}": (e, p) for e in WIERSZE for p in KOLUMNY}
SLOWA = {f"{PREFIKS_SLOWA}{s}" for lista in stan.SLOWA.values() for s in lista}

TEKST_SIATKI = ("Jak się dziś czujesz? Jedno stuknięcie.\n"
                "Wiersz: energia (⚡⚡ wysoka → 🌙🌙 niska). Kolumna: samopoczucie (😣 → 😄).")


def wlaczone() -> bool:
    return bool(magazyn.ustawienia().get("stan", True))


def klawiatura_siatki() -> dict:
    return {"keyboard": [[{"text": f"{ENERGIA[e]} {PRZYJEMNOSC[p]}"} for p in KOLUMNY] for e in WIERSZE],
            "one_time_keyboard": True, "resize_keyboard": True, "is_persistent": False}


def siatka() -> dict:
    return {"text": TEKST_SIATKI, "reply_markup": klawiatura_siatki()}


def _wiersz_uwagi() -> list[dict]:
    return [{"text": t} for t in FOKUS]


def klawiatura_uwagi() -> dict:
    """Sam rząd stanu uwagi (komenda `/fokus`)."""
    return {"keyboard": [_wiersz_uwagi()], "one_time_keyboard": True, "resize_keyboard": True}


def _klawiatura_po_wpisie(cwiartka: str) -> dict:
    """FR-2 + FR-11: słowa z ćwiartki, „Pomiń” i jeden rząd stanu uwagi. Brak wyboru = W normie."""
    rzad = [{"text": PREFIKS_SLOWA + s} for s in stan.SLOWA[cwiartka]] + [{"text": PRZYCISK_POMIN}]
    return {"keyboard": [rzad[i:i + 2] for i in range(0, len(rzad), 2)] + [_wiersz_uwagi()],
            "one_time_keyboard": True, "resize_keyboard": True}


_ZDEJMIJ = {"remove_keyboard": True}


def _odp(tekst: str, markup: dict | None = None) -> dict:
    return {"text": tekst, "reply_markup": markup or _ZDEJMIJ}


def _po_tapnieciu(w: str, e: int, p: int, teraz, sciezka) -> dict:
    r = stan.zapisz_wpis(w, e, p, zrodlo="manual", teraz=teraz, sciezka=sciezka)
    try:
        a = karta.aktywna(w)
    except Exception:
        a = None   # reakcja bez kroku z karty jest lepsza niż brak reakcji
    return _odp(f"Zapisane: {tryb.nazwa(r['cwiartka'])}. {tryb.reakcja(r['cwiartka'], a and a['krok'])}\n\n"
                "Słowo i stan uwagi są opcjonalne — bez wyboru zostaje „W normie”.", _klawiatura_po_wpisie(r["cwiartka"]))


def _norm(tekst: str | None) -> str:
    """Telegram bywa dokłada selektor wariantu emoji (U+FE0F); klucze klawiatury go nie mają."""
    return (tekst or "").replace("\ufe0f", "").strip()


def rozpoznaj(tekst: str) -> bool:
    """Szybka bramka bez bazy: czy to w ogóle może być wiadomość z klawiatury stanu."""
    t = _norm(tekst)
    return t in POLA or t in SLOWA or t in FOKUS or t in sygnaly.ODPOWIEDZI or t == PRZYCISK_POMIN or t.lower().startswith(PREFIKS_NOTATKI)


def obsluz(w: str, tekst: str, *, teraz: datetime | None = None, sciezka: Path | None = None) -> dict | None:
    """Zwraca odpowiedź do wysłania ({text, reply_markup}) albo None, gdy wiadomość nie jest nasza
    (wtedy trafia do Bibo bez zmian). Błąd zapisu daje uczciwy komunikat, że nic nie zapisano."""
    t = _norm(tekst)
    try:
        if t in POLA:
            return _po_tapnieciu(w, *POLA[t], teraz, sciezka)
        if t in sygnaly.ODPOWIEDZI:
            return sygnaly.odpowiedz(w, t, teraz=teraz, sciezka=sciezka)   # None = brak zadanego pytania → do Bibo
        if t in FOKUS:
            return _odp(uwaga.wybierz(w, FOKUS[t], teraz=teraz, sciezka=sciezka))
        if t == PRZYCISK_POMIN:
            if stan.dzisiejszy(w, teraz=teraz, sciezka=sciezka) is None:
                return None
            return _odp("Dobrze, zostawiam.")
        if t in SLOWA:
            stan.doprecyzuj(w, slowo=t[len(PREFIKS_SLOWA):], teraz=teraz, sciezka=sciezka)
            return _odp("Dopisane.")
        if t.lower().startswith(PREFIKS_NOTATKI):
            nota = t[len(PREFIKS_NOTATKI):].strip()
            if not nota or stan.dzisiejszy(w, teraz=teraz, sciezka=sciezka) is None:
                return None
            stan.doprecyzuj(w, notatka=nota, teraz=teraz, sciezka=sciezka)
            return _odp("Notatka dopisana.")
    except stan.BladStanu as e:
        if e.kod == "brak_wpisu":
            return None
        return _odp(f"Nie zapisałem tego: {e.komunikat}")
    except Exception:
        log.warning("bibo-tryby: siatka stanu", exc_info=True)
        return _odp("Nie udało się zapisać wpisu — nic nie zostało zmienione. Spróbuj jeszcze raz.")
    return None


async def wyslij(uid: str, uslugi, odp: dict | None = None) -> bool:
    """Wysyła siatkę (domyślnie) albo odpowiedź z `obsluz` do właściciela."""
    if not getattr(uslugi, "bot", None):
        return False
    try:
        await uslugi.bot.wywolaj("sendMessage", {"chat_id": uid, **(odp or siatka())})
        return True
    except Exception as e:
        log.warning("bibo-tryby: siatka stanu nie wysłana: %s", type(e).__name__)
        return False
