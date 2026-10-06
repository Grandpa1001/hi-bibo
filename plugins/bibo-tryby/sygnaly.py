"""Wykrywanie gorszego dnia, hiperfokusu i hipofokusu (FR-5, FR-6, FR-12, FR-13) oraz łagodna sugestia wsparcia.

Zasady, które trzymają całość uczciwą wobec usera:
- sygnały to proste reguły w kodzie na tym, co Bibo widzi sam (frazy, godzina, długość wiadomości, czas
  w rozmowie, karty spraw), bez wywołań modelu i bez zapisu treści; zapisujemy tylko rodzaj sygnału;
- to dowody, nie diagnoza: stan zmienia się wyłącznie po odpowiedzi „Tak”, a „Nie” nic nie zapisuje poza
  odpowiedzią przy sygnale (do liczenia fałszywych alarmów);
- pytanie najwyżej raz dziennie o dany cel i najwyżej dwa pytania dziennie, jedno naraz;
- bez dzisiejszego wpisu nie pytamy o uwagę (nie ma do czego jej dołożyć);
- Bibo widzi tylko czas spędzony w rozmowie z nim i swoje karty, więc „długa sesja” i „porzucone zadania”
  to przybliżenia; dlatego progi są ostrożne.
"""
from __future__ import annotations

import logging
import re
import unicodedata
from datetime import datetime
from pathlib import Path

from . import karta, kontakt, stan, tryb, uwaga

log = logging.getLogger("bibo-tryby")

TAK, NIE = "✅ Tak", "❌ Nie"
ODPOWIEDZI = (TAK, NIE)
PYTANIA = {"bad_day": "Gorszy dzień?", "hyperfocus": "Jesteś w hiperfokusie?", "hypofocus": "Rozproszony dzień?"}
KOLEJNOSC = ("bad_day", "hyperfocus", "hypofocus")

# Próg to suma wag różnych rodzajów sygnałów dla celu. Wyraźna fraza albo sesja >3 h wystarcza sama,
# słabsze cechy (pora, krótkie wiadomości, przeskoki) trzeba zebrać po dwie.
PROG = 2
WAGI = {
    ("phrase", "bad_day"): 2, ("late_hour", "bad_day"): 1, ("short_messages", "bad_day"): 1,
    ("long_session", "hyperfocus"): 2, ("late_hour", "hyperfocus"): 1,
    ("topic_switching", "hypofocus"): 1, ("abandoned_tasks", "hypofocus"): 1,
}
MAKS_PYTAN_DZIENNIE = 2
GODZINA_NOCNA_OD, GODZINA_NOCNA_DO = 23, 5
DLUGA_SESJA_H = 3
KROTKIE_WIADOMOSCI = 0.4       # średnia z 3 ostatnich < 40% typowej
MIN_TYPOWA_DLUGOSC = 40        # przy bardzo krótkich wiadomościach „krótsze niż zwykle” nic nie znaczy
PRZESKOKI_SESJE, PRZESKOKI_MAKS_MIN = 4, 10
PORZUCONE_KARTY = 2
DNI_BEZ_WPISU = 3              # „po 2 dniach bez wpisu” = ostatni wpis 3 doby temu: dwie doby pominięte
DNI_REGENERACJI = 5
ZLE_DNI_MOCNE = 3

FRAZY = [re.compile(p) for p in (
    r"\bnie mam (juz )?sily\b", r"\bnie daje rady\b", r"\bnie dam rady\b", r"\bnie ogarniam\b", r"\bjestem wykonczon",
    r"\bpadam (na twarz|z nog)", r"\bmam dosc\b", r"\bwszystko mnie przytlacza\b", r"\bnic mi sie nie chce\b",
    r"\bnie mam (ani )?energii\b", r"\bjestem (tak |bardzo )?zmeczon", r"\bfatalnie sie czuje\b",
    r"\b(zly|kiepski|okropny|beznadziejny) dzien\b",
)]

WSPARCIE = ("Zauważam, że od kilku dni jest Ci ciężej. Jeśli masz na to ochotę, porozmawiaj o tym z kimś bliskim "
            "albo ze specjalistą — to dobry pomysł, gdy ciężej trwa dłużej, a nie wyrok. Napiszę to tylko ten jeden raz.")


def _norm(tekst: str) -> str:
    t = unicodedata.normalize("NFKD", (tekst or "").lower().replace("ł", "l"))
    return "".join(c for c in t if not unicodedata.combining(c))


def _markup() -> dict:
    return {"keyboard": [[{"text": TAK}, {"text": NIE}]], "one_time_keyboard": True, "resize_keyboard": True}


def _pytanie(cel: str) -> dict:
    return {"text": PYTANIA[cel], "reply_markup": _markup(), "cel": cel}


# --- zbieranie sygnałów -----------------------------------------------------------

