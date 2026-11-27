"""
Biko-Chef lässt Code-Aufgaben von Claude Code auf Nikos eigenem PC erledigen, mit Nikos Claude-Abo statt mit API-Geld.

So hängt es zusammen:
  Chef        legt eine Aufgabe mit der Rolle `programmierer` und einem Repo an (z. B. "n1kob1ko/Biko-Bot").
  PC-Arbeiter `abo-arbeiter/biko_arbeiter.py` läuft auf Nikos PC. Er fragt alle paar Sekunden nach
              (POST /api/abo/abholen), arbeitet die Aufgabe mit `claude -p` in einem eigenen Git-Arbeitsordner ab,
              schiebt den Zweig hoch, öffnet einen PR und meldet das Ergebnis (POST /api/abo/fertig).
              Während er arbeitet, meldet er sich jede Minute (POST /api/abo/lebt).
  Freigabe    Zu jedem PR fragt Biko Niko in /chef: „Mergen?“. Erst bei Ja holt der PC-Arbeiter einen Merge-Auftrag ab
              (gh pr merge). Mergen nach main heißt bei Biko-Bot: geht live auf Railway. Das entscheidet nur Niko.

Warum so: Anthropic erlaubt, das unveränderte Claude Code mit dem eigenen Abo auf dem eigenen Rechner zu benutzen, auch
aus einem eigenen Skript. Nicht erlaubt ist, das Abo für andere Leute oder Kunden einzusetzen. Darum nur Nikos Repos.

Grenzen: Die Abo-Läufe kosten kein API-Geld, zählen aber gegen Nikos Abo-Grenzen (5 Stunden und Woche, geteilt mit
claude.ai). Darum höchstens `abo_tag` Läufe pro Tag (Standard 10) und immer nur einer zur selben Zeit. Meldet Claude Code
„Grenze erreicht“, pausiert Biko die Abo-Aufgaben, bis die Grenze wieder frei ist.

Einstellung (Umgebung): CHEF_ABO_TOKEN (mindestens 24 Zeichen, derselbe Wert wie auf dem PC). Ohne Token ist alles aus.
"""

import hmac
import json
import os
import re
import threading
import time
from datetime import datetime, timedelta

import chef

ROLLE = "programmierer"
LAEUFE_STANDARD = 10
LAEUFE_HOECHSTENS = 30
VERBUNDEN_SEKUNDEN = 180     # so lange gilt der PC nach der letzten Meldung als verbunden
TOT_SEKUNDEN = 600           # meldet sich der PC so lange nicht zu einer laufenden Aufgabe, geht sie zurück
PAUSE_STANDARD = 60          # Minuten Pause nach „Grenze erreicht“, wenn Claude Code keine Zeit nennt
REPO_MUSTER = re.compile(r"[A-Za-z0-9_.-]{1,60}/[A-Za-z0-9_.-]{1,100}")
CHEF_ABHOLEN_SEKUNDEN = 20  # holt der PC eine Chef-Antwort so lange nicht ab, antwortet der Chef über die API
CHEF_ANTWORT_SEKUNDEN = 150 # und so lange darf der PC für eine Chef-Antwort brauchen
CHEF_RUNDEN = 4             # so oft darf der Chef nacheinander Werkzeuge benutzen
LESEN = {"ergebnis_lesen", "dreamstudy_stand"}   # nach diesen Werkzeugen braucht der Chef das Ergebnis
_pc = {"gesehen": 0.0}      # im Speicher, damit nicht jede Nachfrage die Datei schreibt
PR_MUSTER = re.compile(r"https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/pull/\d+")

def token():
    return os.environ.get("CHEF_ABO_TOKEN", "").strip()


def an():
    return len(token()) >= 24


def token_passt(kopf):
    """Der PC schickt `Authorization: Bearer <token>`."""
    if not an() or not isinstance(kopf, str) or not kopf.startswith("Bearer "):
        return False
    return hmac.compare_digest(kopf[7:].strip().encode(), token().encode())


def ist_abo(a):
    return chef.ROLLEN.get(a.get("rolle"), {}).get("abo") is True


