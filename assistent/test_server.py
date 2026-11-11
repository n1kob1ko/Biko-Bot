"""Tests ohne echte KI: python -m unittest test_server  (im Ordner assistent/)"""

import json
import os
import tempfile
import threading
import unittest
import unittest.mock
import urllib.error
import urllib.request
from datetime import date, timedelta
from http.server import ThreadingHTTPServer
from types import SimpleNamespace

os.environ["DATA_DIR"] = tempfile.mkdtemp()
os.environ["APP_PASSWORT"] = "geheim123"
import server  # noqa: E402

GEFRAGT = []


def falsche_ki(system, messages, max_tokens=4000, websuche=False, werkzeuge=None, modell=None):
    GEFRAGT.append({"system": system, "messages": list(messages), "websuche": websuche, "werkzeuge": werkzeuge,
                    "modell": modell})
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


def texte(inhalt):
    """Alle Texte aus einem Inhalt (Text, Liste von Blöcken oder ein ganzer Systemtext als Blöcke)."""
    if isinstance(inhalt, str):
        return [inhalt]
    return [b["text"] for b in inhalt if isinstance(b, dict) and b.get("type") == "text"]


def frage_text(inhalt):
    """Was die Person gesagt hat, ohne den Hinweis der App davor."""
    return "".join(t for t in texte(inhalt) if not t.startswith("<app>"))


