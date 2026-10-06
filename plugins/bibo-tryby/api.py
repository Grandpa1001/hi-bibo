"""Trasy HTTP wtyczki: front Mini App (static/), /health, /api/*, diagnostyka /spike.

Kontrakt API i kody błędów: docs/BIBOTEKTYW-DEV.md §8.
"""
from __future__ import annotations

import asyncio
import html
import json
import logging
from datetime import timedelta
from pathlib import Path

from aiohttp import web

from . import auth, czat, gateway_most, magazyn
from .telegram import BladTelegrama, EFEKT_KONFETTI, token
from .llm import BladModelu
from .tryby import detektyw

log = logging.getLogger("bibo-tryby")
ZASOBY = Path(__file__).parent / "zasoby"
STATIC = Path(__file__).parent / "static"      # miniapp/dist kopiowany przez install.sh / aktualizuj.sh
WERSJA = "0.4.0"
API_GOTOWE = True

WERDYKT_ETYKIETY = {"obalona": "💥 WYMÓWKA OBALONA",
                    "czesciowo": "⚖️ WERDYKT: CZĘŚCIOWO",
                    "uniewinniona": "🟢 WYMÓWKA UNIEWINNIONA"}
WERDYKT_KARTA = {"obalona": "radosc.png", "czesciowo": "mysli.png", "uniewinniona": "skupienie.png"}


def trasy(app: web.Application) -> None:
    app.router.add_get("/health", health)
    app.router.add_get("/spike", spike_strona)
    app.router.add_post("/api/spike/kto", spike_kto)
    app.router.add_post("/api/spike/haiku", spike_haiku)
    app.router.add_post("/api/spike/karta", spike_karta)
    app.router.add_post("/api/spike/bibo", spike_bibo)
    app.router.add_post("/api/spike/propozycja", spike_propozycja)
    app.router.add_get("/api/hub", api_hub)
    app.router.add_post("/api/sprawa", api_sprawa_nowa)
    app.router.add_get("/api/sprawa/{id}", api_sprawa_dane)
    app.router.add_post("/api/sprawa/{id}/zeznanie", api_zeznanie)
    app.router.add_post("/api/sprawa/{id}/riposta", api_riposta)
    app.router.add_post("/api/sprawa/{id}/zamknij", api_zamknij)
    app.router.add_post("/api/sprawa/{id}/kontrola", api_kontrola)
    app.router.add_get("/api/kartoteka", api_kartoteka)
    from . import api_stan
    api_stan.trasy(app)
    app.router.add_get("/{sciezka:(?!api/).*}", front)


async def front(request: web.Request) -> web.StreamResponse:
    """Pliki frontu; nieznana ścieżka → index.html. Bez wyjścia poza katalog static/."""
    if not (STATIC / "index.html").is_file():
        return await spike_strona(request)
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
    "sprawa": "Nie znaleziono tej sprawy. Może przedawniła się (30 min bez zamknięcia).",
    "stan": "Ta sprawa jest w innym etapie — otwórz ją od początku.",
    "dane": "Coś się nie zgadza w danych. Spróbuj ponownie.",
    "wylaczone": "Ta funkcja jest wyłączona w ustawieniach tej instancji.",
    "brak_wpisu": "Najpierw wpis na siatce — bez niego nie ma trybu dnia.",
    "limit": "Za dużo zapytań w tej godzinie — spróbuj później.",
    "model": "Nie udało się teraz dokończyć. Możesz spróbować jeszcze raz albo wyjść — nic się nie zapisało.",
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


def _wywolaj(request: web.Request):
    """Atrapa Haiku dla testów: request.app["wywolaj_haiku"]. Domyślnie None → prawdziwy call_llm."""
    return request.app.get("wywolaj_haiku")


async def _haiku(request: web.Request, uid: str, fn, *args, **kwargs) -> dict:
    """Uruchamia model w executorze, z limitem 30/h. Awaria modelu → 503 (bez zastępczej treści)."""
    if not magazyn.sprawdz_i_zapisz_limit(uid):
        raise BladApi(429, "limit")
    kwargs["wywolaj"] = _wywolaj(request)
    try:
        return await asyncio.get_running_loop().run_in_executor(None, lambda: fn(*args, **kwargs))
    except BladModelu:
        raise BladApi(503, "model")