def _stand(z):
    s = z.setdefault("abo", {})
    s.setdefault("repos", [])
    s.setdefault("laeufe", {})
    s.setdefault("merges", [])
    s.setdefault("max_tag", LAEUFE_STANDARD)
    return s


def _iso(t=None):
    return (t or chef.jetzt()).isoformat(timespec="seconds")


def _seit(iso):
    """Sekunden seit dem Zeitpunkt, sehr groß, wenn es keinen gibt."""
    try:
        return (chef.jetzt() - datetime.fromisoformat(iso)).total_seconds()
    except (TypeError, ValueError):
        return 1e9


def heute_laeufe(s):
    return s["laeufe"].get(chef.heute(), 0)


def repo_pruefen(repo, z=None):
    """Für die Aufgabe des Chefs: das Repo muss eines sein, das der PC-Arbeiter kennt (wenn er schon da war)."""
    repo = str(repo or "").strip()
    if not REPO_MUSTER.fullmatch(repo):
        raise ValueError("Eine Programmierer-Aufgabe braucht ein Repo wie „n1kob1ko/Biko-Bot“.")
    bekannt = _stand(z if z is not None else chef.laden())["repos"]
    if bekannt and repo.lower() not in [r.lower() for r in bekannt]:
        raise ValueError("Dieses Repo kennt der PC-Arbeiter nicht. Er kennt: " + ", ".join(bekannt) + ".")
    return next((r for r in bekannt if r.lower() == repo.lower()), repo)


# ---------- Wege für den PC-Arbeiter ----------
def gesehen():
    _pc["gesehen"] = time.time()


def pausiert(s):
    return bool(s.get("pause_bis")) and _seit(s["pause_bis"]) < 0


def abholen(daten):
    """Gibt dem PC die nächste Arbeit: erst eine Chef-Antwort, dann freigegebene Merges, dann eine Code-Aufgabe.
    `chef_frei` / `code_frei`: was der PC gerade annehmen kann (er beantwortet Chef-Fragen neben einer Code-Aufgabe).
    None, wenn nichts da ist."""
    gesehen()
    repos = [str(r).strip() for r in (daten.get("repos") or []) if REPO_MUSTER.fullmatch(str(r).strip())][:20]
    with chef._lock:
        z = chef.laden()
        s = _stand(z)
        if repos != s["repos"] or s.get("version") != str(daten.get("version") or "")[:20]:
            s["repos"], s["version"] = repos, str(daten.get("version") or "")[:20]
            chef.speichern(z)
        if pausiert(s):
            return None
        if s.pop("pause_bis", None):
            chef.speichern(z)
        c = s.get("chef")
        if c and c["stand"] == "wartet" and daten.get("chef_frei", True) is not False:
            c.update(stand="laeuft", seit=_iso())
            eingabe = c.get("folge") or chef_eingabe(z)
            chef.speichern(z)
            return {"art": "chef", "id": c["id"], "system": chef_system(), "schema": CHEF_SCHEMA,
                    "modell": chef.CHEF_MODELL, "eingabe": eingabe, "resume": c.get("session")}
        if daten.get("code_frei", True) is False:
            return None
        for m in s["merges"]:
            if m["stand"] == "wartet":
                m.update(stand="laeuft", seit=_iso())
                chef.speichern(z)
                return {"art": "mergen", "id": m["id"], "pr": m["pr"], "repo": m["repo"]}
        if any(ist_abo(a) and a["status"] == "laeuft" for p in z["projekte"] for a in p["aufgaben"]):
            return None   # immer nur eine Code-Aufgabe zur selben Zeit
        for p in z["projekte"]:
            if p["status"] != "aktiv":
                continue
            for a in chef.bereite_aufgaben(p):
                if not ist_abo(a):
                    continue
                if heute_laeufe(s) >= s["max_tag"]:
                    if z["gemeldet"].get("abo") != chef.heute():
                        z["gemeldet"]["abo"] = chef.heute()
                        chef.eintrag(z, "meldung", f"Heute sind schon {s['max_tag']} Abo-Läufe auf deinem PC gelaufen. "
                                                   "Morgen geht es weiter, oder du stellst mehr ein.")
                    chef.speichern(z)
                    return None
                a.update(status="laeuft", gestartet=_iso(), abo_lebt=_iso())
                s["laeufe"][chef.heute()] = heute_laeufe(s) + 1
                s["laeufe"] = {k: s["laeufe"][k] for k in sorted(s["laeufe"])[-31:]}
                chef.protokoll_zeile(z, f"Start auf deinem PC: {a['titel']} ({a.get('repo')})", p["id"])
                chef.speichern(z)
                return {"art": "code", "id": a["id"], "repo": a.get("repo"), "titel": a["titel"],
                        "zweig": f"biko/{a['id']}-{a.get('versuche', 0) + 1}", "auftrag": chef.arbeiter_eingabe(p, a)}
    return None


