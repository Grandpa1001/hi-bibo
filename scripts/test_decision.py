#!/usr/bin/env python3
"""Unit tests for T006 — decision slot, decay, anti-silence, brain thaw."""

from __future__ import annotations

import os
import sys
import unittest
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import decision  # noqa: E402


def _brain(**kwargs):
    base = {
        "breath_count": 5,
        "phase": "adaptation",
        "partner": {"contact": {"frequency": "normal"}},
        "nawyki": {"data": {}},
        "zachowania_biezace": {"data": {}, "entries": [], "last_updated": None},
    }
    base.update(kwargs)
    return base


class CapTests(unittest.TestCase):
    def test_adaptation_normal_is_three(self) -> None:
        self.assertEqual(decision.daily_cap(_brain(phase="adaptation")), 3)

    def test_partnership_normal_is_six(self) -> None:
        self.assertEqual(decision.daily_cap(_brain(phase="partnership")), 6)

    def test_silence_phase_is_one(self) -> None:
        self.assertEqual(decision.daily_cap(_brain(phase="silence")), 1)

    def test_rarely_overrides_partnership(self) -> None:
        brain = _brain(phase="partnership")
        brain["partner"]["contact"]["frequency"] = "rarely"
        self.assertEqual(decision.daily_cap(brain), 1)

    def test_often_overrides_adaptation(self) -> None:
        brain = _brain(phase="adaptation")
        brain["partner"]["contact"]["frequency"] = "often"
        self.assertEqual(decision.daily_cap(brain), 6)


class SlotTests(unittest.TestCase):
    def setUp(self) -> None:
        self.now = datetime(2026, 9, 16, 15, 0, tzinfo=timezone.utc)

    def test_partnership_allows_four_messages(self) -> None:
        events = [
            {
                "type": "outbound",
                "silent": False,
                "ts": (self.now - timedelta(hours=i)).isoformat(),
            }
            for i in range(4)
        ]
        slot = decision.compute_slot(
            _brain(phase="partnership"), now=self.now, events=events
        )
        self.assertEqual(slot["slot"], "MAY_WRITE")
        self.assertEqual(slot["cap"], 6)
        self.assertEqual(slot["spoken_today"], 4)

    def test_adaptation_caps_at_three(self) -> None:
        events = [
            {
                "type": "outbound",
                "silent": False,
                "ts": (self.now - timedelta(hours=i)).isoformat(),
            }
            for i in range(3)
        ]
        slot = decision.compute_slot(
            _brain(phase="adaptation"), now=self.now, events=events
        )
        self.assertEqual(slot["slot"], "SILENT")

    def test_anti_silence_twelve_hours(self) -> None:
        events = [
            {"type": "inbound", "ts": (self.now - timedelta(hours=15)).isoformat()},
            {
                "type": "outbound",
                "silent": False,
                "ts": (self.now - timedelta(hours=14)).isoformat(),
            },
        ]
        slot = decision.compute_slot(_brain(), now=self.now, events=events)
        self.assertEqual(slot["slot"], "MUST_WRITE")
        self.assertFalse(slot["failure_24h"])

    def test_failure_flag_after_24h_does_not_spam_if_pinged_recently(self) -> None:
        events = [
            {"type": "inbound", "ts": (self.now - timedelta(hours=30)).isoformat()},
            {
                "type": "outbound",
                "silent": False,
                "ts": (self.now - timedelta(hours=2)).isoformat(),
            },
        ]
        slot = decision.compute_slot(_brain(), now=self.now, events=events)
        self.assertTrue(slot["failure_24h"])
        self.assertEqual(slot["slot"], "MAY_WRITE")

    def test_brain_timestamp_used_when_analytics_empty(self) -> None:
        brain = _brain(
            last_user_contact=(self.now - timedelta(hours=16)).isoformat(),
            last_bibo_message=(self.now - timedelta(hours=13)).isoformat(),
        )
        slot = decision.compute_slot(brain, now=self.now, events=[])
        self.assertEqual(slot["slot"], "MUST_WRITE")
        self.assertGreaterEqual(slot["hours_since_user"], 15)

    def test_night_quiet_holds_anti_silence(self) -> None:
        now = datetime(2026, 9, 16, 3, 0, tzinfo=timezone.utc)
        events = [
            {"type": "inbound", "ts": (now - timedelta(hours=15)).isoformat()},
            {"type": "outbound", "silent": False, "ts": (now - timedelta(hours=14)).isoformat()},
        ]
        slot = decision.compute_slot(_brain(), now=now, events=events)
        self.assertEqual(slot["slot"], "SILENT")
        self.assertIn("nocna", slot["reason"])

    def test_first_breath_writes_even_at_night(self) -> None:
        now = datetime(2026, 9, 16, 3, 0, tzinfo=timezone.utc)
        slot = decision.compute_slot(_brain(breath_count=0), now=now, events=[])
        self.assertEqual(slot["slot"], "MUST_WRITE")