def zbierz(w: str, tekst: str, cele: set[str], *, teraz: datetime | None = None, sciezka: Path | None = None,
           sciezka_karty: Path | None = None) -> list[tuple[str, str]]:
    """Sygnały widoczne w tej turze jako pary (rodzaj, cel), tylko dla `cele` (o pozostałe dziś już pytano,
    więc nie liczymy dla nich nic ekstra). Zapisuje samą długość wiadomości, nie treść."""
    teraz = teraz or kontakt.teraz()
    z = kontakt.strefa()
    wyniki: list[tuple[str, str]] = []
    t = _norm(tekst)
    if "bad_day" in cele and any(p.search(t) for p in FRAZY):
        wyniki.append(("phrase", "bad_day"))
    godz = teraz.astimezone(z).hour
    if godz >= GODZINA_NOCNA_OD or godz < GODZINA_NOCNA_DO:
        wyniki += [("late_hour", c) for c in ("bad_day", "hyperfocus") if c in cele]

    tempo = stan.zapisz_dlugosc(w, len(tekst or ""), teraz=teraz, sciezka=sciezka)   # zawsze: buduje typowe tempo usera
    if "bad_day" in cele and tempo["dzis"] is not None and tempo["baza"] is not None \
            and tempo["baza"] >= MIN_TYPOWA_DLUGOSC and tempo["dzis"] < KROTKIE_WIADOMOSCI * tempo["baza"]:
        wyniki.append(("short_messages", "bad_day"))

    if cele & {"hyperfocus", "hypofocus"}:
        s = stan.sesja(w, teraz=teraz, sciezka=sciezka)
        if s:
            if "hyperfocus" in cele and (teraz - datetime.fromisoformat(s["start_sesji"])).total_seconds() >= DLUGA_SESJA_H * 3600:
                wyniki.append(("long_session", "hyperfocus"))
            if "hypofocus" in cele and s["sesje"] >= PRZESKOKI_SESJE and s["sekundy"] / 60 / s["sesje"] < PRZESKOKI_MAKS_MIN:
                wyniki.append(("topic_switching", "hypofocus"))
    if "hypofocus" in cele:
        try:
            dzis = teraz.astimezone(z).date()
            odlozone = [k for k in karta.odczytaj(w, status="odlozona", sciezka=sciezka_karty)
                        if datetime.fromisoformat(k["zaktualizowano"]).astimezone(z).date() == dzis]
            if len(odlozone) >= PORZUCONE_KARTY:
                wyniki.append(("abandoned_tasks", "hypofocus"))
        except Exception:
            log.debug("bibo-tryby: sygnał porzuconych kart", exc_info=True)
    return wyniki


def _mozna_pytac(w: str, cel: str, teraz, sciezka) -> bool:
    d = stan.dzisiejszy(w, teraz=teraz, sciezka=sciezka)
    if cel == "bad_day":
        return not (d and d["cwiartka"] == "recovery")   # user już sam powiedział, że jest ciężko
    return d is not None and d["uwaga"] != cel


def po_turze(w: str, tekst: str, *, teraz: datetime | None = None, sciezka: Path | None = None,
             sciezka_karty: Path | None = None) -> dict | None:
    """Zapisuje sygnały z tury i zwraca pytanie do zadania ({text, reply_markup, cel}) albo None.
    Pytanie oznaczamy jako zadane zanim wyjdzie, więc awaria wysyłki nie powoduje powtórki.
    Koszt: kilka krótkich zapytań po turze, a po wyczerpaniu dziennych pytań tylko zapis długości wiadomości."""
    teraz = teraz or kontakt.teraz()
    st = stan.stan_pytan(w, teraz=teraz, sciezka=sciezka)
    cele = set(KOLEJNOSC) - st["zapytane"] if st["pytan"] < MAKS_PYTAN_DZIENNIE else set()
    istniejace = {(r["rodzaj"], r["cel"]) for r in st["sygnaly"]}
    for rodzaj, cel in zbierz(w, tekst, cele, teraz=teraz, sciezka=sciezka, sciezka_karty=sciezka_karty):
        if (rodzaj, cel) not in istniejace:   # ten sam rodzaj sygnału liczy się raz na dobę
            stan.zapisz_sygnal(w, rodzaj, cel, teraz=teraz, sciezka=sciezka)
            istniejace.add((rodzaj, cel))
    if st["oczekuje"] or not cele:
        return None
    for cel in KOLEJNOSC:
        if cel in cele and sum(WAGI.get((r, c), 0) for r, c in istniejace if c == cel) >= PROG and _mozna_pytac(w, cel, teraz, sciezka):
            stan.oznacz_pytanie_celu(w, cel, teraz=teraz, sciezka=sciezka)
            return _pytanie(cel)
    return None


# --- FR-6: oszacowanie po przerwie ----------------------------------------------------

