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

    def test_bildschirm_geht_mit_der_naechsten_frage_mit(self):
        c = self.anmelden()
        server._bildschirm.update(bild=None, zeit=0)
        bild = b"\xff\xd8\xff\xe0" + b"x" * 100
        req = urllib.request.Request(self.url + "/api/bildschirm", data=bild, method="POST")
        req.add_header("Content-Type", "image/jpeg")
        # ohne Anmeldung nicht
        with self.assertRaises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(req)
        self.assertEqual(e.exception.code, 401)
        req.add_header("Cookie", c)
        with urllib.request.urlopen(req) as r:
            self.assertEqual(r.status, 200)
        self.rufe("/api/chat", {"text": "Was schreibt Mei?"}, cookie=c)
        frage = GEFRAGT[-1]["messages"][-1]["content"]
        self.assertEqual(frage[0]["type"], "image")
        self.assertEqual(frage[1], {"type": "text", "text": "Was schreibt Mei?"})
        self.assertIn("Bildschirmfoto", GEFRAGT[-1]["system"])
        # gespeichert wird nur der Text
        g = self.rufe("/api/gespraeche", cookie=c)[1][0]
        self.assertEqual(self.rufe("/api/gespraech?id=" + g["id"], cookie=c)[1]["nachrichten"][-2]["text"], "Was schreibt Mei?")
        # nach ein paar Minuten gilt das Bild nicht mehr
        server._bildschirm["zeit"] -= server.BILDSCHIRM_GILT + 1
        self.rufe("/api/chat", {"text": "Und jetzt?"}, cookie=c)
        self.assertEqual(GEFRAGT[-1]["messages"][-1]["content"], "Und jetzt?")
        self.assertNotIn("Bildschirmfoto", GEFRAGT[-1]["system"])

    def test_bildschirm_nur_jpeg(self):
        c = self.anmelden()
        req = urllib.request.Request(self.url + "/api/bildschirm", data=b"kein bild", method="POST")
        req.add_header("Cookie", c)
        with self.assertRaises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(req)
        self.assertEqual(e.exception.code, 400)

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

    # ---------- Sprachdienst: natürliche Stimme und Zuhören in jeder Sprache ----------

    def roh(self, pfad, koerper=None, typ=None, cookie=None):
        """Wie rufe(), aber mit rohen Bytes hin und zurück (Ton statt JSON)."""
        req = urllib.request.Request(self.url + pfad, method="POST" if koerper is not None else "GET", data=koerper)
        if typ:
            req.add_header("Content-Type", typ)
        if cookie:
            req.add_header("Cookie", cookie)
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, r.read(), r.headers
        except urllib.error.HTTPError as e:
            return e.code, e.read(), e.headers

    def sprachdienst(self, antworten=None, stimme=""):
        """Schaltet den Sprachdienst für einen Test ein. Der Dienst antwortet nach `antworten` (Pfadanfang -> Bytes
        oder Ausnahme). Liefert die Liste der Anfragen."""
        anfragen = []
        antworten = {"/v2/voices": json.dumps({"voices": [{"voice_id": "stimme1", "name": "Anna"}]}).encode(),
                     "/v1/text-to-speech/": b"ID3-ton", **(antworten or {})}

        def dienst(pfad, daten=None, kopf=None):
            anfragen.append({"pfad": pfad, "daten": daten, "kopf": kopf or {}})
            ergebnis = next(v for k, v in antworten.items() if pfad.startswith(k))
            if isinstance(ergebnis, Exception):
                raise ergebnis
            return ergebnis

        def dienst_strom(pfad, daten, kopf=None):   # der Ton kommt in Stücken, so wie beim echten Dienst
            ergebnis = dienst(pfad, daten, kopf)
            return iter([ergebnis[i:i + 4] for i in range(0, len(ergebnis), 4)])

        alt = (server.SPRACH_KEY, server.SPRACH_STIMME, server.sprach_anfrage, server._stimme, server.sprach_strom)
        server.SPRACH_KEY, server.SPRACH_STIMME, server.sprach_anfrage, server._stimme = "sk_test", stimme, dienst, None
        server.sprach_strom = dienst_strom
        self.addCleanup(lambda: (setattr(server, "SPRACH_KEY", alt[0]), setattr(server, "SPRACH_STIMME", alt[1]),
                                 setattr(server, "sprach_anfrage", alt[2]), setattr(server, "_stimme", alt[3]),
                                 setattr(server, "sprach_strom", alt[4])))
        return anfragen

    # ---------- Reden wie am Telefon: Antwort und Stimme kommen stückweise ----------

    def ereignisse(self, daten, cookie, sprache=None):
        """Ruft /api/chat als Strom auf und liefert die Server-Sent Events als Liste."""
        req = urllib.request.Request(self.url + "/api/chat", data=json.dumps({**daten, "strom": True}).encode(), method="POST",
                                     headers={"Content-Type": "application/json", "Cookie": cookie, **({"X-Sprache": sprache} if sprache else {})})
        with urllib.request.urlopen(req) as r:
            self.assertTrue(r.headers["Content-Type"].startswith("text/event-stream"))
            self.assertEqual(r.headers["Cache-Control"], "no-store")
            roh_ = r.read().decode()
        return [json.loads(z[len("data: "):]) for z in roh_.split("\n\n") if z.startswith("data: ")]

    def strom_drehbuch(self, *runden):
        """Echte Schleife, aber Claude antwortet nach Drehbuch und schickt den Text in Stücken. Jede Runde:
        (Stücke, Antwort). Liefert die Anfragen."""
        anfragen, rest = [], list(runden)

        def strom(beim_text, **kw):
            anfragen.append({**kw, "messages": list(kw["messages"])})
            stuecke, ganz = rest.pop(0)
            for s_ in stuecke:
                beim_text(s_)
            return ganz

        alt = (server.frage_claude, server.claude_strom)
        server.frage_claude, server.claude_strom = ECHTE_SCHLEIFE, strom
        self.addCleanup(lambda: (setattr(server, "frage_claude", alt[0]), setattr(server, "claude_strom", alt[1])))
        return anfragen

    def test_antwort_kommt_stueckweise_und_landet_trotzdem_ganz_im_gespraech(self):
        c = self.anmelden()
        self.leeren(c)
        morgen = tag(1)
        anfragen = self.strom_drehbuch(
            (["Moment, ", "ich schreib's mir auf."],
             antwort("tool_use", text("Moment, ich schreib's mir auf."),
                     werkzeug("erinnerung_merken", {"text": "Arzt", "zeit": "15:00", "datum": morgen}))),
            (["Gemerkt: ", "morgen um 15 Uhr."], antwort("end_turn", text("Gemerkt: morgen um 15 Uhr."))),
        )
        e = self.ereignisse({"text": "Erinnere mich morgen um 15 Uhr an den Arzt", "gesprochen": True}, c)
        stuecke = "".join(x["text"] for x in e if "text" in x)
        # nach dem Werkzeug beginnt ein neuer Satz, damit die App die Stücke richtig in Sätze teilt
        self.assertEqual(stuecke, "Moment, ich schreib's mir auf.\nGemerkt: morgen um 15 Uhr.")
        fertig = e[-1]["fertig"]
        self.assertEqual(fertig["antwort"], "Gemerkt: morgen um 15 Uhr.")
        self.assertEqual([x["text"] for x in fertig["gemerkt"]], ["Arzt"])
        # am Telefon soll Biko kurz und ohne Listen antworten
        self.assertIn("wie am Telefon", anfragen[0]["system"])
        g = self.rufe("/api/gespraech?id=" + fertig["gespraech"]["id"], cookie=c)[1]
        self.assertEqual([m["text"] for m in g["nachrichten"]],
                         ["Erinnere mich morgen um 15 Uhr an den Arzt", "Gemerkt: morgen um 15 Uhr."])
        # getippt heißt: kein Hinweis aufs Telefonieren
        self.strom_drehbuch((["Hallo!"], antwort("end_turn", text("Hallo!"))))
        self.ereignisse({"text": "Hallo", "gespraech": fertig["gespraech"]["id"]}, c)
        self.assertNotIn("wie am Telefon", server.system_prompt())

    def test_fehler_im_strom_kommt_als_ereignis_und_auf_chinesisch(self):
        c = self.anmelden()

        def kaputt(beim_text, **kw):
            raise server.anthropic.APIConnectionError(request=None)

        alt = (server.frage_claude, server.claude_strom)
        server.frage_claude, server.claude_strom = ECHTE_SCHLEIFE, kaputt
        self.addCleanup(lambda: (setattr(server, "frage_claude", alt[0]), setattr(server, "claude_strom", alt[1])))
        self.assertEqual(self.ereignisse({"text": "Hallo"}, c), [{"fehler": "Keine Verbindung zur KI. Ist das Internet am Server da?"}])
        self.assertEqual(self.ereignisse({"text": "你好"}, c, sprache="zh-CN"), [{"fehler": "无法连接到 AI。服务器有网络吗？"}])
        self.assertEqual(self.rufe("/api/chat", {"text": "", "strom": True}, cookie=c)[0], 400)

    def test_stimme_kommt_roh_und_stueckweise_vom_sprachdienst(self):
        c = self.anmelden()
        anfragen = self.sprachdienst({"/v1/text-to-speech/": b"PCM-ton-in-stuecken"}, stimme="s1")
        status, ton, kopf = self.roh("/api/stimme", json.dumps({"text": "Wie geht es dir?", "vorher": "Hallo!"}).encode(),
                                     "application/json", c)
        self.assertEqual((status, ton, kopf["Content-Type"]), (200, b"PCM-ton-in-stuecken", "application/octet-stream"))
        self.assertEqual(anfragen[0]["pfad"], "/v1/text-to-speech/s1/stream?output_format=pcm_24000")
        gesendet = json.loads(anfragen[0]["daten"])
        self.assertEqual((gesendet["text"], gesendet["previous_text"]), ("Wie geht es dir?", "Hallo!"))
        self.roh("/api/stimme", json.dumps({"text": "x" * 2000}).encode(), "application/json", c)
        self.assertEqual(len(json.loads(anfragen[1]["daten"])["text"]), server.MAX_SATZ)
        self.assertNotIn("previous_text", json.loads(anfragen[1]["daten"]))
        self.assertEqual(self.rufe("/api/stimme", {"text": "Hallo"})[0], 401)
        self.assertEqual(self.rufe("/api/stimme", {"text": " "}, cookie=c)[0], 400)

    def test_stimme_fehler_kommen_freundlich_an(self):
        c = self.anmelden()
        self.sprachdienst({"/v1/text-to-speech/": urllib.error.HTTPError("https://x", 401, "Unauthorized", {}, None)}, stimme="s")
        status, j, _ = self.rufe("/api/stimme", {"text": "Hallo"}, cookie=c)
        self.assertEqual(status, 503)
        self.assertIn("Schlüssel für die Stimme", j["fehler"])

    def test_live_zugang_fuer_das_zuhoeren_wie_am_telefon(self):
        c = self.anmelden()
        self.assertEqual(self.rufe("/api/live-zugang", {}, cookie=c)[0], 503, "ohne Sprachdienst gibt es keinen Zugang")
        anfragen = self.sprachdienst({"/v1/single-use-token/realtime_scribe": json.dumps({"token": "einmal-123"}).encode()})
        self.assertEqual(self.rufe("/api/live-zugang", {})[0], 401)
        status, j, kopf = self.rufe("/api/live-zugang", {}, cookie=c)
        self.assertEqual((status, j), (200, {"token": "einmal-123", "modell": "scribe_v2_realtime"}))
        self.assertEqual(anfragen[0]["pfad"], "/v1/single-use-token/realtime_scribe")
        self.assertIsNotNone(anfragen[0]["daten"], "der Zugang wird mit POST geholt")
        # die App darf das Mikrofon direkt zum Sprachdienst schicken, sonst nirgends hin
        self.assertIn("connect-src 'self' wss://api.elevenlabs.io;", kopf["Content-Security-Policy"])

    def test_ohne_schluessel_gibt_es_keinen_sprachdienst(self):
        c = self.anmelden()
        self.assertFalse(self.rufe("/api/status")[1]["sprachdienst"])
        self.assertEqual(self.rufe("/api/vorlesen", {"text": "Hallo"}, cookie=c)[0], 503)
        self.assertEqual(self.roh("/api/zuhoeren", b"ton", "audio/webm", c)[0], 503)
        self.sprachdienst()
        self.assertTrue(self.rufe("/api/status")[1]["sprachdienst"])

    def test_vorlesen_holt_den_ton_vom_sprachdienst(self):
        c = self.anmelden()
        anfragen = self.sprachdienst()
        status, ton, kopf = self.roh("/api/vorlesen", json.dumps({"text": "Guten Morgen, 你好"}).encode(), "application/json", c)
        self.assertEqual((status, ton, kopf["Content-Type"], kopf["Cache-Control"]), (200, b"ID3-ton", "audio/mpeg", "no-store"))
        # ohne festgelegte Stimme nimmt Biko die erste Stimme des Kontos und merkt sie sich
        self.assertEqual([a["pfad"].split("?")[0] for a in anfragen], ["/v2/voices", "/v1/text-to-speech/stimme1"])
        gesendet = json.loads(anfragen[1]["daten"])
        self.assertEqual((gesendet["text"], gesendet["model_id"]), ("Guten Morgen, 你好", server.SPRACH_MODELL))
        self.assertEqual(anfragen[1]["kopf"]["Content-Type"], "application/json")
        self.roh("/api/vorlesen", json.dumps({"text": "Nochmal"}).encode(), "application/json", c)
        self.assertEqual(len(anfragen), 3, "die Stimme wird nur einmal gesucht")

    def test_vorlesen_mit_festgelegter_stimme_und_langem_text(self):
        c = self.anmelden()
        anfragen = self.sprachdienst(stimme="meine-stimme")
        self.roh("/api/vorlesen", json.dumps({"text": "a" * 1990}).encode(), "application/json", c)
        self.assertEqual(anfragen[0]["pfad"].split("?")[0], "/v1/text-to-speech/meine-stimme")
        self.assertEqual(self.rufe("/api/vorlesen", {"text": "  "}, cookie=c)[0], 400)
        self.assertEqual(self.rufe("/api/vorlesen", {"text": "Hallo"})[0], 401)
        self.assertEqual(len(anfragen), 1)

    def test_zuhoeren_schickt_die_aufnahme_zum_sprachdienst_und_liefert_den_text(self):
        c = self.anmelden()
        anfragen = self.sprachdienst({"/v1/speech-to-text": json.dumps({"language_code": "zh", "text": " 你好 Biko "}).encode()})
        status, antwort_, _ = self.roh("/api/zuhoeren", b"\x1aE\xdf\xa3-aufnahme", "audio/webm;codecs=opus", c)
        self.assertEqual((status, json.loads(antwort_)), (200, {"text": "你好 Biko", "sprache": "zh"}))
        a = anfragen[0]
        self.assertEqual(a["pfad"], "/v1/speech-to-text")
        self.assertTrue(a["kopf"]["Content-Type"].startswith("multipart/form-data; boundary="))
        grenze = a["kopf"]["Content-Type"].split("boundary=")[1].encode()
        teile = a["daten"].split(b"--" + grenze)
        self.assertTrue(any(b'name="model_id"' in t and b"scribe_v2" in t for t in teile))
        self.assertTrue(any(b'name="file"; filename="aufnahme.webm"' in t and b"Content-Type: audio/webm" in t
                            and t.rstrip(b"\r\n").endswith(b"\x1aE\xdf\xa3-aufnahme") for t in teile))
        # keine Sprache vorgeben: der Dienst erkennt selbst, ob Deutsch oder Chinesisch gesprochen wurde
        self.assertNotIn(b"language_code", a["daten"])
        self.assertTrue(a["daten"].rstrip(b"\r\n").endswith(b"--" + grenze + b"--"))

    def test_zuhoeren_nimmt_auch_aufnahmen_vom_iphone_und_lehnt_anderes_ab(self):
        c = self.anmelden()
        anfragen = self.sprachdienst({"/v1/speech-to-text": json.dumps({"language_code": "de", "text": "Hallo"}).encode()})
        self.assertEqual(self.roh("/api/zuhoeren", b"ftyp-aufnahme", "audio/mp4", c)[0], 200)
        self.assertIn(b'filename="aufnahme.mp4"', anfragen[0]["daten"])
        self.assertEqual(self.roh("/api/zuhoeren", b"ton", "audio/webm")[0], 401)
        self.assertEqual(self.roh("/api/zuhoeren", b"", "audio/webm", c)[0], 400)
        self.assertEqual(self.roh("/api/zuhoeren", b"kein ton", "text/plain", c)[0], 400)
        alt = server.MAX_AUFNAHME
        server.MAX_AUFNAHME = 1000
        self.addCleanup(setattr, server, "MAX_AUFNAHME", alt)
        self.assertEqual(self.roh("/api/zuhoeren", b"x" * 1001, "audio/webm", c)[0], 400)
        self.assertEqual(len(anfragen), 1)

    def test_fehler_vom_sprachdienst_kommen_freundlich_an(self):
        c = self.anmelden()
        falscher_schluessel = urllib.error.HTTPError("https://dienst.example", 401, "Unauthorized", {}, None)
        self.sprachdienst({"/v1/text-to-speech/": falscher_schluessel,
                           "/v1/speech-to-text": urllib.error.URLError("kein Netz")}, stimme="s")
        status, j, _ = self.rufe("/api/vorlesen", {"text": "Hallo"}, cookie=c)
        self.assertEqual(status, 503)
        self.assertIn("Schlüssel für die Stimme", j["fehler"])
        status, roh_, _ = self.roh("/api/zuhoeren", b"ton", "audio/webm", c)
        self.assertEqual(status, 503)
        self.assertIn("nicht erreichbar", json.loads(roh_)["fehler"])

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
