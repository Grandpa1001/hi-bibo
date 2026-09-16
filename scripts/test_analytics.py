#!/usr/bin/env python3
"""Unit tests for scripts/analytics.py — run: python3 scripts/test_analytics.py"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import analytics  # noqa: E402


class AnalyticsTests(unittest.TestCase):
    def test_breath_prompt_is_not_inbound(self) -> None:
        self.assertTrue(analytics.is_breath_prompt("## Aktualny czas\nOddech nr: 1"))
        self.assertTrue(analytics.is_breath_prompt("You are Bibo. This is your breath."))
        self.assertFalse(analytics.is_breath_prompt("Hi, dzisiaj znowu nie mogę zacząć"))

    def test_hygiene_flags(self) -> None:
        guilt = analytics.outbound_flags("Hi, gdzie się podziałeś, bibo")
        self.assertTrue(guilt["guilt"])
        clean = analytics.outbound_flags("Hi, widzę że zadanie leży otwarte od 5 dni, bibo")
        self.assertFalse(clean["guilt"])
        self.assertFalse(clean["sycophancy"])
        syco = analytics.outbound_flags("Hi, super pomysł!, bibo")
        self.assertTrue(syco["sycophancy"])
        silent = analytics.outbound_flags("[SILENT]")
        self.assertTrue(silent["silent"])
        leak = analytics.outbound_flags("bibo")
        self.assertTrue(leak["thought_leak"])

    def test_emit_skips_breath_inbound(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "analytics.jsonl")
            analytics.emit_inbound(
                "Jesteś Bibo. To jest Twój oddech.\nOdczytaj prompt.md",
                path=path,
            )
            analytics.emit_inbound("nie mogę zacząć tego raportu", path=path)
            events = analytics.load_events(path)
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0]["type"], "inbound")

    def test_reply_rate_and_wow(self) -> None:
        now = datetime(2026, 9, 16, 18, 0, tzinfo=timezone.utc)
        events = []
        for i in range(14, 8, -1):
            events.append(
                {
                    "v": 1,
                    "ts": (now - timedelta(hours=i * 24)).isoformat(),
                    "type": "breath",
                    "brain": {"mean_confidence": 0.1},
                }
            )
            events.append(
                {
                    "v": 1,
                    "ts": (now - timedelta(hours=i * 24 - 0.1)).isoformat(),
                    "type": "outbound",
                    "silent": False,
                    "hash": f"old{i}",
                    "guilt": True,
                    "sycophancy": False,
                    "overlength": False,
                    "thought_leak": False,
                    "char_len": 120,
                }
            )
        for i in range(6, 0, -1):
            events.append(
                {
                    "v": 1,
                    "ts": (now - timedelta(hours=i * 24)).isoformat(),
                    "type": "breath",
                    "brain": {"mean_confidence": 0.4},
                }
            )
            events.append(
                {
                    "v": 1,
                    "ts": (now - timedelta(hours=i * 24 - 0.2)).isoformat(),
                    "type": "outbound",
                    "silent": False,
                    "hash": f"new{i}",
                    "guilt": False,
                    "sycophancy": False,
                    "overlength": False,
                    "thought_leak": False,
                    "char_len": 90,
                }
            )
            events.append(
                {
                    "v": 1,
                    "ts": (now - timedelta(hours=i * 24 - 1.0)).isoformat(),
                    "type": "inbound",
                    "char_len": 40,
                    "hash": f"u{i}",
                }
            )
        report = analytics.compare_windows(events, days=7, now=now, brain_now={"mean_confidence": 0.4})
        self.assertEqual(report["current"]["engagement"]["reply_rate_6h"], 1.0)
        self.assertGreater(report["current"]["quality_index"], report["baseline"]["quality_index"])
        self.assertEqual(report["verdict"], "rosnie")

    def test_empty_events_does_not_crash(self) -> None:
        now = datetime(2026, 9, 16, 18, 0, tzinfo=timezone.utc)
        report = analytics.compare_windows([], days=7, now=now, brain_now={"mean_confidence": 0.0})
        self.assertEqual(report["verdict"], "za_malo_danych")
        self.assertIsNone(report["current"]["quality_index"])
        text = analytics.format_telegram_report(report)
        self.assertIn("Indeks", text)


if __name__ == "__main__":
    unittest.main()
