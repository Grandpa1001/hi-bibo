"""Test promptów na sucho: każda wymówka z zestawu → Haiku #1 → riposta z pliku → Haiku #2.

Uruchamiane przez `hermes bibo dry-run` (proces Hermesa ma logowanie do modelu).
Wynik: raport Markdown do oceny tonu + podsumowanie liczbowe.
"""
from __future__ import annotations

import re
import time
from pathlib import Path

import yaml

from .tryby import detektyw

ZESTAW = Path(__file__).parent / "tryby" / "wymowki_testowe.yaml"

# Ostrzeżenia stylu (nie blokują gry — do oceny w raporcie).
STYL = [
    (re.compile(r"prokrastyn|unikani|katastrofi", re.I), "etykietuje gracza"),
    (re.compile(r"\b\w+(?:łeś|łaś|łbyś|łabyś)\b|\bgdyby[śm]\s+\w+ł[ao]?\b", re.I), "forma rodzajowa"),
    (re.compile(r"\b(?:feature|feedback|bonus|deadline)\w*", re.I), "anglicyzm"),
    (re.compile(r"zanim się rozmyśl|natychmiast|(?<!nie )musisz", re.I), "presja"),
]
# Limit czasu to presja tylko w kroku („wyślij w ciągu 3 minut”); w pytaniu zawęża zadanie.
PRESJA_W_KROKU = re.compile(r"w ciągu \d+ ?(?:min|sek)|od razu", re.I)


def _sprawdz(przypadek: dict, z: dict, w: dict) -> list[str]:
    o = przypadek.get("oczekiwania") or {}
    uwagi = []
    if o.get("podejrzany") and z["podejrzany"] != o["podejrzany"]:
        uwagi.append(f"podejrzany {z['podejrzany']} ≠ oczekiwany {o['podejrzany']}")
    if o.get("werdykt") and w["werdykt"] != o["werdykt"]:
        uwagi.append(f"werdykt „{w['werdykt']}” ≠ oczekiwany „{o['werdykt']}”")
    if w["werdykt"] in (o.get("nie") or []):
        uwagi.append(f"werdykt „{w['werdykt']}” niedozwolony w tym przypadku")
    calosc = " ".join(str(v) for v in (*z.values(), *w.values())).lower()
    for zakazane in o.get("zakazane") or []:
        if zakazane.lower() in calosc:
            uwagi.append(f"w odpowiedzi jest zakazane „{zakazane}”")
    teksty = {"pytanie": z["pytanie"], "podpowiedź": z["podpowiedz"], "podsumowanie": w["podsumowanie"], "krok": w["krok"]}
    for pole, tekst in teksty.items():
        for wzor, opis in STYL:
            m = wzor.search(tekst)
            if m:
                uwagi.append(f"{opis} w polu {pole}: „{m.group(0)}”")
    m = PRESJA_W_KROKU.search(w["krok"])
    if m:
        uwagi.append(f"presja w polu krok: „{m.group(0)}”")
    for pole, d in (("pytanie", z), ("krok", w)):
        if d["zrodlo"] == "bank":
            uwagi.append(f"{pole} z banku zapasowego (model zawiódł)")
    return uwagi


def uruchom(zestaw: Path = ZESTAW, raport: Path | None = None, wywolaj=None, wypisz=print) -> dict:
    przypadki = yaml.safe_load(zestaw.read_text(encoding="utf-8"))
    linie = [f"# Bibotektyw — test na sucho ({time.strftime('%Y-%m-%d %H:%M')})", ""]
    staty = {"przypadki": 0, "json_za_1": 0, "wywolania": 0, "z_banku": 0, "problemy": 0, "czas_s": 0.0}
    for i, p in enumerate(przypadki, 1):
        t0 = time.time()
        z = detektyw.przesluchaj(p["wymowka"], wywolaj=wywolaj)
        w = detektyw.osadz(p["wymowka"], z["podejrzany"], z["pytanie"], p.get("riposta"),
                           uniewinnienie=bool(p.get("uniewinnienie")), wywolaj=wywolaj)
        dt = time.time() - t0
        uwagi = _sprawdz(p, z, w)
        staty["przypadki"] += 1
        staty["json_za_1"] += (z["proby"] == 1 and z["zrodlo"] == "model") + (w["proby"] == 1 and w["zrodlo"] == "model")
        staty["wywolania"] += z["proby"] + w["proby"]
        staty["z_banku"] += (z["zrodlo"] == "bank") + (w["zrodlo"] == "bank")
        staty["problemy"] += bool(uwagi)
        staty["czas_s"] += dt
        wypisz(f"[{i}/{len(przypadki)}] {p['nazwa']}: {z['emoji']} {z['podejrzany']} → {w['werdykt']}"
               f"{'  ⚠ ' + '; '.join(uwagi) if uwagi else ''}")
        linie += [
            f"## {i}. {p['nazwa']}{'  ⚠' if uwagi else ''}", "",
            f"**Wymówka:** {p['wymowka']}", "",
            f"**Podejrzany:** {z['emoji']} {z['podejrzany']}{' (nowy)' if z['nowy'] else ''} · źródło: {z['zrodlo']}, prób: {z['proby']}  ",
            f"**Pytanie:** {z['pytanie']}  ",
            f"**Podpowiedź:** {z['podpowiedz']}", "",
            f"**Riposta:** {'(gracz kliknął „Ona ma rację”)' if p.get('uniewinnienie') else p.get('riposta', '')}", "",
            f"**Werdykt:** {w['werdykt']} · źródło: {w['zrodlo']}, prób: {w['proby']}  ",
            f"**Podsumowanie:** {w['podsumowanie']}  ",
            f"**Krok:** {w['krok']}", "",
        ]
        if uwagi:
            linie += ["**Uwagi:** " + "; ".join(uwagi), ""]
        linie += [f"_{dt:.1f} s_", ""]
    n = max(1, staty["przypadki"] * 2)
    podsumowanie = (f"Przypadków: {staty['przypadki']} · JSON poprawny za 1. razem: {100 * staty['json_za_1'] / n:.0f}% · "
                    f"wywołań modelu: {staty['wywolania']} · z banku: {staty['z_banku']} · "
                    f"z uwagami: {staty['problemy']} · czas: {staty['czas_s']:.0f} s")
    linie[1:1] = ["", f"**{podsumowanie}**", ""]
    if raport:
        raport.parent.mkdir(parents=True, exist_ok=True)
        raport.write_text("\n".join(linie), encoding="utf-8")
    wypisz("\n" + podsumowanie)
    return staty