def _znajdz_sprawe(request: web.Request, uid: str) -> tuple[str, dict, dict]:
    sid = request.match_info["id"]
    stan = magazyn.sprawy()
    magazyn.wygas_stare(stan)
    sprawa = stan.get(sid)
    if not sprawa or str(sprawa.get("user")) != uid:
        magazyn.zapisz_sprawy(stan)
        raise BladApi(404, "sprawa")
    return sid, sprawa, stan


def _oczekuj_etapu(sprawa: dict, etap: str) -> None:
    if sprawa.get("etap") != etap:
        raise BladApi(409, "stan")


def _podejrzany_widok(kart: dict, nazwa: str, nowy: bool, emoji: str) -> dict:
    p = kart["podejrzani"].get(nazwa, {})
    return {"nazwa": nazwa, "emoji": p.get("emoji") or emoji, "nowy": nowy,
            "zatrzymanie": p.get("zatrzymania", 0), "ostatnio": p.get("ostatnio")}


def _tekst_notatki(numer: int, sprawa: dict, kart: dict) -> str:
    p = kart["podejrzani"].get(sprawa["podejrzany"], {})
    kontrola = sprawa.get("kontrola")
    czesci = [
        "[bibo-tryby · notatka systemowa, nie wiadomość od usera]",
        f"Sprawa #{numer} w Bibotektywie zamknięta przed chwilą. User widzi już kartę wyniku.",
        f"Podejrzany: {sprawa['podejrzany']} ({p.get('zatrzymania', 0)}. zatrzymanie).",
        f"Wymówka: „{sprawa.get('wymowka', '')}”",
        f"Werdykt: {sprawa.get('werdykt', '')}. Podsumowanie: „{sprawa.get('podsumowanie', '')}”",
        f"Krok: „{sprawa.get('krok', '')}”." + (f" Kontrola: {kontrola[11:16]}." if kontrola else " Kontrola: brak."),
        "Napisz JEDNĄ krótką wiadomość (max 200 znaków), jak kumpel, który trzyma za słowo — "
        "nawiąż do kroku, nie powtarzaj karty, bez pochwał. Jeśli ten podejrzany wraca "
        "≥3 raz, zapisz wzorzec w memory.",
    ]
    return "\n".join(czesci)


# --- middleware --------------------------------------------------------------

@web.middleware
async def bledy(request: web.Request, handler):
    try:
        return await handler(request)
    except BladApi as e:
        return _blad(e.status, e.kod, e.komunikat)
    except web.HTTPRequestEntityTooLarge:
        return _blad(422, "dane", "Wiadomość jest za długa.")


# --- /health / /api/hub ------------------------------------------------------

async def health(request: web.Request) -> web.Response:
    return web.json_response({"ok": True, "wersja": WERSJA})


async def api_hub(request: web.Request) -> web.Response:
    uid = _uid(request)
    kart = magazyn.kartoteka()
    stan = magazyn.sprawy()
    magazyn.wygas_stare(stan)
    magazyn.zapisz_sprawy(stan)

    zamkniete = sum(1 for s in kart["sprawy"] if s.get("werdykt"))
    obalone = sum(1 for s in kart["sprawy"] if s.get("werdykt") == "obalona")
    najczestszy = None
    if kart["podejrzani"]:
        n, d = max(kart["podejrzani"].items(),
                   key=lambda kv: (kv[1].get("zatrzymania", 0), kv[0]))
        if d.get("zatrzymania", 0) > 0:
            najczestszy = {"nazwa": n, "emoji": d.get("emoji", "🌫️")}

    aktywna = magazyn.aktywna_sprawa(stan, uid)
    aktywna_widok = None
    if aktywna:
        aktywna_widok = {"id": aktywna["id"], "numer": aktywna.get("numer"), "etap": aktywna.get("etap")}

    tryby = [{"id": "detektyw", "nazwa": detektyw.NAZWA, "opis": detektyw.OPIS, "aktywny": True}]
    return web.json_response({
        "tryby": tryby,
        "statystyki": {"zamkniete": zamkniete, "obalone": obalone, "najczestszy": najczestszy},
        "aktywna_sprawa": aktywna_widok,
    })


