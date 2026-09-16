#!/usr/bin/env python3
"""Tests for installer helpers and the deterministic decision slot."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "install"))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import decision  # noqa: E402
import setup as installer  # noqa: E402


class InstallerTests(unittest.TestCase):
    def test_voice_pack_pl(self) -> None:
        self.assertEqual(installer.voice_id("pl", "zofia"), "pl-PL-ZofiaNeural")
        self.assertEqual(installer.voice_id("pl", "marek"), "pl-PL-MarekNeural")

    def test_build_brain_contract(self) -> None:
        with open(os.path.join(ROOT, "brain.template.json"), encoding="utf-8") as fh:
            template = json.load(fh)
        brain = installer.build_brain(
            template,
            name="Mira",
            language="pl",
            goal="dowozić sprint",
            voice="pl-PL-ZofiaNeural",
            tts_on=True,
            frequency="normal",
        )
        self.assertEqual(brain["partner"]["name"], "Mira")
        self.assertEqual(brain["partner"]["goal"], "dowozić sprint")
        self.assertTrue(brain["setup"]["complete"])
        self.assertIn("dowozić sprint", brain["cele_i_kierunek"]["deklaracje"])
        self.assertIn("wnioski", brain)
        self.assertEqual(brain["partner"]["tts"]["provider"], "edge")

    def test_suggest_names_are_from_pool(self) -> None:
        names = installer.suggest_names(3)
        self.assertEqual(len(names), 3)
        self.assertTrue(set(names) <= set(installer.NAMES))


class DecisionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.now = datetime(2026, 9, 16, 15, 0, tzinfo=timezone.utc)
        self.brain = {
            "breath_count": 5,
            "partner": {"contact": {"frequency": "normal"}},
            "nawyki": {"data": {}},
        }

    def test_daily_cap_forces_silent(self) -> None:
        events = []
        for i in range(3):
            events.append({
                "type": "outbound",
                "silent": False,
                "ts": (self.now - timedelta(hours=i)).isoformat(),
            })
        slot = decision.compute_slot(self.brain, now=self.now, events=events)
        self.assertEqual(slot["slot"], "SILENT")
        self.assertEqual(slot["spoken_today"], 3)

    def test_first_breath_must_write(self) -> None:
        brain = dict(self.brain)
        brain["breath_count"] = 0
        slot = decision.compute_slot(brain, now=self.now, events=[])
        self.assertEqual(slot["slot"], "MUST_WRITE")

    def test_anti_silence(self) -> None:
        events = [
            {"type": "inbound", "ts": (self.now - timedelta(hours=15)).isoformat()},
            {"type": "outbound", "silent": False, "ts": (self.now - timedelta(hours=14)).isoformat()},
        ]
        slot = decision.compute_slot(self.brain, now=self.now, events=events)
        self.assertEqual(slot["slot"], "MUST_WRITE")


if __name__ == "__main__":
    unittest.main()
