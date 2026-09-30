"""Jeden uzgodniony check-in na kartę sprawy: zapis terminu, atomowe przejęcie i wysyłka.

Zasady:
- potwierdzenie tylko po trwałym zapisie; odbiorca = właściciel karty (nie „ostatni aktywny”);
- wysyła istniejąca pętla `kontrola.petla`, bez drugiego harmonogramu;
- zadanie przejmujemy atomowo (`oczekuje` → `wysylanie`) PRZED wysyłką, transakcja nie trwa
  podczas pracy sieci; anulować można tylko `oczekuje`;
- przed wysyłką sprawdzamy: włączenie funkcji, aktywną kartę, pauzę i ciszę;
- po restarcie starsze niż MAKS_SPOZNIENIE_MIN terminy wygasają bez wysyłki;
- niejednoznaczny błąd po wysyłce → `niepewny`, bez ponawiania; ponawiamy tylko błędy
  Bot API, które jednoznacznie oznaczają „nie przyjęto” (maks. MAKS_PROBY);
- brak odpowiedzi nie uruchamia kolejnej wiadomości.
"""
from __future__ import annotations

import logging
import re
import secrets
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import gateway_most, kontakt, magazyn
from .karta import BladKarty, _polacz, _wymagaj_wlasciciela
from .telegram import BladTelegrama

log = logging.getLogger("bibo-tryby")

MAKS_SPOZNIENIE_MIN = 15      # ustawienie techniczne do oceny w próbach
MAKS_PROBY = 3
ZAWIESZONE_MIN = 5            # `wysylanie` dłużej niż tyle = proces padł w trakcie → niepewny
MIN_ZA_MIN = 1
MAKS_DNI = 14
DNI = ("pon", "wt", "śr", "czw", "pt", "sob", "niedz")
ODPOWIEDZI = ["Ruszyłem", "Utknąłem", "Odkładam"]


def wlaczone() -> bool:
    return bool(magazyn.ustawienia().get("checkiny", True))


