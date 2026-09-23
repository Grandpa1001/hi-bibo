#!/usr/bin/env python3
"""Bibo — raport: co wie, ile kosztuje, czego się nauczył, jaki ma plan.

    python3 $HERMES_HOME/scripts/bibo_raport.py            # pełny raport (0 tokenów)
    python3 $HERMES_HOME/scripts/bibo_raport.py --dni 14   # okno zużycia
    python3 $HERMES_HOME/scripts/bibo_raport.py --opinia   # + opinia Bibo o Tobie (1 wywołanie modelu)

Czyta tylko lokalne pliki Hermesa (state.db, memories/). Nic nie zmienia,
poza dopisaniem dziennego „zdjęcia” licznika do local/bibo_usage.jsonl.
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import time
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

HOME = Path(os.environ.get("HERMES_HOME") or Path(__file__).resolve().parent.parent)
DB = HOME / "state.db"
SNAPSHOTS = HOME / "local" / "bibo_usage.jsonl"

# Cennik API ($ za 1 mln tokenów) — używany, gdy Hermes nie policzył kosztu
# (np. przy logowaniu kontem Claude). Cache: odczyt 0.1x, zapis 1h 2x.
PRICES = {"sonnet-5": (2.0, 10.0), "sonnet-4-6": (3.0, 15.0), "haiku-4-5": (1.0, 5.0),
          "opus-5": (5.0, 25.0), "fable-5": (10.0, 50.0)}


def price(model: str, inp: int, out: int, cr: int, cw: int) -> float:
    p = next((v for k, v in PRICES.items() if k in (model or "")), PRICES["sonnet-5"])
    return (inp * p[0] + out * p[1] + cr * p[0] * 0.1 + cw * p[0] * 2) / 1e6


def give_back(path: Path) -> None:
    """Uruchomiony jako root (Docker): oddaj plik właścicielowi katalogu Hermesa,
    inaczej cron działający jako `hermes` nie dopisze kolejnego zdjęcia."""
    if os.geteuid() == 0:
        st = HOME.stat()
        for p in (path.parent, path):
            try:
                os.chown(p, st.st_uid, st.st_gid)
            except OSError:
                pass


def db() -> sqlite3.Connection:
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True, timeout=5)
    con.row_factory = sqlite3.Row
    return con


def h(title: str) -> None:
    print(f"\n\033[1m━━ {title} ━━\033[0m")


def n(x: float) -> str:
    """Liczba z odstępami tysięcy: 12 345."""
    return f"{int(x):,}".replace(",", " ")


def day(ts: float) -> str:
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d")


# ---------------------------------------------------------------- a) dane
def read_memory() -> dict[str, str]:
    out = {}
    for name in ("USER.md", "MEMORY.md"):
        p = HOME / "memories" / name
        out[name] = p.read_text(encoding="utf-8").strip() if p.exists() else ""
    return out


def section_data(mem: dict[str, str]) -> None:
    h("a) Co Bibo o Tobie zebrał")
    limits = {"USER.md": 2500, "MEMORY.md": 3000}
    labels = {"USER.md": "Profil (kim jesteś)", "MEMORY.md": "Notatki (obietnice, wzorce, wątki)"}
    for name, text in mem.items():
        fill = len(text) * 100 // limits[name]
        print(f"\n{labels[name]} — {name}, {len(text)}/{limits[name]} znaków ({fill}%)")
        if not text:
            print("  (pusto)")
            continue
        for entry in text.split("§"):
            entry = entry.strip()
            if entry:
                print("  • " + entry.replace("\n", "\n    "))


# ------------------------------------------------------------- b) zużycie
def usage_rows(con) -> list[dict]:
    """Zużycie per sesja + zadanie (rozmowa, streszczanie, ...)."""
    try:
        rows = con.execute(
            "SELECT s.id, s.source, s.started_at, u.model, u.task, u.api_call_count AS calls, "
            "u.input_tokens AS inp, u.output_tokens AS out, u.cache_read_tokens AS cr, "
            "u.cache_write_tokens AS cw, u.estimated_cost_usd AS est, u.last_seen "
            "FROM session_model_usage u JOIN sessions s ON s.id = u.session_id"
        ).fetchall()
    except sqlite3.Error:
        rows = con.execute(
            "SELECT id, source, started_at, model, '' AS task, api_call_count AS calls, "
            "input_tokens AS inp, output_tokens AS out, cache_read_tokens AS cr, "
            "cache_write_tokens AS cw, estimated_cost_usd AS est, last_activity_at AS last_seen FROM sessions"
        ).fetchall()
    res = []
    for r in rows:
        d = dict(r)
        for k in ("calls", "inp", "out", "cr", "cw"):
            d[k] = d[k] or 0
        d["cost"] = d["est"] if d["est"] else price(d["model"], d["inp"], d["out"], d["cr"], d["cw"])
        d["kind"] = "cron" if d["source"] == "cron" else ("streszczanie" if "compress" in (d["task"] or "") else
                                                           (d["task"] or d["source"] or "?"))
        res.append(d)
    return res


def totals(rows) -> dict:
    t = defaultdict(float)
    for r in rows:
        for k in ("calls", "inp", "out", "cr", "cw", "cost"):
            t[k] += r[k]
    return t


def fmt(t) -> str:
    tok = t["inp"] + t["out"] + t["cr"] + t["cw"]
    return f"{int(t['calls']):>4} wywołań · {n(tok):>9} tok (w tym cache {n(t['cr'])}) · ${t['cost']:.3f}"


def snapshot(rows) -> None:
    """Dopisz dzienne zdjęcie licznika — z różnic między dniami liczymy zużycie dzienne."""
    t = totals(rows)
    SNAPSHOTS.parent.mkdir(parents=True, exist_ok=True)
    today = datetime.now().strftime("%Y-%m-%d")
    lines = SNAPSHOTS.read_text().splitlines() if SNAPSHOTS.exists() else []
    lines = [l for l in lines if json.loads(l).get("day") != today]
    lines.append(json.dumps({"day": today, "ts": time.time(), **{k: t[k] for k in ("calls", "inp", "out", "cr", "cw", "cost")}}))
    SNAPSHOTS.write_text("\n".join(lines) + "\n")
    give_back(SNAPSHOTS)


def user_messages_per_day(con) -> dict[str, int]:
    out = defaultdict(int)
    try:
        for (ts,) in con.execute(
            "SELECT m.timestamp FROM messages m JOIN sessions s ON s.id = m.session_id "
            "WHERE m.role = 'user' AND s.source = 'telegram'"
        ):
            out[day(ts)] += 1
    except sqlite3.Error:
        pass
    return out


def section_usage(con, days: int) -> None:
    h("b) Zużycie")
    rows = usage_rows(con)
    if not rows:
        print("Brak danych o zużyciu.")
        return
    snapshot(rows)

    by_kind = defaultdict(list)
    for r in rows:
        by_kind[r["kind"]].append(r)
    print("\nŁącznie od instalacji:")
    for kind, rs in sorted(by_kind.items()):
        print(f"  {kind:<14} {fmt(totals(rs))}")
    print(f"  {'RAZEM':<14} {fmt(totals(rows))}")

    msgs = user_messages_per_day(con)
    tg = totals(by_kind.get("telegram", []))
    n_msgs = sum(msgs.values())
    if n_msgs:
        tok = tg["inp"] + tg["out"] + tg["cr"] + tg["cw"]
        print(f"\nNa wiadomość (Telegram, średnio z {n_msgs}): {n(tok / n_msgs)} tok · ${tg['cost'] / n_msgs:.4f}")

    cron = sorted(by_kind.get("cron", []), key=lambda r: r["started_at"] or 0)
    if cron:
        t = totals(cron)
        print(f"\nCron (zaczepki, które przeszły bramkę): {len(cron)} uruchomień, "
              f"średnio ${t['cost'] / len(cron):.4f} na zaczepkę. Ostatnie:")
        for r in cron[-5:]:
            print(f"  {datetime.fromtimestamp(r['started_at']):%m-%d %H:%M}  "
                  f"{n(r['inp'] + r['cr'] + r['cw']):>7} tok wej. · {r['out']:>4} wyj. · ${r['cost']:.4f}")
        print("  (godziny, w których bramka nic nie wysłała, kosztują 0 — nie ma ich tutaj)")

    snaps = [json.loads(l) for l in SNAPSHOTS.read_text().splitlines()] if SNAPSHOTS.exists() else []
    print(f"\nNa dzień (ostatnie {days} dni; z dziennych zdjęć licznika):")
    if len(snaps) < 2:
        print("  Za mało zdjęć — pojawią się od jutra (robi je zadanie cron `bibo-usage` o 23:55).")
    since = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    for prev, cur in zip(snaps, snaps[1:]):
        if cur["day"] < since:
            continue
        d = {k: cur[k] - prev[k] for k in ("calls", "inp", "out", "cr", "cw", "cost")}
        m = msgs.get(cur["day"], 0)
        per = f" · ${d['cost'] / m:.4f}/wiad." if m else ""
        print(f"  {cur['day']}  {m:>3} wiad. · {fmt(d)}{per}")


# --------------------------------------------------------------- c) nauka
def memory_events(con) -> list[tuple[float, str, str, str]]:
    """Każde wywołanie narzędzia memory: (czas, akcja, cel, treść)."""
    events = []
    try:
        rows = con.execute("SELECT timestamp, tool_calls FROM messages WHERE tool_calls LIKE '%memory%'").fetchall()
    except sqlite3.Error:
        return events
    for ts, raw in rows:
        try:
            calls = json.loads(raw)
        except (TypeError, ValueError):
            continue
        for c in calls if isinstance(calls, list) else [calls]:
            fn = c.get("function", c) if isinstance(c, dict) else {}
            if fn.get("name") != "memory":
                continue
            args = fn.get("arguments") or fn.get("input") or {}
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except ValueError:
                    args = {}
            events.append((ts, args.get("action", "?"), args.get("target", "?"),
                           (args.get("content") or args.get("old_text") or "").strip()))
    return sorted(events)


def section_learning(con) -> None:
    h("c) Jak się uczy — historia zapisów do pamięci")
    ev = memory_events(con)
    if not ev:
        print("Jeszcze nic nie zapisał.")
        return
    per_day = defaultdict(int)
    for ts, *_ in ev:
        per_day[day(ts)] += 1
    print("Zapisy na dzień: " + ", ".join(f"{d}: {n}" for d, n in sorted(per_day.items())[-10:]))
    icon = {"add": "+", "replace": "~", "remove": "−"}
    print("\nOstatnie 20 zmian (+ dodał, ~ poprawił, − usunął; user = profil, memory = notatki):")
    for ts, action, target, text in ev[-20:]:
        short = text.replace("\n", " ")
        short = short if len(short) <= 110 else short[:107] + "..."
        print(f"  {datetime.fromtimestamp(ts):%m-%d %H:%M} {icon.get(action, '?')} [{target}] {short}")
    print("\nOsobowość (SOUL.md) się nie zmienia — Bibo „rośnie” tylko przez pamięć.")
    print("Wykres w czasie: hermes journey   ·   edycja/usunięcie wpisu: hermes journey list / delete")


# ------------------------------------------------------- d) opinia i plan
OPINION_PROMPT = (
    "To jest prośba właściciela o raport, nie rozmowa. NIE zmieniaj pamięci. "
    "Na podstawie swojej pamięci o userze napisz po polsku, bez podpisu ,bibo, bez limitu długości:\n"
    "1. Jak widzisz usera (3–5 punktów, z czego to wnioskujesz).\n"
    "2. Co z tego, co robisz, działa, a co nie.\n"
    "3. Twój plan wsparcia na najbliższe 2 tygodnie (konkretnie).\n"
    "4. Czego o userze jeszcze nie wiesz, a przydałoby się.\n"
    "Oddziel fakty z pamięci od swoich przypuszczeń."
)


def section_plan(mem: dict[str, str], ask_model: bool) -> None:
    h("d) Opinia o Tobie i plan wsparcia")
    plan = [e.strip() for e in mem["MEMORY.md"].split("§") if e.strip().upper().startswith("PLAN")]
    print("Plan zapisany w pamięci Bibo:")
    print("  " + (plan[0].replace("\n", "\n  ") if plan else "(jeszcze brak wpisu PLAN — pojawi się po kilku rozmowach)"))
    if not ask_model:
        print("\nPełna opinia Bibo (1 wywołanie modelu, ~kilka centów): dodaj --opinia")
        return
    print("\nPytam Bibo (jedno wywołanie modelu)...\n")
    # Katalog zapisywalny dla wszystkich: w Dockerze `hermes` zrzuca uprawnienia
    # z root na użytkownika hermes i nie mógłby zapisać raportu do pliku roota.
    tmp = Path(tempfile.mkdtemp(prefix="bibo-opinia-"))
    tmp.chmod(0o777)
    usage_file = str(tmp / "usage.json")
    try:
        r = subprocess.run(["hermes", "-t", "memory", "-z", OPINION_PROMPT, "--usage-file", usage_file],
                           capture_output=True, text=True, timeout=300)
        print(r.stdout.strip() or r.stderr.strip())
        try:
            u = json.loads(Path(usage_file).read_text())
            cost = u.get("estimated_cost_usd") or u.get("cost_usd") or u.get("estimated_cost")
            if cost is not None:
                print(f"\n(koszt tej opinii: ${float(cost):.4f})")
        except (OSError, ValueError, TypeError):
            pass
    finally:
        Path(usage_file).unlink(missing_ok=True)
        tmp.rmdir()


def main() -> int:
    ap = argparse.ArgumentParser(description="Raport Bibo")
    ap.add_argument("--dni", type=int, default=7, help="okno zużycia dziennego (domyślnie 7)")
    ap.add_argument("--opinia", action="store_true", help="dopytaj Bibo o opinię i plan (1 wywołanie modelu)")
    ap.add_argument("--snapshot", action="store_true", help="tylko zapisz dzienne zdjęcie licznika (dla crona)")
    args = ap.parse_args()

    if not DB.exists():
        print(f"Nie widzę bazy Hermesa: {DB}")
        return 1
    con = db()
    if args.snapshot:
        snapshot(usage_rows(con))
        return 0

    print(f"Raport Bibo — {datetime.now():%Y-%m-%d %H:%M} — {HOME}")
    mem = read_memory()
    section_data(mem)
    section_usage(con, args.dni)
    section_learning(con)
    section_plan(mem, args.opinia)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
