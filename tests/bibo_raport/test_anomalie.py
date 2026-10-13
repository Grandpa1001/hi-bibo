import importlib.util
import sqlite3
import unittest
from pathlib import Path

SKRYPT = Path(__file__).resolve().parents[2] / "scripts" / "bibo_raport.py"
spec = importlib.util.spec_from_file_location("bibo_raport", SKRYPT)
raport = importlib.util.module_from_spec(spec)
spec.loader.exec_module(raport)


def baza(wiadomosci):
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    con.execute("CREATE TABLE sessions (id TEXT, source TEXT)")
    con.execute("CREATE TABLE messages (id INTEGER PRIMARY KEY, session_id TEXT, role TEXT, content TEXT, "
                "tool_calls TEXT, timestamp REAL, active INTEGER DEFAULT 1, compacted INTEGER DEFAULT 0, "
                "finish_reason TEXT DEFAULT 'stop', display_kind TEXT)")
    con.execute("INSERT INTO sessions VALUES ('s1', 'telegram')")
    for rola, tresc, ts, *tc in wiadomosci:
        opcje = tc[1] if len(tc) > 1 else {}
        con.execute("INSERT INTO messages (session_id, role, content, tool_calls, timestamp, active, compacted, "
                    "finish_reason) VALUES ('s1', ?, ?, ?, ?, ?, ?, ?)",
                    (rola, tresc, tc[0] if tc else None, ts, opcje.get("active", 1), opcje.get("compacted", 0),
                     opcje.get("fr", "stop")))
    return con


class Anomalie(unittest.TestCase):
    def rodzaje(self, wiadomosci):
        return [(a["rodzaj"], a["rola"]) for a in raport.anomalie(baza(wiadomosci))]

    def test_czysta_rozmowa(self):
        self.assertEqual(self.rodzaje([("user", "cześć", 1), ("assistant", "hej", 2), ("user", "cześć", 5000)]), [])

    def test_pusta_odpowiedz_asystenta(self):
        self.assertEqual(self.rodzaje([("user", "cześć", 1), ("assistant", "  ", 2)]), [("pusta", "assistant")])
        self.assertEqual(self.rodzaje([("assistant", None, 2)]), [("pusta", "assistant")])

    def test_puste_z_wywolaniem_narzedzia_jest_ok(self):
        self.assertEqual(self.rodzaje([("assistant", "", 2, '[{"function": {"name": "memory"}}]')]), [])

    def test_identyczna_odpowiedz_pod_rzad(self):
        self.assertEqual(self.rodzaje([("assistant", "Dasz radę.", 1), ("user", "ok", 2), ("assistant", "Dasz radę.", 3)]),
                         [("dubel", "assistant")])

    def test_zdublowany_user(self):
        self.assertEqual(self.rodzaje([("user", "napisz", 1), ("user", "napisz", 2)]), [("dubel", "user")])

    def test_kopie_po_kompresji_kontekstu_to_nie_dubel(self):
        # oryginał skompresowany (active=0) + kopia aktywna — tak Hermes przepisuje ogon rozmowy
        orig = {"active": 0, "compacted": 1}
        self.assertEqual(self.rodzaje([("user", "napisz", 1, None, orig), ("user", "napisz", 100)]), [])

    def test_pusta_odpowiedz_skompresowana_liczy_sie_raz(self):
        orig = {"active": 0, "compacted": 1}
        self.assertEqual(self.rodzaje([("user", "pytanie", 1, None, orig), ("assistant", "", 2, None, orig),
                                       ("user", "pytanie", 90, None, orig), ("assistant", "", 91, None, orig)]),
                         [("pusta", "assistant")])

    def test_wewnetrzne_puste_nie_licza_sie(self):
        self.assertEqual(self.rodzaje([("assistant", "", 2, None, {"fr": "tool_calls"})]), [])

    def test_ta_sama_tresc_po_dlugim_czasie_to_nie_dubel(self):
        self.assertEqual(self.rodzaje([("assistant", "Dobra robota.", 1), ("assistant", "Dobra robota.", 1 + 3600)]), [])


if __name__ == "__main__":
    unittest.main()
