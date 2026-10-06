"""bibo-tryby — tryby Bibo w Telegram Mini App (Bibotektyw).

Wtyczka dotyka Bibo w trzech miejscach, wszystkie opcjonalne:
- `pre_gateway_dispatch` — zapamiętuje źródło rozmowy; jedyne, co przechwytuje, to
  stuknięcia w siatkę stanu dnia właściciela (`siatka.py`, bez udziału modelu); treści kryzysowe
  tylko uruchamiają numery pomocy (`kryzys.py`), a wiadomość dalej idzie do Bibo,
- `pre_llm_call` — dokleja zaległą notatkę z Mini App (fallback) i krótkie
  podsumowanie karty bieżącej sprawy oraz tryb dnia (`tryb.py`; przy okazji liczy turę
  do zaangażowania, same czasy bez treści),
- `post_llm_call` — raz dziennie, po pierwszej turze, pokazuje siatkę stanu dnia (po przerwie
  oszacowanie); zbiera sygnały gorszego dnia i uwagi i zadaje najwyżej jedno pytanie Tak/Nie;
  wykrywa znacznik propozycji `[[tryb:detektyw]]`
  (znacznik z tekstu usuwa `bibo-podpis`; `transform_llm_output` bierze tylko
  pierwszą podmianę, więc nie konkurujemy z podpisem).

Serwer API, tunel Cloudflare i Bot API żyją w osobnym wątku (`uslugi.py`),
który startuje tylko w procesie gatewaya.
"""
from __future__ import annotations

import logging

from . import czat, gateway_most, karta, karta_narzedzie, kontakt, kryzys, siatka, stan, sygnaly, tryb, uslugi, uwaga

log = logging.getLogger("bibo-tryby")
ZNACZNIK = "[[tryb:detektyw]]"
_siatka_dzien: dict[str, object] = {}


def _stan_wlasciciela(user_id: str) -> str | None:
    """Id właściciela, gdy stan dnia jest włączony i dotyczy tego usera; inaczej None."""
    w = karta.wlasciciel()
    return w if w and str(user_id) == w and siatka.wlaczone() else None


def _na_wiadomosc(event=None, **_):
    try:
        src = getattr(event, "source", None)
        platforma = getattr(getattr(src, "platform", None), "value", "")
        if src is not None and platforma == "telegram":
            gateway_most.zapamietaj_zrodlo(src)
            tekst = getattr(event, "text", "") or ""
            if getattr(src, "chat_type", "dm") == "dm" and not gateway_most.wewnetrzna(tekst) and kryzys.wykryj(tekst):
                _kryzys(src)   # bezpieczeństwo przed wszystkim; wiadomość nadal trafia do Bibo (z poleceniem w kontekście)
                return None
            w = _stan_wlasciciela(getattr(src, "user_id", "")) if siatka.rozpoznaj(tekst) else None
            u = uslugi.aktywne()
            if w and u and u.bot and getattr(src, "chat_type", "dm") == "dm":
                odp = siatka.obsluz(w, tekst)
                if odp:
                    u.zleć(siatka.wyslij(w, u, odp))
                    return {"action": "skip", "reason": "bibo-stan: obsłużone przez siatkę"}
    except Exception:
        log.debug("bibo-tryby: pre_gateway_dispatch", exc_info=True)
    return None


def _kryzys(src) -> None:
    """Treści o kryzysie: numery pomocy od razu, a do końca doby żadnego planowania ani pytań o stan."""
    uid = str(getattr(src, "chat_id", "") or getattr(src, "user_id", ""))
    kryzys.zanotuj(str(getattr(src, "user_id", "") or uid))
    u = uslugi.aktywne()
    if u and u.bot and uid:
        u.zleć(kryzys.wyslij(uid, u))


