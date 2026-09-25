"""python -m unittest discover -s tests/bibo_tryby  (z katalogu repo, w środowisku Hermesa)"""
import hashlib
import hmac
import json
import os
import sys
import unittest
from pathlib import Path
from urllib.parse import urlencode

sys.path.insert(0, str(Path(__file__).parent))
from _ladowanie import podmodul  # noqa: E402

auth = podmodul("bibo-tryby", "auth")
TOKEN = "123456:TEST-token"


def podpisz(pola: dict, token: str = TOKEN) -> str:
    dcs = "\n".join(f"{k}={v}" for k, v in sorted(pola.items()))
    sekret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    return urlencode({**pola, "hash": hmac.new(sekret, dcs.encode(), hashlib.sha256).hexdigest()})


POLA = {"auth_date": "1000", "query_id": "AAE", "signature": "abc",
        "user": json.dumps({"id": 42, "first_name": "Kamil"}, separators=(",", ":"))}


class InitData(unittest.TestCase):
    def test_poprawny(self):
        self.assertEqual(auth.weryfikuj_init_data(podpisz(POLA), TOKEN, teraz=1100)["id"], 42)

    def test_zmieniony_bajt(self):
        raw = podpisz(POLA).replace("Kamil", "Kamik")
        with self.assertRaises(auth.BladAuth):
            auth.weryfikuj_init_data(raw, TOKEN, teraz=1100)

    def test_inny_bot(self):
        with self.assertRaises(auth.BladAuth):
            auth.weryfikuj_init_data(podpisz(POLA, "999:inny"), TOKEN, teraz=1100)

    def test_przeterminowany(self):
        with self.assertRaises(auth.BladAuth):
            auth.weryfikuj_init_data(podpisz(POLA), TOKEN, teraz=1000 + 3601)

    def test_bez_hash_i_smieci(self):
        for raw in ("", "user=%7B%7D&auth_date=1", "%%%"):
            with self.assertRaises(auth.BladAuth):
                auth.weryfikuj_init_data(raw, TOKEN, teraz=1100)

    def test_pusty_token(self):
        with self.assertRaises(auth.BladAuth):
            auth.weryfikuj_init_data(podpisz(POLA, ""), "", teraz=1100)


class Uzytkownicy(unittest.TestCase):
    def setUp(self):
        self._stare = os.environ.get("TELEGRAM_ALLOWED_USERS")

    def tearDown(self):
        if self._stare is None:
            os.environ.pop("TELEGRAM_ALLOWED_USERS", None)
        else:
            os.environ["TELEGRAM_ALLOWED_USERS"] = self._stare

    def test_dozwolony_i_obcy(self):
        os.environ["TELEGRAM_ALLOWED_USERS"] = "42, 7"
        self.assertEqual(auth.sprawdz_usera({"id": 42}), "42")
        with self.assertRaises(auth.BladAuth):
            auth.sprawdz_usera({"id": 5})

    def test_pusta_lista_blokuje(self):
        os.environ["TELEGRAM_ALLOWED_USERS"] = ""
        with self.assertRaises(auth.BladAuth):
            auth.sprawdz_usera({"id": 42})


if __name__ == "__main__":
    unittest.main()