# --- sprawy ------------------------------------------------------------------

async def api_sprawa_nowa(request: web.Request) -> web.Response:
    uid = _uid(request)
    stan = magazyn.sprawy()
    magazyn.wygas_stare(stan)
    # jedna aktywna sprawa naraz — porzucamy poprzednią niezamkniętą
    for sid, sprawa in list(stan.items()):
        if str(sprawa.get("user")) == uid and sprawa.get("etap") != "zamknieta":
            del stan[sid]

    kart = magazyn.kartoteka()
    numer = int(kart.get("nastepny_numer", 1))
    kart["nastepny_numer"] = numer + 1
    magazyn.zapisz_kartoteke(kart)

    sid = magazyn.nowe_id()
    while sid in stan:
        sid = magazyn.nowe_id()
    stan[sid] = {"numer": numer, "user": uid, "etap": "nowa",
                 "ostatnia_akcja": magazyn.iso(), "kontrola": None, "kontrola_wyslana": False}
    magazyn.zapisz_sprawy(stan)
    return web.json_response({"id": sid, "numer": numer}, status=201)


async def api_sprawa_dane(request: web.Request) -> web.Response:
    uid = _uid(request)
    _, sprawa, _ = _znajdz_sprawe(request, uid)
    p = None
    if sprawa.get("podejrzany"):
        kart = magazyn.kartoteka()
        emoji = kart["podejrzani"].get(sprawa["podejrzany"], {}).get("emoji", "🌫️")
        p = {"nazwa": sprawa["podejrzany"], "emoji": emoji}
    return web.json_response({"id": request.match_info["id"], "numer": sprawa.get("numer"),
                              "etap": sprawa.get("etap"),
                              "podejrzany": p, "krok": sprawa.get("krok"),
                              "werdykt": sprawa.get("werdykt"),
                              "kontrola": sprawa.get("kontrola")})


async def api_zeznanie(request: web.Request) -> web.Response:
    uid = _uid(request)
    sid, sprawa, stan = _znajdz_sprawe(request, uid)
    _oczekuj_etapu(sprawa, "nowa")
    dane = await _cialo(request)
    wymowka = dane.get("wymowka")
    if not isinstance(wymowka, str) or not wymowka.strip():
        raise BladApi(422, "dane", "Napisz wymówkę — jedno lub dwa zdania wystarczą.")
    if len(wymowka) > detektyw.MAKS_WYMOWKA:
        raise BladApi(422, "dane", f"Wymówka może mieć maks. {detektyw.MAKS_WYMOWKA} znaków.")

    kart = magazyn.kartoteka()
    wynik = await _haiku(request, uid, detektyw.przesluchaj, wymowka,
                         znani=magazyn.znani_podejrzani(kart))
    nazwa = wynik["podejrzany"]
    if wynik.get("nowy") and nazwa not in kart["podejrzani"]:
        if len(kart["podejrzani"]) >= magazyn.MAKS_PODEJRZANYCH:
            # kartoteka pełna — mapujemy na istniejącego (bez etykietki „nowy”)
            nazwa = detektyw._zgadnij_podejrzanego(wymowka)
            wynik["nowy"] = False
        else:
            kart["podejrzani"][nazwa] = {"emoji": wynik.get("emoji", "🌫️"),
                                         "zatrzymania": 0, "obalone": 0, "ruszylo": 0, "ostatnio": None}

    p = kart["podejrzani"].setdefault(nazwa, {"emoji": wynik.get("emoji", "🌫️"),
                                              "zatrzymania": 0, "obalone": 0, "ruszylo": 0, "ostatnio": None})
    p["zatrzymania"] = int(p.get("zatrzymania", 0)) + 1
    p["ostatnio"] = magazyn.data()
    magazyn.zapisz_kartoteke(kart)

    sprawa.update({"etap": "zeznanie", "wymowka": wymowka, "podejrzany": nazwa,
                   "pytanie": wynik["pytanie"], "podpowiedz": wynik["podpowiedz"],
                   "ostatnia_akcja": magazyn.iso()})
    stan[sid] = sprawa
    magazyn.zapisz_sprawy(stan)

    return web.json_response({"podejrzany": _podejrzany_widok(kart, nazwa, wynik.get("nowy", False),
                                                              wynik.get("emoji", "🌫️")),
                              "pytanie": wynik["pytanie"], "podpowiedz": wynik["podpowiedz"],
                              "zrodlo": wynik["zrodlo"]})


