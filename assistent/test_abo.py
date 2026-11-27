"""Tests für die Code-Aufgaben auf Nikos PC (abo.py und abo-arbeiter/): python -m unittest test_abo  (im Ordner assistent/)

Der Ende-zu-Ende-Test startet den echten Server und den echten Biko-Arbeiter, mit einem falschen `claude` und `gh`
und einem lokalen Git-Repo als GitHub. Er braucht git und läuft nur unter Linux/macOS."""

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from datetime import timedelta
from types import SimpleNamespace
from pathlib import Path

os.environ["DATA_DIR"] = tempfile.mkdtemp()
os.environ["CHEF_ABO_TOKEN"] = "t" * 32
import chef  # noqa: E402
import abo  # noqa: E402

chef.print = lambda *a, **k: None
HIER = Path(__file__).resolve().parent


def leeren():
    chef.speichern(chef.laden() | {"projekte": [], "gespraech": [], "kosten": {}, "protokoll": [], "abo": {},
                                   "grenzen": {"tag": 3.0, "gleichzeitig": 3}, "gemeldet": {}, "bericht_tag": ""})


def code_projekt(**mehr):
    chef.projekt_anlegen({"name": "Code", "ziel": "Biko kann X", "aufgaben": [
        {"titel": "X bauen", "rolle": "programmierer", "repo": "n1kob1ko/Biko-Bot", "auftrag": "Bau X"}, *mehr.get("dazu", [])]})
    return chef.laden()["projekte"][0]


def tearDownModule():
    abo._pc["gesehen"] = 0.0   # andere Testmodule sollen keinen verbundenen „PC“ sehen
    os.environ.pop("CHEF_ABO_TOKEN", None)   # und keinen Abo-Modus


