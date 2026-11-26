"""Tests für die DreamStudy-Anbindung ohne echte KI und ohne Netz: python -m unittest test_dreamstudy  (im Ordner assistent/)"""

import json
import os
import tempfile
import time
import unittest
import urllib.error
from types import SimpleNamespace

os.environ["DATA_DIR"] = tempfile.mkdtemp()
os.environ["DREAMSTUDY_TOKEN"] = "biko-test-schluessel-0123456789abcdef"
import chef  # noqa: E402
import dreamstudy  # noqa: E402

chef.print = lambda *a, **k: None
dreamstudy.print = lambda *a, **k: None

SCHEMA = {"type": "object", "properties": {"ueberblick": {"type": "string"}}, "required": ["ueberblick"]}


def antwort(*bloecke, stop="tool_use"):
    return SimpleNamespace(stop_reason=stop, content=list(bloecke), model="claude-sonnet-5-5",
                           usage=SimpleNamespace(input_tokens=4000, output_tokens=800, cache_read_input_tokens=0,
                                                 cache_creation_input_tokens=0, server_tool_use=None))


class FalschesDreamStudy:
    """Merkt sich alle Anfragen und antwortet wie DreamStudy."""

    def __init__(self, auftraege, datei=b"%PDF-1.4 test"):
        self.auftraege, self.datei, self.anfragen, self.post_status = auftraege, datei, [], 200

    def __call__(self, methode, pfad, daten=None, roh=False, timeout=30):
        self.anfragen.append((methode, pfad, daten))
        if methode == "GET" and pfad == "/api/biko/auftraege":
            a, self.auftraege = self.auftraege, []
            return {"auftraege": a}
        if methode == "GET" and pfad.endswith("/datei"):
            return self.datei, "application/pdf"
        if methode == "POST":
            if self.post_status != 200:
                raise urllib.error.HTTPError(pfad, self.post_status, "x", {}, None)
            return {"ok": True}
        raise AssertionError(pfad)