def _utc(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds")


def opisz_termin(dt: datetime, teraz: datetime | None = None) -> str:
    """„dziś, 15:30” / „jutro, 09:00” / „wt 01.10, 09:00” — w strefie usera."""
    z = kontakt.strefa()
    dt = dt.astimezone(z)
    dzis = (teraz or kontakt.teraz()).astimezone(z).date()
    if dt.date() == dzis:
        dzien = "dziś"
    elif dt.date() == dzis + timedelta(days=1):
        dzien = "jutro"
    else:
        dzien = f"{DNI[dt.weekday()]} {dt:%d.%m}"
    return f"{dzien}, {dt:%H:%M}"


def _widok(c: dict | None, teraz: datetime | None = None) -> dict | None:
    if not c:
        return None
    t = datetime.fromisoformat(c["termin_utc"])
    return {"id": c["id"], "status": c["status"], "termin": opisz_termin(t, teraz),
            "termin_iso": t.astimezone(kontakt.strefa()).isoformat(timespec="minutes")}


def _termin(za_minut, godzina, data, teraz: datetime) -> datetime:
    z = kontakt.strefa()
    if za_minut is not None:
        if isinstance(za_minut, bool) or not isinstance(za_minut, int) or not MIN_ZA_MIN <= za_minut <= MAKS_DNI * 24 * 60:
            raise BladKarty("dane", f"„za_minut” to liczba od {MIN_ZA_MIN} do {MAKS_DNI * 24 * 60}.")
        return teraz + timedelta(minutes=za_minut)
    if godzina is None:
        raise BladKarty("dane", "Podaj `za_minut` albo `godzina` (HH:MM). Gdy user nie podał czasu jasno, dopytaj.")
    m = re.fullmatch(r"\s*(\d{1,2}):(\d{2})\s*", str(godzina))
    if not m or int(m[1]) > 23 or int(m[2]) > 59:
        raise BladKarty("dane", "„godzina” ma mieć format HH:MM.")
    try:
        dzien = datetime.strptime(data, "%Y-%m-%d").date() if data else teraz.astimezone(z).date()
    except (ValueError, TypeError):
        raise BladKarty("dane", "„data” ma mieć format RRRR-MM-DD.")
    t = datetime(dzien.year, dzien.month, dzien.day, int(m[1]), int(m[2]), tzinfo=z)
    if t <= teraz + timedelta(minutes=MIN_ZA_MIN):
        raise BladKarty("dane", "Ta godzina już minęła — zapytaj usera o dzień (podaj `data`) albo inną porę.")
    if t > teraz + timedelta(days=MAKS_DNI):
        raise BladKarty("dane", f"Najdalej {MAKS_DNI} dni do przodu.")
    return t


def ustaw(w: str, *, za_minut=None, godzina=None, data=None, zastap: bool = False,
          teraz: datetime | None = None, sciezka: Path | None = None) -> dict:
    """Zapisuje check-in do aktywnej karty. Zwraca wpis dopiero po trwałym zapisie."""
    w = _wymagaj_wlasciciela(w)
    teraz = teraz or kontakt.teraz()
    if not wlaczone():
        raise BladKarty("wylaczone", "Check-iny są wyłączone w ustawieniach tej instancji.")
    termin = _termin(za_minut, godzina, data, teraz)
    powod = kontakt.powod_blokady(termin)
    if powod == "pauza":
        raise BladKarty("pauza", f"Na ten czas jest pauza w kontakcie (do {opisz_termin(kontakt.pauza_do(), teraz)}). "
                                 "Poproś usera o inny termin albo najpierw zakończ pauzę.")
    if powod == "cisza":
        od, do = kontakt.cisza_godziny()
        raise BladKarty("cisza", f"To godziny ciszy ({od}:00–{do}:00) — w tym czasie się nie odzywam. Poproś o inny termin.")
    with closing(_polacz(sciezka)) as db:
        db.execute("BEGIN IMMEDIATE")
        try:
            k = db.execute("SELECT id FROM karty WHERE wlasciciel=? AND status='aktywna'", (w,)).fetchone()
            if not k:
                raise BladKarty("brak_karty", "Check-in wymaga aktywnej sprawy.")
            stary = db.execute("SELECT * FROM checkiny WHERE karta_id=? AND wlasciciel=? AND status IN ('oczekuje','wysylanie')",
                               (k["id"], w)).fetchone()
            if stary:
                if not zastap:
                    raise BladKarty("jest_checkin", f"Jest już check-in: {opisz_termin(datetime.fromisoformat(stary['termin_utc']), teraz)}. "
                                    "Zapytaj usera, czy go zastąpić (wtedy `zastap`: true).")
                if stary["status"] != "oczekuje":
                    raise BladKarty("juz_wysylane", "Ten check-in właśnie się wysyła — nie da się go zmienić.")
                db.execute("UPDATE checkiny SET status='anulowany', zaktualizowano=? WHERE id=?", (_utc(teraz), stary["id"]))
            cid = "c_" + secrets.token_hex(4)
            db.execute("INSERT INTO checkiny (id, karta_id, wlasciciel, kanal, termin_utc, strefa, status, utworzono, zaktualizowano) "
                       "VALUES (?,?,?, 'telegram', ?, ?, 'oczekuje', ?, ?)",
                       (cid, k["id"], w, _utc(termin), getattr(kontakt.strefa(), "key", "UTC"), _utc(teraz), _utc(teraz)))
            db.execute("COMMIT")
        except BaseException:
            db.execute("ROLLBACK")
            raise
        return _widok(dict(db.execute("SELECT * FROM checkiny WHERE id=?", (cid,)).fetchone()), teraz)


def oczekujacy(w: str, sciezka: Path | None = None, teraz: datetime | None = None) -> dict | None:
    w = _wymagaj_wlasciciela(w)
    with closing(_polacz(sciezka)) as db:
        r = db.execute("SELECT c.* FROM checkiny c JOIN karty k ON k.id=c.karta_id "
                       "WHERE c.wlasciciel=? AND k.status='aktywna' AND c.status IN ('oczekuje','wysylanie') "
                       "ORDER BY c.termin_utc LIMIT 1", (w,)).fetchone()
        return _widok(dict(r), teraz) if r else None


def anuluj(w: str, sciezka: Path | None = None) -> None:
    """Anuluje oczekujący check-in. Gdy już się wysyła/wysłano — uczciwy błąd, bez obietnicy cofnięcia."""
    w = _wymagaj_wlasciciela(w)
    with closing(_polacz(sciezka)) as db:
        db.execute("BEGIN IMMEDIATE")
        try:
            r = db.execute("SELECT c.* FROM checkiny c JOIN karty k ON k.id=c.karta_id "
                           "WHERE c.wlasciciel=? AND k.status='aktywna' AND c.status IN ('oczekuje','wysylanie') LIMIT 1",
                           (w,)).fetchone()
            if not r:
                raise BladKarty("brak_checkinu", "Nie ma oczekującego check-inu.")
            if r["status"] != "oczekuje":
                raise BladKarty("juz_wysylane", "Wiadomość właśnie wychodzi — nie da się już anulować. "
                                "Nie obiecuj, że zniknie; user może po prostu nie odpowiadać.")
            db.execute("UPDATE checkiny SET status='anulowany', zaktualizowano=? WHERE id=?", (_utc(kontakt.teraz()), r["id"]))
            db.execute("COMMIT")
        except BaseException:
            db.execute("ROLLBACK")
            raise


def anuluj_wszystkie(powod: str = "anulowany", sciezka: Path | None = None) -> int:
    """Wyłączenie funkcji: żadnych oczekujących zadań w kolejce."""
    with closing(_polacz(sciezka)) as db:
        return db.execute("UPDATE checkiny SET status=?, zaktualizowano=? WHERE status='oczekuje'",
                          (powod, _utc(kontakt.teraz()))).rowcount


# --- przejęcie zadań do wysyłki --------------------------------------------------

def przejmij(teraz: datetime | None = None, sciezka: Path | None = None) -> list[dict]:
    """Atomowo oznacza zaległe check-iny jako `wysylanie` i zwraca je do wysłania.
    Pozostałe zaległe dostają status wygasły / anulowany / pominięty. Bez pracy w sieci."""
    teraz = teraz or kontakt.teraz()
    do_wyslania = []
    with closing(_polacz(sciezka)) as db:
        db.execute("BEGIN IMMEDIATE")
        try:
            t = _utc(teraz)
            db.execute("UPDATE checkiny SET status='niepewny', zaktualizowano=? WHERE status='wysylanie' AND zaktualizowano<?",
                       (t, _utc(teraz - timedelta(minutes=ZAWIESZONE_MIN))))
            for c in db.execute("SELECT * FROM checkiny WHERE status='oczekuje' ORDER BY termin_utc").fetchall():
                termin = datetime.fromisoformat(c["termin_utc"])
                if termin > teraz:
                    continue
                k = db.execute("SELECT * FROM karty WHERE id=?", (c["karta_id"],)).fetchone()
                if termin < teraz - timedelta(minutes=MAKS_SPOZNIENIE_MIN):
                    nowy = "wygasly"
                elif not k or k["status"] != "aktywna" or k["wlasciciel"] != c["wlasciciel"]:
                    nowy = "anulowany"
                elif kontakt.powod_blokady(teraz):
                    nowy = "pominiety"
                else:
                    db.execute("UPDATE checkiny SET status='wysylanie', proby=proby+1, zaktualizowano=? WHERE id=? AND status='oczekuje'",
                               (t, c["id"]))
                    do_wyslania.append({**dict(c), "proby": c["proby"] + 1, "karta": dict(k)})
                    continue
                db.execute("UPDATE checkiny SET status=?, zaktualizowano=? WHERE id=? AND status='oczekuje'", (nowy, t, c["id"]))
            db.execute("COMMIT")
        except BaseException:
            db.execute("ROLLBACK")
            raise
    return do_wyslania


def _zakoncz(cid: str, status: str, id_wiadomosci: str | None = None, sciezka: Path | None = None) -> None:
    """Zmienia tylko wiersz nadal w `wysylanie` — usunięty lub zmieniony nie jest odtwarzany."""
    with closing(_polacz(sciezka)) as db:
        db.execute("UPDATE checkiny SET status=?, id_wiadomosci=COALESCE(?, id_wiadomosci), zaktualizowano=? "
                   "WHERE id=? AND status='wysylanie'", (status, id_wiadomosci, _utc(kontakt.teraz()), cid))


def tekst_wiadomosci(karta: dict) -> str:
    temat = (karta.get("krok") or karta.get("cel") or "").strip()
    temat = temat if len(temat) <= 80 else temat[:79].rstrip() + "…"
    wstep = f"Wracamy do: {temat}." if temat else "Wracamy do tej sprawy."
    return f"{wstep} Jak poszło? Możesz odpisać własnymi słowami."


def _jednoznaczny_blad(e: Exception) -> bool:
    """Bot API odrzuciło wywołanie (4xx) → wiadomość na pewno nie wyszła."""
    return isinstance(e, BladTelegrama) and e.kod is not None and e.kod < 500


async def _wyslij(c: dict, uslugi, sciezka: Path | None) -> bool:
    karta = c["karta"]
    dane = {"chat_id": c["wlasciciel"], "text": tekst_wiadomosci(karta),
            "reply_markup": {"keyboard": [[{"text": t} for t in ODPOWIEDZI]],
                             "one_time_keyboard": True, "resize_keyboard": True}}
    try:
        odp = await uslugi.bot.wywolaj("sendMessage", dane)
    except Exception as e:
        if _jednoznaczny_blad(e) and c["proby"] < MAKS_PROBY:
            log.warning("bibo-tryby: check-in %s odrzucony (%s) — ponowię", c["id"], e)
            with closing(_polacz(sciezka)) as db:
                db.execute("UPDATE checkiny SET status='oczekuje', zaktualizowano=? WHERE id=? AND status='wysylanie'",
                           (_utc(kontakt.teraz()), c["id"]))
        else:
            # brak odpowiedzi/5xx: nie wiadomo, czy wyszła — nie ponawiamy. Błąd 4xx po wyczerpaniu prób: `blad`.
            _zakoncz(c["id"], "blad" if _jednoznaczny_blad(e) else "niepewny", sciezka=sciezka)
            log.warning("bibo-tryby: check-in %s: %s", c["id"], type(e).__name__)
        return False
    _zakoncz(c["id"], "wyslany", str(odp.get("message_id") or "") or None, sciezka)
    try:
        gateway_most.zostaw_notatke(
            "[bibo-tryby · notatka systemowa, nie wiadomość od usera]\n"
            f"Wysłano uzgodniony check-in: „{dane['text']}” z przyciskami Ruszyłem / Utknąłem / Odkładam. "
            "Kolejna wiadomość usera może być odpowiedzią na niego. Nie ponaglaj, jeśli nie odpowie.")
    except Exception:
        log.debug("bibo-tryby: notatka po check-inie", exc_info=True)
    return True


async def sprawdz(uslugi, teraz: datetime | None = None, sciezka: Path | None = None) -> int:
    """Wywoływane przez pętlę kontroli. Zwraca liczbę wysłanych check-inów."""
    if not wlaczone():
        anuluj_wszystkie(sciezka=sciezka)   # wyłączenie nie zostawia kolejki
        return 0
    if not getattr(uslugi, "bot", None):
        return 0   # nic nie przejmujemy, gdy nie ma czym wysłać
    wyslane = 0
    for c in przejmij(teraz, sciezka):
        wyslane += await _wyslij(c, uslugi, sciezka)
    return wyslane
