"""Tests ohne echte KI: python -m unittest test_server  (im Ordner assistent/)"""

import json
import os
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from datetime import timedelta
from http.server import ThreadingHTTPServer
from types import SimpleNamespace

os.environ["DATA_DIR"] = tempfile.mkdtemp()
os.environ["APP_PASSWORT"] = "geheim123"
import server  # noqa: E402

GEFRAGT = []


def falsche_ki(system, messages, max_tokens=4000, websuche=False, werkzeuge=None):
    GEFRAGT.append({"system": system, "messages": list(messages), "websuche": websuche, "werkzeuge": werkzeuge})
    return "Antwort von Biko"


ECHTE_SCHLEIFE = server.frage_claude   # die echte Werkzeug-Schleife, für die Tests mit Drehbuch
server.frage_claude = falsche_ki


def text(t):
    return SimpleNamespace(type="text", text=t)


def werkzeug(name, eingabe, nr="tu_1"):
    return SimpleNamespace(type="tool_use", id=nr, name=name, input=eingabe)


def antwort(stop, *bloecke):
    return SimpleNamespace(stop_reason=stop, content=list(bloecke))


def tag(plus=0):
    return (server.jetzt() + timedelta(days=plus)).strftime("%Y-%m-%d")


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

    # ---------- Erinnerungen im Gespräch: Biko schreibt sie sich selbst auf ----------

    def drehbuch(self, *antworten):
        """Echte Schleife in frage_claude, aber die Claude-API antwortet nach Drehbuch. Liefert die Anfragen."""
        anfragen, rest = [], list(antworten)

        def api(**kw):
            anfragen.append({**kw, "messages": list(kw["messages"])})
            return rest.pop(0)

        alt_schleife, alt_api = server.frage_claude, server.claude_anfrage
        server.frage_claude, server.claude_anfrage = ECHTE_SCHLEIFE, api
        self.addCleanup(lambda: (setattr(server, "frage_claude", alt_schleife), setattr(server, "claude_anfrage", alt_api)))
        return anfragen

    def leeren(self, c):
        self.assertEqual(self.rufe("/api/erinnerungen", {"erinnerungen": []}, cookie=c)[0], 200)

    def test_biko_merkt_sich_eine_erinnerung_aus_dem_gespraech(self):
        c = self.anmelden()
        self.leeren(c)
        anfragen = self.drehbuch(
            antwort("tool_use", werkzeug("erinnerung_merken", {"text": "Arzttermin", "zeit": "15:00", "datum": tag(1)})),
            antwort("end_turn", text("Mach ich. Morgen um 15 Uhr erinnere ich dich an den Arzttermin.")),
        )
        status, j, _ = self.rufe("/api/chat", {"text": "Erinnere mich morgen um 15 Uhr an den Arzttermin"}, cookie=c)
        self.assertEqual(status, 200)
        self.assertIn("Arzttermin", j["antwort"])
        self.assertEqual([(e["text"], e["zeit"], e["datum"]) for e in j["gemerkt"]], [("Arzttermin", "15:00", tag(1))])
        self.assertEqual(j["vergessen"], [])
        self.assertEqual(self.rufe("/api/erinnerungen", cookie=c)[1], j["erinnerungen"])
        self.assertEqual(len(j["erinnerungen"]), 1)
        # Biko hat die Werkzeuge bekommen und das Ergebnis zurückgemeldet bekommen
        namen = {w["name"] for w in anfragen[0]["tools"]}
        self.assertLessEqual({"erinnerung_merken", "erinnerung_loeschen", "web_search"}, namen)
        ergebnis = anfragen[1]["messages"][-1]["content"][0]
        self.assertEqual((ergebnis["type"], ergebnis["tool_use_id"]), ("tool_result", "tu_1"))
        self.assertFalse(ergebnis.get("is_error"))
        self.leeren(c)

    def test_wiederholte_erinnerung_an_bestimmten_wochentagen(self):
        c = self.anmelden()
        self.leeren(c)
        self.drehbuch(
            antwort("tool_use", werkzeug("erinnerung_merken", {"text": "Tablette", "zeit": "08:00", "tage": ["mo", "do"]})),
            antwort("end_turn", text("Gemerkt.")),
        )
        j = self.rufe("/api/chat", {"text": "Jeden Montag und Donnerstag um 8 die Tablette"}, cookie=c)[1]
        self.assertEqual((j["gemerkt"][0]["tage"], j["gemerkt"][0]["datum"]), (["mo", "do"], None))
        self.leeren(c)

    def test_falsche_oder_vergangene_zeit_geht_als_fehler_an_biko_zurueck(self):
        c = self.anmelden()
        self.leeren(c)
        for eingabe in ({"text": "x", "zeit": "25:00"}, {"text": "x", "zeit": "08:00", "datum": tag(-1)},
                        {"text": "x", "zeit": "08:00", "datum": "2026-13-40"}, {"zeit": "08:00"}):
            anfragen = self.drehbuch(antwort("tool_use", werkzeug("erinnerung_merken", eingabe)),
                                     antwort("end_turn", text("Um wie viel Uhr genau?")))
            j = self.rufe("/api/chat", {"text": "Erinnere mich"}, cookie=c)[1]
            self.assertTrue(anfragen[1]["messages"][-1]["content"][0]["is_error"], eingabe)
            self.assertEqual((j["gemerkt"], j["erinnerungen"]), ([], []), eingabe)

    def test_biko_loescht_eine_erinnerung_auf_zuruf(self):
        c = self.anmelden()
        liste = self.rufe("/api/erinnerungen", {"erinnerungen": [{"zeit": "08:00", "text": "Tablette"}]}, cookie=c)[1]
        anfragen = self.drehbuch(
            antwort("tool_use", werkzeug("erinnerung_loeschen", {"id": "gibt-es-nicht"})),
            antwort("tool_use", werkzeug("erinnerung_loeschen", {"id": liste[0]["id"]}, "tu_2")),
            antwort("end_turn", text("Erledigt, daran erinnere ich dich nicht mehr.")),
        )
        j = self.rufe("/api/chat", {"text": "Vergiss die Tablette"}, cookie=c)[1]
        self.assertTrue(anfragen[1]["messages"][-1]["content"][0]["is_error"])
        self.assertEqual([e["text"] for e in j["vergessen"]], ["Tablette"])
        self.assertEqual(self.rufe("/api/erinnerungen", cookie=c)[1], [])

    def test_biko_kennt_seine_erinnerungen_und_soll_nichts_behaupten(self):
        c = self.anmelden()
        liste = self.rufe("/api/erinnerungen", {"erinnerungen": [{"zeit": "08:00", "text": "Blutdrucktablette"}]}, cookie=c)[1]
        self.rufe("/api/chat", {"text": "Woran erinnerst du mich?"}, cookie=c)
        system = GEFRAGT[-1]["system"]
        self.assertIn("Blutdrucktablette", system)
        self.assertIn(liste[0]["id"], system)
        self.assertIn("erinnerung_merken", system)
        self.assertTrue(GEFRAGT[-1]["werkzeuge"])
        self.leeren(c)

    def test_nachricht_bekommt_keine_werkzeuge(self):
        c = self.anmelden()
        self.rufe("/api/nachricht", {"an": "Enkel", "was": "danke"}, cookie=c)
        self.assertFalse(GEFRAGT[-1]["werkzeuge"])

    def test_einmalige_erinnerung_von_gestern_verschwindet(self):
        c = self.anmelden()
        server.schreiben("erinnerungen", [
            {"id": "alt", "zeit": "08:00", "text": "war gestern", "tage": sorted(server.TAGE), "aktiv": True, "datum": tag(-1)},
            {"id": "neu", "zeit": "08:00", "text": "ist heute", "tage": sorted(server.TAGE), "aktiv": True, "datum": tag(0)},
        ])
        self.assertEqual([e["id"] for e in self.rufe("/api/erinnerungen", cookie=c)[1]], ["neu"])
        self.leeren(c)

    def test_seite_und_kein_pfad_ausbruch(self):
        with urllib.request.urlopen(self.url + "/../server.py") as r:
            self.assertIn(b"<!doctype html>", r.read())


    def test_schrift_wird_als_schrift_ausgeliefert_und_gecacht(self):
        with urllib.request.urlopen(self.url + "/fonts/atkinson-latin.woff2") as r:
            self.assertEqual(r.headers["Content-Type"], "font/woff2")
            self.assertIn("max-age", r.headers["Cache-Control"])
            self.assertEqual(r.read()[:4], b"wOF2")


if __name__ == "__main__":
    unittest.main()