class DreamStudyTest(unittest.TestCase):
    def setUp(self):
        chef.speichern(json.loads(json.dumps(chef.LEER)))
        self.ki_anfragen = []

        def ki(**kw):
            self.ki_anfragen.append(kw)
            return antwort(SimpleNamespace(type="tool_use", id="t1", name="abgeben", input={"ueberblick": "S1 hat bald Schularbeit."}))

        chef.claude_anfrage = ki

    def test_briefing_wird_erledigt_und_zurueckgeschickt(self):
        ds = FalschesDreamStudy([{"id": 7, "art": "briefing", "system": "Du schreibst das Tagesbriefing.",
                                  "anfrage": "## S1 · 14:00", "schema": SCHEMA, "max_tokens": 8000, "datei": None}])
        dreamstudy._anfrage = ds
        dreamstudy.runde()
        kw = self.ki_anfragen[0]
        self.assertEqual(kw["model"], dreamstudy.MODELL)
        self.assertEqual(kw["tools"][0]["input_schema"], SCHEMA)
        self.assertEqual(kw["messages"][0]["content"][-1]["text"], "## S1 · 14:00")
        post = [a for a in ds.anfragen if a[0] == "POST"][0]
        self.assertEqual(post[1], "/api/biko/auftraege/7")
        self.assertEqual(post[2]["ergebnis"], {"ueberblick": "S1 hat bald Schularbeit."})
        self.assertAlmostEqual(post[2]["kosten_usd"], 0.016)   # 4000 × 2 $ + 800 × 10 $ je Million
        self.assertEqual(post[2]["tokens_ein"], 4000)
        z = chef.laden()
        self.assertAlmostEqual(chef.heute_ausgegeben(z), 0.016)
        self.assertTrue(z["dreamstudy"]["erledigt"][-1]["ok"])
        self.assertTrue(z["dreamstudy"]["zuletzt"])
        self.assertNotIn("S1 hat", json.dumps(z), "kein Text aus DreamStudy im Zustand")
        self.assertIn("Fertig: DreamStudy-Tagesbriefing", z["protokoll"][-1]["text"])

    def test_dokument_kommt_als_pdf_mit(self):
        ds = FalschesDreamStudy([{"id": 9, "art": "material", "system": "Lernzettel", "anfrage": "Für: S1", "schema": SCHEMA,
                                  "datei": {"pfad": "/api/biko/auftraege/9/datei", "mime": "application/pdf"}}])
        dreamstudy._anfrage = ds
        dreamstudy.runde()
        block = self.ki_anfragen[0]["messages"][0]["content"][0]
        self.assertEqual(block["type"], "document")
        self.assertEqual(block["source"]["media_type"], "application/pdf")
        self.assertIn("Lernzettel aus einem Dokument", chef.laden()["gespraech"][-1]["text"])

    def test_fremder_pfad_fuer_die_datei_wird_nicht_geholt(self):
        ds = FalschesDreamStudy([{"id": 3, "art": "material", "system": "x", "anfrage": "x", "schema": SCHEMA,
                                  "datei": {"pfad": "https://boese.example/x", "mime": "application/pdf"}}])
        dreamstudy._anfrage = ds
        dreamstudy.runde()
        self.assertEqual(self.ki_anfragen, [])
        self.assertFalse(any("boese" in a[1] for a in ds.anfragen))
        post = [a for a in ds.anfragen if a[0] == "POST"][0]
        self.assertIn("fehler", post[2])

    def test_tagesgrenze_erreicht_holt_nichts_ab(self):
        z = chef.laden()
        chef.kosten_buchen(z, 5.0)
        chef.speichern(z)
        ds = FalschesDreamStudy([{"id": 1, "art": "briefing", "system": "x", "anfrage": "x", "schema": SCHEMA}])
        dreamstudy._anfrage = ds
        dreamstudy.runde()
        self.assertEqual(ds.anfragen, [])
        self.assertEqual(self.ki_anfragen, [])

    def test_ohne_ergebnis_geht_ein_fehler_zurueck(self):
        chef.claude_anfrage = lambda **kw: antwort(SimpleNamespace(type="text", text="Weiß ich nicht."), stop="end_turn")
        ds = FalschesDreamStudy([{"id": 4, "art": "briefing", "system": "x", "anfrage": "x", "schema": SCHEMA}])
        dreamstudy._anfrage = ds
        dreamstudy.runde()
        post = [a for a in ds.anfragen if a[0] == "POST"][0]
        self.assertEqual(post[2]["fehler"], "Claude hat kein Ergebnis abgegeben.")
        self.assertGreater(post[2]["kosten_usd"], 0)

    def test_falscher_schluessel_wird_gemeldet(self):
        def nein(*a, **k):
            raise urllib.error.HTTPError("/api/biko/auftraege", 401, "x", {}, None)
        dreamstudy._anfrage = nein
        dreamstudy.runde()
        self.assertIn("Schlüssel passt nicht", chef.laden()["dreamstudy"]["fehler"])
        self.assertIn("Letzter Fehler", dreamstudy.dreamstudy_stand({}))

    def test_takt_hoechstens_alle_paar_minuten(self):
        dreamstudy._anfrage = FalschesDreamStudy([])
        dreamstudy._zuletzt, dreamstudy._laeuft = 0.0, False
        self.assertTrue(dreamstudy.takt(jetzt=1000.0))
        ende = time.time() + 2
        while dreamstudy._laeuft and time.time() < ende:
            time.sleep(0.01)
        self.assertFalse(dreamstudy.takt(jetzt=1050.0))
        self.assertTrue(dreamstudy.takt(jetzt=1000.0 + dreamstudy.abstand()))
        while dreamstudy._laeuft and time.time() < ende:
            time.sleep(0.01)

    def test_ohne_schluessel_aus(self):
        alt = os.environ.pop("DREAMSTUDY_TOKEN")
        try:
            self.assertFalse(dreamstudy.takt(jetzt=10 ** 9))
            self.assertIn("nicht verbunden", dreamstudy.dreamstudy_stand({}))
        finally:
            os.environ["DREAMSTUDY_TOKEN"] = alt

    def test_chef_hat_die_werkzeuge(self):
        self.assertIn("dreamstudy_stand", chef.CHEF_WERKZEUGE)
        self.assertIn("dreamstudy_jetzt", chef.CHEF_WERKZEUGE)
        self.assertIn("dreamstudy", chef.ansicht())


if __name__ == "__main__":
    unittest.main()