def alles(anfrage):
    """Der ganze Text einer Anfrage: Anleitung und alle Nachrichten."""
    return "\n".join(texte(anfrage["system"]) + [t for m in anfrage["messages"] for t in texte(m["content"])])


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
        self.rufe("/api/profil", {"name": "Oma Li", "sprache": "zh-CN"}, cookie=c)
        server.schreiben("wissen", [{"id": "w1", "text": "Darf wenig Zucker essen", "zeit": ""}])
        status, j, _ = self.rufe("/api/chat", {"text": "Darf ich Kuchen essen?"}, cookie=c)
        self.assertEqual((status, j["antwort"]), (200, "Antwort von Biko"))
        letzte = GEFRAGT[-1]
        self.assertTrue(letzte["websuche"])
        self.assertIn("Oma Li", letzte["system"])
        self.assertIn("Nummer w1: Darf wenig Zucker essen", alles(letzte))
        self.assertNotIn("w1", letzte["system"], "was sich ändert, steht nicht in der Anleitung, sonst geht der Zwischenspeicher verloren")
        self.assertIn("Chinesisch", letzte["system"])
        server.schreiben("wissen", [])

    def test_alte_felder_diaet_und_notizen_wandern_ins_gedaechtnis(self):
        c = self.anmelden()
        server._pfad("wissen").unlink(missing_ok=True)
        server.schreiben("profil", {"name": "Oma Li", "anrede": "Sie", "diaet": "wenig Zucker", "notizen": "Enkel heißt Niko"})
        # schon das Speichern des Profils übernimmt sie vorher, damit nichts verloren geht
        self.rufe("/api/profil", {"name": "Oma Li", "anrede": "Sie"}, cookie=c)
        self.assertEqual([w["text"] for w in self.rufe("/api/wissen", cookie=c)[1]], ["Diät: wenig Zucker", "Enkel heißt Niko"])
        self.assertEqual(set(self.rufe("/api/profil", cookie=c)[1]), {"name", "anrede", "sprache"})
        self.assertNotIn("diaet", server.lesen("profil", {}))
        server.schreiben("wissen", [])

    def test_biko_merkt_sich_was_die_person_ueber_sich_erzaehlt(self):
        c = self.anmelden()
        server.schreiben("wissen", [])
        anfragen = self.drehbuch(
            antwort("tool_use", werkzeug("wissen_merken", {"text": "Hat Diabetes Typ 2"}),
                    werkzeug("wissen_merken", {"text": "  "}, "tu_2")),
            antwort("end_turn", text("Das merk ich mir. Dann schauen wir beim Essen auf den Zucker.")),
        )
        j = self.rufe("/api/chat", {"text": "Ich hab übrigens Diabetes"}, cookie=c)[1]
        self.assertEqual([w["text"] for w in j["gelernt"]], ["Hat Diabetes Typ 2"])
        self.assertEqual(j["wissen"], self.rufe("/api/wissen", cookie=c)[1])
        self.assertLessEqual({"wissen_merken", "wissen_vergessen"}, {w["name"] for w in anfragen[0]["tools"]})
        ergebnisse = anfragen[1]["messages"][-1]["content"]
        self.assertFalse(ergebnisse[0].get("is_error"))
        self.assertTrue(ergebnisse[1]["is_error"])   # leerer Text geht als Fehler an Biko zurück
        # steht auch im gespeicherten Gespräch und beim nächsten Mal im Systemtext
        letzte = self.rufe("/api/gespraech?id=" + j["gespraech"]["id"], cookie=c)[1]["nachrichten"][-1]
        self.assertEqual([w["text"] for w in letzte["gelernt"]], ["Hat Diabetes Typ 2"])
        self.assertIn("Hat Diabetes Typ 2", server.hinweis())
        # dasselbe nochmal merken gibt keinen zweiten Eintrag
        self.assertIn("schon", server.wissen_merken({"text": "hat diabetes typ 2"}))
        self.assertEqual(len(server.wissen_lesen()), 1)

        # "Vergiss das": Biko streicht es, und in den Einstellungen kann man es auch löschen
        nr = j["wissen"][0]["id"]
        self.drehbuch(antwort("tool_use", werkzeug("wissen_vergessen", {"id": nr})), antwort("end_turn", text("Gestrichen.")))
        self.rufe("/api/chat", {"text": "Vergiss das mit dem Diabetes"}, cookie=c)
        self.assertEqual(server.wissen_lesen(), [])
        server.wissen_merken({"text": "Mag Gartenarbeit"})
        nr = server.wissen_lesen()[0]["id"]
        self.assertEqual(self.rufe("/api/wissen/loeschen", {"id": nr}, cookie=c)[1], [])
        self.assertEqual(self.rufe("/api/wissen/loeschen", {"id": nr}, cookie=c), (200, [], unittest.mock.ANY))

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
        gid = self.rufe("/api/chat", {"text": "Was schreibt Mei?"}, cookie=c)[1]["gespraech"]["id"]
        frage = GEFRAGT[-1]["messages"][-1]["content"]
        self.assertEqual([b["type"] for b in frage], ["text", "image", "text"])
        self.assertIn("Bildschirmfoto", frage[0]["text"])
        self.assertEqual(frage[2], {"type": "text", "text": "Was schreibt Mei?"})
        self.assertNotIn("Zu dieser Frage siehst du ein Bildschirmfoto", GEFRAGT[-1]["system"])
        # gespeichert wird nur der Text
        self.assertEqual(self.rufe("/api/gespraech?id=" + gid, cookie=c)[1]["nachrichten"][-2]["text"], "Was schreibt Mei?")
        # die nächste Frage schickt das Bild nicht nochmal neu: es steht im Verlauf bei der ersten Frage
        # (dort kommt es aus dem Zwischenspeicher), Biko sieht es also weiter
        self.rufe("/api/chat", {"text": "Was soll ich antworten?", "gespraech": gid}, cookie=c)
        m = GEFRAGT[-1]["messages"]
        self.assertEqual([b["type"] for b in m[-1]["content"]], ["text", "text"])
        self.assertEqual([b["type"] for b in m[0]["content"]], ["image", "text"])
        self.assertIn("Bildschirmfoto", m[-1]["content"][0]["text"])
        # nach ein paar Minuten gilt das Bild nicht mehr
        server._bildschirm["zeit"] -= server.BILDSCHIRM_GILT + 1
        self.rufe("/api/chat", {"text": "Und jetzt?", "gespraech": gid}, cookie=c)
        m = GEFRAGT[-1]["messages"]
        self.assertEqual(frage_text(m[-1]["content"]), "Und jetzt?")
        self.assertNotIn("Bildschirmfoto", json.dumps(m, ensure_ascii=False))
        self.assertNotIn("image", json.dumps(m))

    def test_foto_von_einem_brief_erklaert_biko_mit_dem_starken_modell(self):
        c = self.anmelden()
        server._bildschirm.update(bild=None, zeit=0)
        req = urllib.request.Request(self.url + "/api/bildschirm?foto", data=b"\xff\xd8\xff\xe0" + b"x" * 100, method="POST")
        req.add_header("Content-Type", "image/jpeg")
        req.add_header("Cookie", c)
        with urllib.request.urlopen(req) as r:
            self.assertEqual(r.status, 200)
        self.rufe("/api/chat", {"text": "Was steht da?"}, cookie=c)
        anfrage = GEFRAGT[-1]
        frage = anfrage["messages"][-1]["content"]
        self.assertEqual([b["type"] for b in frage], ["text", "image", "text"])
        self.assertIn("mit der Kamera ein Foto gemacht", frage[0]["text"])
        self.assertIn("bis wann", frage[0]["text"])
        self.assertNotIn("Bildschirmfoto vom Handy", frage[0]["text"])
        self.assertEqual(anfrage["modell"], server.MODELL)
        server._bildschirm.update(bild=None, zeit=0, art="bildschirm")

    def test_einfaches_geht_ans_guenstige_modell_wichtiges_ans_starke(self):
        c = self.anmelden()
        server._bildschirm.update(bild=None, zeit=0)
        for text, modell in [("Wie geht es dir heute?", server.EINFACH_MODELL),
                             ("Erzähl mir einen Witz", server.EINFACH_MODELL),
                             ("Ist diese SMS von der Bank echt?", server.MODELL),
                             ("Ich habe einen Brief vom Finanzamt bekommen", server.MODELL),
                             ("Darf ich das Medikament mit Alkohol nehmen?", server.MODELL),
                             ("这是诈骗吗？", server.MODELL)]:
            self.rufe("/api/chat", {"text": text}, cookie=c)
            self.assertEqual(GEFRAGT[-1]["modell"], modell, text)
        # mit Bildschirm immer das starke
        server.bildschirm_merken(b"\xff\xd8bild")
        self.rufe("/api/chat", {"text": "Was steht da?"}, cookie=c)
        self.assertEqual(GEFRAGT[-1]["modell"], server.MODELL)
        server._bildschirm.update(bild=None, zeit=0)

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
        self.assertEqual([(m["role"], frage_text(m["content"])) for m in GEFRAGT[-1]["messages"]],
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
        self.assertEqual([frage_text(m["content"]) for m in GEFRAGT[-1]["messages"]], ["Zweites Gespräch"])
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

    def test_whatsapp_mit_nummer_und_anrufen_mit_knopf(self):
        c = self.anmelden()
        anfragen = self.drehbuch(
            antwort("tool_use",
                    werkzeug("nachricht_zeigen", {"an": "Peter", "text": "Ich komme um 5.", "ueber": "whatsapp",
                                                  "nummer": "0664 123 4567"}, "tu_1"),
                    werkzeug("anruf_zeigen", {"name": "Peter", "nummer": "0664/1234567"}, "tu_2"),
                    werkzeug("anruf_zeigen", {"name": "Erfunden", "nummer": "ruf mich an"}, "tu_3")),
            antwort("end_turn", text("Hier ist die Nachricht, und du kannst Peter gleich anrufen.")),
        )
        j = self.rufe("/api/chat", {"text": "Schreib Peter auf WhatsApp, dass ich um 5 komme, und ruf ihn an"}, cookie=c)[1]
        self.assertEqual(j["nachrichten"], [{"an": "Peter", "text": "Ich komme um 5.", "ueber": "whatsapp",
                                             "nummer": "0664 123 4567"}])
        self.assertEqual(j["anrufe"], [{"name": "Peter", "nummer": "0664/1234567"}])
        ergebnisse = anfragen[1]["messages"][-1]["content"]
        self.assertEqual([bool(e.get("is_error")) for e in ergebnisse], [False, False, True], "keine erfundene Nummer")
        self.assertIn("anruf_zeigen", {w["name"] for w in anfragen[0]["tools"]})
        g = self.rufe("/api/gespraech?id=" + j["gespraech"]["id"], cookie=c)[1]
        self.assertEqual(g["nachrichten"][-1]["anrufe"], j["anrufe"])

    def test_einkaufsliste_im_gespraech_fuehren_zeigen_und_wegtippen(self):
        c = self.anmelden()
        server.schreiben("listen", {})
        self.assertIn("Milch", server.liste_aendern({"liste": "Einkaufen", "dazu": ["Milch", "6 Eier", "Käse (Emmentaler)"]}))
        server.liste_aendern({"liste": "einkaufen", "dazu": ["milch", "Brot"]})   # gleiche Liste, Milch nicht doppelt
        self.assertEqual([e["text"] for e in server.listen_lesen()["Einkaufen"]], ["Milch", "6 Eier", "Käse (Emmentaler)", "Brot"])
        self.assertIn("Deine Listen:\n- Einkaufen: Milch, 6 Eier, Käse (Emmentaler), Brot", server.hinweis())
        server.liste_aendern({"liste": "Einkaufen", "weg": ["Käse", "Brot"]})   # "Käse" findet "Käse (Emmentaler)"
        self.assertEqual([e["text"] for e in server.listen_lesen()["Einkaufen"]], ["Milch", "6 Eier"])
        self.assertIn("Nichts davon", server.liste_aendern({"liste": "Einkaufen", "weg": ["Bananen"]}))
        # Biko zeigt die Liste als Karte unter der Antwort
        anfragen = self.drehbuch(
            antwort("tool_use", werkzeug("liste_zeigen", {"liste": "Einkaufen"}, "tu_1"),
                    werkzeug("liste_zeigen", {"liste": "Geschenke"}, "tu_2")),
            antwort("end_turn", text("Auf deiner Einkaufsliste stehen Milch und 6 Eier.")),
        )
        j = self.rufe("/api/chat", {"text": "Was muss ich einkaufen?"}, cookie=c)[1]
        self.assertEqual([(k["name"], [e["text"] for e in k["eintraege"]]) for k in j["listen"]], [("Einkaufen", ["Milch", "6 Eier"])])
        self.assertTrue(anfragen[1]["messages"][-1]["content"][1].get("is_error"), "leere Liste gibt es nicht")
        self.assertLessEqual({"liste_aendern", "liste_zeigen"}, {w["name"] for w in anfragen[0]["tools"]})
        # In der Karte Gekauftes wegtippen, zweimal schadet nicht; die leere Liste verschwindet
        milch, eier = j["listen"][0]["eintraege"]
        self.assertEqual(self.rufe("/api/liste/weg", {"liste": "Einkaufen", "id": milch["id"]}, cookie=c)[1]["eintraege"], [eier])
        self.assertEqual(self.rufe("/api/liste/weg", {"liste": "Einkaufen", "id": milch["id"]}, cookie=c)[0], 200)
        self.rufe("/api/liste/weg", {"liste": "Einkaufen", "id": eier["id"]}, cookie=c)
        self.assertEqual(self.rufe("/api/listen", cookie=c)[1], {})
        self.assertIn("Deine Listen:\n- noch keine", server.hinweis())

    def test_gesundheitstagebuch_notieren_im_hinweis_und_als_karte(self):
        c = self.anmelden()
        server.schreiben("gesundheit", [])
        self.assertIn("135/85", server.gesundheit_notieren({"art": "blutdruck", "wert": "135 zu 85", "notiz": "morgens"}))
        server.gesundheit_notieren({"art": "zucker", "wert": "112 mg/dl"})
        self.assertRaises(ValueError, server.gesundheit_notieren, {"art": "blutdruck", "wert": "135"})
        self.assertRaises(ValueError, server.gesundheit_notieren, {"art": "laune", "wert": "gut"})
        # ein alter Eintrag (vor drei Wochen) steht nicht mehr im Hinweis
        alt = {"id": "alt1", "zeit": (server.jetzt() - timedelta(days=21)).isoformat(timespec="seconds"),
               "art": "gewicht", "wert": "70 kg"}
        server.schreiben("gesundheit", [alt] + server.tagebuch_lesen())
        h = server.hinweis()
        self.assertIn("Blutdruck 135/85 (morgens)", h)
        self.assertIn("Blutzucker 112 mg/dl", h)
        self.assertNotIn("70 kg", h)
        anfragen = self.drehbuch(
            antwort("tool_use", werkzeug("tagebuch_zeigen", {"arten": ["blutdruck"]})),
            antwort("end_turn", text("Diese Woche hattest du einmal 135 zu 85.")),
        )
        j = self.rufe("/api/chat", {"text": "Wie war mein Blutdruck diese Woche? Für den Arzt"}, cookie=c)[1]
        self.assertEqual([(z["art"], z["wert"]) for z in j["tagebuch"][0]["zeilen"]], [("blutdruck", "135/85")])
        self.assertLessEqual({"gesundheit_notieren", "gesundheit_streichen", "tagebuch_zeigen"},
                             {w["name"] for w in anfragen[0]["tools"]})
        nr = server.tagebuch_lesen()[1]["id"]
        server.gesundheit_streichen({"id": nr})
        self.assertNotIn("135/85", server.hinweis())
        server.schreiben("gesundheit", [])

    def test_geburtstage_merken_der_naechste_zuerst_im_hinweis(self):
        c = self.anmelden()
        server.schreiben("geburtstage", [])
        heute = server.jetzt().date()
        morgen = heute + timedelta(days=1)
        self.assertIn("morgen wird Peter 41", server.geburtstag_merken(
            {"name": "Peter", "tag": morgen.day, "monat": morgen.month, "jahr": morgen.year - 41}))
        server.geburtstag_merken({"name": "Lea", "tag": heute.day, "monat": heute.month})
        server.geburtstag_merken({"name": "Oma Rosa", "tag": 29, "monat": 2})
        self.assertRaises(ValueError, server.geburtstag_merken, {"name": "Anna", "tag": 31, "monat": 4})
        self.assertRaises(ValueError, server.geburtstag_merken, {"name": "", "tag": 1, "monat": 1})
        h = server.hinweis()
        self.assertLess(h.index("- Lea: "), h.index("- Peter: "))
        self.assertIn(f"- Lea: {heute.day}.{heute.month}., heute", h)
        self.assertIn("morgen (wird 41)", h)
        # 29.2.: in einem Jahr ohne Schalttag am 28.2.
        self.assertEqual(server.geburtstag_naechster({"tag": 29, "monat": 2, "jahr": 1950}, date(2027, 2, 1)), (27, 77))
        # ein zweites Mal ersetzt das Datum, statt Peter doppelt zu führen
        server.geburtstag_merken({"name": "peter", "tag": 1, "monat": 1})
        self.assertEqual([g["name"] for g in server.geburtstage_lesen()].count("peter"), 1)
        self.assertNotIn("Peter", [g["name"] for g in server.geburtstage_lesen()])
        server.geburtstag_streichen({"name": "Oma Rosa"})
        self.assertEqual(sorted(g["name"] for g in self.rufe("/api/geburtstage", cookie=c)[1]), ["Lea", "peter"])
        self.assertRaises(ValueError, server.geburtstag_streichen, {"name": "Niemand"})
        server.schreiben("geburtstage", [])

    def test_dolmetscher_an_im_hinweis_und_nach_30_minuten_von_selbst_aus(self):
        c = self.anmelden()
        self.assertNotIn("Dolmetscher zwischen", server.hinweis(gesprochen=True))
        server.dolmetscher({"an": True, "sprache_a": "Chinesisch", "sprache_b": "Deutsch"})
        h = server.hinweis(gesprochen=True)
        self.assertIn("Dolmetscher zwischen Chinesisch und Deutsch", h)
        self.assertNotIn(server.GESPROCHEN, h)   # beim Dolmetschen wird nicht gekürzt
        self.assertRaises(ValueError, server.dolmetscher, {"an": True, "sprache_a": "Deutsch", "sprache_b": "deutsch"})
        anfragen = self.drehbuch(antwort("end_turn", text("Ich habe seit drei Tagen Kopfschmerzen.")))
        j = self.rufe("/api/chat", {"text": "我头疼三天了"}, cookie=c)[1]
        self.assertEqual(j["dolmetscher"], {"a": "Chinesisch", "b": "Deutsch"})
        self.assertIn("dolmetscher", {w["name"] for w in anfragen[0]["tools"]})
        self.assertEqual(self.rufe("/api/dolmetscher", cookie=c)[1]["dolmetscher"]["b"], "Deutsch")
        with unittest.mock.patch.object(server.time, "time", return_value=server.time.time() + 31 * 60):
            self.assertIsNone(server.dolmetscher_jetzt())
        server.dolmetscher({"an": False})
        self.assertIsNone(self.rufe("/api/dolmetscher", cookie=c)[1]["dolmetscher"])

    def test_checkin_ohne_lebenszeichen_bekommt_die_familie_eine_sms_und_spaeter_eine_entwarnung(self):
        c = self.anmelden()
        server.schreiben("checkin", {})
        self.assertRaises(ValueError, server.checkin_einstellen, {"zeit": "10:00"})   # wer bekommt die SMS?
        self.assertIn("noch nicht eingerichtet", server.checkin_einstellen(
            {"zeit": "10:00", "kontakte": [{"name": "Peter", "nummer": "0664 1234567"}]}))
        self.assertIn("SMS-Dienst ist aber noch nicht eingerichtet", server.hinweis())
        self.assertRaises(ValueError, server.familie_benachrichtigen, {"text": "Ich bin gestürzt."})
        self.assertEqual(server.nummer_international("0664 123 45-67"), "+436641234567")
        self.assertEqual(server.nummer_international("0049 170 1"), "+491701")
        self.assertEqual(server.nummer_international("+86 138 0013 8000"), "+8613800138000")
        # seit gestern eingestellt, das letzte Lebenszeichen war gestern
        heute = server.jetzt()
        gestern = (heute - timedelta(days=1)).isoformat(timespec="seconds")
        server.schreiben("checkin", {**server.checkin_lesen(), "seit": gestern, "zuletzt": gestern})
        um = lambda h, m=0: heute.replace(hour=h, minute=m, second=0, microsecond=0)
        sms = unittest.mock.Mock()
        with unittest.mock.patch.multiple(server, TWILIO_SID="AC1", TWILIO_TOKEN="geheim", TWILIO_VON="+4312345",
                                          sms_schicken=sms):
            self.assertIsNone(server.checkin_pruefen(um(11)))          # Frist ist erst um 12
            self.assertEqual(server.checkin_pruefen(um(12, 5)), ["Peter"])
            self.assertEqual(sms.call_args[0][0], "0664 1234567")
            self.assertIn("10:00", sms.call_args[0][1])                # in der Sprache der Person (hier Chinesisch)
            self.assertIsNone(server.checkin_pruefen(um(13)))          # nur einmal am Tag
            self.assertEqual(self.rufe("/api/lebenszeichen", {}, cookie=c)[1], {"gemeldet": True})
            self.assertIn("放心", sms.call_args[0][1])                  # Entwarnung
            server.lebenszeichen()
            self.assertEqual(sms.call_count, 2)                        # keine zweite Entwarnung
            # ein Lebenszeichen kurz vor der Uhrzeit zählt schon für heute
            server.schreiben("checkin", {**server.checkin_lesen(), "alarm": {}, "zuletzt": um(9).isoformat()})
            self.assertIsNone(server.checkin_pruefen(um(12, 5)))
            self.assertTrue(server.gemeldet_heute(um(12, 5)))
            # Notfall auf Wunsch, aber nicht unbegrenzt viele SMS an einem Tag
            self.assertIn("Peter", server.familie_benachrichtigen({"text": "Ich bin gestürzt, die Rettung kommt."}))
            self.assertRegex(sms.call_args[0][1], r"^Biko.*: Ich bin gestürzt")
            for _ in range(3):
                server.familie_benachrichtigen({"text": "Test"})
            self.assertRaises(ValueError, server.familie_benachrichtigen, {"text": "Noch eine"})
            anfragen = self.drehbuch(antwort("end_turn", text("Hallo!")))
            j = self.rufe("/api/chat", {"text": "Hallo"}, cookie=c)[1]
            self.assertEqual(j["checkin"], "10:00")
            self.assertLessEqual({"checkin_einstellen", "familie_benachrichtigen"}, {w["name"] for w in anfragen[0]["tools"]})
        # heute eingestellt, als 10 Uhr schon vorbei war: gilt erst ab morgen
        server.schreiben("checkin", {**server.checkin_lesen(), "seit": um(11).isoformat(), "zuletzt": gestern, "alarm": {}})
        self.assertIsNone(server.checkin_heute(um(12, 5)))
        self.assertIn("aus", server.checkin_einstellen({"zeit": "aus"}))
        server.schreiben("checkin", {})

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
        self.assertEqual((frage_text(m[3]["content"]), frage_text(m[4]["content"])), ("Hier ist die Nachricht für Anna.", "Mach sie kürzer"))

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
        self.assertIn("link_zeigen", alles(anfragen[0]))
        self.assertIn("nachricht_zeigen", alles(anfragen[0]))

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

    def test_zwischenspeicher_anleitung_bleibt_gleich_und_verlauf_ist_markiert(self):
        c = self.anmelden()
        self.rufe("/api/verlauf/loeschen", {}, cookie=c)
        anfragen = self.drehbuch(*[antwort("end_turn", text(f"Antwort {i}")) for i in range(3)])
        gid = self.rufe("/api/chat", {"text": "Hallo"}, cookie=c)[1]["gespraech"]["id"]
        server.wissen_merken({"text": "Mag Tee"})
        self.rufe("/api/chat", {"text": "Wie geht's?", "gespraech": gid}, cookie=c)
        self.rufe("/api/chat", {"text": "Und morgen?", "gespraech": gid, "gesprochen": True}, cookie=c)
        # die Anleitung ist Wort für Wort gleich, auch wenn sich Wissen, Uhrzeit oder die Art zu reden ändern
        self.assertEqual(anfragen[0]["system"], anfragen[2]["system"])
        self.assertEqual(anfragen[0]["system"][0]["cache_control"], {"type": "ephemeral"})
        self.assertEqual(anfragen[2]["cache_control"], {"type": "ephemeral"})
        # das Ende des bisherigen Verlaufs ist markiert, die neue Frage nicht
        m = anfragen[2]["messages"]
        self.assertEqual(m[-2]["content"][-1].get("cache_control"), {"type": "ephemeral"})
        self.assertNotIn("cache_control", json.dumps(m[-1]))
        self.assertIn("Mag Tee", m[-1]["content"][0]["text"])
        self.assertIn("wie am Telefon", m[-1]["content"][0]["text"])
        # der Verlauf davor ist genau so, wie er beim letzten Mal geschickt wurde (bis auf die Markierung)
        ohne = lambda x: json.loads(json.dumps(x).replace(', "cache_control": {"type": "ephemeral"}', ""))
        self.assertEqual([frage_text(x["content"]) for x in ohne(anfragen[1]["messages"])[:-1]],
                         [frage_text(x["content"]) for x in ohne(m)[:2]])
        server.schreiben("wissen", [])

    def test_langes_gespraech_der_anfang_rueckt_in_zehnerschritten_weiter(self):
        nachrichten = [{"von": "ich" if i % 2 == 0 else "biko", "text": str(i)} for i in range(60)]
        fenster = {len(nachrichten[:n]): server.fuer_claude(nachrichten[:n])[0]["content"] for n in range(30, 60, 2)}
        for n, erste in fenster.items():
            self.assertGreaterEqual(n - int(erste), server.MAX_VERLAUF - 1, n)   # nie weniger als bisher
        self.assertEqual(len(set(fenster.values())), 3, "der Anfang bleibt mehrere Fragen lang gleich")

    def test_kosten_stehen_im_protokoll_und_in_der_tagessumme(self):
        c = self.anmelden()
        zeilen = []
        alt = server.protokoll
        server.protokoll = zeilen.append
        self.addCleanup(lambda: setattr(server, "protokoll", alt))
        server.schreiben("kosten", {})
        verbrauch = SimpleNamespace(input_tokens=1000, output_tokens=200, cache_read_input_tokens=4000,
                                    cache_creation_input_tokens=500, server_tool_use=SimpleNamespace(web_search_requests=1))
        r = antwort("end_turn", text("Hallo!"))
        r.usage, r.model = verbrauch, "claude-sonnet-5-5"
        self.drehbuch(r)
        self.rufe("/api/chat", {"text": "Hallo"}, cookie=c)
        # 1000 × 2 + 200 × 10 + 4000 × 0,10 + 500 × 2,50 = 5650 Dollar pro Million, dazu eine Suche um 1 Cent
        zeile = next(z for z in zeilen if z.startswith("Claude ("))
        self.assertIn("Eingabe 5500 Tokens (davon 4000 aus dem Zwischenspeicher, 500 neu gespeichert)", zeile)
        self.assertIn("Kosten 1.57 US-Cent", zeile)
        heute = server.lesen("kosten", {})[server.jetzt().strftime("%Y-%m-%d")]
        self.assertEqual((round(heute["ki"], 5), heute["antworten"]), (0.01565, 1))

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

    def test_biko_stellt_die_morgenrunde_im_gespraech_ein(self):
        c = self.anmelden()
        server.schreiben("morgenrunde", {})
        self.drehbuch(
            antwort("tool_use", werkzeug("morgenrunde_einstellen", {"zeit": "08:00"})),
            antwort("end_turn", text("Gern, ab jetzt melde ich mich jeden Morgen um 8.")),
        )
        status, j, _ = self.rufe("/api/chat", {"text": "Meld dich jeden Morgen um 8"}, cookie=c)
        self.assertEqual((status, j["morgenrunde"]), (200, "08:00"))
        self.assertEqual(self.rufe("/api/morgenrunde", cookie=c)[1]["zeit"], "08:00")
        self.assertIn("Morgenrunde: jeden Tag um 08:00 Uhr.", server.hinweis())
        self.assertRaises(ValueError, server.morgenrunde_einstellen, {"zeit": "acht"})
        server.morgenrunde_einstellen({"zeit": "aus"})
        self.assertIn("Morgenrunde: nicht eingestellt.", server.hinweis())
        server.schreiben("morgenrunde", {})

    def test_morgenrunde_ist_kurz_vor_der_zeit_faellig_und_nicht_gleich_nach_dem_einstellen(self):
        heute = server.jetzt().replace(hour=8, minute=0, second=0, microsecond=0)
        server.schreiben("morgenrunde", {"zeit": "08:00", "seit": (heute - timedelta(days=1)).isoformat()})
        self.assertIsNone(server.morgenrunde_faellig(heute - timedelta(minutes=30)))
        self.assertEqual(server.morgenrunde_faellig(heute - timedelta(minutes=10)), (tag(), "08:00"))
        self.assertIsNotNone(server.morgenrunde_faellig(heute + timedelta(minutes=90)), "Server war kurz weg: nachholen")
        self.assertIsNone(server.morgenrunde_faellig(heute + timedelta(hours=5)))
        # Um 9 auf 8 Uhr gestellt: heute nicht mehr, erst morgen
        server.schreiben("morgenrunde", {"zeit": "08:00", "seit": (heute + timedelta(hours=1)).isoformat()})
        self.assertIsNone(server.morgenrunde_faellig(heute + timedelta(hours=1, minutes=1)))
        server.schreiben("morgenrunde", {})

    def test_morgenrunde_wird_einmal_geschrieben_und_man_kann_darin_weiterreden(self):
        c = self.anmelden()
        nachher = (server.jetzt() + timedelta(minutes=5)).strftime("%H:%M")
        server.schreiben("morgenrunde", {"zeit": nachher, "seit": (server.jetzt() - timedelta(days=1)).isoformat()})
        self.assertIsNone(self.rufe("/api/morgenrunde", cookie=c)[1]["heute"], "ohne ?jetzt schreibt der Hausmeister")
        vorher = len(GEFRAGT)
        heute = self.rufe("/api/morgenrunde?jetzt", cookie=c)[1]["heute"]
        self.assertEqual((heute["datum"], heute["text"]), (tag(), "Antwort von Biko"))
        anfrage = GEFRAGT[-1]
        self.assertTrue(anfrage["websuche"])
        self.assertEqual(anfrage["modell"], server.EINFACH_MODELL)
        self.assertIn("Morgenrunde", alles(anfrage))
        self.assertEqual(self.rufe("/api/morgenrunde?jetzt", cookie=c)[1]["heute"], heute)
        self.assertEqual(len(GEFRAGT), vorher + 1, "nur einmal am Tag")
        g = self.rufe("/api/gespraech?id=" + heute["gespraech"], cookie=c)[1]
        self.assertIn(g["titel"], ("Morgenrunde", "早安"))   # je nach Sprache der Person
        self.assertEqual(g["nachrichten"][0]["von"], "biko")
        # Die Person antwortet: Claude sieht die Morgenrunde als seine eigene Nachricht
        self.rufe("/api/chat", {"text": "Danke, und wie wird es morgen?", "gespraech": heute["gespraech"]}, cookie=c)
        nachrichten = GEFRAGT[-1]["messages"]
        self.assertEqual([m["role"] for m in nachrichten], ["user", "assistant", "user"])
        self.assertIn("von selbst gemeldet", nachrichten[0]["content"])
        self.assertEqual(texte(nachrichten[1]["content"]), ["Antwort von Biko"])
        server.schreiben("morgenrunde", {})

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
        system = alles(GEFRAGT[-1])
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
        server._toene.clear()
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
        self.assertIn("wie am Telefon", alles(anfragen[0]))
        g = self.rufe("/api/gespraech?id=" + fertig["gespraech"]["id"], cookie=c)[1]
        self.assertEqual([m["text"] for m in g["nachrichten"]],
                         ["Erinnere mich morgen um 15 Uhr an den Arzt", "Gemerkt: morgen um 15 Uhr."])
        # getippt heißt: kein Hinweis aufs Telefonieren
        self.strom_drehbuch((["Hallo!"], antwort("end_turn", text("Hallo!"))))
        self.ereignisse({"text": "Hallo", "gespraech": fertig["gespraech"]["id"]}, c)
        self.assertNotIn("wie am Telefon", server.hinweis())

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

    def test_kurze_saetze_spricht_biko_beim_zweiten_mal_aus_dem_speicher(self):
        c = self.anmelden()
        anfragen = self.sprachdienst({"/v1/text-to-speech/": b"PCM-moment"}, stimme="s1")
        for _ in range(2):
            status, ton, _ = self.roh("/api/stimme", json.dumps({"text": "Moment, ich schau kurz nach."}).encode(),
                                      "application/json", c)
            self.assertEqual((status, ton), (200, b"PCM-moment"))
        self.assertEqual(len(anfragen), 1, "der zweite Satz kommt aus dem Speicher")
        # mitten in einer Antwort (mit "vorher") und bei langen Sätzen fragt Biko immer neu, damit es natürlich klingt
        for daten in ({"text": "Moment, ich schau kurz nach.", "vorher": "Gute Frage."}, {"text": "x" * 200}, {"text": "x" * 200}):
            self.roh("/api/stimme", json.dumps(daten).encode(), "application/json", c)
        self.assertEqual(len(anfragen), 4)
        # wird die Antwort unterbrochen, merkt Biko sich nichts Halbes
        server._toene.clear()
        teile = server.ton_strom("Gerne!")
        next(teile)
        self.assertEqual(len(server._toene), 0)

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