async def api_riposta(request: web.Request) -> web.Response:
    uid = _uid(request)
    sid, sprawa, stan = _znajdz_sprawe(request, uid)
    _oczekuj_etapu(sprawa, "zeznanie")
    dane = await _cialo(request)
    uniewinnienie = bool(dane.get("uniewinnienie"))
    riposta = dane.get("riposta")
    if not uniewinnienie:
        if not isinstance(riposta, str) or not riposta.strip():
            raise BladApi(422, "dane", "Odpowiedz jednym zdaniem albo wybierz „Ona ma rację”.")
        if len(riposta) > detektyw.MAKS_WYMOWKA:
            raise BladApi(422, "dane", f"Riposta może mieć maks. {detektyw.MAKS_WYMOWKA} znaków.")
    else:
        riposta = None

    wynik = await _haiku(request, uid, detektyw.osadz, sprawa["wymowka"], sprawa["podejrzany"],
                         sprawa["pytanie"], riposta=riposta, uniewinnienie=uniewinnienie)

    sprawa.update({"etap": "werdykt", "riposta": riposta or "",
                   "uniewinnienie": uniewinnienie, "werdykt": wynik["werdykt"],
                   "podsumowanie": wynik["podsumowanie"], "krok": wynik["krok"],
                   "ostatnia_akcja": magazyn.iso()})
    stan[sid] = sprawa
    magazyn.zapisz_sprawy(stan)

    return web.json_response({"werdykt": wynik["werdykt"], "podsumowanie": wynik["podsumowanie"],
                              "krok": wynik["krok"], "zrodlo": wynik["zrodlo"]})


async def api_zamknij(request: web.Request) -> web.Response:
    uid = _uid(request)
    sid, sprawa, stan = _znajdz_sprawe(request, uid)
    _oczekuj_etapu(sprawa, "werdykt")
    dane = await _cialo(request)
    ust = magazyn.ustawienia()
    minuty = dane.get("kontrola_min", ust.get("kontrola_min", 10))
    if minuty is not None:
        try:
            minuty = int(minuty)
        except (TypeError, ValueError):
            raise BladApi(422, "dane")
        if not 1 <= minuty <= 24 * 60:
            raise BladApi(422, "dane")
        kontrola_iso = magazyn.iso(magazyn.teraz() + timedelta(minutes=minuty))
    else:
        kontrola_iso = None

    kart = magazyn.kartoteka()
    p = kart["podejrzani"].setdefault(sprawa["podejrzany"], {"emoji": "🌫️", "zatrzymania": 1,
                                                             "obalone": 0, "ruszylo": 0, "ostatnio": None})
    if sprawa["werdykt"] == "obalona":
        p["obalone"] = int(p.get("obalone", 0)) + 1
    kart["sprawy"].append({
        "numer": sprawa["numer"], "data": magazyn.iso(), "podejrzany": sprawa["podejrzany"],
        "wymowka": sprawa["wymowka"], "pytanie": sprawa["pytanie"],
        "riposta": sprawa.get("riposta", ""), "werdykt": sprawa["werdykt"],
        "podsumowanie": sprawa["podsumowanie"], "krok": sprawa["krok"],
        "ruszylo": None,
    })
    sprawa.update({"etap": "zamknieta", "kontrola": kontrola_iso, "kontrola_wyslana": False,
                   "ostatnia_akcja": magazyn.iso()})
    stan[sid] = sprawa
    notatka = _tekst_notatki(sprawa["numer"], sprawa, kart)
    kart["notatka_dla_bibo"] = notatka
    magazyn.zapisz_kartoteke(kart)
    magazyn.zapisz_sprawy(stan)

    u = request.app.get("uslugi")
    if u is not None and getattr(u, "bot", None):
        asyncio.create_task(czat.zakoncz_sprawe(uid, {"id": sid, **sprawa}, notatka, u))

    return web.json_response({"ok": True, "kontrola": kontrola_iso})