def lebt(daten):
    with chef._lock:
        z = chef.laden()
        gesehen()
        try:
            _, a = chef.aufgabe_finden(z, daten.get("id"))
            if a["status"] == "laeuft":
                a["abo_lebt"] = _iso()
        except ValueError:
            pass
        chef.speichern(z)
    return {"ok": True}


def fertig(daten):
    """Der PC meldet das Ergebnis einer Code-Aufgabe."""
    with chef._lock:
        z = chef.laden()
        s = _stand(z)
        gesehen()
        p, a = chef.aufgabe_finden(z, daten.get("id"))
        if not ist_abo(a) or a["status"] != "laeuft":
            return {"ok": True}   # schon erledigt oder zurückgesetzt
        a.pop("abo_lebt", None)
        if daten.get("grenze") is True:
            minuten = daten.get("pause_minuten")
            minuten = minuten if isinstance(minuten, int) and 5 <= minuten <= 7 * 24 * 60 else PAUSE_STANDARD
            bis = chef.jetzt() + timedelta(minutes=minuten)
            s["pause_bis"] = _iso(bis)
            a["status"] = "offen"
            s["laeufe"][chef.heute()] = max(0, heute_laeufe(s) - 1)
            chef.eintrag(z, "meldung", f"Dein Claude-Abo ist gerade an seiner Grenze. Ich mache um "
                                       f"{bis.strftime('%H:%M')} Uhr mit „{a['titel']}“ weiter.", projekt=p["id"])
            chef.protokoll_zeile(z, "Abo-Grenze erreicht, Pause", p["id"])
            chef.speichern(z)
            return {"ok": True}
        a["versuche"] = a.get("versuche", 0) + 1
        a["zusammenfassung"] = chef._kurz(daten.get("zusammenfassung"), 400)
        a["ergebnis"] = chef._kurz(daten.get("ergebnis"), 15000)
        if daten.get("ok") is not True:
            a["status"] = "fehler"
            a["urteil"] = "Auf dem PC hat es nicht geklappt: " + chef._kurz(daten.get("fehler"), 300)
            chef.protokoll_zeile(z, f"Fehler auf dem PC: {a['titel']}", p["id"])
            chef.eintrag(z, "meldung", f"„{a['titel']}“ hat auf deinem PC nicht geklappt: {chef._kurz(daten.get('fehler'), 300)} "
                                       "Sag mir, ob ich es nochmal versuchen soll.", projekt=p["id"], aufgabe=a["id"])
            chef.speichern(z)
            return {"ok": True}
        pr = str(daten.get("pr") or "").strip()
        a["pr"] = pr if PR_MUSTER.fullmatch(pr) else ""
        a["status"] = "fertig"
        a.pop("hinweis", None)
        chef.protokoll_zeile(z, f"Fertig auf deinem PC: {a['titel']}" + (f", PR {a['pr']}" if a["pr"] else ""), p["id"])
        chef.eintrag(z, "meldung", f"Fertig in „{p['name']}“: {a['titel']}. {a['zusammenfassung']}"
                                   + (f" PR: {a['pr']}" if a["pr"] else " (keine Änderung am Code)"),
                     projekt=p["id"], aufgabe=a["id"])
        if a["pr"]:
            live = " Danach geht es live auf Railway." if a.get("repo", "").lower() == "n1kob1ko/biko-bot" else ""
            chef.frage_stellen(z, p, f"Der PR für „{a['titel']}“ ist fertig: {a['pr']} Soll ich ihn mergen?{live}",
                               art="merge", aufgabe=a["id"], pr=a["pr"], repo=a.get("repo", ""))
        if all(b["status"] == "fertig" for b in p["aufgaben"]):
            p["status"] = "fertig"
            chef.eintrag(z, "meldung", f"Alle Aufgaben von „{p['name']}“ sind fertig. Kosten: "
                                       f"{chef.geld(p.get('ausgegeben', 0))}.", projekt=p["id"])
        chef.speichern(z)
    return {"ok": True}


