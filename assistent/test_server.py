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
server.protokoll = lambda t: None   # hält die Testausgabe ruhig


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

    # ---------- Gespräche: der Verlauf besteht aus mehreren Sitzungen ----------

    def test_gespraech_wird_gespeichert_und_laesst_sich_wieder_oeffnen(self):
        c = self.anmelden()
        self.rufe("/api/verlauf/loeschen", {}, cookie=c)
        j1 = self.rufe("/api/chat", {"text": "Darf ich Kuchen essen?"}, cookie=c)[1]
        gid = j1["gespraech"]["id"]
        j2 = self.rufe("/api/chat", {"text": "Und Obst?", "gespraech": gid}, cookie=c)[1]
        self.assertEqual(j2["gespraech"]["id"], gid)
        # Claude bekommt das ganze Gespräch, als einfachen Text
        self.assertEqual([(m["role"], m["content"]) for m in GEFRAGT[-1]["messages"]],
                         [("user", "Darf ich Kuchen essen?"), ("assistant", "Antwort von Biko"), ("user", "Und Obst?")])
        liste = self.rufe("/api/gespraeche", cookie=c)[1]
        self.assertEqual([(g["id"], g["titel"], g["anzahl"]) for g in liste], [(gid, "Darf ich Kuchen essen?", 4)])
        self.assertNotIn("nachrichten", liste[0])
        g = self.rufe("/api/gespraech?id=" + gid, cookie=c)[1]
        self.assertEqual([(m["von"], m["text"]) for m in g["nachrichten"]],
                         [("ich", "Darf ich Kuchen essen?"), ("biko", "Antwort von Biko"),
                          ("ich", "Und Obst?"), ("biko", "Antwort von Biko")])

    def test_neues_gespraech_beginnt_ohne_das_alte(self):
        c = self.anmelden()
        self.rufe("/api/verlauf/loeschen", {}, cookie=c)
        alt = self.rufe("/api/chat", {"text": "Erstes Gespräch"}, cookie=c)[1]["gespraech"]["id"]
        neu = self.rufe("/api/chat", {"text": "Zweites Gespräch"}, cookie=c)[1]["gespraech"]["id"]
        self.assertNotEqual(alt, neu)
        self.assertEqual([m["content"] for m in GEFRAGT[-1]["messages"]], ["Zweites Gespräch"])
        # das zuletzt benutzte Gespräch steht oben
        self.assertEqual([g["id"] for g in self.rufe("/api/gespraeche", cookie=c)[1]], [neu, alt])
        self.rufe("/api/chat", {"text": "Nochmal im ersten", "gespraech": alt}, cookie=c)
        self.assertEqual([g["id"] for g in self.rufe("/api/gespraeche", cookie=c)[1]], [alt, neu])
        # eine unbekannte Nummer beginnt einfach ein neues Gespräch
        drittes = self.rufe("/api/chat", {"text": "Drittes", "gespraech": "gibt-es-nicht"}, cookie=c)[1]["gespraech"]["id"]
        self.assertNotIn(drittes, (alt, neu, "gibt-es-nicht"))

    def test_gespraech_loeschen_und_alles_vergessen(self):
        c = self.anmelden()
        self.rufe("/api/verlauf/loeschen", {}, cookie=c)
        a = self.rufe("/api/chat", {"text": "A"}, cookie=c)[1]["gespraech"]["id"]
        b = self.rufe("/api/chat", {"text": "B"}, cookie=c)[1]["gespraech"]["id"]
        status, rest, _ = self.rufe("/api/gespraech/loeschen", {"id": a}, cookie=c)
        self.assertEqual((status, [g["id"] for g in rest]), (200, [b]))
        self.assertEqual(self.rufe("/api/gespraech?id=" + a, cookie=c)[0], 404)
        self.assertEqual(self.rufe("/api/verlauf/loeschen", {}, cookie=c)[0], 200)
        self.assertEqual(self.rufe("/api/gespraeche", cookie=c)[1], [])

    def test_langer_titel_wird_gekuerzt_und_alte_gespraeche_fallen_weg(self):
        c = self.anmelden()
        self.rufe("/api/verlauf/loeschen", {}, cookie=c)
        for i in range(server.MAX_GESPRAECHE + 2):
            self.rufe("/api/chat", {"text": f"Frage {i} " + "sehr lang " * 20}, cookie=c)
        liste = self.rufe("/api/gespraeche", cookie=c)[1]
        self.assertEqual(len(liste), server.MAX_GESPRAECHE)
        self.assertTrue(liste[0]["titel"].startswith(f"Frage {server.MAX_GESPRAECHE + 1} "))
        self.assertLessEqual(len(liste[0]["titel"]), 61)
        self.rufe("/api/verlauf/loeschen", {}, cookie=c)

    def test_altes_gespraech_aus_der_ersten_version_wird_uebernommen(self):
        c = self.anmelden()
        self.rufe("/api/verlauf/loeschen", {}, cookie=c)
        os.remove(server._pfad("gespraeche"))
        server.schreiben("verlauf", [{"role": "user", "content": "Hallo Biko"}, {"role": "assistant", "content": "Hallo!"}])
        liste = self.rufe("/api/gespraeche", cookie=c)[1]
        self.assertEqual([(g["titel"], g["anzahl"]) for g in liste], [("Hallo Biko", 2)])
        g = self.rufe("/api/gespraech?id=" + liste[0]["id"], cookie=c)[1]
        self.assertEqual([(m["von"], m["text"]) for m in g["nachrichten"]], [("ich", "Hallo Biko"), ("biko", "Hallo!")])
        self.rufe("/api/verlauf/loeschen", {}, cookie=c)

    # ---------- Nachricht und Links: Biko stellt sie direkt ins Gespräch ----------

    def test_biko_schreibt_eine_nachricht_fuer_jemanden_ins_gespraech(self):
        c = self.anmelden()
        anfragen = self.drehbuch(
            antwort("tool_use", werkzeug("nachricht_zeigen", {"an": "Anna", "text": "Liebe Anna, danke für die Blumen!"})),
            antwort("end_turn", text("Hier ist die Nachricht für Anna.")),
        )
        j = self.rufe("/api/chat", {"text": "Schreib Anna danke für die Blumen"}, cookie=c)[1]
        self.assertEqual(j["nachrichten"], [{"an": "Anna", "text": "Liebe Anna, danke für die Blumen!"}])
        self.assertLessEqual({"nachricht_zeigen", "link_zeigen"}, {w["name"] for w in anfragen[0]["tools"]})
        self.assertFalse(anfragen[1]["messages"][-1]["content"][0].get("is_error"))
        # der Entwurf bleibt im gespeicherten Gespräch sichtbar
        g = self.rufe("/api/gespraech?id=" + j["gespraech"]["id"], cookie=c)[1]
        self.assertEqual(g["nachrichten"][-1]["nachrichten"], j["nachrichten"])
        # den eigenen Bereich mit Formular gibt es nicht mehr
        self.assertEqual(self.rufe("/api/nachricht", {"an": "Enkel", "was": "danke"}, cookie=c)[0], 404)

    def test_biko_weiss_beim_naechsten_mal_noch_was_in_der_nachricht_stand(self):
        c = self.anmelden()
        anfragen = self.drehbuch(
            antwort("tool_use", werkzeug("nachricht_zeigen", {"an": "Anna", "text": "Liebe Anna, danke für die Blumen!"})),
            antwort("end_turn", text("Hier ist die Nachricht für Anna.")),
            antwort("end_turn", text("Gern.")),
        )
        gid = self.rufe("/api/chat", {"text": "Schreib Anna danke für die Blumen"}, cookie=c)[1]["gespraech"]["id"]
        self.rufe("/api/chat", {"text": "Mach sie kürzer", "gespraech": gid}, cookie=c)
        m = anfragen[2]["messages"]
        self.assertEqual([x["role"] for x in m], ["user", "assistant", "user", "assistant", "user"])
        aufruf, ergebnis = m[1]["content"][0], m[2]["content"][0]
        self.assertEqual((aufruf["type"], aufruf["name"], aufruf["input"]["text"]),
                         ("tool_use", "nachricht_zeigen", "Liebe Anna, danke für die Blumen!"))
        self.assertEqual((ergebnis["type"], ergebnis["tool_use_id"]), ("tool_result", aufruf["id"]))
        self.assertEqual((m[3]["content"], m[4]["content"]), ("Hier ist die Nachricht für Anna.", "Mach sie kürzer"))

    def test_leere_nachricht_geht_als_fehler_an_biko_zurueck(self):
        c = self.anmelden()
        anfragen = self.drehbuch(antwort("tool_use", werkzeug("nachricht_zeigen", {"an": "Anna", "text": "  "})),
                                 antwort("end_turn", text("Was soll ich Anna schreiben?")))
        j = self.rufe("/api/chat", {"text": "Schreib Anna"}, cookie=c)[1]
        self.assertTrue(anfragen[1]["messages"][-1]["content"][0]["is_error"])
        self.assertEqual(j["nachrichten"], [])

    def test_biko_stellt_einen_link_zum_prospekt_ins_gespraech(self):
        c = self.anmelden()
        self.drehbuch(
            antwort("tool_use", werkzeug("link_zeigen", {"titel": "Billa Flugblatt", "url": "https://www.billa.at/flugblatt"})),
            antwort("end_turn", text("Genaues habe ich nicht gefunden. Schau am besten selbst ins Flugblatt.")),
        )
        j = self.rufe("/api/chat", {"text": "Gibt es Angebote für Kaffee?"}, cookie=c)[1]
        self.assertEqual(j["links"], [{"titel": "Billa Flugblatt", "url": "https://www.billa.at/flugblatt"}])
        g = self.rufe("/api/gespraech?id=" + j["gespraech"]["id"], cookie=c)[1]
        self.assertEqual(g["nachrichten"][-1]["links"], j["links"])

    def test_nur_sichere_links_kommen_ins_gespraech(self):
        c = self.anmelden()
        for url in ("http://unsicher.example/prospekt", "javascript:alert(1)", "https://", "kein link", "https://leer zeichen.example"):
            anfragen = self.drehbuch(antwort("tool_use", werkzeug("link_zeigen", {"titel": "Prospekt", "url": url})),
                                     antwort("end_turn", text("Schau im Geschäft nach.")))
            j = self.rufe("/api/chat", {"text": "Angebote?"}, cookie=c)[1]
            self.assertTrue(anfragen[1]["messages"][-1]["content"][0]["is_error"], url)
            self.assertEqual(j["links"], [], url)

    def test_biko_darf_gruendlich_suchen_und_seiten_oeffnen(self):
        c = self.anmelden()
        anfragen = self.drehbuch(antwort("end_turn", text("Bei Billa gibt es Kaffee um 30 % günstiger.")))
        self.rufe("/api/chat", {"text": "Gibt es Angebote für Kaffee?"}, cookie=c)
        werkzeuge = {w["name"]: w for w in anfragen[0]["tools"]}
        self.assertGreaterEqual(werkzeuge["web_search"]["max_uses"], 5)
        self.assertEqual(werkzeuge["web_fetch"]["type"], "web_fetch_20260209")
        self.assertIn("link_zeigen", anfragen[0]["system"])
        self.assertIn("nachricht_zeigen", anfragen[0]["system"])

    def test_lehnt_die_ki_das_oeffnen_von_seiten_ab_antwortet_biko_trotzdem(self):
        import anthropic
        c = self.anmelden()
        anfragen = []
        abgelehnt = SimpleNamespace(status_code=400, headers={}, request=None)   # so sieht die Antwort "400" für das SDK aus

        def api(**kw):
            anfragen.append(kw)
            if any(w["name"] == "web_fetch" for w in kw["tools"]):
                raise anthropic.BadRequestError("tools.1: unknown tool type", body=None, response=abgelehnt)
            return antwort("end_turn", text("Bei Billa gibt es Kaffee günstiger."))

        alt_schleife, alt_api = server.frage_claude, server.claude_anfrage
        server.frage_claude, server.claude_anfrage = ECHTE_SCHLEIFE, api
        self.addCleanup(lambda: (setattr(server, "frage_claude", alt_schleife), setattr(server, "claude_anfrage", alt_api),
                                 setattr(server, "_seiten_oeffnen", True)))
        status, j, _ = self.rufe("/api/chat", {"text": "Gibt es Angebote für Kaffee?"}, cookie=c)
        self.assertEqual((status, j["antwort"]), (200, "Bei Billa gibt es Kaffee günstiger."))
        self.assertEqual(len(anfragen), 2)
        self.assertIn("web_search", {w["name"] for w in anfragen[1]["tools"]})
        # beim nächsten Mal fragt Biko gleich ohne, statt wieder zu scheitern
        self.rufe("/api/chat", {"text": "Und Tee?"}, cookie=c)
        self.assertEqual(len(anfragen), 3)
        # ein anderer Fehler in der Anfrage wird nicht versteckt
        server.claude_anfrage = lambda **kw: (_ for _ in ()).throw(
            anthropic.BadRequestError("messages: zu lang", body=None, response=abgelehnt))
        self.assertEqual(self.rufe("/api/chat", {"text": "Hallo"}, cookie=c)[0], 503)

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

    def test_was_biko_sich_gemerkt_hat_steht_auch_im_gespeicherten_gespraech(self):
        c = self.anmelden()
        self.leeren(c)
        self.drehbuch(antwort("tool_use", werkzeug("erinnerung_merken", {"text": "Tablette", "zeit": "08:00"})),
                      antwort("end_turn", text("Gemerkt.")))
        j = self.rufe("/api/chat", {"text": "Erinnere mich um 8 an die Tablette"}, cookie=c)[1]
        letzte = self.rufe("/api/gespraech?id=" + j["gespraech"]["id"], cookie=c)[1]["nachrichten"][-1]
        self.assertEqual([e["text"] for e in letzte["gemerkt"]], ["Tablette"])
        self.leeren(c)

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