async def api_kontrola(request: web.Request) -> web.Response:
    uid = _uid(request)
    sid, sprawa, stan = _znajdz_sprawe(request, uid)
    if sprawa.get("etap") != "zamknieta":
        raise BladApi(409, "stan")
    dane = await _cialo(request)
    if "ruszylo" not in dane or not isinstance(dane["ruszylo"], bool):
        raise BladApi(422, "dane")
    ruszylo = dane["ruszylo"]

    kart = magazyn.kartoteka()
    for wpis in kart["sprawy"]:
        if wpis.get("numer") == sprawa.get("numer"):
            wpis["ruszylo"] = ruszylo
            break
    p = kart["podejrzani"].get(sprawa["podejrzany"])
    if ruszylo and p:
        p["ruszylo"] = int(p.get("ruszylo", 0)) + 1
    magazyn.zapisz_kartoteke(kart)

    # po odbytej kontroli sprawa może wypaść ze `sprawy.json`
    del stan[sid]
    magazyn.zapisz_sprawy(stan)

    if not ruszylo:
        u = request.app.get("uslugi")
        if u is not None:
            asyncio.create_task(czat.zapytaj_co_blokuje(uid, sprawa))
    return web.json_response({"ok": True})


async def api_kartoteka(request: web.Request) -> web.Response:
    _uid(request)
    kart = magazyn.kartoteka()
    podejrzani = [{"nazwa": n, **d} for n, d in kart["podejrzani"].items()]
    podejrzani.sort(key=lambda x: (-x.get("zatrzymania", 0), x["nazwa"]))
    return web.json_response({"podejrzani": podejrzani, "sprawy": kart["sprawy"]})


# --- M0: diagnostyka integracji ----------------------------------------------

async def spike_kto(request: web.Request) -> web.Response:
    uid = _uid(request)
    u = request.app["uslugi"]
    return web.json_response({"ok": True, "user": uid, "url": u.url, "gateway": gateway_most.diagnostyka()})


async def spike_haiku(request: web.Request) -> web.Response:
    _uid(request)

    def wywolaj():
        from agent.auxiliary_client import call_llm
        r = call_llm(task="bibo_tryby", max_tokens=80, temperature=0, messages=[
            {"role": "system", "content": 'Odpowiedz wyłącznie JSON: {"ok": true, "slowo": str}'},
            {"role": "user", "content": "Jedno polskie słowo kojarzące się z detektywem."}])
        return r.choices[0].message.content, getattr(r, "model", None)

    try:
        tekst, model = await asyncio.get_running_loop().run_in_executor(None, wywolaj)
        return web.json_response({"ok": True, "odpowiedz": tekst, "model": model})
    except Exception as e:
        log.warning("bibo-tryby: haiku spike: %s", e)
        return _blad(503, "model", f"{type(e).__name__}: {e}"[:300])


async def spike_karta(request: web.Request) -> web.Response:
    uid = _uid(request)
    u = request.app["uslugi"]
    try:
        await u.bot.karta(uid, str(ZASOBY / "radosc.png"),
                          "<b>📁 SPRAWA #0 · TEST</b>\n💥 WYMÓWKA OBALONA\n👣 <b>Test karty wyniku z efektem</b>",
                          efekt=EFEKT_KONFETTI)
        return web.json_response({"ok": True})
    except BladTelegrama as e:
        return _blad(502, "telegram", str(e))