def merge_einreihen(z, p, f):
    """Niko hat Ja zum Mergen gesagt: der PC holt den Auftrag beim nächsten Mal ab."""
    s = _stand(z)
    s["merges"].append({"id": chef.neue_id("m"), "pr": f["pr"], "repo": f.get("repo", ""), "aufgabe": f.get("aufgabe"),
                        "projekt": p["id"], "stand": "wartet", "zeit": _iso()})
    s["merges"] = s["merges"][-30:]


def gemergt(daten):
    with chef._lock:
        z = chef.laden()
        s = _stand(z)
        gesehen()
        m = next((m for m in s["merges"] if m["id"] == daten.get("id")), None)
        if not m or m["stand"] != "laeuft":
            return {"ok": True}
        ok = daten.get("ok") is True
        m["stand"] = "fertig" if ok else "fehler"
        text = (f"Gemergt: {m['pr']}." if ok else
                f"Mergen von {m['pr']} hat nicht geklappt: {chef._kurz(daten.get('fehler'), 300)}")
        chef.protokoll_zeile(z, text, m.get("projekt"))
        chef.eintrag(z, "meldung", text, projekt=m.get("projekt"))
        chef.speichern(z)
    return {"ok": True}


# ---------- Das Gespräch mit dem Chef über das Abo ----------
CHEF_SCHEMA = {"type": "object", "properties": {
    "text": {"type": "string", "description": "Deine Nachricht an Niko."},
    "werkzeuge": {"type": "array", "description": "Werkzeuge, die Biko jetzt für dich ausführt, der Reihe nach.",
                  "items": {"type": "object", "properties": {
                      "name": {"type": "string"}, "eingabe": {"type": "object"}}, "required": ["name", "eingabe"]}}},
    "required": ["text", "werkzeuge"]}


def chef_system():
    werkzeuge = "\n".join(f"- {name}: {schema['description']} Eingabe (JSON-Schema): "
                           f"{json.dumps(schema['input_schema'], ensure_ascii=False)}"
                           for name, (schema, _) in chef.CHEF_WERKZEUGE.items())
    return (chef.CHEF_SYSTEM + "\n\nSo benutzt du Werkzeuge: Du antwortest immer im vorgegebenen JSON. `text` ist deine "
            "Nachricht an Niko, `werkzeuge` die Aufrufe, die Biko danach für dich ausführt (leer, wenn keine). "
            "Brauchst du das Ergebnis (bei " + ", ".join(sorted(LESEN)) + " oder wenn ein Aufruf fehlschlägt), "
            "bekommst du es als <werkzeug_ergebnisse>, dann schreibst du deine eigentliche Antwort. Sonst ist dein "
            "`text` gleich die Antwort, schreib ihn so, als wäre das Werkzeug schon gelaufen.\n\nWerkzeuge:\n" + werkzeuge)


def chef_eingabe(z):
    """Das Gespräch als ein Text für `claude -p` (jede Antwort ist eine neue Sitzung, der Verlauf steht hier drin)."""
    teile = []
    for n in chef.chef_nachrichten(z):
        tag = "du" if n["role"] == "assistant" else "niko"
        teile.append(f"<{tag}>\n{n['content']}\n</{tag}>")
    return ("Bisheriges Gespräch (<niko> sind Nikos Nachrichten und Meldungen, <du> deine Antworten). "
            "Antworte auf das Letzte.\n\n" + "\n\n".join(teile))


