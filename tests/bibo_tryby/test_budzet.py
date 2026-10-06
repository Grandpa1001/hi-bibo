"""Budżet kontekstu: Hermes zapisuje kontekst z `pre_llm_call` w historii, więc linie stanu nie mogą kumulować się co turę.

Regresja po komunikacie „Context is over the compression threshold … compression is blocked (structural_backoff)”:
stały prompt urósł, a karta sprawy i tryb dnia były doklejane do KAŻDEJ wiadomości i odtwarzane w historii.
"""
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).parent))
from _ladowanie import podmodul, wtyczka  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
stan = podmodul("bibo-tryby", "stan")
tryb = podmodul("bibo-tryby", "tryb")
karta = podmodul("bibo-tryby", "karta")
nar = podmodul("bibo-tryby", "karta_narzedzie")
kontakt = podmodul("bibo-tryby", "kontakt")
kryzys = podmodul("bibo-tryby", "kryzys")
wt = wtyczka("bibo-tryby")

W = "42"
TERAZ = datetime(2026, 10, 7, 12, 0, tzinfo=timezone.utc)


class RazNaZmiane(unittest.TestCase):
    def setUp(self):
        wt._wstrzykniete.clear()

    def test_ta_sama_linia_wchodzi_raz_potem_co_n_tur(self):
        wyniki = [wt._raz_na_zmiane(W, "tryb", "linia", "s1") for _ in range(2 * wt.ODSWIEZ_CO_TUR + 1)]
        wstrzykniete = [i for i, w in enumerate(wyniki) if w]
        self.assertEqual(wstrzykniete, [0, wt.ODSWIEZ_CO_TUR, 2 * wt.ODSWIEZ_CO_TUR])

    def test_zmiana_tresci_nowa_sesja_i_pierwsza_tura_wymuszaja_wstrzykniecie(self):
        self.assertIsNotNone(wt._raz_na_zmiane(W, "tryb", "a", "s1"))
        self.assertIsNone(wt._raz_na_zmiane(W, "tryb", "a", "s1"))
        self.assertEqual(wt._raz_na_zmiane(W, "tryb", "b", "s1"), "b")                       # zmiana trybu
        self.assertIsNone(wt._raz_na_zmiane(W, "tryb", "b", "s1"))
        self.assertEqual(wt._raz_na_zmiane(W, "tryb", "b", "s2"), "b")                       # /new → inna sesja
        self.assertIsNone(wt._raz_na_zmiane(W, "tryb", "b", "s2"))
        self.assertEqual(wt._raz_na_zmiane(W, "tryb", "b", "s2", pierwsza_tura=True), "b")   # pusta historia

    def test_zniknieta_linia_resetuje_pamiec(self):
        wt._raz_na_zmiane(W, "karta", "karta v1", "s")
        self.assertIsNone(wt._raz_na_zmiane(W, "karta", None, "s"))
        self.assertEqual(wt._raz_na_zmiane(W, "karta", "karta v1", "s"), "karta v1")        # wraca od razu po przerwie

    def test_klucze_i_userzy_sa_niezalezni(self):
        self.assertIsNotNone(wt._raz_na_zmiane(W, "tryb", "x", "s"))
        self.assertIsNotNone(wt._raz_na_zmiane(W, "karta", "x", "s"))
        self.assertIsNotNone(wt._raz_na_zmiane("7", "tryb", "x", "s"))