def oszacowanie(w: str, *, teraz: datetime | None = None, sciezka: Path | None = None) -> dict | None:
    """Pierwsza tura dnia po przerwie ≥ DNI_BEZ_WPISU dób: jedno pytanie z własnym oszacowaniem Bibo.
    Raz na przerwę, bez przypomnień; None, gdy nie ma na czym oprzeć oszacowania."""
    teraz = teraz or kontakt.teraz()
    ostatni, dni = stan.dni_bez_wpisu(w, teraz=teraz, sciezka=sciezka)
    if ostatni is None or dni < DNI_BEZ_WPISU or stan.czy_byla_propozycja_od(w, ostatni, sciezka=sciezka):
        return None
    typowy = stan.typowy_stan(w, teraz=teraz, sciezka=sciezka)
    if typowy is None or not stan.zapisz_oszacowanie(w, typowy, teraz=teraz, sciezka=sciezka):
        return None
    return {"text": f"Od kilku dni nie było wpisu. Moje oszacowanie na podstawie ostatnich dni: {tryb.nazwa(typowy['cwiartka'])}. "
                    "Pasuje na dziś?",
            "reply_markup": _markup()}


# --- odpowiedzi „Tak” / „Nie” ---------------------------------------------------------------

def _gorszy_dzien(w: str, teraz, sciezka, sciezka_karty) -> str:
    """Potwierdzony gorszy dzień: obniżamy tylko przyjemność, energię zostawiamy taką, jak user zadeklarował."""
    d = stan.dzisiejszy(w, teraz=teraz, sciezka=sciezka)
    e = d["energia"] if d else -1
    p = min(d["przyjemnosc"], -1) if d else -1
    r = stan.zapisz_wpis(w, e, p, uwaga=d["uwaga"] if d else "normal", zrodlo="inferred_confirmed", teraz=teraz, sciezka=sciezka)
    try:
        a = karta.aktywna(w, sciezka_karty)
    except Exception:
        a = None
    return f"Zmieniam tryb dnia na {tryb.nazwa(r['cwiartka'])}. {tryb.reakcja(r['cwiartka'], a and a['krok'])}"


def odpowiedz(w: str, tekst: str, *, teraz: datetime | None = None, sciezka: Path | None = None,
              sciezka_karty: Path | None = None) -> dict | None:
    """Obsługa „Tak”/„Nie”. None, gdy nie ma zadanego pytania (wiadomość idzie wtedy do Bibo bez zmian)."""
    teraz = teraz or kontakt.teraz()
    p = stan.oczekujace_pytanie(w, teraz=teraz, sciezka=sciezka)
    if p is None:
        return None
    tak = tekst == TAK
    try:
        if p["typ"] == "oszacowanie":
            stan.odpowiedz_na_oszacowanie(w, tak, teraz=teraz, sciezka=sciezka)
            if not tak:
                from . import siatka
                return {"text": "Dobrze, to wybierz sam. Jedno stuknięcie.", "reply_markup": siatka.klawiatura_siatki()}
            r = stan.zapisz_wpis(w, p["energia"], p["przyjemnosc"], zrodlo="inferred_confirmed", teraz=teraz, sciezka=sciezka)
            return {"text": f"Zapisane: {tryb.nazwa(r['cwiartka'])}.", "reply_markup": {"remove_keyboard": True}}
        cel = p["cel"]
        if not tak:
            stan.odpowiedz_na_cel(w, cel, False, teraz=teraz, sciezka=sciezka)
            return {"text": "Dobrze, zostawiam bez zmian.", "reply_markup": {"remove_keyboard": True}}
        stan.odpowiedz_na_cel(w, cel, True, teraz=teraz, sciezka=sciezka)
        if cel == "bad_day":
            tekst_odp = _gorszy_dzien(w, teraz, sciezka, sciezka_karty)
        else:
            tekst_odp = uwaga.wybierz(w, cel, teraz=teraz, sciezka=sciezka, sciezka_karty=sciezka_karty)
        return {"text": tekst_odp, "reply_markup": {"remove_keyboard": True}}
    except stan.BladStanu as e:
        if e.kod == "brak_wpisu":
            return None
        return {"text": f"Nie zapisałem tego: {e.komunikat}", "reply_markup": {"remove_keyboard": True}}
    except Exception:
        log.warning("bibo-tryby: odpowiedź na pytanie o stan", exc_info=True)
        return {"text": "Nie udało się zapisać — nic nie zostało zmienione. Spróbuj jeszcze raz.", "reply_markup": {"remove_keyboard": True}}


# --- łagodna sugestia wsparcia ----------------------------------------------------------

def sugestia_wsparcia(w: str, *, teraz: datetime | None = None, sciezka: Path | None = None) -> str | None:
    """Raz (najwyżej co 14 dni): po 5 dniach z rzędu w Regeneracji albo przy częstych potwierdzonych gorszych dniach.
    Bez diagnozy, bez nacisku. Zapis „pokazano” następuje przed wysyłką."""
    teraz = teraz or kontakt.teraz()
    if stan.wsparcie_niedawno(w, teraz=teraz, sciezka=sciezka):
        return None
    if stan.regeneracja_z_rzedu(w, teraz=teraz, sciezka=sciezka) < DNI_REGENERACJI \
            and stan.potwierdzone_zle_dni(w, teraz=teraz, sciezka=sciezka) < ZLE_DNI_MOCNE:
        return None
    stan.zapisz_wsparcie(w, teraz=teraz, sciezka=sciezka)
    return WSPARCIE
