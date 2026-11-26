"""Tests für Biko-Chef ohne echte KI: python -m unittest test_chef  (im Ordner assistent/)"""

import os
import tempfile
import threading
import time
import unittest
from types import SimpleNamespace

os.environ["DATA_DIR"] = tempfile.mkdtemp()
import chef  # noqa: E402

chef.print = lambda *a, **k: None   # ruhige Testausgabe


def text(t):
    return SimpleNamespace(type="text", text=t)


def werkzeug(name, eingabe, nr="tu_1"):
    return SimpleNamespace(type="tool_use", id=nr, name=name, input=eingabe)


def antwort(stop, *bloecke, eingabe=1000, ausgabe=500, modell="claude-opus-5-5"):
    return SimpleNamespace(stop_reason=stop, content=list(bloecke), model=modell,
                           usage=SimpleNamespace(input_tokens=eingabe, output_tokens=ausgabe,
                                                 cache_read_input_tokens=0, cache_creation_input_tokens=0,
                                                 server_tool_use=None))


class FalscheKI:
    """Antwortet je nach Anleitung (Chef, Arbeiter, Prüfer) und merkt sich alle Anfragen."""

    def __init__(self):
        self.anfragen = []
        self.pruefer_gut = [True]
        self.lock = threading.Lock()

    def __call__(self, **kw):
        with self.lock:
            self.anfragen.append({**kw, "messages": list(kw["messages"])})
        system = kw["system"][0]["text"]
        letzte = kw["messages"][-1]["content"]
        schon_werkzeug = isinstance(letzte, list)   # die Antwort auf ein Werkzeug ist da: fertig
        if system.startswith("Du bist Prüfer"):
            if schon_werkzeug:
                return antwort("end_turn", text(""))
            gut = self.pruefer_gut.pop(0) if len(self.pruefer_gut) > 1 else self.pruefer_gut[0]
            return antwort("tool_use", werkzeug("urteil", {"gut": gut, "begruendung": "passt" if gut else "Mehr Quellen"}))
        if system.startswith("Du bist ") and not system.startswith("Du bist Biko-Chef"):   # ein Arbeiter
            if schon_werkzeug:
                return antwort("end_turn", text("Fertig."))
            e = {"zusammenfassung": "Drei Konkurrenten gefunden.", "ergebnis": "# Ergebnis\n- A\n- B"}
            if "Entwickler" in system:
                e["html"] = "<!doctype html><title>Nachhilfe</title><h1>Nachhilfe Niko</h1>"
            return antwort("tool_use", werkzeug("abgeben", e))
        # der Chef
        if schon_werkzeug:
            return antwort("end_turn", text("Ich habe das Projekt angelegt, die Recherche startet gleich."))
        frage = letzte if isinstance(letzte, str) else ""
        if "Landingpage" in frage:
            return antwort("tool_use", werkzeug("projekt_anlegen", {
                "name": "Nachhilfe-Seite", "ziel": "Landingpage für Nachhilfe Niko", "budget_dollar": 2,
                "aufgaben": [
                    {"titel": "Konkurrenz", "rolle": "recherche", "auftrag": "5 Seiten ansehen"},
                    {"titel": "Preise", "rolle": "recherche", "auftrag": "Preise in Wien", "gleichzeitig": True},
                    {"titel": "Seite bauen", "rolle": "entwickler", "auftrag": "Landingpage bauen"},
                ]}))
        return antwort("end_turn", text("Alles klar."))




def warten_bis(bedingung, sekunden=5):
    ende = time.time() + sekunden
    while time.time() < ende:
        chef.takt_runde()
        if bedingung():
            return True
        time.sleep(0.02)
    return False