class WTurze(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = mock.patch.dict(os.environ, {"TELEGRAM_ALLOWED_USERS": W, "HERMES_HOME": self.tmp.name})
        self.env.start()
        os.environ.pop("BIBO_STREFA", None)
        self.zegar = mock.patch.object(kontakt, "teraz", return_value=TERAZ)
        self.zegar.start()
        kryzys._dzien.clear()
        kryzys._tura.clear()
        wt._wstrzykniete.clear()
        karta.utworz(W, {"cel": "Dokończyć raport kwartalny dla zarządu", "przeszkoda": "nie wiem, od czego zacząć",
                         "krok": "Otworzyć plik i wypisać trzy punkty", "zatrzymanie": "Zatrzymałem się na tabeli z wynikami"})
        stan.zapisz_wpis(W, 2, -1, uwaga="hyperfocus", teraz=TERAZ)

    def tearDown(self):
        self.zegar.stop()
        self.env.stop()
        self.tmp.cleanup()

    def tura(self, sesja="s1", pierwsza=False, tekst="hej"):
        return (wt._przed_tura(platform="telegram", sender_id=W, user_message=tekst, session_id=sesja, is_first_turn=pierwsza) or {}).get("context", "")

    def test_dwanascie_tur_wstrzykuje_stan_dwa_razy_a_nie_dwanascie(self):
        wstrzykniecia = [self.tura(pierwsza=(i == 0)) for i in range(12)]
        z_trescia = [c for c in wstrzykniecia if "Stan dnia" in c]
        self.assertEqual(len(z_trescia), -(-12 // wt.ODSWIEZ_CO_TUR))           # tury 0 i 6
        razem = sum(len(c) for c in wstrzykniecia)
        naiwnie = 12 * len(wstrzykniecia[0])
        self.assertLess(razem, naiwnie * 0.4)                                   # kilkakrotnie mniej niż „co turę”
        self.assertEqual(wstrzykniecia[0].count("Karta sprawy"), 1)

    def test_zmiana_trybu_albo_karty_wchodzi_od_razu(self):
        self.tura(pierwsza=True)
        self.assertEqual(self.tura(), "")                                       # nic nowego
        stan.zapisz_wpis(W, -2, -2, teraz=TERAZ)                                # nowy tryb dnia
        c = self.tura()
        self.assertIn("Regeneracja", c)
        self.assertNotIn("Karta sprawy", c)                                     # karta bez zmian: nie powtarzamy
        karta.aktualizuj(W, {"krok": "Zadzwonić do klienta"})
        self.assertIn("Zadzwonić do klienta", self.tura())

    def test_nowa_sesja_dostaje_pelny_stan(self):
        self.tura("s1", pierwsza=True)
        c = self.tura("s2", pierwsza=True)                                      # /new
        self.assertIn("Karta sprawy", c)
        self.assertIn("Stan dnia", c)

    def test_licznik_tur_i_aktywnosc_dzialaja_mimo_pominietego_tekstu(self):
        for i in range(5):
            self.tura(pierwsza=(i == 0))
        self.assertEqual(stan.zaangazowanie(W)["tury"], 5)

    def test_kryzys_nigdy_nie_jest_pomijany(self):
        self.tura(pierwsza=True)
        kryzys.zanotuj(W)
        self.assertIn("Przerwij tryb planowania", self.tura())
        self.assertIn("Nie planuj dnia", self.tura())
        self.assertIn("Nie planuj dnia", self.tura())                           # linia dnia bez deduplikacji


class StalyBudzet(unittest.TestCase):
    """Górne granice, które mają zatrzymać ciche puchnięcie stałego promptu (każdy bajt płacisz przy każdej wiadomości)."""

    def test_soul_nie_rosnie_ponad_budzet(self):
        n = len((REPO / "SOUL.md").read_bytes())
        self.assertLessEqual(n, 10_000, f"SOUL.md ma {n} B; budżet 10 000 B (≈3,6 tys. tokenów). Skróć, zanim dodasz.")

    def test_schemat_narzedzia_karty(self):
        n = len(json.dumps(nar.SCHEMAT, ensure_ascii=False))
        self.assertLessEqual(n, 2_500, f"schemat bibo_karta ma {n} B; budżet 2 500 B")

    def test_linie_doklejane_do_tury_sa_krotkie(self):
        self.assertLessEqual(len(tryb.kontekst({"cwiartka": "tension", "uwaga": "normal"})), 300)
        self.assertLessEqual(len(tryb.kontekst({"cwiartka": "tension", "uwaga": "hyperfocus"})), 560)
        self.assertLessEqual(len(tryb.kontekst({"cwiartka": "tension", "uwaga": "hypofocus"})), 560)

    def test_prog_kompresji_zostawia_miejsce_na_rozmowe(self):
        cfg = (REPO / "config.yaml").read_text(encoding="utf-8")
        install = (REPO / "install.sh").read_text(encoding="utf-8")
        self.assertIn("threshold_tokens: 20000", cfg)
        self.assertIn('"compression.threshold_tokens=20000"', install)
        self.assertIn('"compression.protect_last_n=8"', install)


if __name__ == "__main__":
    unittest.main()