def _pokaz_siatke_gdy_pierwsza_tura(platform: str) -> bool:
    """FR-1: raz dziennie, gdy dziś nie ma wpisu (po przerwie ≥ 3 doby zamiast siatki pada oszacowanie, FR-6).
    Dzień już załatwiony pamiętamy w pamięci procesu, więc kolejne tury tego dnia nie dotykają bazy.
    Zwraca True, gdy wysłano wiadomość."""
    w = karta.wlasciciel()
    if platform != "telegram" or not w or not siatka.wlaczone() or gateway_most.ostatni_user() != w or kryzys.aktywny(w):
        return False
    dzien = kontakt.teraz().astimezone(kontakt.strefa()).date()
    if _siatka_dzien.get(w) == dzien:
        return False
    u = uslugi.aktywne()
    if not (u and u.bot):
        return False   # usługi jeszcze wstają: spróbujemy przy następnej turze
    _siatka_dzien[w] = dzien
    if not stan.czy_pokazac_siatke(w):
        return False
    u.zleć(siatka.wyslij(w, u, sygnaly.oszacowanie(w)))   # None → zwykła siatka
    return True


def _sygnaly_po_turze(platform: str, user_message) -> None:
    """FR-5/12/13 + łagodna sugestia wsparcia. Po turze, więc nie opóźnia odpowiedzi; najwyżej jedna wiadomość."""
    w = karta.wlasciciel()
    if platform != "telegram" or not w or not siatka.wlaczone() or gateway_most.ostatni_user() != w or kryzys.aktywny(w):
        return
    if not isinstance(user_message, str) or gateway_most.wewnetrzna(user_message):
        return   # tura wewnętrzna albo nie tekst: to nie jest aktywność usera
    u = uslugi.aktywne()
    if not (u and u.bot):
        return
    pytanie = sygnaly.po_turze(w, user_message)
    if pytanie:
        u.zleć(siatka.wyslij(w, u, pytanie))
        return
    tekst = sygnaly.sugestia_wsparcia(w)
    if tekst:
        u.zleć(siatka.wyslij(w, u, {"text": tekst, "reply_markup": {"remove_keyboard": True}}))


def _komenda_stan(raw_args: str = "") -> str | None:
    """FR-7: `/stan` pokazuje siatkę; nowy wpis zastępuje tryb z poprzedniego."""
    w = karta.wlasciciel()
    u = uslugi.aktywne()
    if not w or not siatka.wlaczone():
        return "Stan dnia jest niedostępny w tej instancji."
    if not (u and u.bot):
        return "Teraz nie mogę pokazać siatki — spróbuj za chwilę."
    u.zleć(siatka.wyslij(w, u))
    return None


def _tryb_dnia(sender_id: str, user_message=None) -> str | None:
    """FR-3/FR-10: zlicza turę (czasy, bez treści) i zwraca wytyczne trybu dnia — jedno połączenie z bazą.
    Tury wewnętrzne (notatki wtyczki) nie liczą się do aktywności; w dobie kryzysu wytyczne trybu nie wychodzą."""
    w = _stan_wlasciciela(sender_id)
    if not w or kryzys.aktywny(w):
        return None
    try:
        if gateway_most.wewnetrzna(user_message):
            return tryb.kontekst(stan.dzisiejszy(w))
        return tryb.kontekst(stan.rejestruj_ture(w))
    except Exception:
        log.debug("bibo-tryby: tryb dnia", exc_info=True)
        return None


def _komenda_fokus(raw_args: str = "") -> str | None:
    """FR-11: `/fokus` pokazuje rząd stanu uwagi; `/fokus hiper|rozproszony|norma` ustawia od razu."""
    w = karta.wlasciciel()
    u = uslugi.aktywne()
    if not w or not siatka.wlaczone():
        return "Stan uwagi jest niedostępny w tej instancji."
    wybor = uwaga.z_argumentu(raw_args)
    if (raw_args or "").strip() and not wybor:
        return "Podaj: rozproszony, norma albo hiperfokus — albo samo /fokus, a pokażę przyciski."
    try:
        if wybor:
            return uwaga.wybierz(w, wybor)
        if not (u and u.bot):
            return "Teraz nie mogę pokazać przycisków — spróbuj za chwilę."
        if stan.dzisiejszy(w) is None:
            u.zleć(siatka.wyslij(w, u, {"text": "Najpierw wpis na siatce — potem ustawię stan uwagi.",
                                         "reply_markup": siatka.klawiatura_siatki()}))
        else:
            u.zleć(siatka.wyslij(w, u, {"text": "Jak z uwagą?", "reply_markup": siatka.klawiatura_uwagi()}))
    except stan.BladStanu as e:
        if e.kod != "brak_wpisu":
            return f"Nie zapisałem tego: {e.komunikat}"
        if u and u.bot:
            u.zleć(siatka.wyslij(w, u, {"text": "Najpierw wpis na siatce — potem ustawię stan uwagi.",
                                         "reply_markup": siatka.klawiatura_siatki()}))
    except Exception:
        log.warning("bibo-tryby: /fokus", exc_info=True)
        return "Nie udało się zapisać — stan uwagi NIE został zmieniony."
    return None


