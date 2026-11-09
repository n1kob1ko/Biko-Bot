"""Tests ohne echte KI: python -m unittest test_server  (im Ordner assistent/)"""

import json
import os
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

os.environ["DATA_DIR"] = tempfile.mkdtemp()
os.environ["APP_PASSWORT"] = "geheim123"
import server  # noqa: E402

GEFRAGT = []


def falsche_ki(system, messages, max_tokens=4000, websuche=False):
    GEFRAGT.append({"system": system, "messages": list(messages), "websuche": websuche})
    return "Antwort von Biko"


server.frage_claude = falsche_ki


class Test(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        cls.url = f"http://127.0.0.1:{cls.httpd.server_port}"
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()

    def rufe(self, pfad, daten=None, cookie=None, sprache=None):
        req = urllib.request.Request(self.url + pfad, method="POST" if daten is not None else "GET",
                                     data=json.dumps(daten).encode() if daten is not None else None)
        req.add_header("Content-Type", "application/json")
        if cookie:
            req.add_header("Cookie", cookie)
        if sprache:
            req.add_header("X-Sprache", sprache)
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, json.loads(r.read()), r.headers
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read()), e.headers

    def anmelden(self):
        status, _, h = self.rufe("/api/login", {"passwort": "geheim123"})
        self.assertEqual(status, 200)
        return h["Set-Cookie"].split(";")[0]

    def test_ohne_login_gesperrt(self):
        self.assertEqual(self.rufe("/api/chat", {"text": "hallo"})[0], 401)
        self.assertEqual(self.rufe("/api/profil")[0], 401)

    def test_falsches_passwort_und_chinesischer_fehler(self):
        status, j, _ = self.rufe("/api/login", {"passwort": "falsch"}, sprache="zh-CN")
        self.assertEqual(status, 403)
        self.assertEqual(j["fehler"], "密码不对。")

    def test_gefaelschtes_cookie(self):
        self.assertEqual(self.rufe("/api/profil", cookie="biko_assistent=123.abc")[0], 401)

    def test_chat_merkt_verlauf_und_nutzt_profil(self):
        c = self.anmelden()
        self.rufe("/api/profil", {"name": "Oma Li", "diaet": "wenig Zucker", "sprache": "zh-CN"}, cookie=c)
        status, j, _ = self.rufe("/api/chat", {"text": "Darf ich Kuchen essen?"}, cookie=c)
        self.assertEqual((status, j["antwort"]), (200, "Antwort von Biko"))
        letzte = GEFRAGT[-1]
        self.assertTrue(letzte["websuche"])
        self.assertIn("Oma Li", letzte["system"])
        self.assertIn("wenig Zucker", letzte["system"])
        self.assertIn("Chinesisch", letzte["system"])
        self.rufe("/api/chat", {"text": "Und Obst?"}, cookie=c)
        self.assertEqual([m["role"] for m in GEFRAGT[-1]["messages"]][-3:], ["user", "assistant", "user"])
        self.assertEqual(self.rufe("/api/verlauf/loeschen", {}, cookie=c)[0], 200)
        self.assertEqual(self.rufe("/api/verlauf", cookie=c)[1], [])

    def test_nachricht(self):
        c = self.anmelden()
        status, j, _ = self.rufe("/api/nachricht", {"an": "Enkel", "was": "danke"}, cookie=c)
        self.assertEqual((status, j["nachricht"]), (200, "Antwort von Biko"))
        self.assertFalse(GEFRAGT[-1]["websuche"])

    def test_erinnerungen_pruefen(self):
        c = self.anmelden()
        status, liste, _ = self.rufe("/api/erinnerungen", {"erinnerungen": [
            {"zeit": "20:00", "text": "Tablette", "tage": ["mo", "xx"]},
            {"zeit": "08:00", "text": "Blutdruck"},
        ]}, cookie=c)
        self.assertEqual(status, 200)
        self.assertEqual([e["zeit"] for e in liste], ["08:00", "20:00"])
        self.assertEqual(liste[1]["tage"], ["mo"])
        self.assertEqual(len(liste[0]["tage"]), 7)
        self.assertEqual(self.rufe("/api/erinnerungen", {"erinnerungen": [{"zeit": "25:00", "text": "x"}]}, cookie=c)[0], 400)

    def test_seite_und_kein_pfad_ausbruch(self):
        with urllib.request.urlopen(self.url + "/../server.py") as r:
            self.assertIn(b"<!doctype html>", r.read())


if __name__ == "__main__":
    unittest.main()