async def spike_bibo(request: web.Request) -> web.Response:
    uid = _uid(request)
    tekst = ("[bibo-tryby · notatka systemowa, nie wiadomość od usera]\n"
             "To test wtyczki Bibotektyw (M0). Odpowiedz userowi jednym krótkim zdaniem, "
             "że dostałeś notatkę z Mini App i wszystko działa.")
    sposob = await gateway_most.wstrzyknij(uid, tekst)
    return web.json_response({"ok": True, "sposob": sposob})


async def spike_propozycja(request: web.Request) -> web.Response:
    uid = _uid(request)
    u = request.app["uslugi"]
    try:
        await u.bot.wiadomosc_z_aplikacja(uid, "🕵️ (test) Brzmi jak klasyczny zator. Otwieramy śledztwo?",
                                          "🔍 Otwieramy", (u.url or "") + ("" if API_GOTOWE else "/?mock=1"))
        return web.json_response({"ok": True})
    except BladTelegrama as e:
        return _blad(502, "telegram", str(e))


async def spike_strona(request: web.Request) -> web.Response:
    return web.Response(text=_STRONA.replace("{{WERSJA}}", html.escape(WERSJA)),
                        content_type="text/html", headers={"Cache-Control": "no-store"})


_STRONA = """<!doctype html><html lang="pl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>Bibotektyw · M0</title>
<script src="https://telegram.org/js/telegram-web-app.js"></script>
<style>
body{font:15px/1.45 system-ui,sans-serif;margin:0;padding:16px;background:#F2F2F2;color:#111}
h1{font-size:20px;margin:0 0 4px;color:#009688}p{margin:0 0 12px;color:#555}
button{display:block;width:100%;margin:8px 0;padding:12px;border:2px solid #000;border-radius:8px;
background:#fff;font:600 15px system-ui;text-align:left}
pre{white-space:pre-wrap;word-break:break-word;background:#fff;border:1px solid #ddd;border-radius:8px;
padding:10px;font-size:12px;min-height:60px}
</style></head><body>
<h1>Bibotektyw · diagnostyka M0</h1><p>Wersja wtyczki {{WERSJA}}. Klikaj po kolei i przepisz wyniki.</p>
<button data-t="kto">1. Podpis Telegrama i stan gatewaya</button>
<button data-t="haiku">2. Haiku przez logowanie Hermesa</button>
<button data-t="karta">3. Karta wyniku z konfetti (sprawdź czat)</button>
<button data-t="propozycja">4. Wiadomość z przyciskiem Mini App (sprawdź czat)</button>
<button data-t="bibo">5. Notatka do Bibo → Bibo odpisuje w czacie</button>
<button id="haptic">6. Wibracja (haptyka)</button>
<pre id="out">Telegram WebApp: …</pre>
<script>
const tg = window.Telegram && Telegram.WebApp; const out = document.getElementById('out');
function log(x){ out.textContent = typeof x === 'string' ? x : JSON.stringify(x, null, 2); }
if (tg) { tg.ready(); tg.expand();
  try { tg.setHeaderColor('#FFFFFF'); tg.setBackgroundColor('#F2F2F2'); } catch(e) {}
  log({wersja_webapp: tg.version, platforma: tg.platform, initData: tg.initData ? 'jest' : 'BRAK (otwórz z Telegrama)'}); }
else log('Brak Telegram.WebApp — otwórz stronę z bota.');
document.querySelectorAll('[data-t]').forEach(b => b.onclick = async () => {
  log('…');
  try { const r = await fetch('/api/spike/' + b.dataset.t, {method:'POST',
          headers: {'X-Init-Data': tg ? tg.initData : ''}});
        log({status: r.status, ...(await r.json().catch(() => ({})))}); }
  catch (e) { log(String(e)); } });
document.getElementById('haptic').onclick = () => {
  try { tg.HapticFeedback.notificationOccurred('success'); log('haptyka: wysłana'); } catch(e) { log(String(e)); } };
</script></body></html>"""