class AboTest(unittest.TestCase):
    def setUp(self):
        leeren()
        abo._pc["gesehen"] = 0.0
        self.addCleanup(abo._pc.update, gesehen=0.0)   # sonst ginge in anderen Tests der Chef an den „PC“
        chef.claude_anfrage = lambda **kw: self.fail("Abo-Aufgaben dürfen keine API-Anfrage machen")
        chef.BERICHT_UM = 25

    def test_ohne_token_geht_nichts(self):
        alt = os.environ.pop("CHEF_ABO_TOKEN")
        try:
            self.assertFalse(abo.token_passt("Bearer " + "t" * 32))
            with self.assertRaises(ValueError):
                code_projekt()
        finally:
            os.environ["CHEF_ABO_TOKEN"] = alt
        self.assertTrue(abo.token_passt("Bearer " + "t" * 32))
        self.assertFalse(abo.token_passt("Bearer " + "x" * 32))
        self.assertFalse(abo.token_passt(None))

    def test_takt_startet_keine_api_arbeiter_fuer_code(self):
        code_projekt()
        for _ in range(3):
            chef.takt_runde()
        self.assertEqual(chef._laufend, {})
        self.assertEqual(chef.laden()["projekte"][0]["aufgaben"][0]["status"], "offen")

    def test_repo_muss_bekannt_sein_wenn_pc_da_war(self):
        abo.abholen({"repos": ["n1kob1ko/Biko-Bot"]})
        with self.assertRaises(ValueError):
            chef.projekt_anlegen({"name": "C", "ziel": "Z", "aufgaben": [
                {"titel": "T", "rolle": "programmierer", "repo": "fremd/repo", "auftrag": "A"}]})
        with self.assertRaises(ValueError):
            chef.projekt_anlegen({"name": "C", "ziel": "Z", "aufgaben": [
                {"titel": "T", "rolle": "programmierer", "auftrag": "A"}]})
        p = code_projekt()
        self.assertEqual(p["aufgaben"][0]["repo"], "n1kob1ko/Biko-Bot")

    def test_ablauf_pr_frage_und_merge_nur_nach_ja(self):
        p = code_projekt()
        job = abo.abholen({"repos": ["n1kob1ko/Biko-Bot"]})
        self.assertEqual(job["art"], "code")
        self.assertIn("Bau X", job["auftrag"])
        self.assertTrue(job["zweig"].startswith("biko/"))
        self.assertIsNone(abo.abholen({"repos": ["n1kob1ko/Biko-Bot"]}), "nur eine Aufgabe zur selben Zeit")
        self.assertTrue(abo.ansicht()["verbunden"])
        abo.fertig({"id": job["id"], "ok": True, "zusammenfassung": "X geht.", "ergebnis": "…",
                    "pr": "https://github.com/n1kob1ko/Biko-Bot/pull/99"})
        p = chef.laden()["projekte"][0]
        a = p["aufgaben"][0]
        self.assertEqual((a["status"], a["pr"], p["status"]), ("fertig", "https://github.com/n1kob1ko/Biko-Bot/pull/99", "fertig"))
        f = p["fragen"][0]
        self.assertEqual(f["art"], "merge")
        self.assertIn("live auf Railway", f["frage"])
        self.assertIsNone(abo.abholen({}), "ohne Ja wird nicht gemergt")
        chef.freigabe(p["id"], f["id"], True)
        m = abo.abholen({})
        self.assertEqual((m["art"], m["pr"]), ("mergen", "https://github.com/n1kob1ko/Biko-Bot/pull/99"))
        self.assertIsNone(abo.abholen({}))
        abo.gemergt({"id": m["id"], "ok": True})
        self.assertTrue(any("Gemergt" in e["text"] for e in chef.laden()["gespraech"]))
        self.assertEqual(chef.laden()["kosten"], {}, "kein API-Geld")

    def test_nein_merged_nicht(self):
        p = code_projekt()
        job = abo.abholen({})
        abo.fertig({"id": job["id"], "ok": True, "pr": "https://github.com/n1kob1ko/Biko-Bot/pull/5"})
        f = chef.laden()["projekte"][0]["fragen"][0]
        chef.freigabe(p["id"], f["id"], False)
        self.assertIsNone(abo.abholen({}))

    def test_falscher_pr_link_wird_nicht_uebernommen(self):
        code_projekt()
        job = abo.abholen({})
        abo.fertig({"id": job["id"], "ok": True, "pr": "https://boese.example/pull/1"})
        p = chef.laden()["projekte"][0]
        self.assertEqual(p["aufgaben"][0]["pr"], "")
        self.assertEqual(p["fragen"], [])

    def test_abo_grenze_pausiert_und_nimmt_lauf_zurueck(self):
        code_projekt()
        job = abo.abholen({})
        abo.fertig({"id": job["id"], "grenze": True, "pause_minuten": 30})
        z = chef.laden()
        self.assertEqual(z["projekte"][0]["aufgaben"][0]["status"], "offen")
        self.assertEqual(abo.heute_laeufe(z["abo"]), 0)
        self.assertIsNone(abo.abholen({}), "Pause")
        z["abo"]["pause_bis"] = (chef.jetzt() - timedelta(minutes=1)).isoformat(timespec="seconds")
        chef.speichern(z)
        self.assertEqual(abo.abholen({})["id"], job["id"])

    def test_laeufe_pro_tag_begrenzt(self):
        abo.abo_einstellen({"laeufe_pro_tag": 1})
        chef.projekt_anlegen({"name": "C", "ziel": "Z", "aufgaben": [
            {"titel": "Eins", "rolle": "programmierer", "repo": "a/b", "auftrag": "A"},
            {"titel": "Zwei", "rolle": "programmierer", "repo": "a/b", "auftrag": "B"}]})
        job = abo.abholen({})
        abo.fertig({"id": job["id"], "ok": True, "pr": ""})
        self.assertIsNone(abo.abholen({}))
        self.assertEqual(len([e for e in chef.laden()["gespraech"] if "Code-Läufe" in e["text"]]), 1)
        with self.assertRaises(ValueError):
            abo.abo_einstellen({"laeufe_pro_tag": 99})

    def test_stiller_pc_gibt_aufgabe_zurueck(self):
        code_projekt()
        job = abo.abholen({})
        z = chef.laden()
        z["projekte"][0]["aufgaben"][0]["abo_lebt"] = (chef.jetzt() - timedelta(minutes=20)).isoformat(timespec="seconds")
        chef.speichern(z)
        chef.takt_runde()
        self.assertEqual(chef.laden()["projekte"][0]["aufgaben"][0]["status"], "offen")
        self.assertEqual(abo.abholen({})["id"], job["id"])

    # ---------- das Gespräch mit dem Chef über das Abo ----------
    def api_chef(self, text="Über die API."):
        anfragen = []

        def ki(**kw):
            anfragen.append(kw)
            return SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text=text)],
                                   model="claude-opus-5-5", usage=None)
        chef.claude_anfrage = ki
        return anfragen

    def test_chef_antwortet_ueber_den_pc(self):
        abo.gesehen()
        z = chef.chat("Hallo Biko")
        self.assertTrue(z["abo"]["chef_denkt"])
        self.assertEqual(z["gespraech"][-1]["wer"], "niko")
        job = abo.abholen({"chef_frei": True, "code_frei": True})
        self.assertEqual(job["art"], "chef")
        self.assertIn("Hallo Biko", job["eingabe"])
        self.assertIn("<stand>", job["eingabe"])
        self.assertIn("projekt_anlegen", job["system"])
        self.assertEqual(job["modell"], chef.CHEF_MODELL)
        self.assertIsNone(abo.abholen({}), "nur eine Chef-Antwort zur selben Zeit")
        abo.chef_fertig({"id": job["id"], "ok": True, "antwort": {"text": "Hallo Niko!", "werkzeuge": []}})
        z = chef.ansicht()
        self.assertEqual((z["gespraech"][-1]["wer"], z["gespraech"][-1]["text"]), ("chef", "Hallo Niko!"))
        self.assertFalse(z["abo"]["chef_denkt"])
        self.assertEqual(chef.laden()["kosten"], {}, "kein API-Geld")

    def test_chef_werkzeuge_vom_pc_werden_ausgefuehrt(self):
        abo.gesehen()
        chef.chat("Bau mir was")
        job = abo.abholen({})
        abo.chef_fertig({"id": job["id"], "ok": True, "session": "s1", "antwort": {"text": "Ich lege es an.", "werkzeuge": [
            {"name": "projekt_anlegen", "eingabe": {"name": "Seite", "ziel": "Z", "aufgaben": [
                {"titel": "T", "rolle": "programmierer", "repo": "n1kob1ko/Biko-Bot", "auftrag": "A"}]}}]}})
        z = chef.laden()
        self.assertEqual(z["projekte"][0]["name"], "Seite")
        self.assertEqual(z["gespraech"][-1]["text"], "Ich lege es an.")
        self.assertNotIn("chef", z["abo"])

    def test_chef_bekommt_ergebnisse_und_fehler_zurueck(self):
        abo.gesehen()
        chef.chat("Was kam raus?")
        job = abo.abholen({})
        abo.chef_fertig({"id": job["id"], "ok": True, "session": "s1", "antwort": {"text": "Ich schau nach.", "werkzeuge": [
            {"name": "ergebnis_lesen", "eingabe": {"aufgabe": "a000000"}}]}})
        self.assertNotEqual(chef.laden()["gespraech"][-1]["wer"], "chef", "Zwischentext kommt nicht zu Niko")
        weiter = abo.abholen({})
        self.assertEqual((weiter["art"], weiter["resume"]), ("chef", "s1"))
        self.assertIn("<werkzeug_ergebnisse>", weiter["eingabe"])
        self.assertIn("Fehler", weiter["eingabe"])
        abo.chef_fertig({"id": weiter["id"], "ok": True, "antwort": {"text": "Die Aufgabe gibt es nicht.", "werkzeuge": []}})
        self.assertEqual(chef.laden()["gespraech"][-1]["text"], "Die Aufgabe gibt es nicht.")

    def test_ohne_pc_antwortet_der_chef_ueber_die_api(self):
        anfragen = self.api_chef()
        chef.chat("Hallo")
        self.assertEqual(len(anfragen), 1)
        self.assertEqual(chef.laden()["gespraech"][-1]["text"], "Über die API.")

    def test_pc_holt_nicht_ab_dann_api(self):
        anfragen = self.api_chef()
        abo.gesehen()
        chef.chat("Hallo")
        self.assertEqual(anfragen, [])
        z = chef.laden()
        z["abo"]["chef"]["zeit"] = (chef.jetzt() - timedelta(seconds=60)).isoformat(timespec="seconds")
        chef.speichern(z)
        chef.takt_runde()
        for _ in range(100):
            if chef.laden()["gespraech"][-1]["wer"] == "chef":
                break
            time.sleep(0.02)
        self.assertEqual(chef.laden()["gespraech"][-1]["text"], "Über die API.")
        self.assertNotIn("chef", chef.laden()["abo"])

    def test_pc_fehler_oder_grenze_dann_api(self):
        anfragen = self.api_chef()
        abo.gesehen()
        chef.chat("Hallo")
        job = abo.abholen({})
        abo.chef_fertig({"id": job["id"], "grenze": True})
        for _ in range(100):
            if anfragen:
                break
            time.sleep(0.02)
        self.assertEqual(len(anfragen), 1)
        self.assertTrue(abo.pausiert(chef.laden()["abo"]))
        time.sleep(0.1)
        chef.chat("Und jetzt?")   # während der Pause gleich über die API
        self.assertEqual(len(anfragen), 2)

    def test_nachgeschoben_waehrend_der_pc_denkt(self):
        abo.gesehen()
        chef.chat("Eins")
        job = abo.abholen({})
        chef.chat("Zwei")
        abo.chef_fertig({"id": job["id"], "ok": True, "antwort": {"text": "Zu eins.", "werkzeuge": []}})
        weiter = abo.abholen({})
        self.assertEqual(weiter["art"], "chef")
        self.assertIn("Zwei", weiter["eingabe"])

    def test_code_frei_false_gibt_nur_chef(self):
        abo.gesehen()
        code_projekt()
        self.assertIsNone(abo.abholen({"code_frei": False}))
        self.assertEqual(abo.abholen({"code_frei": True})["art"], "code")

    # ---------- Abo-Modus: alle Arbeiter auf dem PC ----------
    def text_projekt(self):
        chef.projekt_anlegen({"name": "Daten", "ziel": "Analyse", "aufgaben": [
            {"titel": "Quellen", "rolle": "recherche", "auftrag": "Such Daten"},
            {"titel": "Werkzeug", "rolle": "entwickler", "auftrag": "Bau HTML", "gleichzeitig": True}]})

    def test_abo_modus_alle_arbeiter_auf_dem_pc(self):
        self.text_projekt()
        for _ in range(3):
            chef.takt_runde()   # nichts über die API (claude_anfrage würde den Test scheitern lassen)
        self.assertEqual(chef._laufend, {})
        self.assertIsNone(abo.abholen({}), "ohne text_frei bekommt ein alter PC-Arbeiter keine Textaufgaben")
        r = abo.abholen({"text_frei": True})
        self.assertEqual((r["art"], r["titel"], r["web"]), ("text", "Quellen", True))
        self.assertIn("Such Daten", r["eingabe"])
        self.assertIn("zusammenfassung", r["schema"]["properties"])
        e = abo.abholen({"text_frei": True})
        self.assertEqual((e["titel"], e["web"]), ("Werkzeug", False), "gleichzeitig: beide auf einmal")
        self.assertIn("html", e["schema"]["required"])
        z = chef.ansicht()
        self.assertTrue(z["abo"]["alles"])
        self.assertTrue(all(a["am_pc"] for a in z["projekte"][0]["aufgaben"]))
        abo.text_fertig({"id": r["id"], "ok": True, "antwort": {"zusammenfassung": "5 Quellen.", "ergebnis": "# Quellen"}})
        abo.text_fertig({"id": e["id"], "ok": True, "antwort": {"zusammenfassung": "Werkzeug da.", "ergebnis": "x",
                                                                 "html": "<!doctype html><h1>Analyse</h1>"}})
        p = chef.laden()["projekte"][0]
        self.assertEqual(p["status"], "fertig")
        self.assertIn("Analyse", chef.vorschau_lesen(e["id"]))
        self.assertEqual(chef.laden()["kosten"], {})

    def test_abo_modus_wartet_auf_pc_statt_api(self):
        self.text_projekt()
        z = chef.laden()
        z["projekte"][0]["aufgaben"][0].update(status="laeuft", am_pc=True,
                                               abo_lebt=(chef.jetzt() - timedelta(minutes=20)).isoformat(timespec="seconds"))
        chef.speichern(z)
        chef.takt_runde()
        a = chef.laden()["projekte"][0]["aufgaben"][0]
        self.assertEqual(a["status"], "offen", "PC weg: Aufgabe wartet wieder, startet aber nicht über die API")
        self.assertEqual(chef._laufend, {})

    def test_abo_modus_aus_nimmt_die_api(self):
        self.assertIn("alle Arbeiter über dein Abo", abo.abo_einstellen({"alles_ueber_abo": True}))
        abo.abo_einstellen({"alles_ueber_abo": False})
        self.assertFalse(abo.alles_ueber_pc(chef.laden()))
        self.text_projekt()
        self.assertIsNone(abo.abholen({"text_frei": True}))
        with self.assertRaises(ValueError):
            abo.abo_einstellen({})

    def test_text_fehler_und_grenze(self):
        self.text_projekt()
        r = abo.abholen({"text_frei": True})
        abo.text_fertig({"id": r["id"], "grenze": True})
        z = chef.laden()
        self.assertEqual(z["projekte"][0]["aufgaben"][0]["status"], "offen")
        self.assertTrue(abo.pausiert(z["abo"]))
        z["abo"].pop("pause_bis")
        chef.speichern(z)
        r = abo.abholen({"text_frei": True})
        abo.text_fertig({"id": r["id"], "ok": False, "fehler": "kaputt"})
        self.assertEqual(chef.laden()["projekte"][0]["aufgaben"][0]["status"], "fehler")

    def test_stand_fuer_den_chef(self):
        code_projekt()
        text = chef.stand_text(chef.laden())
        self.assertIn("PC-Arbeiter", text)
        self.assertIn("programmierer, n1kob1ko/Biko-Bot", text)


