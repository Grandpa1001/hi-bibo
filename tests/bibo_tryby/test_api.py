"""python -m unittest discover -s tests/bibo_tryby  (z katalogu repo, w środowisku Hermesa)."""
import hashlib
import hmac
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from urllib.parse import urlencode

from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

sys.path.insert(0, str(Path(__file__).parent))
from _ladowanie import podmodul  # noqa: E402

api = podmodul("bibo-tryby", "api")
auth = podmodul("bibo-tryby", "auth")

TOKEN = "123456:TEST-token"
UID = 42


def podpisz(user_id: int = UID, teraz: int | None = None, token: str = TOKEN) -> str:
    pola = {"auth_date": str(int(teraz if teraz is not None else time.time())),
            "query_id": "AAE", "signature": "abc",
            "user": json.dumps({"id": user_id, "first_name": "Kamil"}, separators=(",", ":"))}
    dcs = "\n".join(f"{k}={v}" for k, v in sorted(pola.items()))
    sekret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    return urlencode({**pola, "hash": hmac.new(sekret, dcs.encode(), hashlib.sha256).hexdigest()})


class BazaApi(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self._stare = {k: os.environ.get(k) for k in
                       ("HERMES_HOME", "TELEGRAM_BOT_TOKEN", "TELEGRAM_ALLOWED_USERS")}
        os.environ["HERMES_HOME"] = self.tmp.name
        os.environ["TELEGRAM_BOT_TOKEN"] = TOKEN
        os.environ["TELEGRAM_ALLOWED_USERS"] = str(UID)

        app = web.Application(client_max_size=4096, middlewares=[api.bledy])
        api.trasy(app)
        self.server = TestServer(app)
        await self.server.start_server()
        self.client = TestClient(self.server)
        await self.client.start_server()

    async def asyncTearDown(self):
        await self.client.close()
        await self.server.close()
        for k, v in self._stare.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        self.tmp.cleanup()

    def naglowki(self, user_id: int = UID) -> dict:
        return {"X-Init-Data": podpisz(user_id)}

    async def POST(self, sciezka, dane=None, naglowki=None):
        return await self.client.post(sciezka, json=(dane if dane is not None else {}),
                                      headers=naglowki if naglowki is not None else self.naglowki())

    async def GET(self, sciezka, naglowki=None):
        return await self.client.get(sciezka, headers=naglowki if naglowki is not None else self.naglowki())


class KodyBledow(BazaApi):
    async def test_401_bez_initdata(self):
        for r in (await self.client.get("/api/stan"),
                  await self.client.get("/api/stan", headers={"X-Init-Data": "smieci"})):
            j = await r.json()
            self.assertEqual((r.status, j["blad"]), (401, "podpis"))
            self.assertTrue(j["komunikat"])

    async def test_403_obcy_user(self):
        r = await self.GET("/api/stan", naglowki={"X-Init-Data": podpisz(user_id=999)})
        j = await r.json()
        self.assertEqual((r.status, j["blad"]), (403, "uzytkownik"))

    async def test_health_bez_auth(self):
        r = await self.client.get("/health")
        j = await r.json()
        self.assertEqual((r.status, j["ok"]), (200, True))
        self.assertNotIn("adres", j)


if __name__ == "__main__":
    unittest.main()
