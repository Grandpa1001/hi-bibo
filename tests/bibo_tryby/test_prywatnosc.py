"""Eksport i usuwanie danych stanu: kompletność, plik tymczasowy znika, potwierdzenie, czyszczenie pliku bazy, zakres."""
import asyncio
import json
import os
import sqlite3
import sys
import tempfile
import unittest
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock
from unittest.mock import AsyncMock, MagicMock

sys.path.insert(0, str(Path(__file__).parent))
from _ladowanie import podmodul, wtyczka  # noqa: E402

prywatnosc = podmodul("bibo-tryby", "prywatnosc")
stan = podmodul("bibo-tryby", "stan")
karta = podmodul("bibo-tryby", "karta")
kontakt = podmodul("bibo-tryby", "kontakt")
magazyn = podmodul("bibo-tryby", "magazyn")
wt = wtyczka("bibo-tryby")

W = "42"
TERAZ = datetime(2026, 10, 7, 8, 0, tzinfo=timezone.utc)
SEKRET = "wiadomość tajna tylko w notatce"


class Baza(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = mock.patch.dict(os.environ, {"TELEGRAM_ALLOWED_USERS": W, "HERMES_HOME": self.tmp.name})
        self.env.start()
        os.environ.pop("BIBO_STREFA", None)
        self.zegar = mock.patch.object(kontakt, "teraz", return_value=TERAZ)
        self.zegar.start()
        self.zapelnij()

    def tearDown(self):
        self.zegar.stop()
        self.env.stop()
        self.tmp.cleanup()

    def zapelnij(self):
        """Po jednym zapisie w każdej tabeli stanu (domyślna baza w tymczasowym HERMES_HOME)."""
        for d in (1, 2, 3):
            stan.zapisz_wpis(W, 2, 2, teraz=TERAZ - timedelta(days=d))
        stan.doprecyzuj(W, notatka=SEKRET, teraz=TERAZ - timedelta(days=3))
        s = stan.zapisz_sygnal(W, "phrase", "bad_day", teraz=TERAZ)
        stan.oznacz_pytanie_celu(W, "bad_day", teraz=TERAZ)
        stan.odpowiedz_na_cel(W, "bad_day", False, teraz=TERAZ)
        stan.czy_pokazac_siatke(W, teraz=TERAZ)
        stan.zapisz_oszacowanie(W, {"cwiartka": "peak", "energia": 2, "przyjemnosc": 2}, teraz=TERAZ)
        stan.zapisz_wsparcie(W, teraz=TERAZ)
        stan.rejestruj_ture(W, teraz=TERAZ)
        stan.zapisz_dlugosc(W, 55, teraz=TERAZ)
        stan.zapisz_podsumowanie_tygodnia(W, "2026-W41", "t", "{}", teraz=TERAZ)
        with closing(stan._polacz()) as db:
            db.execute("INSERT INTO przypomnienia_uwagi VALUES (?,?,?,1)", (W, "2026-10-07", "2026-10-07T08:00:00+00:00"))
            # dane innego usera, których eksport i usuwanie nie mogą ruszyć
            db.execute("INSERT INTO wpisy_stanu (id,wlasciciel,utworzono,energia,przyjemnosc,cwiartka,uwaga,zrodlo) VALUES "
                       "('x','99','2026-10-01T00:00:00+00:00',1,1,'peak','normal','manual')")


class Eksport(Baza):
    def test_obejmuje_wszystkie_tabele_wlasciciela_i_nie_cudze(self):
        e = stan.eksport(W)
        self.assertEqual(e["format"], "bibo-stan-1")
        self.assertEqual(set(e["tabele"]), set(stan.TABELE_DANYCH))
        for tabela, wiersze in e["tabele"].items():
            self.assertTrue(wiersze, f"pusta tabela w eksporcie: {tabela}")
            self.assertTrue(all(r["wlasciciel"] == W for r in wiersze), tabela)
        self.assertIn(SEKRET, json.dumps(e, ensure_ascii=False))        # notatka usera jest w eksporcie: to jego dane
        self.assertIn("falszywe_alarmy", e["metryki"])

    def test_metryka_falszywych_alarmow(self):
        self.assertEqual(stan.falszywe_alarmy(W), {"razem": 1, "nie": 1, "odsetek": 100})
        t = TERAZ + timedelta(days=1)
        stan.zapisz_sygnal(W, "phrase", "bad_day", teraz=t)
        stan.oznacz_pytanie_celu(W, "bad_day", teraz=t)
        stan.odpowiedz_na_cel(W, "bad_day", True, teraz=t)
        self.assertEqual(stan.falszywe_alarmy(W), {"razem": 2, "nie": 1, "odsetek": 50})

    def test_wysylka_pliku_json_do_wlasciciela_a_kopia_znika(self):
        u = MagicMock()
        wyslane = {}

        async def wywolaj(metoda, dane=None, pliki=None):
            if metoda == "sendDocument":
                sciezka = Path(pliki["document"])
                wyslane["nazwa"] = sciezka.name
                wyslane["tryb"] = oct(sciezka.stat().st_mode & 0o777)
                wyslane["tresc"] = json.loads(sciezka.read_text(encoding="utf-8"))
                wyslane["katalog"] = sciezka.parent
                wyslane["dane"] = dane
            return {}

        u.bot.wywolaj = wywolaj
        self.assertTrue(asyncio.run(prywatnosc.wyslij_eksport(W, u)))
        self.assertEqual(wyslane["nazwa"], "stan-2026-10-07.json")
        self.assertEqual(wyslane["tryb"], "0o600")
        self.assertEqual(wyslane["dane"]["chat_id"], W)
        self.assertEqual(len(wyslane["tresc"]["tabele"]["wpisy_stanu"]), 3)
        self.assertFalse(wyslane["katalog"].exists())                         # katalog tymczasowy usunięty
        self.assertEqual([p for p in magazyn.katalog().iterdir() if p.name.startswith(".eksport")], [])

    def test_awaria_wysylki_kasuje_kopie_i_mowi_userowi(self):
        u = MagicMock()
        wywolania = []

        async def wywolaj(metoda, dane=None, pliki=None):
            wywolania.append(metoda)
            if metoda == "sendDocument":
                raise RuntimeError("siec")
            return {}

        u.bot.wywolaj = wywolaj
        self.assertFalse(asyncio.run(prywatnosc.wyslij_eksport(W, u)))
        self.assertEqual(wywolania, ["sendDocument", "sendMessage"])
        self.assertEqual([p for p in magazyn.katalog().iterdir() if p.name.startswith(".eksport")], [])

    def test_komenda_bez_wlasciciela_i_bez_botu(self):
        with mock.patch.dict(os.environ, {"TELEGRAM_ALLOWED_USERS": "1,2"}):
            self.assertIn("niedostępny", wt._komenda_eksport(""))
        u = MagicMock()
        u.bot = None
        with mock.patch.object(wt.uslugi, "aktywne", return_value=u):
            self.assertIn("za chwilę", wt._komenda_eksport(""))


class Usuwanie(Baza):
    def test_bez_potwierdzenia_tylko_pyta_i_niczego_nie_kasuje(self):
        for arg in ("", "tak", "potwierdz", "usuń"):
            t = wt._komenda_usun(arg)
            self.assertIn("nie da się tego cofnąć", t.lower())
            self.assertIn("/stan_usun potwierdzam", t)
        self.assertEqual(stan.policz_dane(W)["wpisy_stanu"], 3)

    def test_z_potwierdzeniem_kasuje_wszystko_wlasciciela_ale_nie_cudze(self):
        t = wt._komenda_usun("Potwierdzam")
        self.assertIn("Usunięto", t)
        self.assertTrue(all(n == 0 for n in stan.policz_dane(W).values()))
        with closing(stan._polacz()) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM wpisy_stanu WHERE wlasciciel='99'").fetchone()[0], 1)

    def test_tresc_znika_tez_z_pliku_bazy(self):
        plik = magazyn.katalog() / "stan.sqlite3"
        self.assertIn(SEKRET.encode(), b"".join(p.read_bytes() for p in magazyn.katalog().glob("stan.sqlite3*")))
        wt._komenda_usun("potwierdzam")
        for p in magazyn.katalog().glob("stan.sqlite3*"):
            self.assertFalse(SEKRET.encode() in p.read_bytes(), f"treść notatki została w pliku {p.name}")

    def test_blokujacy_czytelnik_daje_uczciwy_komunikat_a_dane_z_tabel_i_tak_znikaja(self):
        czytelnik = sqlite3.connect(magazyn.katalog() / "stan.sqlite3", isolation_level=None)
        try:
            czytelnik.execute("BEGIN")
            czytelnik.execute("SELECT COUNT(*) FROM wpisy_stanu").fetchone()      # trzyma migawkę i blokuje obcięcie WAL
            with mock.patch.object(stan.time, "sleep"):
                t = wt._komenda_usun("potwierdzam")
        finally:
            czytelnik.close()
        self.assertIn("Usunięto", t)
        self.assertIn("fizyczne czyszczenie", t)
        self.assertTrue(all(n == 0 for n in stan.policz_dane(W).values()))
        wt._komenda_usun("potwierdzam")   # ponowienie, gdy czytelnik zniknął
        for p in magazyn.katalog().glob("stan.sqlite3*"):
            self.assertFalse(SEKRET.encode() in p.read_bytes(), p.name)

    def test_po_usunieciu_aplikacja_dziala_od_zera(self):
        wt._komenda_usun("potwierdzam")
        self.assertIsNone(stan.dzisiejszy(W))
        stan.zapisz_wpis(W, 1, 1)
        self.assertEqual(stan.policz_dane(W)["wpisy_stanu"], 1)
        self.assertEqual(wt._siatka_dzien.get(W), None)

    def test_usuwanie_dziala_przy_wylaczonym_stanie(self):
        with mock.patch.object(wt.siatka.magazyn, "ustawienia", return_value={"stan": False}):
            self.assertIn("Usunięto", wt._komenda_usun("potwierdzam"))

    def test_karta_sprawy_zostaje(self):
        karta.utworz(W, {"cel": "Raport"})
        wt._komenda_usun("potwierdzam")
        self.assertEqual(karta.aktywna(W)["cel"], "Raport")
        self.assertIn("karty sprawy", prywatnosc.pytanie_o_usuniecie(W))

    def test_awaria_nie_udaje_sukcesu(self):
        with mock.patch.object(stan, "usun_wszystko", side_effect=RuntimeError("dysk")):
            t = wt._komenda_usun("potwierdzam")
        self.assertNotIn("Usunięto", t)
        self.assertIn("nic nie zostało zmienione", t)


class Komendy(Baza):
    def test_komendy_sa_zarejestrowane(self):
        zarejestrowane = {}
        ctx = MagicMock()
        ctx.register_command = lambda nazwa, fn, **kw: zarejestrowane.__setitem__(nazwa, fn)
        wt.register(ctx)
        for nazwa in ("tydzien", "stan_eksport", "stan_usun", "stan", "fokus"):
            self.assertIn(nazwa, zarejestrowane)


if __name__ == "__main__":
    unittest.main()