class ChefTest(unittest.TestCase):
    def setUp(self):
        chef.speichern(chef.laden() | {"projekte": [], "gespraech": [], "kosten": {}, "protokoll": [],
                                       "grenzen": {"tag": 3.0, "gleichzeitig": 3}, "gemeldet": {}, "bericht_tag": ""})
        self.ki = FalscheKI()
        chef.claude_anfrage = self.ki
        chef.BERICHT_UM = 25   # kein Tagesbericht mitten im Test

    def tearDown(self):
        warten_bis(lambda: not chef._laufend, 5)

    def projekt(self):
        return chef.laden()["projekte"][0]

    def test_chat_legt_projekt_an_und_arbeiter_erledigen_es(self):
        z = chef.chat("Bau mir eine Landingpage für meine Nachhilfe")
        self.assertEqual(z["projekte"][0]["name"], "Nachhilfe-Seite")
        self.assertEqual(z["gespraech"][-1]["wer"], "chef")
        self.assertIn("<stand>", self.ki.anfragen[0]["messages"][-1]["content"])
        # die zwei Recherchen laufen gleichzeitig, der Entwickler wartet auf beide
        chef.takt_runde()
        p = self.projekt()
        self.assertEqual([a["status"] for a in p["aufgaben"]][2], "offen")
        self.assertTrue(warten_bis(lambda: self.projekt()["status"] == "fertig"))
        p = self.projekt()
        self.assertTrue(all(a["status"] == "fertig" for a in p["aufgaben"]))
        self.assertTrue(p["aufgaben"][2]["vorschau"])
        self.assertIn("Nachhilfe Niko", chef.vorschau_lesen(p["aufgaben"][2]["id"]))
        self.assertGreater(p["ausgegeben"], 0)
        texte = [e["text"] for e in chef.laden()["gespraech"] if e["wer"] == "meldung"]
        self.assertTrue(any("Alle Aufgaben" in t for t in texte))
        # der Entwickler hat die Ergebnisse der Recherche bekommen
        entwickler = [a for a in self.ki.anfragen if "Entwickler" in a["system"][0]["text"]][0]
        self.assertIn("Drei Konkurrenten", entwickler["messages"][0]["content"])

    def test_pruefer_schickt_zurueck(self):
        self.ki.pruefer_gut = [False, True]
        chef.projekt_anlegen({"name": "R", "ziel": "Z", "aufgaben": [{"titel": "T", "rolle": "recherche", "auftrag": "A"}]})
        self.assertTrue(warten_bis(lambda: self.projekt()["status"] == "fertig"))
        a = self.projekt()["aufgaben"][0]
        self.assertEqual(a["versuche"], 2)
        zweiter = [x for x in self.ki.anfragen if x["system"][0]["text"].startswith("Du bist Recherche")][-1]
        self.assertIn("Mehr Quellen", zweiter["messages"][0]["content"])

    def test_pruefer_hoert_nach_drei_versuchen_auf(self):
        self.ki.pruefer_gut = [False]
        chef.projekt_anlegen({"name": "R", "ziel": "Z", "aufgaben": [{"titel": "T", "rolle": "texter", "auftrag": "A"}]})
        self.assertTrue(warten_bis(lambda: self.projekt()["status"] == "fertig"))
        self.assertEqual(self.projekt()["aufgaben"][0]["versuche"], chef.MAX_VERSUCHE)

    def test_projektbudget_haelt_an_und_fragt(self):
        chef.projekt_anlegen({"name": "Teuer", "ziel": "Z", "budget_dollar": 0.1, "aufgaben": [
            {"titel": "Eins", "rolle": "recherche", "auftrag": "A"}, {"titel": "Zwei", "rolle": "recherche", "auftrag": "B"}]})
        # jede falsche Anfrage kostet 1,4 Cent; nach ein paar Anfragen ist das Budget weg
        self.assertTrue(warten_bis(lambda: self.projekt()["status"] == "wartet"))
        warten_bis(lambda: not chef._laufend)
        p = self.projekt()
        self.assertEqual(len([f for f in p["fragen"] if f["stand"] == "offen"]), 1)
        vorher = len(self.ki.anfragen)
        for _ in range(5):
            chef.takt_runde()
        self.assertEqual(len(self.ki.anfragen), vorher, "ohne Freigabe startet nichts mehr")
        # Ja: mehr Budget, es geht weiter
        f = p["fragen"][0]
        chef.freigabe(p["id"], f["id"], True)
        p = self.projekt()
        self.assertEqual(p["status"], "aktiv")
        self.assertGreater(p["budget"], 0.1)
        self.assertTrue(warten_bis(lambda: len(self.ki.anfragen) > vorher))

    def test_tagesgrenze_stoppt_alles(self):
        z = chef.laden()
        z["kosten"][chef.heute()] = 3.0
        chef.speichern(z)
        chef.projekt_anlegen({"name": "R", "ziel": "Z", "aufgaben": [{"titel": "T", "rolle": "recherche", "auftrag": "A"}]})
        for _ in range(3):
            chef.takt_runde()
        self.assertEqual(self.ki.anfragen, [])
        meldungen = [e["text"] for e in chef.laden()["gespraech"] if e["wer"] == "meldung"]
        self.assertEqual(len([m for m in meldungen if "Tagesgrenze" in m]), 1, "nur einmal gemeldet")
        # reden geht trotzdem noch (Reserve), damit Niko die Grenze ändern kann
        chef.chat("Wie viel hab ich heute ausgegeben?")
        self.assertEqual(len(self.ki.anfragen), 1)

    def test_grenzen_haben_eine_obergrenze(self):
        with self.assertRaises(ValueError):
            chef.grenzen_setzen({"tag_dollar": 500})
        with self.assertRaises(ValueError):
            chef.grenzen_setzen({"gleichzeitig": 50})
        with self.assertRaises(ValueError):
            chef.projekt_anlegen({"name": "X", "ziel": "Y", "budget_dollar": 99,
                                  "aufgaben": [{"titel": "T", "rolle": "recherche", "auftrag": "A"}]})
        self.assertIn("5,00", chef.grenzen_setzen({"tag_dollar": 5}).replace(".", ","))

    def test_gleichzeitig_hoechstens_eingestellt(self):
        chef.grenzen_setzen({"gleichzeitig": 1})
        chef.projekt_anlegen({"name": "A", "ziel": "Z", "aufgaben": [{"titel": "T", "rolle": "recherche", "auftrag": "A"}]})
        chef.projekt_anlegen({"name": "B", "ziel": "Z", "aufgaben": [{"titel": "T", "rolle": "recherche", "auftrag": "A"}]})
        sperre = threading.Event()
        echt = self.ki

        def langsam(**kw):
            sperre.wait(5)
            return echt(**kw)
        chef.claude_anfrage = langsam
        chef.takt_runde()
        chef.takt_runde()
        self.assertEqual(len(chef._laufend), 1)
        sperre.set()
        self.assertTrue(warten_bis(lambda: all(p["status"] == "fertig" for p in chef.laden()["projekte"])))

    def test_freigabe_frage_vom_chef(self):
        chef.projekt_anlegen({"name": "A", "ziel": "Z", "aufgaben": [{"titel": "T", "rolle": "texter", "auftrag": "A"}]})
        p = self.projekt()
        chef.freigabe_anfragen({"projekt": p["id"], "frage": "Seite veröffentlichen?"})
        p = self.projekt()
        f = p["fragen"][0]
        z = chef.freigabe(p["id"], f["id"], False)
        self.assertEqual(self.projekt()["fragen"][0]["stand"], "nein")
        self.assertIn("mit Nein beantwortet", [e for e in z["gespraech"] if e["wer"] == "meldung"][-1]["text"])
        self.assertEqual(z["gespraech"][-1]["wer"], "chef", "der Chef reagiert gleich auf die Antwort")

    def test_aufgabe_wiederholen_mit_hinweis(self):
        chef.projekt_anlegen({"name": "A", "ziel": "Z", "aufgaben": [{"titel": "T", "rolle": "texter", "auftrag": "A"}]})
        self.assertTrue(warten_bis(lambda: self.projekt()["status"] == "fertig"))
        aid = self.projekt()["aufgaben"][0]["id"]
        chef.aufgabe_wiederholen({"aufgabe": aid, "hinweis": "kürzer bitte"})
        self.assertEqual(self.projekt()["status"], "aktiv")
        self.assertTrue(warten_bis(lambda: self.projekt()["status"] == "fertig"))
        letzter = [x for x in self.ki.anfragen if x["system"][0]["text"].startswith("Du bist Texter")][-1]
        self.assertIn("kürzer bitte", letzter["messages"][0]["content"])

    def test_tagesbericht(self):
        chef.projekt_anlegen({"name": "A", "ziel": "Z", "aufgaben": [{"titel": "T", "rolle": "texter", "auftrag": "A"}]})
        self.assertTrue(warten_bis(lambda: self.projekt()["status"] == "fertig"))
        chef.BERICHT_UM = 0
        chef.takt_runde()
        chef.takt_runde()
        berichte = [e for e in chef.laden()["gespraech"] if e["wer"] == "bericht"]
        self.assertEqual(len(berichte), 1)
        self.assertIn("1 Aufgaben fertig", berichte[0]["text"])

    def test_falsche_eingaben(self):
        for falsch in ({"name": "", "ziel": "Z", "aufgaben": [{"titel": "T", "rolle": "recherche", "auftrag": "A"}]},
                       {"name": "N", "ziel": "Z", "aufgaben": []},
                       {"name": "N", "ziel": "Z", "aufgaben": [{"titel": "T", "rolle": "hacker", "auftrag": "A"}]}):
            with self.assertRaises(ValueError):
                chef.projekt_anlegen(falsch)
        with self.assertRaises(ValueError):
            chef.vorschau_datei("../../etc/passwd")

    def test_fehler_im_arbeiter_wird_gemeldet(self):
        def kaputt(**kw):
            raise ConnectionError("weg")
        chef.claude_anfrage = kaputt
        chef.projekt_anlegen({"name": "A", "ziel": "Z", "aufgaben": [{"titel": "T", "rolle": "texter", "auftrag": "A"}]})
        self.assertTrue(warten_bis(lambda: self.projekt()["aufgaben"][0]["status"] == "fehler"))
        self.assertIn("technischer Fehler", chef.laden()["gespraech"][-1]["text"])


if __name__ == "__main__":
    unittest.main()
