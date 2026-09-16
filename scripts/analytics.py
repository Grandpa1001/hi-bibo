#!/usr/bin/env python3
"""Hi-Bibo analytics — operator tool for measuring partner quality over time.

This is NOT a clinical outcome tracker and Bibo must not read these reports
(Goodhart). It records behavioral proxies from live use, then scores whether
they moved week-over-week.

Events land in ``$BIBO_DIR/logs/analytics.jsonl`` (gitignored). Message bodies
are never stored — only length, hashes, and hygiene flags.

Usage:
    python3 scripts/analytics.py report
    python3 scripts/analytics.py report --days 7 --json
    python3 scripts/analytics.py selftest
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import unicodedata
from datetime import datetime, timedelta
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

BIBO_DIR = os.environ.get("BIBO_DIR", "/opt/data/hi-bibo")
LOG_PATH = os.path.join(BIBO_DIR, "logs", "analytics.jsonl")
BRAIN_PATH = os.path.join(BIBO_DIR, "brain.json")

REPLY_WINDOW_H = 6.0
SILENCE_PING_H = 12.0
OVERLENGTH_CHARS = 400
OVERLENGTH_SENTENCES = 3
MIN_EVENTS_FOR_INDEX = 8

GUILT_PATTERNS = (
    r"gdzie się podział",
    r"gdzie sie podzial",
    r"dawno cię nie było",
    r"dawno cie nie bylo",
    r"znowu nie",
    r"obiecałe[sś]",
    r"obiecales",
    r"miałe[sś] zrobić",
    r"miales zrobic",
)
SYCOPHANCY_PATTERNS = (
    r"super pomysł",
    r"super pomysl",
    r"świetnie!",
    r"swietnie!",
    r"\bbrawo\b",
    r"\bsuper!\b",
)
BREATH_MARKERS = (
    "to jest twój oddech",
    "to jest twoj oddech",
    "this is your breath",
    "oddech nr",
    "## stan brain.json",
    "## aktualny czas",
    "zdecyduj czy pisać",
    "zdecyduj czy pisac",
)

CONFIDENCE_BUCKETS = (
    "profil",
    "preferencje_kontaktu",
    "nawyki",
    "problemy_stale",
)

CHAR_KEYS = (
    "bezposredniosc",
    "cierpliwosc",
    "humor",
    "prowokacyjnosc",
    "emocjonalnosc",
    "ciekawosc",
)


# ---------------------------------------------------------------------------
# IO
# ---------------------------------------------------------------------------

def _now() -> datetime:
    return datetime.now().astimezone()


def _parse_ts(value: Any) -> Optional[datetime]:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def append_event(event: Dict[str, Any], path: str = LOG_PATH) -> None:
    """Append one JSONL event. Never raises."""
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        payload = dict(event)
        payload.setdefault("v", 1)
        payload.setdefault("ts", _now().isoformat(timespec="seconds"))
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except OSError:
        return


def load_events(path: str = LOG_PATH) -> List[Dict[str, Any]]:
    if not os.path.isfile(path):
        return []
    events: List[Dict[str, Any]] = []
    try:
        with open(path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    item = json.loads(line)
                except ValueError:
                    continue
                if isinstance(item, dict):
                    events.append(item)
    except OSError:
        return []
    return events


def snapshot_brain(brain: Optional[Dict[str, Any]] = None, path: str = BRAIN_PATH) -> Optional[Dict[str, Any]]:
    """Compact, non-PII snapshot of the user model."""
    if brain is None:
        try:
            with open(path, "r", encoding="utf-8") as fh:
                brain = json.load(fh)
        except (OSError, ValueError):
            return None
    if not isinstance(brain, dict):
        return None

    conf: Dict[str, float] = {}
    for key in CONFIDENCE_BUCKETS:
        bucket = brain.get(key) or {}
        if isinstance(bucket, dict):
            try:
                conf[key] = float(bucket.get("confidence") or 0.0)
            except (TypeError, ValueError):
                conf[key] = 0.0

    char_src = brain.get("charakter_bibo") or {}
    char: Dict[str, float] = {}
    if isinstance(char_src, dict):
        for key in CHAR_KEYS:
            try:
                char[key] = float(char_src.get(key) or 0.0)
            except (TypeError, ValueError):
                char[key] = 0.0

    co = brain.get("co_dziala") or {}
    cele = brain.get("cele_i_kierunek") or {}
    return {
        "phase": brain.get("phase"),
        "breath_count": brain.get("breath_count", 0),
        "debug_mode": bool(brain.get("debug_mode", False)),
        "last_updated": brain.get("last_updated"),
        "confidence": conf,
        "mean_confidence": round(_mean(conf.values()), 4) if conf else 0.0,
        "charakter": char,
        "co_dziala_skuteczne": len(co.get("skuteczne") or []) if isinstance(co, dict) else 0,
        "co_dziala_nieskuteczne": len(co.get("nieskuteczne") or []) if isinstance(co, dict) else 0,
        "deklaracje": len(cele.get("deklaracje") or []) if isinstance(cele, dict) else 0,
        "rzeczywistosc": len(cele.get("rzeczywistosc") or []) if isinstance(cele, dict) else 0,
    }


# ---------------------------------------------------------------------------
# Text flags (no body stored)
# ---------------------------------------------------------------------------

_PL_MAP = str.maketrans("ąćęłńóśźżĄĆĘŁŃÓŚŹŻ", "acelnoszzACELNOSZZ")


def _strip_diacritics(text: str) -> str:
    nfkd = unicodedata.normalize("NFKD", text.translate(_PL_MAP))
    return "".join(ch for ch in nfkd if not unicodedata.combining(ch))


def normalize_text(text: str) -> str:
    t = text.strip().lower()
    t = re.sub(r"^hi[\s,]*", "", t)
    t = re.sub(r"[,\s]*bibo\s*$", "", t)
    t = re.sub(r"\s+", " ", t)
    return t.strip()


def text_hash(text: str) -> str:
    return hashlib.sha256(normalize_text(text).encode("utf-8")).hexdigest()[:16]


def sentence_count(text: str) -> int:
    parts = re.findall(r"[.!?…]+", text)
    return max(1, len(parts)) if text.strip() else 0


def flag_patterns(text: str, patterns: Sequence[str]) -> bool:
    blob = _strip_diacritics(text.lower())
    return any(re.search(_strip_diacritics(p), blob) for p in patterns)


def is_breath_prompt(text: str) -> bool:
    blob = _strip_diacritics((text or "").lower())
    return any(marker in blob for marker in BREATH_MARKERS)


def is_silent(text: str) -> bool:
    stripped = (text or "").strip()
    return stripped in ("[SILENT]", "SILENT")


def outbound_flags(text: str) -> Dict[str, Any]:
    silent = is_silent(text)
    length = len(text or "")
    sentences = sentence_count(text or "")
    return {
        "silent": silent,
        "char_len": length,
        "sentences": sentences,
        "hash": text_hash(text or "") if not silent else None,
        "guilt": False if silent else flag_patterns(text, GUILT_PATTERNS),
        "sycophancy": False if silent else flag_patterns(text, SYCOPHANCY_PATTERNS),
        "overlength": False if silent else (length > OVERLENGTH_CHARS or sentences > OVERLENGTH_SENTENCES),
        "thought_leak": (not silent) and (normalize_text(text or "") in ("", "bibo")),
    }


# ---------------------------------------------------------------------------
# Emitters used by breath.py and the plugin
# ---------------------------------------------------------------------------

def emit_breath(brain: Dict[str, Any], extra: Optional[Dict[str, Any]] = None, path: str = LOG_PATH) -> None:
    event: Dict[str, Any] = {
        "type": "breath",
        "brain": snapshot_brain(brain),
    }
    if extra:
        event.update(extra)
    append_event(event, path=path)


def emit_inbound(text: str, session_id: str = "", platform: str = "", path: str = LOG_PATH) -> None:
    if is_breath_prompt(text):
        return
    append_event(
        {
            "type": "inbound",
            "char_len": len(text or ""),
            "hash": text_hash(text or ""),
            "session_id": session_id,
            "platform": platform,
        },
        path=path,
    )


def emit_outbound(
    text: str,
    session_id: str = "",
    platform: str = "",
    *,
    thought_leak: bool = False,
    path: str = LOG_PATH,
) -> None:
    flags = outbound_flags(text)
    if thought_leak:
        flags["thought_leak"] = True
    flags.update(
        {
            "type": "outbound",
            "session_id": session_id,
            "platform": platform,
        }
    )
    append_event(flags, path=path)


def emit_brain_write(repaired_keys: Optional[Sequence[str]] = None, path: str = LOG_PATH) -> None:
    append_event(
        {
            "type": "brain_write",
            "repaired_keys": list(repaired_keys or []),
            "brain": snapshot_brain(),
        },
        path=path,
    )


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def _mean(values: Iterable[Any]) -> float:
    nums = [float(v) for v in values]
    return sum(nums) / len(nums) if nums else 0.0


def _in_window(event: Dict[str, Any], start: datetime, end: datetime) -> bool:
    ts = _parse_ts(event.get("ts"))
    if ts is None:
        return False
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=end.tzinfo)
    return start <= ts <= end


def _events_in(events: Sequence[Dict[str, Any]], start: datetime, end: datetime) -> List[Dict[str, Any]]:
    return [e for e in events if _in_window(e, start, end)]


def _match_replies(
    outbound: Sequence[Dict[str, Any]],
    inbound: Sequence[Dict[str, Any]],
    window_h: float = REPLY_WINDOW_H,
) -> Tuple[int, int, List[float]]:
    spoken = [e for e in outbound if not e.get("silent")]
    in_ts = [_parse_ts(e.get("ts")) for e in inbound]
    used = [False] * len(inbound)
    hits = 0
    delays: List[float] = []
    for out in spoken:
        ots = _parse_ts(out.get("ts"))
        if ots is None:
            continue
        deadline = ots + timedelta(hours=window_h)
        for i, its in enumerate(in_ts):
            if used[i] or its is None:
                continue
            if ots < its <= deadline:
                used[i] = True
                hits += 1
                delays.append((its - ots).total_seconds() / 3600.0)
                break
    return hits, len(spoken), delays


def _duplicate_rate(outbound: Sequence[Dict[str, Any]]) -> float:
    hashes = [e.get("hash") for e in outbound if not e.get("silent") and e.get("hash")]
    if len(hashes) < 2:
        return 0.0
    unique = len(set(hashes))
    return 1.0 - (unique / len(hashes))


def _presence_score(breaths: Sequence[Dict[str, Any]], outbound: Sequence[Dict[str, Any]], inbound: Sequence[Dict[str, Any]]) -> float:
    """1.0 = Bibo pings when the user has been quiet >12h. 0.0 = death loop."""
    last_in = None
    in_times = [_parse_ts(e.get("ts")) for e in inbound]
    in_times = [t for t in in_times if t is not None]
    spoken_times = [_parse_ts(e.get("ts")) for e in outbound if not e.get("silent")]
    spoken_times = [t for t in spoken_times if t is not None]

    windows = 0
    pings = 0
    for breath in breaths:
        bts = _parse_ts(breath.get("ts"))
        if bts is None:
            continue
        prior_in = [t for t in in_times if t <= bts]
        last_in = max(prior_in) if prior_in else None
        if last_in is None:
            continue
        quiet_h = (bts - last_in).total_seconds() / 3600.0
        if quiet_h < SILENCE_PING_H:
            continue
        windows += 1
        if any(abs((t - bts).total_seconds()) <= 3600 for t in spoken_times):
            pings += 1
    if not in_times:
        return 0.0
    if windows == 0:
        return 1.0
    return pings / windows


def score_window(
    events: Sequence[Dict[str, Any]],
    brain_now: Optional[Dict[str, Any]] = None,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    breaths = [e for e in events if e.get("type") == "breath"]
    inbound = [e for e in events if e.get("type") == "inbound"]
    outbound = [e for e in events if e.get("type") == "outbound"]
    writes = [e for e in events if e.get("type") == "brain_write"]
    spoken = [e for e in outbound if not e.get("silent")]
    silent = [e for e in outbound if e.get("silent")]

    hits, spoken_n, delays = _match_replies(outbound, inbound)
    reply_rate = (hits / spoken_n) if spoken_n else None
    guilt_n = sum(1 for e in spoken if e.get("guilt"))
    syco_n = sum(1 for e in spoken if e.get("sycophancy"))
    over_n = sum(1 for e in spoken if e.get("overlength"))
    leak_n = sum(1 for e in outbound if e.get("thought_leak"))

    snapshots = [e.get("brain") for e in breaths if isinstance(e.get("brain"), dict)]
    if brain_now:
        snapshots.append(brain_now)
    mean_conf_series = [float(s.get("mean_confidence") or 0.0) for s in snapshots if s]
    learning = mean_conf_series[-1] if mean_conf_series else (brain_now or {}).get("mean_confidence", 0.0)
    learning_delta = (mean_conf_series[-1] - mean_conf_series[0]) if len(mean_conf_series) >= 2 else 0.0

    hygiene_penalties = 0.0
    if spoken_n:
        hygiene_penalties += guilt_n / spoken_n
        hygiene_penalties += syco_n / spoken_n
        hygiene_penalties += over_n / spoken_n
    if outbound:
        hygiene_penalties += leak_n / len(outbound)
    hygiene = max(0.0, 1.0 - min(1.0, hygiene_penalties))

    presence = _presence_score(breaths, outbound, inbound) if (breaths or inbound or outbound) else None
    silent_ratio = (len(silent) / len(outbound)) if outbound else None
    dup = _duplicate_rate(outbound) if spoken else None

    if spoken_n == 0 and not outbound:
        hygiene = None
    else:
        hygiene = max(0.0, 1.0 - min(1.0, hygiene_penalties))

    components = {
        "reply_rate": reply_rate,
        "presence": presence,
        "learning": float(learning or 0.0),
        "hygiene": hygiene,
    }
    # Missing reply_rate (no spoken messages) → don't pretend engagement is fine.
    usable = dict(components)
    if usable["reply_rate"] is None:
        usable["reply_rate"] = 0.0 if spoken_n == 0 and inbound else None

    index = None
    enough = (len(events) >= MIN_EVENTS_FOR_INDEX) and (spoken_n >= 1 or len(breaths) >= 12)
    if (
        enough
        and usable["reply_rate"] is not None
        and presence is not None
        and hygiene is not None
    ):
        index = round(
            100.0
            * (
                0.35 * usable["reply_rate"]
                + 0.25 * presence
                + 0.20 * min(1.0, float(learning or 0.0))
                + 0.20 * hygiene
            ),
            1,
        )

    last_in = _parse_ts(inbound[-1]["ts"]) if inbound else None
    last_out = _parse_ts(spoken[-1]["ts"]) if spoken else None
    last_breath = _parse_ts(breaths[-1]["ts"]) if breaths else None
    now = now or _now()

    return {
        "counts": {
            "events": len(events),
            "breaths": len(breaths),
            "inbound": len(inbound),
            "outbound": len(outbound),
            "spoken": spoken_n,
            "silent": len(silent),
            "brain_writes": len(writes),
        },
        "engagement": {
            "reply_rate_6h": round(reply_rate, 3) if reply_rate is not None else None,
            "replies_matched": hits,
            "median_reply_h": round(sorted(delays)[len(delays) // 2], 2) if delays else None,
            "inbound_per_day": None,
        },
        "presence": {
            "score": round(presence, 3) if presence is not None else None,
            "silent_ratio": round(silent_ratio, 3) if silent_ratio is not None else None,
            "duplicate_rate": round(dup, 3) if dup is not None else None,
            "hours_since_user": round((now - last_in).total_seconds() / 3600.0, 2) if last_in else None,
            "hours_since_bibo": round((now - last_out).total_seconds() / 3600.0, 2) if last_out else None,
            "hours_since_breath": round((now - last_breath).total_seconds() / 3600.0, 2) if last_breath else None,
        },
        "hygiene": {
            "score": round(hygiene, 3) if hygiene is not None else None,
            "guilt": guilt_n,
            "sycophancy": syco_n,
            "overlength": over_n,
            "thought_leaks": leak_n,
            "mean_chars": round(_mean(e.get("char_len") or 0 for e in spoken), 1) if spoken else None,
        },
        "learning": {
            "mean_confidence": round(float(learning or 0.0), 3),
            "confidence_delta": round(learning_delta, 3),
            "brain": snapshots[-1] if snapshots else brain_now,
        },
        "quality_index": index,
        "components": {
            "reply_rate": round(usable["reply_rate"], 3) if usable["reply_rate"] is not None else None,
            "presence": round(presence, 3) if presence is not None else None,
            "learning": round(min(1.0, float(learning or 0.0)), 3),
            "hygiene": round(hygiene, 3) if hygiene is not None else None,
        },
        "enough_data": enough,
    }


def _fill_per_day(score: Dict[str, Any], start: datetime, end: datetime) -> None:
    span_h = max((end - start).total_seconds() / 3600.0, 1.0)
    days = span_h / 24.0
    inbound = score["counts"]["inbound"]
    spoken = score["counts"]["spoken"]
    score["engagement"]["inbound_per_day"] = round(inbound / days, 2)
    score["engagement"]["spoken_per_day"] = round(spoken / days, 2)
    score["engagement"]["window_days"] = round(days, 2)


def compare_windows(events: Sequence[Dict[str, Any]], days: int = 7, now: Optional[datetime] = None, brain_now: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    now = now or _now()
    current_start = now - timedelta(days=days)
    baseline_start = current_start - timedelta(days=days)
    current_events = _events_in(events, current_start, now)
    baseline_events = _events_in(events, baseline_start, current_start)

    current = score_window(current_events, brain_now=brain_now, now=now)
    baseline = score_window(baseline_events, brain_now=None, now=current_start)
    _fill_per_day(current, current_start, now)
    _fill_per_day(baseline, baseline_start, current_start)

    def _delta(a: Any, b: Any) -> Optional[float]:
        if a is None or b is None:
            return None
        return round(float(a) - float(b), 3)

    return {
        "generated_at": now.isoformat(timespec="seconds"),
        "window_days": days,
        "current": current,
        "baseline": baseline,
        "delta": {
            "quality_index": _delta(current.get("quality_index"), baseline.get("quality_index")),
            "reply_rate_6h": _delta(current["engagement"]["reply_rate_6h"], baseline["engagement"]["reply_rate_6h"]),
            "presence": _delta(current["presence"]["score"], baseline["presence"]["score"]),
            "mean_confidence": _delta(current["learning"]["mean_confidence"], baseline["learning"]["mean_confidence"]),
            "hygiene": _delta(current["hygiene"]["score"], baseline["hygiene"]["score"]),
            "inbound_per_day": _delta(current["engagement"]["inbound_per_day"], baseline["engagement"]["inbound_per_day"]),
        },
        "verdict": _verdict(current, baseline),
        "note": (
            "Indeks jakości to proxy behawioralne (odpowiedzi, obecność, uczenie mózgu, higiena), "
            "nie pomiar kliniczny ADHD. Bibo nie powinien tego czytać."
        ),
    }


def _verdict(current: Dict[str, Any], baseline: Dict[str, Any]) -> str:
    if not current.get("enough_data"):
        return "za_malo_danych"
    cur = current.get("quality_index")
    base = baseline.get("quality_index")
    if cur is None:
        return "za_malo_danych"
    if base is None:
        return "baseline_brak"
    if cur - base >= 5:
        return "rosnie"
    if base - cur >= 5:
        return "spada"
    return "stabilne"


VERDICT_PL = {
    "za_malo_danych": "Za mało danych — zbieraj oddechy i wiadomości przez kilka dni.",
    "baseline_brak": "Jest indeks bieżący, ale brak okna porównawczego (poprzedni tydzień).",
    "rosnie": "Jakość proxy rośnie względem poprzedniego okna.",
    "spada": "Jakość proxy spada — sprawdź ciszę, reply rate i higienę.",
    "stabilne": "Bez istotnej zmiany (±5 pkt) względem poprzedniego okna.",
}


def build_report(days: int = 7, events_path: str = LOG_PATH, brain_path: str = BRAIN_PATH) -> Dict[str, Any]:
    events = load_events(events_path)
    brain_now = snapshot_brain(path=brain_path)
    report = compare_windows(events, days=days, brain_now=brain_now)
    report["paths"] = {"events": events_path, "brain": brain_path}
    report["event_count"] = len(events)
    return report


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def _fmt(value: Any, digits: int = 3, suffix: str = "") -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{value:.{digits}f}{suffix}"
    return f"{value}{suffix}"


def _delta_s(value: Optional[float]) -> str:
    if value is None:
        return "—"
    sign = "+" if value > 0 else ""
    return f"{sign}{value:.3f}"


def format_text_report(report: Dict[str, Any]) -> str:
    cur = report["current"]
    dlt = report["delta"]
    lines = [
        "Hi-Bibo — raport jakości (proxy, nie klinika)",
        f"Wygenerowano: {report['generated_at']}  |  okno: {report['window_days']} dni vs poprzednie {report['window_days']} dni",
        "",
        f"Werdykt: {VERDICT_PL.get(report['verdict'], report['verdict'])}",
        f"Indeks jakości: {_fmt(cur.get('quality_index'), 1)} / 100   (Δ {_delta_s(dlt.get('quality_index'))})",
        "",
        "Składowe indeksu  (wagi: reply 35% · obecność 25% · uczenie 20% · higiena 20%)",
        f"  reply rate 6h : {_fmt(cur['engagement']['reply_rate_6h'])}   Δ {_delta_s(dlt.get('reply_rate_6h'))}",
        f"  obecność      : {_fmt(cur['presence']['score'])}   Δ {_delta_s(dlt.get('presence'))}",
        f"  mean conf.    : {_fmt(cur['learning']['mean_confidence'])}   Δ {_delta_s(dlt.get('mean_confidence'))}",
        f"  higiena       : {_fmt(cur['hygiene']['score'])}   Δ {_delta_s(dlt.get('hygiene'))}",
        "",
        "Wolumen",
        f"  oddechy {cur['counts']['breaths']}  |  Bibo→user {cur['counts']['spoken']}  |  user→Bibo {cur['counts']['inbound']}  |  [SILENT] {cur['counts']['silent']}",
        f"  spoken/dzień {cur['engagement'].get('spoken_per_day', '—')}  |  inbound/dzień {cur['engagement'].get('inbound_per_day', '—')}  Δ {_delta_s(dlt.get('inbound_per_day'))}",
        f"  silent ratio {_fmt(cur['presence']['silent_ratio'])}  |  duplikaty {_fmt(cur['presence']['duplicate_rate'])}",
        "",
        "Timing",
        f"  godz. od usera {_fmt(cur['presence']['hours_since_user'], 2)}  |  od Bibo {_fmt(cur['presence']['hours_since_bibo'], 2)}  |  od oddechu {_fmt(cur['presence']['hours_since_breath'], 2)}",
        f"  mediana odpowiedzi {_fmt(cur['engagement']['median_reply_h'], 2)} h",
        "",
        "Higiena wiadomości",
        f"  guilt-trip {cur['hygiene']['guilt']}  |  sycophancy {cur['hygiene']['sycophancy']}  |  za długie {cur['hygiene']['overlength']}  |  przecieki myśli {cur['hygiene']['thought_leaks']}",
        f"  średnia długość {_fmt(cur['hygiene']['mean_chars'], 1)} znaków",
        "",
        report["note"],
    ]
    if report.get("event_count", 0) == 0 and cur["counts"]["events"] == 0:
        lines.insert(3, "Brak telemetrii — logs/analytics.jsonl jest pusty. Oddechy i plugin 1.2 zaczną je zapełniać.")
    return "\n".join(lines)


def format_telegram_report(report: Dict[str, Any]) -> str:
    cur = report["current"]
    dlt = report["delta"]
    verdict = VERDICT_PL.get(report["verdict"], report["verdict"])
    return "\n".join(
        [
            "*Bibo — jakość (proxy)*",
            "",
            verdict,
            f"Indeks: `{_fmt(cur.get('quality_index'), 1)}/100`  Δ `{_delta_s(dlt.get('quality_index'))}`",
            "",
            f"Reply 6h `{_fmt(cur['engagement']['reply_rate_6h'])}`  Δ `{_delta_s(dlt.get('reply_rate_6h'))}`",
            f"Obecność `{_fmt(cur['presence']['score'])}`  ·  silent `{_fmt(cur['presence']['silent_ratio'])}`",
            f"Uczenie `{_fmt(cur['learning']['mean_confidence'])}`  Δ `{_delta_s(dlt.get('mean_confidence'))}`",
            f"Higiena `{_fmt(cur['hygiene']['score'])}`  (guilt {cur['hygiene']['guilt']} / syco {cur['hygiene']['sycophancy']} / leak {cur['hygiene']['thought_leaks']})",
            "",
            f"Oddechy {cur['counts']['breaths']} · Bibo {cur['counts']['spoken']} · user {cur['counts']['inbound']}",
            f"Od usera: `{_fmt(cur['presence']['hours_since_user'], 1)}h`",
            "",
            "_Nie idzie do modelu. Indeks ≠ efekt kliniczny._",
        ]
    )


# ---------------------------------------------------------------------------
# Self-test + CLI
# ---------------------------------------------------------------------------

def _synth_ts(now: datetime, hours_ago: float) -> str:
    return (now - timedelta(hours=hours_ago)).isoformat(timespec="seconds")


def _selftest() -> int:
    now = datetime(2026, 9, 16, 18, 0, tzinfo=_now().tzinfo)
    events: List[Dict[str, Any]] = []
    # Previous week: low reply, some guilt, frozen confidence
    for i in range(14, 8, -1):
        events.append({"v": 1, "ts": _synth_ts(now, i * 24), "type": "breath", "brain": {"mean_confidence": 0.1, "phase": "adaptation"}})
        events.append({"v": 1, "ts": _synth_ts(now, i * 24 - 0.1), "type": "outbound", "silent": False, "hash": f"old{i}", "guilt": True, "sycophancy": False, "overlength": False, "thought_leak": False, "char_len": 120})
    # Current week: replies, no guilt, rising confidence
    for i in range(6, 0, -1):
        events.append({"v": 1, "ts": _synth_ts(now, i * 24), "type": "breath", "brain": {"mean_confidence": 0.4, "phase": "adaptation"}})
        events.append({"v": 1, "ts": _synth_ts(now, i * 24 - 0.2), "type": "outbound", "silent": False, "hash": f"new{i}", "guilt": False, "sycophancy": False, "overlength": False, "thought_leak": False, "char_len": 90})
        events.append({"v": 1, "ts": _synth_ts(now, i * 24 - 1.0), "type": "inbound", "char_len": 40, "hash": f"u{i}"})

    report = compare_windows(events, days=7, now=now, brain_now={"mean_confidence": 0.4})
    assert report["current"]["engagement"]["reply_rate_6h"] == 1.0, report["current"]["engagement"]
    assert report["current"]["hygiene"]["guilt"] == 0
    assert report["baseline"]["hygiene"]["guilt"] > 0
    assert report["current"]["quality_index"] is not None
    assert report["baseline"]["quality_index"] is not None
    assert report["current"]["quality_index"] > report["baseline"]["quality_index"]
    assert report["verdict"] == "rosnie", report["verdict"]
    assert is_silent("[SILENT]") and not is_silent("Hi hej, bibo")
    assert is_breath_prompt("## Aktualny czas\nOddech nr: 3")
    assert is_breath_prompt("Jesteś Bibo. To jest Twój oddech.")
    assert flag_patterns("Hi, gdzie się podziałeś, bibo", GUILT_PATTERNS)
    assert not flag_patterns("Hi, widzę że zadanie leży otwarte, bibo", GUILT_PATTERNS)
    flags = outbound_flags("Hi, super pomysł! lecimy z nowym projektem, bibo")
    assert flags["sycophancy"] is True
    print("selftest ok")
    print(format_text_report(report))
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Hi-Bibo quality analytics")
    sub = parser.add_subparsers(dest="cmd", required=True)

    rep = sub.add_parser("report", help="Policz indeks jakości z logs/analytics.jsonl")
    rep.add_argument("--days", type=int, default=7)
    rep.add_argument("--json", action="store_true")
    rep.add_argument("--events", default=LOG_PATH)
    rep.add_argument("--brain", default=BRAIN_PATH)

    sub.add_parser("selftest", help="Sprawdź scorowanie na syntetycznych zdarzeniach")

    args = parser.parse_args(argv)
    if args.cmd == "selftest":
        return _selftest()

    report = build_report(days=args.days, events_path=args.events, brain_path=args.brain)
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(format_text_report(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
