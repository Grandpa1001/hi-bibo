import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _ladowanie import wtyczka  # noqa: E402

podpis = wtyczka("bibo-podpis")


class Znaczniki(unittest.TestCase):
    def test_usuwa_znacznik_przed_podpisem(self):
        self.assertEqual(podpis.sign("Która rzecz bardziej uwiera? [[tryb:detektyw]]", "telegram"),
                         "Która rzecz bardziej uwiera? bibo")

    def test_znacznik_w_nowej_linii(self):
        self.assertEqual(podpis.sign("Ok.\n[[tryb:detektyw]]", "telegram"), "Ok. bibo")

    def test_bez_znacznika_bez_zmian(self):
        self.assertEqual(podpis.sign("Cześć!", "telegram"), "Cześć! bibo")

    def test_nie_rusza_zwyklych_nawiasow(self):
        self.assertEqual(podpis.sign("Lista [[a]] zostaje", "telegram"), "Lista [[a]] zostaje bibo")

    def test_poza_telegramem_nic(self):
        self.assertIsNone(podpis.sign("tekst [[tryb:detektyw]]", "cli"))


if __name__ == "__main__":
    unittest.main()