def chef_ueber_pc():
    """Wenn der PC da ist: die nächste Chef-Antwort kommt vom Abo. True, wenn eingereiht."""
    if not an() or not verbunden():
        return False
    with chef._lock:
        z = chef.laden()
        s = _stand(z)
        if pausiert(s):
            return False
        c = s.get("chef")
        if c and c["stand"] == "laeuft":
            c["nochmal"] = True   # Niko hat etwas nachgeschoben, danach gleich noch eine Runde
        elif not c:
            s["chef"] = {"id": chef.neue_id("c"), "stand": "wartet", "zeit": _iso(), "runde": 1}
        chef.speichern(z)
    return True


def _ueber_api():
    """Der Ersatz: der Chef antwortet wie bisher über die API (in einem eigenen Faden, der Takt wartet nicht)."""
    def los():
        try:
            chef.chef_antwort()
        except Exception as e:   # noqa: BLE001  der Faden darf den Server nie mitreißen
            print(f"Chef: Ersatz über die API ging nicht ({type(e).__name__})", flush=True)
    threading.Thread(target=los, daemon=True).start()


def chef_fertig(daten):
    """Der PC liefert eine Chef-Antwort: Werkzeuge ausführen, dann Antwort ins Gespräch oder noch eine Runde."""
    gesehen()
    with chef._lock:
        z = chef.laden()
        s = _stand(z)
        c = s.get("chef")
        if not c or c["id"] != daten.get("id") or c["stand"] != "laeuft":
            return {"ok": True}   # zu spät, der Chef hat schon über die API geantwortet
        if daten.get("grenze") is True or daten.get("ok") is not True:
            s.pop("chef")
            if daten.get("grenze") is True:
                s["pause_bis"] = _iso(chef.jetzt() + timedelta(minutes=PAUSE_STANDARD))
            chef.protokoll_zeile(z, "Chef-Antwort vom PC ging nicht, der Chef antwortet über die API")
            chef.speichern(z)
            _ueber_api()
            return {"ok": True}
    antwort = daten.get("antwort") if isinstance(daten.get("antwort"), dict) else {}
    text = str(antwort.get("text") or "").strip()
    aufrufe = antwort.get("werkzeuge") if isinstance(antwort.get("werkzeuge"), list) else []
    ergebnisse, nochmal = [], False
    for w in aufrufe[:8]:
        name = str((w or {}).get("name") or "") if isinstance(w, dict) else ""
        eingabe = w.get("eingabe") if isinstance(w, dict) and isinstance(w.get("eingabe"), dict) else {}
        try:
            if name not in chef.CHEF_WERKZEUGE:
                raise ValueError("Dieses Werkzeug gibt es nicht.")
            ergebnisse.append(f"{name}: {chef.CHEF_WERKZEUGE[name][1](eingabe)}")
            nochmal = nochmal or name in LESEN
        except ValueError as e:
            ergebnisse.append(f"{name}: Fehler: {e}")
            nochmal = True
    with chef._lock:
        z = chef.laden()
        s = _stand(z)
        c = s.get("chef")
        if not c or c["id"] != daten.get("id"):
            return {"ok": True}
        if nochmal and c["runde"] < CHEF_RUNDEN:
            c.update(stand="wartet", zeit=_iso(), runde=c["runde"] + 1, session=str(daten.get("session") or "")[:80] or None,
                     folge="<werkzeug_ergebnisse>\n" + "\n\n".join(ergebnisse) + "\n</werkzeug_ergebnisse>")
            chef.speichern(z)
            return {"ok": True}
        chef.eintrag(z, "chef", text or "Erledigt.")
        chef.protokoll_zeile(z, "Chef hat über dein Abo geantwortet")
        s.pop("chef")
        if c.get("nochmal"):
            s["chef"] = {"id": chef.neue_id("c"), "stand": "wartet", "zeit": _iso(), "runde": 1}
        chef.speichern(z)
    return {"ok": True}