def _przed_tura(platform: str = "", sender_id: str = "", user_message=None, **_):
    try:
        if platform == "telegram":
            czesci = [kryzys.kontekst(sender_id), gateway_most.odbierz_notatki(), karta_narzedzie.podsumowanie(sender_id),
                      _tryb_dnia(sender_id, user_message)]
            czesci = [c for c in czesci if c]
            if czesci:
                return {"context": "\n\n".join(czesci)}
    except Exception:
        log.debug("bibo-tryby: pre_llm_call", exc_info=True)
    return None


def _po_turze(assistant_response: str = "", platform: str = "", user_message=None, **_):
    try:
        if not _pokaz_siatke_gdy_pierwsza_tura(platform):
            _sygnaly_po_turze(platform, user_message)
    except Exception:
        log.debug("bibo-tryby: siatka i sygnały po turze", exc_info=True)
    try:
        if platform != "telegram" or ZNACZNIK not in (assistant_response or ""):
            return
        u = uslugi.aktywne()
        uid = gateway_most.ostatni_user()
        if u and uid:
            u.zleć(czat.wyslij_propozycje(uid, u))
        else:
            log.info("bibo-tryby: znacznik propozycji wykryty, ale usługi/user niedostępne")
    except Exception:
        log.debug("bibo-tryby: post_llm_call", exc_info=True)


def _komenda_diagnostyka(raw_args: str = "") -> str:
    u = uslugi.aktywne()
    d = gateway_most.diagnostyka()
    if u is None:
        return "bibo-tryby: usługi nie działają w tym procesie (czy gateway jest uruchomiony?)."
    return (f"bibo-tryby {u.ust.get('port')} · tunel: {u.url or 'brak (sprawdź cloudflared)'}\n"
            f"gateway: runner={d['runner']} pętla={d['petla']} telegram={d['adapter_telegram']}\n"
            f"Otwórz Mini App przyciskiem „Bibo” obok pola wiadomości.")


def register(ctx):
    try:
        ctx.register_auxiliary_task(
            "bibo_tryby", display_name="Bibo — tryby",
            description="Krótkie wywołania gier Bibo (Bibotektyw): pytanie śledczego i werdykt.",
            defaults={"provider": "anthropic", "model": "claude-haiku-4-5"})
    except Exception as e:
        log.warning("bibo-tryby: nie zarejestrowano zadania auxiliary: %s", e)
    try:
        karta_narzedzie.zarejestruj(ctx)
    except Exception as e:
        log.warning("bibo-tryby: nie zarejestrowano narzędzia bibo_karta: %s", e)
    ctx.register_hook("pre_gateway_dispatch", _na_wiadomosc)
    ctx.register_hook("pre_llm_call", _przed_tura)
    ctx.register_hook("post_llm_call", _po_turze)
    ctx.register_command("stan", _komenda_stan, description="Bibo: jak się dziś czujesz (siatka stanu)")
    ctx.register_command("fokus", _komenda_fokus, description="Bibo: stan uwagi (rozproszony / norma / hiperfokus)",
                         args_hint="[rozproszony|norma|hiperfokus]")
    ctx.register_command("bt_diag", _komenda_diagnostyka, description="Bibotektyw: diagnostyka wtyczki")
    uslugi.uruchom_gdy_gateway()
