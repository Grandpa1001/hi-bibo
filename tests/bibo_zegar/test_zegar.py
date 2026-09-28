"""python -m unittest discover -s tests/bibo_zegar."""
import os
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "bibo_tryby"))
from _ladowanie import podmodul  # noqa: E402

zegar = podmodul("bibo-zegar", "__init__")


class Format(unittest.TestCase):
    def setUp(self):
        self._stara = os.environ.get("BIBO_STREFA")
        os.environ["BIBO_STREFA"] = "Europe/Warsaw"

    def tearDown(self):
        if self._stara is None:
            os.environ.pop("BIBO_STREFA", None)
        else:
            os.environ["BIBO_STREFA"] = self._stara

    def test_zawiera_dzien_date_i_godzine(self):
        # niedziela 28.09.2026, 12:00 UTC = 14:00 Europe/Warsaw (CEST)
        chwila = datetime(2026, 9, 28, 12, 0, tzinfo=timezone.utc)
        tekst = zegar.teraz_tekst(chwila)
        self.assertIn("poniedziałek", tekst)   # 28.09.2026 to poniedziałek
        self.assertIn("28.09.2026", tekst)
        self.assertIn("14:00", tekst)
        self.assertIn("Zaraz", tekst)

    def test_strefa_zima_letnia(self):
        # 15.01.2026 13:00 UTC → 14:00 CET (zima, +1)
        zima = zegar.teraz_tekst(datetime(2026, 1, 15, 13, 0, tzinfo=timezone.utc))
        # 15.07.2026 13:00 UTC → 15:00 CEST (lato, +2)
        lato = zegar.teraz_tekst(datetime(2026, 7, 15, 13, 0, tzinfo=timezone.utc))
        self.assertIn("14:00", zima)
        self.assertIn("15:00", lato)

    def test_zla_strefa_wraca_do_lokalnej(self):
        os.environ["BIBO_STREFA"] = "Nie/Ma-Takiej"
        tekst = zegar.teraz_tekst(datetime(2026, 9, 28, 12, 0, tzinfo=timezone.utc))
        self.assertIn("28.09.2026", tekst)     # sam format działa dalej


class Hook(unittest.TestCase):
    def test_zwraca_context(self):
        wynik = zegar._przed_tura(platform="telegram")
        self.assertIsInstance(wynik, dict)
        self.assertIn("context", wynik)
        self.assertIn("Teraz:", wynik["context"])

    def test_zawsze_zwraca_niezaleznie_od_platformy(self):
        for platform in ("telegram", "cron", "cli", ""):
            self.assertIsNotNone(zegar._przed_tura(platform=platform))


if __name__ == "__main__":
    unittest.main()