# ---------- Takt, Anzeige, Werkzeug ----------
def aufraeumen(z):
    """Im Takt: meldet sich der PC zu einer laufenden Aufgabe lange nicht, geht sie zurück. True, wenn sich etwas tat."""
    geaendert = False
    for p in z["projekte"]:
        for a in p["aufgaben"]:
            if ist_abo(a) and a["status"] == "laeuft" and _seit(a.get("abo_lebt")) > TOT_SEKUNDEN:
                a["status"] = "offen"
                a.pop("abo_lebt", None)
                chef.protokoll_zeile(z, f"PC meldet sich nicht mehr, „{a['titel']}“ wartet wieder", p["id"])
                geaendert = True
    for m in _stand(z)["merges"]:
        if m["stand"] == "laeuft" and _seit(m.get("seit")) > TOT_SEKUNDEN:
            m["stand"] = "wartet"
            geaendert = True
    c = _stand(z).get("chef")
    if c and ((c["stand"] == "wartet" and _seit(c["zeit"]) > CHEF_ABHOLEN_SEKUNDEN)
              or (c["stand"] == "laeuft" and _seit(c.get("seit")) > CHEF_ANTWORT_SEKUNDEN)):
        _stand(z).pop("chef")
        chef.protokoll_zeile(z, "PC hat nicht rechtzeitig geantwortet, der Chef antwortet über die API")
        _ueber_api()
        geaendert = True
    return geaendert


def verbunden(_s=None):
    return time.time() - _pc["gesehen"] < VERBUNDEN_SEKUNDEN


def ansicht():
    with chef._lock:
        s = _stand(chef.laden())
    return {"an": an(), "verbunden": verbunden(), "repos": s["repos"], "heute": heute_laeufe(s), "max_tag": s["max_tag"],
            "pause_bis": s.get("pause_bis"), "chef_denkt": bool(s.get("chef"))}


def stand_text(z):
    s = _stand(z)
    if not an():
        return "PC-Arbeiter (Claude Code mit Nikos Abo): aus, CHEF_ABO_TOKEN fehlt."
    teile = [f"PC-Arbeiter (Claude Code mit Nikos Abo): {'verbunden' if verbunden() else 'nicht verbunden'}, "
             f"heute {heute_laeufe(s)} von {s['max_tag']} Läufen"]
    if s["repos"]:
        teile.append("Repos: " + ", ".join(s["repos"]))
    if s.get("pause_bis") and _seit(s["pause_bis"]) < 0:
        teile.append("Pause wegen Abo-Grenze bis " + s["pause_bis"][11:16])
    return ". ".join(teile) + "."


def abo_einstellen(e):
    try:
        n = int(e.get("laeufe_pro_tag"))
    except (TypeError, ValueError):
        raise ValueError("Bitte eine Zahl.")
    if not 1 <= n <= LAEUFE_HOECHSTENS:
        raise ValueError(f"Zwischen 1 und {LAEUFE_HOECHSTENS} Läufen pro Tag.")
    with chef._lock:
        z = chef.laden()
        _stand(z)["max_tag"] = n
        z["gemeldet"].pop("abo", None)
        chef.protokoll_zeile(z, f"Abo-Läufe pro Tag: {n}")
        chef.speichern(z)
    return f"Eingestellt: höchstens {n} Abo-Läufe pro Tag."


chef.CHEF_WERKZEUGE["abo_einstellen"] = (
    {"name": "abo_einstellen", "description": "Stellt ein, wie viele Code-Aufgaben pro Tag auf Nikos PC mit seinem "
     "Claude-Abo laufen dürfen. Nur wenn Niko das ausdrücklich will.",
     "input_schema": {"type": "object", "properties": {
         "laeufe_pro_tag": {"type": "integer", "description": f"1 bis {LAEUFE_HOECHSTENS}."}},
         "required": ["laeufe_pro_tag"]}}, abo_einstellen)