@unittest.skipUnless(shutil.which("git") and os.name == "posix", "braucht git unter Linux/macOS")
class EndeZuEndeTest(unittest.TestCase):
    """Echter Server + echter Biko-Arbeiter, falsches claude/gh, lokales Repo als GitHub."""

    def setUp(self):
        leeren()
        self.tmp = Path(tempfile.mkdtemp())
        bin_ = self.tmp / "bin"
        bin_.mkdir()
        (bin_ / "claude").write_text(
            "#!/bin/sh\ncase \"$*\" in *json-schema*) cat > /dev/null; printf '%s' "
            "'{\"result\":\"x\",\"session_id\":\"s1\",\"structured_output\":{\"text\":\"Hallo Niko\",\"werkzeuge\":[]}}'; exit 0;; esac\n"
            "cat > \"$PWD/../claude-eingabe.txt\"\n"
            "echo 'neu' > neu.txt && git add neu.txt && git -c user.name=t -c user.email=t@t commit -qm 'X gebaut'\n"
            "printf '%s' '{\"type\":\"result\",\"is_error\":false,\"num_turns\":3,"
            "\"result\":\"ZUSAMMENFASSUNG: X ist gebaut.\\nTests laufen.\"}'\n")
        (bin_ / "gh").write_text("#!/bin/sh\necho \"$@\" >> \"" + str(self.tmp / "gh.log") + "\"\n"
                                 "cat > /dev/null\necho https://github.com/n1kob1ko/Biko-Bot/pull/123\n")
        for d in bin_.iterdir():
            d.chmod(0o755)
        os.environ["PATH"] = f"{bin_}{os.pathsep}{os.environ['PATH']}"
        # „GitHub“ ist ein lokales nacktes Repo
        g = lambda *a, cwd=None: subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *a], cwd=cwd,
                                                check=True, capture_output=True)
        g("init", "-q", "--bare", "-b", "main", str(self.tmp / "origin.git"))
        g("clone", "-q", str(self.tmp / "origin.git"), str(self.tmp / "Biko-Bot"))
        (self.tmp / "Biko-Bot" / "README.md").write_text("hi\n")
        g("add", ".", cwd=self.tmp / "Biko-Bot")
        g("commit", "-qm", "start", cwd=self.tmp / "Biko-Bot")
        g("push", "-q", "origin", "main", cwd=self.tmp / "Biko-Bot")
        g("remote", "set-head", "origin", "main", cwd=self.tmp / "Biko-Bot")

    def test_aufgabe_wird_auf_dem_pc_zum_pr(self):
        import server
        from http.server import ThreadingHTTPServer
        srv = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.shutdown)
        spec = importlib.util.spec_from_file_location("biko_arbeiter", HIER / "abo-arbeiter" / "biko_arbeiter.py")
        ba = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(ba)
        e = {"url": f"http://localhost:{srv.server_address[1]}", "token": "t" * 32, "minuten": 5, "takt": 10,
             "repos": {"n1kob1ko/Biko-Bot": str(self.tmp / "Biko-Bot")}}

        # falscher Schlüssel: 401
        with self.assertRaises(Exception):
            ba.biko({**e, "token": "x" * 32}, "/api/abo/abholen", {})
        code_projekt()
        job = ba.biko(e, "/api/abo/abholen", {"repos": list(e["repos"])})["auftrag"]
        os.environ["ANTHROPIC_API_KEY"] = "sk-darf-nicht-ankommen"
        try:
            ergebnis = ba.code_aufgabe(e, job)
        finally:
            os.environ.pop("ANTHROPIC_API_KEY")
        self.assertTrue(ergebnis["ok"], ergebnis)
        self.assertEqual(ergebnis["pr"], "https://github.com/n1kob1ko/Biko-Bot/pull/123")
        self.assertEqual(ergebnis["zusammenfassung"], "X ist gebaut.")
        self.assertIn("Bau X", (self.tmp / ".biko-arbeit" / "claude-eingabe.txt").read_text())
        # der Zweig ist auf „GitHub“, der Arbeitsordner ist wieder weg, Nikos Ordner unberührt
        zweige = subprocess.run(["git", "branch", "--list"], cwd=self.tmp / "origin.git", capture_output=True, text=True).stdout
        self.assertIn(job["zweig"], zweige)
        self.assertFalse((self.tmp / ".biko-arbeit" / job["zweig"].replace("/", "-")).exists())
        self.assertFalse((self.tmp / "Biko-Bot" / "neu.txt").exists())
        self.assertIn("pr create", (self.tmp / "gh.log").read_text())
        ba.biko(e, "/api/abo/fertig", ergebnis)
        p = chef.laden()["projekte"][0]
        self.assertEqual(p["aufgaben"][0]["status"], "fertig")
        chef.freigabe(p["id"], p["fragen"][0]["id"], True)
        m = ba.biko(e, "/api/abo/abholen", {})["auftrag"]
        r = ba.mergen(m)
        self.assertTrue(r["ok"], r)
        self.assertIn("pr merge https://github.com/n1kob1ko/Biko-Bot/pull/123 --squash", (self.tmp / "gh.log").read_text())

    def test_text_aufgabe_vom_pc(self):
        spec = importlib.util.spec_from_file_location("biko_arbeiter", HIER / "abo-arbeiter" / "biko_arbeiter.py")
        ba = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(ba)
        e = {"url": "http://localhost:1", "token": "t" * 32}
        r = ba.text_aufgabe(e, {"id": "a1", "system": "S", "schema": {}, "modell": "sonnet", "eingabe": "x", "web": True})
        self.assertEqual(r, {"id": "a1", "ok": True, "antwort": {"text": "Hallo Niko", "werkzeuge": []}})

    def test_chef_antwort_vom_pc(self):
        spec = importlib.util.spec_from_file_location("biko_arbeiter", HIER / "abo-arbeiter" / "biko_arbeiter.py")
        ba = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(ba)
        r = ba.chef_antworten({"id": "c1", "system": "S", "schema": {}, "modell": "opus", "eingabe": "Hallo"})
        self.assertEqual(r, {"id": "c1", "ok": True, "antwort": {"text": "Hallo Niko", "werkzeuge": []}, "session": "s1"})

    def test_claude_env_ohne_api_schluessel(self):
        spec = importlib.util.spec_from_file_location("biko_arbeiter", HIER / "abo-arbeiter" / "biko_arbeiter.py")
        ba = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(ba)
        os.environ["ANTHROPIC_API_KEY"] = "sk"
        try:
            self.assertNotIn("ANTHROPIC_API_KEY", ba.claude_env())
        finally:
            os.environ.pop("ANTHROPIC_API_KEY")
        self.assertTrue(ba.GRENZE.search("Claude usage limit reached. Your limit resets 3pm"))
        self.assertEqual(ba.pause_minuten("resets in 2 hours"), 120)


if __name__ == "__main__":
    unittest.main()
