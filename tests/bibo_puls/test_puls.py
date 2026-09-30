import importlib.util
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

SKRYPT = Path(__file__).resolve().parents[2] / "scripts" / "bibo_pulse.py"
spec = importlib.util.spec_from_file_location("bibo_pulse", SKRYPT)
puls = importlib.util.module_from_spec(spec)
spec.loader.exec_module(puls)

CFG = {**puls.DEFAULTS, "chance": 1.0}
POLUDNIE = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)


class Pauza(unittest.TestCase):
    def test_pauza_blokuje_puls(self):
        stan = {"date": "", "count": 0, "last_ts": 0}
        self.assertEqual(puls.decide(CFG, dict(stan), POLUDNIE, None, 0.0, POLUDNIE + timedelta(hours=1)),
                         (False, "pauza w kontakcie"))
        self.assertTrue(puls.decide(CFG, dict(stan), POLUDNIE, None, 0.0, POLUDNIE - timedelta(hours=1))[0])
        self.assertTrue(puls.decide(CFG, dict(stan), POLUDNIE, None, 0.0, None)[0])

    def test_odczyt_pliku_pauzy(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "bibo_pauza.json"
            self.assertIsNone(puls.paused_until(p))
            p.write_text(json.dumps({"do": "2026-10-01T15:00:00+00:00"}))
            self.assertEqual(puls.paused_until(p), datetime(2026, 10, 1, 15, 0, tzinfo=timezone.utc))
            p.write_text(json.dumps({"do": None}))
            self.assertIsNone(puls.paused_until(p))
            p.write_text("{zepsute")
            self.assertIsNone(puls.paused_until(p))


if __name__ == "__main__":
    unittest.main()