class DecayTests(unittest.TestCase):
    def setUp(self) -> None:
        self.now = datetime(2026, 9, 16, 15, 0, tzinfo=timezone.utc)

    def test_entries_halve_then_archive(self) -> None:
        brain = _brain()
        brain["zachowania_biezace"]["entries"] = [
            {"ts": (self.now - timedelta(hours=10)).isoformat(), "note": "świeży"},
            {"ts": (self.now - timedelta(hours=50)).isoformat(), "note": "zirytowany gadulstwem"},
            {"ts": (self.now - timedelta(hours=80)).isoformat(), "note": "stary złość"},
        ]
        stats = decision.decay_zachowania(brain, now=self.now)
        self.assertEqual(stats["active"], 2)
        self.assertEqual(stats["halved"], 1)
        self.assertEqual(stats["archived"], 1)
        notes = {e["note"]: e["weight"] for e in brain["zachowania_biezace"]["entries"]}
        self.assertEqual(notes["świeży"], 1.0)
        self.assertEqual(notes["zirytowany gadulstwem"], 0.5)
        archived_notes = [e["note"] for e in brain["zachowania_biezace"]["archived"]]
        self.assertIn("stary złość", archived_notes)

    def test_stale_data_dict_is_archived(self) -> None:
        brain = _brain()
        brain["zachowania_biezace"]["data"] = {"ton": "zirytowany gadulstwem"}
        brain["zachowania_biezace"]["last_updated"] = (
            self.now - timedelta(hours=80)
        ).isoformat()
        decision.decay_zachowania(brain, now=self.now)
        self.assertEqual(brain["zachowania_biezace"]["data"], {})
        self.assertEqual(brain["zachowania_biezace"]["data_weight"], 0.0)
        self.assertEqual(
            brain["zachowania_biezace"]["archived_data"][0]["data"]["ton"],
            "zirytowany gadulstwem",
        )

    def test_maintain_increments_even_on_silent(self) -> None:
        brain = _brain(breath_count=8)
        slot = {
            "hours_since_user": 30.0,
            "failure_24h": True,
            "slot": "SILENT",
        }
        updated = decision.maintain_brain(brain, slot, now=self.now)
        self.assertEqual(updated["breath_count"], 9)
        self.assertTrue(updated["silence"]["failure_24h"])
        self.assertEqual(brain["breath_count"], 8)

    def test_user_reply_clears_failure(self) -> None:
        brain = {
            "silence": {
                "failure_24h": True,
                "failure_at": "2026-09-15T10:00:00+00:00",
            }
        }
        decision.stamp_last_user_contact(brain, now=self.now)
        self.assertFalse(brain["silence"]["failure_24h"])
        self.assertIsNone(brain["silence"]["failure_at"])
        self.assertTrue(brain["last_user_contact"])


if __name__ == "__main__":
    unittest.main()
