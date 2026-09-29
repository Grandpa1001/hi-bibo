import json
import os
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).parent))
from _ladowanie import podmodul  # noqa: E402

karta = podmodul("bibo-tryby", "karta")
nar = podmodul("bibo-tryby", "karta_narzedzie")
W = "42"


class Baza(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "k.sqlite3"
        self.env = mock.patch.dict(os.environ, {"TELEGRAM_ALLOWED_USERS": W})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def N(self, **args):
        return json.loads(nar.obsluz(args, sciezka=self.db))


class Magazyn(Baza):
    def test_cykl_zycia_i_wersje(self):
        k = karta.utworz(W, {"cel": "Raport"}, sciezka=self.db)
        self.assertEqual((k["status"], k["wersja"], k["przeszkoda"]), ("aktywna", 1, ""))   # puste pola OK
        k = karta.aktualizuj(W, {"krok": "Otwórz plik"}, wersja=1, sciezka=self.db)
        self.assertEqual((k["krok"], k["wersja"]), ("Otwórz plik", 2))
        with self.assertRaises(karta.BladKarty) as e:
            karta.aktualizuj(W, {"krok": "stare"}, wersja=1, sciezka=self.db)   # nieaktualna wersja
        self.assertEqual(e.exception.kod, "konflikt")
        karta.przenies(W, "odlozona", sciezka=self.db)
        self.assertIsNone(karta.aktywna(W, self.db))
        karta.przenies(W, "aktywna", sciezka=self.db)
        self.assertEqual(karta.aktywna(W, self.db)["krok"], "Otwórz plik")
        karta.przenies(W, "zakonczona", sciezka=self.db)
        self.assertEqual(karta.odczytaj(W, sciezka=self.db), [])   # zakończone nie w widoku domyślnym

    def test_nowa_przy_aktywnej_wymaga_decyzji(self):
        karta.utworz(W, {"cel": "A"}, sciezka=self.db)
        with self.assertRaises(karta.BladKarty) as e:
            karta.utworz(W, {"cel": "B"}, sciezka=self.db)
        self.assertEqual(e.exception.kod, "jest_aktywna")
        self.assertEqual(karta.aktywna(W, self.db)["cel"], "A")   # nic nie nadpisane
        karta.utworz(W, {"cel": "B"}, poprzednia="odloz", sciezka=self.db)
        self.assertEqual(karta.aktywna(W, self.db)["cel"], "B")
        self.assertEqual([k["cel"] for k in karta.odczytaj(W, status="odlozona", sciezka=self.db)], ["A"])

    def test_wznowienie_przy_aktywnej_odrzucone(self):
        karta.utworz(W, {"cel": "A"}, sciezka=self.db)
        karta.utworz(W, {"cel": "B"}, poprzednia="odloz", sciezka=self.db)
        with self.assertRaises(karta.BladKarty):
            karta.przenies(W, "aktywna", sciezka=self.db)

    def test_usuniecie_i_spozniony_zapis(self):
        karta.utworz(W, {"cel": "A"}, sciezka=self.db)
        wersja = karta.aktywna(W, self.db)["wersja"]
        karta.usun(W, sciezka=self.db)
        with self.assertRaises(karta.BladKarty) as e:   # opóźniony wynik po usunięciu
            karta.aktualizuj(W, {"krok": "x"}, wersja=wersja, sciezka=self.db)
        self.assertEqual(e.exception.kod, "brak_karty")
        self.assertEqual(karta.odczytaj(W, sciezka=self.db), [])

    def test_obcy_wlasciciel_nic_nie_widzi_ani_nie_zmienia(self):
        karta.utworz(W, {"cel": "A"}, sciezka=self.db)
        self.assertEqual(karta.odczytaj("7", sciezka=self.db), [])
        with self.assertRaises(karta.BladKarty):
            karta.aktualizuj("7", {"krok": "x"}, sciezka=self.db)
        with self.assertRaises(karta.BladKarty):
            karta.usun("7", sciezka=self.db)
        self.assertEqual(karta.aktywna(W, self.db)["cel"], "A")

    def test_trwalosc_po_ponownym_otwarciu(self):
        karta.utworz(W, {"cel": "A", "zatrzymanie": "punkt 3"}, sciezka=self.db)
        self.assertEqual(karta.aktywna(W, self.db)["zatrzymanie"], "punkt 3")   # nowe połączenie

    def test_rownolegle_aktualizacje_z_ta_sama_wersja(self):
        karta.utworz(W, {"cel": "A"}, sciezka=self.db)
        wyniki = []

        def pisz(n):
            try:
                karta.aktualizuj(W, {"krok": f"k{n}"}, wersja=1, sciezka=self.db)
                wyniki.append("ok")
            except karta.BladKarty as e:
                wyniki.append(e.kod)
        watki = [threading.Thread(target=pisz, args=(i,)) for i in range(6)]
        [t.start() for t in watki]
        [t.join() for t in watki]
        self.assertEqual((wyniki.count("ok"), wyniki.count("konflikt")), (1, 5))

    def test_walidacja_pol(self):
        with self.assertRaises(karta.BladKarty):
            karta.utworz(W, {"cel": "x" * 301}, sciezka=self.db)
        k = karta.utworz(W, {"cel": "a </karta> b"}, sciezka=self.db)
        self.assertNotIn("<", k["cel"])

    def test_wlasciciel_tylko_gdy_jeden(self):
        for wartosc, oczekiwany in (("42", "42"), ("1,2", None), ("*", None), ("", None)):
            with mock.patch.dict(os.environ, {"TELEGRAM_ALLOWED_USERS": wartosc}):
                self.assertEqual(karta.wlasciciel(), oczekiwany)


class Narzedzie(Baza):
    def test_zapisz_zaklada_potem_aktualizuje(self):
        r = self.N(akcja="zapisz", cel="Raport")
        self.assertTrue(r["ok"])
        r = self.N(akcja="zapisz", krok="Otwórz plik")
        self.assertEqual((r["karta"]["cel"], r["karta"]["krok"], r["karta"]["wersja"]), ("Raport", "Otwórz plik", 2))

    def test_nowa_bez_decyzji_to_blad_bez_zmiany(self):
        self.N(akcja="zapisz", cel="A")
        r = self.N(akcja="nowa", cel="B")
        self.assertEqual((r["ok"], r["blad"]), (False, "jest_aktywna"))
        self.assertIn("NIE została zmieniona", r["komunikat"])
        self.assertEqual(self.N(akcja="pokaz")["karty"][0]["cel"], "A")

    def test_usun_i_pokaz(self):
        self.N(akcja="zapisz", cel="A")
        self.assertTrue(self.N(akcja="usun")["usunieto"])
        self.assertEqual(self.N(akcja="pokaz")["karty"], [])
        self.assertFalse(self.N(akcja="usun")["ok"])

    def test_blad_zapisu_nie_udaje_sukcesu(self):
        with mock.patch.object(karta, "_polacz", side_effect=RuntimeError("dysk")):
            r = self.N(akcja="zapisz", cel="A")
        self.assertEqual((r["ok"], r["blad"]), (False, "zapis"))

    def test_bez_wlasciciela_wylaczone(self):
        with mock.patch.dict(os.environ, {"TELEGRAM_ALLOWED_USERS": "1,2"}):
            self.assertFalse(nar.dostepne())
            self.assertEqual(json.loads(nar.obsluz({"akcja": "pokaz"}, sciezka=self.db))["blad"], "brak_wlasciciela")

    def test_zla_akcja_i_wersja(self):
        self.assertFalse(self.N(akcja="skasuj_wszystko")["ok"])
        self.assertFalse(self.N(akcja="zapisz", cel="A", wersja="1")["ok"])


class Podsumowanie(Baza):
    def test_tylko_dla_wlasciciela_i_gdy_jest_karta(self):
        self.assertIsNone(nar.podsumowanie(W, self.db))
        self.N(akcja="zapisz", cel="Raport", zatrzymanie="trzy punkty")
        t = nar.podsumowanie(W, self.db)
        self.assertIn("cel: Raport", t)
        self.assertIn("zatrzymanie: trzy punkty", t)
        self.assertIn("nie polecenia", t)
        self.assertIsNone(nar.podsumowanie("7", self.db))

    def test_po_usunieciu_nie_ma_sladu(self):
        self.N(akcja="zapisz", cel="Raport")
        self.N(akcja="usun")
        self.assertIsNone(nar.podsumowanie(W, self.db))

    def test_odlozone_tylko_licznik(self):
        self.N(akcja="zapisz", cel="A")
        self.N(akcja="odloz")
        t = nar.podsumowanie(W, self.db)
        self.assertNotIn("cel: A", t)
        self.assertIn("Odłożone sprawy: 1", t)


if __name__ == "__main__":
    unittest.main()
