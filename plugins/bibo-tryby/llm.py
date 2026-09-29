"""Wywołanie Haiku przez Hermesa → JSON → walidacja → jedna ponowna próba.

Zwraca `(dane, proby)`: `dane` to zwalidowany słownik albo None (wtedy tryb
zgłasza `BladModelu` — bez zastępczej treści), `proby` to liczba wywołań modelu (do raportu na sucho).
"""
from __future__ import annotations

import json
import logging
import re
from typing import Callable

log = logging.getLogger("bibo-tryby")

Wywolanie = Callable[[list[dict], float, int], str]
Walidator = Callable[[dict], dict]


class BladModelu(Exception):
    """Model nie dał użytecznej odpowiedzi. Zamiast zastępczego werdyktu
    użytkownik dostaje neutralny komunikat i może ponowić albo wyjść."""


class BladWalidacji(ValueError):
    pass


class BladStylu(BladWalidacji):
    """Odpowiedź poprawna, ale z usterką stylu: prosimy o poprawkę, a przy ostatniej
    próbie przyjmujemy ją mimo to (styl nie może kończyć gry błędem)."""

    def __init__(self, komunikat: str, dane: dict):
        super().__init__(komunikat)
        self.dane = dane


def wywolaj_haiku(messages: list[dict], temperature: float, max_tokens: int) -> str:
    """Domyślne wywołanie: zadanie auxiliary `bibo_tryby` (logowanie Hermesa, model z konfiguracji)."""
    from agent.auxiliary_client import call_llm
    r = call_llm(task="bibo_tryby", messages=messages, temperature=temperature, max_tokens=max_tokens)
    return r.choices[0].message.content or ""


_BLOK = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.S)


def wyciagnij_json(tekst: str) -> dict:
    """JSON wprost, w bloku ```json``` albo pierwszy obiekt {...} w tekście."""
    tekst = (tekst or "").strip()
    kandydaci = [tekst]
    m = _BLOK.search(tekst)
    if m:
        kandydaci.append(m.group(1))
    a, b = tekst.find("{"), tekst.rfind("}")
    if 0 <= a < b:
        kandydaci.append(tekst[a:b + 1])
    for k in kandydaci:
        try:
            d = json.loads(k)
            if isinstance(d, dict):
                return d
        except json.JSONDecodeError:
            continue
    raise BladWalidacji("odpowiedź nie jest obiektem JSON")


def zapytaj(system: str, user: str, waliduj: Walidator, *, temperature: float,
            max_tokens: int = 300, wywolaj: Wywolanie | None = None, proby: int = 2) -> tuple[dict | None, int]:
    wywolaj = wywolaj or wywolaj_haiku
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    z_usterka: dict | None = None   # poprawna treść z usterką stylu — lepsza niż błąd
    for nr in range(1, proby + 1):
        try:
            tekst = wywolaj(messages, temperature, max_tokens)
        except Exception as e:
            log.warning("bibo-tryby: model niedostępny (%s: %s)", type(e).__name__, e)
            return z_usterka, nr
        try:
            return waliduj(wyciagnij_json(tekst)), nr
        except BladStylu as e:
            z_usterka = e.dane
            if nr == proby:
                return e.dane, nr
            log.info("bibo-tryby: próba %s — usterka stylu: %s", nr, e)
            messages = messages + [
                {"role": "assistant", "content": tekst[:2000]},
                {"role": "user", "content": f"Popraw tylko to: {e}. Odpowiedz ponownie samym obiektem JSON."},
            ]
        except BladWalidacji as e:
            log.info("bibo-tryby: próba %s odrzucona: %s", nr, e)
            messages = messages + [
                {"role": "assistant", "content": tekst[:2000]},
                {"role": "user", "content": f"Ta odpowiedź jest niepoprawna: {e}. "
                                            "Odpowiedz jeszcze raz, wyłącznie poprawnym obiektem JSON wg schematu."},
            ]
    return z_usterka, proby
