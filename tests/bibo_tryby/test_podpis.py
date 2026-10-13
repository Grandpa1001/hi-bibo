import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _ladowanie import wtyczka  # noqa: E402

podpis = wtyczka("bibo-podpis")


class Podpis(unittest.TestCase):
    def test_dokleja_podpis(self):
        self.assertEqual(podpis.sign("Cześć!", "telegram"), "Cześć! bibo")

    def test_nie_rusza_nawiasow(self):
        self.assertEqual(podpis.sign("Lista [[a]] zostaje", "telegram"), "Lista [[a]] zostaje bibo")

    def test_poza_telegramem_i_cronem_nic(self):
        self.assertIsNone(podpis.sign("tekst", "cli"))

    def test_cisza_i_pusty_tekst_bez_podpisu(self):
        self.assertIsNone(podpis.sign("[SILENT]", "cron"))
        self.assertIsNone(podpis.sign("   ", "telegram"))

    def test_nie_dubluje_podpisu_modelu(self):
        self.assertEqual(podpis.sign("Dasz radę, bibo", "telegram"), "Dasz radę bibo")


if __name__ == "__main__":
    unittest.main()
