"""
Biko-Arbeiter: läuft auf Nikos PC und erledigt Code-Aufgaben von Biko-Chef mit Claude Code und Nikos Claude-Abo.

Ablauf je Aufgabe:
  1. Biko fragen, ob es Arbeit gibt (POST /api/abo/abholen).
  2. Im Repo einen eigenen Arbeitsordner anlegen (git worktree, neuer Zweig biko/<aufgabe>), dein eigener Ordner bleibt
     unberührt.
  3. `claude -p` dort arbeiten lassen: Code ändern, testen, committen. Claude darf nicht pushen und nicht mergen.
  4. Dieses Programm schiebt den Zweig hoch, öffnet mit `gh` einen PR und meldet Biko das Ergebnis.
  5. Mergen nur, wenn Niko in /chef Ja getippt hat (dann kommt ein eigener Merge-Auftrag).

Braucht: Python 3.10+, Git, Claude Code (einmal `claude` starten und mit dem Abo anmelden), GitHub CLI (`gh auth login`).
Nur Python-Standardbibliothek. Start: `python biko_arbeiter.py` (oder start.bat). Einstellungen: einstellungen.json.

Wichtig: ANTHROPIC_API_KEY wird für Claude Code entfernt, sonst würde es über die API abrechnen statt über das Abo.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

VERSION = "1.2"
HIER = Path(__file__).resolve().parent
AGENT = f"Biko-Arbeiter/{VERSION}"

# Was Claude Code ohne Nachfrage darf. Alles andere (pushen, gh, löschen außerhalb) lehnt es im Hintergrund ab.
ERLAUBT = [
    "Read", "Edit", "Write", "Glob", "Grep", "WebSearch", "WebFetch", "TodoWrite",
    "Bash(git status:*)", "Bash(git diff:*)", "Bash(git log:*)", "Bash(git show:*)", "Bash(git add:*)",
    "Bash(git commit:*)", "Bash(git restore:*)", "Bash(git mv:*)", "Bash(git rm:*)",
    "Bash(ls:*)", "Bash(cat:*)", "Bash(head:*)", "Bash(tail:*)", "Bash(wc:*)", "Bash(mkdir:*)",
    "Bash(python:*)", "Bash(python3:*)", "Bash(py:*)", "Bash(pip install:*)", "Bash(pytest:*)",
    "Bash(node:*)", "Bash(npm:*)", "Bash(npx:*)",
]
VERBOTEN = ["Bash(git push:*)", "Bash(git remote:*)", "Bash(git reset --hard:*)", "Bash(gh:*)", "Bash(curl:*)",
            "Bash(rm -rf:*)"]

ANLEITUNG = """Du arbeitest für Biko-Chef, den KI-Geschäftsführer von Niko (Webentwickler in Wien, schreibt Deutsch).
Du bist in einem eigenen Git-Arbeitsordner des Repos {repo} auf dem Zweig {zweig}.

Regeln:
- Erledige genau die Aufgabe unten. Rückfragen gehen nicht: triff vernünftige Annahmen und nenne sie am Ende.
- Halte dich an CLAUDE.md, README und die Gewohnheiten im Repo. Lies erst, dann ändere.
- Lass vorhandene Tests laufen und schreib Tests für Neues, wo es im Repo Tests gibt.
- Committe deine Änderungen mit einer klaren deutschen Commit-Nachricht. Nicht pushen, nicht mergen, keinen PR
  öffnen: das macht Biko danach selbst.
- Keine Passwörter, Schlüssel oder .env-Dateien anfassen oder committen.
- Ganz am Ende schreibst du für Niko auf Deutsch:
  ZUSAMMENFASSUNG: <ein bis zwei Sätze, was jetzt anders ist>
  Danach kurz: was du geändert hast, wie du es getestet hast, und was offen ist.

{auftrag}
"""


# ---------- Einstellungen ----------
def einstellungen():
    datei = Path(os.environ.get("BIKO_EINSTELLUNGEN", HIER / "einstellungen.json"))
    try:
        e = json.loads(datei.read_text(encoding="utf-8"))
    except FileNotFoundError:
        sys.exit(f"Es fehlt {datei}. Kopier einstellungen.beispiel.json dorthin und trag alles ein.")
    except ValueError as f:
        sys.exit(f"{datei} ist kein gültiges JSON: {f}")
    e["url"] = str(os.environ.get("BIKO_URL") or e.get("url") or "").rstrip("/")
    e["token"] = str(os.environ.get("CHEF_ABO_TOKEN") or e.get("token") or "").strip()
    if not e["url"].startswith("https://") and not e["url"].startswith("http://localhost"):
        sys.exit("In einstellungen.json fehlt \"url\" (z. B. https://dein-biko.up.railway.app).")
    if len(e["token"]) < 24:
        sys.exit("In einstellungen.json fehlt \"token\" (derselbe Wert wie CHEF_ABO_TOKEN in Railway).")
    repos = e.get("repos") or {}
    if not isinstance(repos, dict) or not repos:
        sys.exit("In einstellungen.json fehlt \"repos\", z. B. {\"n1kob1ko/Biko-Bot\": \"C:/Users/niko/Projekte/Biko-Bot\"}.")
    e["repos"] = {k: str(Path(v).expanduser()) for k, v in repos.items()}
    e["minuten"] = int(e.get("max_minuten") or 45)
    e["takt"] = max(2, int(e.get("takt_sekunden") or 3))   # kurz, damit der Chef schnell antwortet
    return e


# Wo die Installer unter Windows hinlegen, falls ein Fenster den neuen PATH noch nicht kennt
WINDOWS_ORTE = {
    "claude": [r"%USERPROFILE%\.local\bin\claude.exe"],
    "gh": [r"%ProgramFiles%\GitHub CLI\gh.exe", r"%LOCALAPPDATA%\Programs\GitHub CLI\gh.exe"],
    "git": [r"%ProgramFiles%\Git\cmd\git.exe", r"%LOCALAPPDATA%\Programs\Git\cmd\git.exe"],
}


def programm(name):
    pfad = shutil.which(name)
    if not pfad and os.name == "nt":
        pfad = next((p for p in map(os.path.expandvars, WINDOWS_ORTE.get(name, [])) if os.path.isfile(p)), None)
    if not pfad:
        sys.exit(f"„{name}“ ist nicht installiert oder nicht im PATH. Siehe LIESMICH.md.")
    return pfad


# ---------- Biko ----------
def biko(e, pfad, daten):
    anfrage = urllib.request.Request(
        e["url"] + pfad, data=json.dumps(daten).encode(), method="POST",
        headers={"Authorization": f"Bearer {e['token']}", "Content-Type": "application/json", "User-Agent": AGENT})
    with urllib.request.urlopen(anfrage, timeout=30) as r:
        return json.loads(r.read() or b"{}")


def melden(e, pfad, daten, versuche=5):
    """Ergebnisse dürfen nicht verloren gehen: ein paar Mal versuchen."""
    for i in range(versuche):
        try:
            return biko(e, pfad, daten)
        except (urllib.error.URLError, OSError, ValueError) as f:
            print(f"  Biko nicht erreichbar ({f}), neuer Versuch …", flush=True)
            time.sleep(10 * (i + 1))
    return None


class Lebenszeichen(threading.Thread):
    def __init__(self, e, aid):
        super().__init__(daemon=True)
        self.e, self.aid, self.stopp = e, aid, threading.Event()

    def run(self):
        while not self.stopp.wait(60):
            try:
                biko(self.e, "/api/abo/lebt", {"id": self.aid})
            except (urllib.error.URLError, OSError, ValueError):
                pass


# ---------- Git und Claude ----------
def lauf(befehl, cwd, timeout=600, eingabe=None, env=None):
    # Ohne Eingabe bekommt das Programm eine leere statt der Konsole: nichts soll still auf eine Antwort warten
    r = subprocess.run(befehl, cwd=cwd, input=eingabe if eingabe is not None else "", capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=timeout, env=env)
    return r.returncode, (r.stdout or "").strip(), (r.stderr or "").strip()


def git(cwd, *args, timeout=600):
    code, aus, fehler = lauf([programm("git"), *args], cwd, timeout)
    if code != 0:
        raise RuntimeError(f"git {args[0]}: {fehler or aus}"[:400])
    return aus


def hauptzweig(repo_ordner):
    try:
        return git(repo_ordner, "symbolic-ref", "--short", "refs/remotes/origin/HEAD").split("/", 1)[1]
    except RuntimeError:
        return "main"


def claude_env():
    env = dict(os.environ)
    for k in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "CLAUDE_CODE_USE_BEDROCK", "CLAUDE_CODE_USE_VERTEX"):
        env.pop(k, None)   # sonst rechnet Claude Code über die API ab statt über das Abo
    return env


GRENZE = re.compile(r"(usage|rate|session|weekly)[ -]?limit|limit (reached|resets)|out of (extra )?usage", re.I)


def pause_minuten(text):
    """Aus „… resets 3pm“ oder „resets in 2 hours“ grob die Minuten bis zur Freigabe, sonst None."""
    m = re.search(r"in (\d+) ?(hours?|h|minutes?|min)", text, re.I)
    if m:
        n = int(m.group(1))
        return n * 60 if m.group(2).lower().startswith("h") else n
    return None


def claude_arbeiten(e, ordner, eingabe):
    befehl = [programm("claude"), "-p", "--output-format", "json", "--permission-mode", "acceptEdits",
              "--max-turns", str(int(e.get("max_runden") or 80)),
              "--allowedTools", *ERLAUBT, "--disallowedTools", *VERBOTEN]
    if e.get("modell"):
        befehl += ["--model", str(e["modell"])]
    code, aus, fehler = lauf(befehl, ordner, e["minuten"] * 60, eingabe=eingabe, env=claude_env())
    j = {}
    for stueck in (aus, aus.splitlines()[-1] if aus else ""):
        try:
            j = json.loads(stueck)
            break
        except ValueError:
            continue
    j = j if isinstance(j, dict) else {}
    text = str(j.get("result") or aus or fehler)
    return code, j, text


def zusammenfassung(text):
    m = re.search(r"ZUSAMMENFASSUNG:\s*(.+)", text)
    return (m.group(1).strip() if m else text.strip().split("\n")[0])[:400]


def code_aufgabe(e, job):
    repo, aid, zweig = job["repo"], job["id"], job["zweig"]
    ordner = e["repos"].get(repo) or next((v for k, v in e["repos"].items() if k.lower() == str(repo).lower()), None)
    if not ordner:
        return {"id": aid, "ok": False, "fehler": f"Das Repo {repo} ist auf dem PC nicht eingerichtet."}
    if not Path(ordner).is_dir():   # beim ersten Mal selbst klonen (mit der Anmeldung von gh)
        print(f"  Klone {repo} nach {ordner} …", flush=True)
        code, aus, fehler = lauf([programm("gh"), "repo", "clone", repo, ordner], str(HIER), 900)
        if code != 0:
            return {"id": aid, "ok": False, "fehler": f"Klonen von {repo} ging nicht: {(fehler or aus)[:250]}"}
    if not re.fullmatch(r"biko/[a-z0-9-]{1,40}", zweig):
        return {"id": aid, "ok": False, "fehler": "Ungültiger Zweigname."}
    arbeit = Path(ordner).parent / ".biko-arbeit" / zweig.replace("/", "-")
    leben = Lebenszeichen(e, aid)
    leben.start()
    try:
        git(ordner, "fetch", "origin", "--prune")
        basis = hauptzweig(ordner)
        if arbeit.exists():
            lauf([programm("git"), "worktree", "remove", "--force", str(arbeit)], ordner)
        arbeit.parent.mkdir(parents=True, exist_ok=True)
        git(ordner, "worktree", "add", "-B", zweig, str(arbeit), f"origin/{basis}")
        print(f"  Claude Code arbeitet in {arbeit} …", flush=True)
        start = time.time()
        code, j, text = claude_arbeiten(e, str(arbeit), ANLEITUNG.format(repo=repo, zweig=zweig, auftrag=job["auftrag"]))
        minuten = round((time.time() - start) / 60, 1)
        if GRENZE.search(text) and (code != 0 or j.get("is_error")):
            return {"id": aid, "grenze": True, "pause_minuten": pause_minuten(text)}
        if code != 0 and not j:
            return {"id": aid, "ok": False, "fehler": f"Claude Code ist abgebrochen: {text[:300]}"}
        if git(arbeit, "status", "--porcelain"):   # vergessen zu committen
            git(arbeit, "add", "-A")
            git(arbeit, "commit", "-m", f"Biko-Chef: {job['titel']}")
        neu = int(git(arbeit, "rev-list", "--count", f"origin/{basis}..HEAD") or 0)
        ergebnis = f"{text}\n\n(Claude Code auf Nikos PC, {minuten} Minuten, {j.get('num_turns', '?')} Schritte.)"
        if not neu:
            return {"id": aid, "ok": True, "zusammenfassung": zusammenfassung(text), "ergebnis": ergebnis, "pr": ""}
        git(arbeit, "push", "-u", "--force-with-lease", "origin", zweig, timeout=300)
        koerper = (f"Von Biko-Chef beauftragt, von Claude Code auf Nikos PC erledigt.\n\n**Aufgabe:** {job['titel']}\n\n"
                   f"{text[:60000]}\n\n---\n_Gemergt wird erst nach Nikos Freigabe in /chef._")
        code, aus, fehler = lauf([programm("gh"), "pr", "create", "--repo", repo, "--head", zweig, "--base", basis,
                                  "--title", f"Biko-Chef: {job['titel']}"[:120], "--body-file", "-"],
                                 arbeit, 120, eingabe=koerper)
        pr = re.search(r"https://github\.com/\S+/pull/\d+", aus + "\n" + fehler)
        if not pr:
            return {"id": aid, "ok": False, "fehler": f"Zweig {zweig} ist hochgeladen, aber der PR ging nicht: "
                                                     f"{(fehler or aus)[:250]}"}
        return {"id": aid, "ok": True, "zusammenfassung": zusammenfassung(text), "ergebnis": ergebnis, "pr": pr.group(0)}
    except subprocess.TimeoutExpired:
        return {"id": aid, "ok": False, "fehler": f"Nach {e['minuten']} Minuten abgebrochen."}
    except (RuntimeError, OSError, ValueError) as f:
        return {"id": aid, "ok": False, "fehler": str(f)[:400]}
    finally:
        leben.stopp.set()
        if arbeit.exists():
            lauf([programm("git"), "worktree", "remove", "--force", str(arbeit)], ordner)


TEXT_GLEICHZEITIG = 2


def strukturiert(job, werkzeuge, max_runden, sekunden, ordner=None):
    """`claude -p` mit Anleitung, Eingabe und JSON-Schema; liefert (antwort, session, fehler, grenze).
    Ohne `ordner` in einem leeren Ordner auf Zeit: Claude sieht keine Dateien von dir."""
    fd, datei = tempfile.mkstemp(suffix=".txt", prefix="biko-")
    weg_damit = ordner is None
    ordner = ordner or tempfile.mkdtemp(prefix="biko-arbeit-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(str(job.get("system") or ""))
        befehl = [programm("claude"), "-p", "--output-format", "json", "--tools", *(werkzeuge or [""]),
                  "--max-turns", str(max_runden), "--system-prompt-file", datei,
                  "--json-schema", json.dumps(job.get("schema") or {}), "--model", str(job.get("modell") or "opus")]
        if werkzeuge:
            befehl += ["--allowedTools", *werkzeuge]
        if job.get("resume"):
            befehl += ["--resume", str(job["resume"])]
        code, aus, fehler = lauf(befehl, ordner, sekunden, eingabe=str(job.get("eingabe") or ""), env=claude_env())
    except subprocess.TimeoutExpired:
        return None, None, "Zeit abgelaufen", False
    finally:
        try:
            os.remove(datei)
        except OSError:
            pass
        if weg_damit:
            shutil.rmtree(ordner, ignore_errors=True)
    j = {}
    try:
        j = json.loads(aus)
    except ValueError:
        pass
    j = j if isinstance(j, dict) else {}
    text = str(j.get("result") or aus or fehler)
    if GRENZE.search(text) and (code != 0 or j.get("is_error")):
        return None, None, text[:300], True
    antwort = j.get("structured_output")
    if not isinstance(antwort, dict):
        try:
            antwort = json.loads(j.get("result") or "")
        except (TypeError, ValueError):
            antwort = None
    if not isinstance(antwort, dict):
        return None, j.get("session_id"), text[:300], False
    return antwort, j.get("session_id"), "", False


def text_aufgabe(e, job):
    """Recherche, Texte, Webseiten, Prüfen: nur Websuche als Werkzeug, Ergebnis als JSON."""
    leben = Lebenszeichen(e, job["id"])
    leben.start()
    try:
        antwort, _, fehler, grenze = strukturiert(job, ["WebSearch", "WebFetch"] if job.get("web") else [], 40,
                                                  int(e.get("text_minuten") or 20) * 60)
    finally:
        leben.stopp.set()
    if grenze:
        return {"id": job["id"], "grenze": True}
    if antwort is None:
        return {"id": job["id"], "ok": False, "fehler": fehler}
    return {"id": job["id"], "ok": True, "antwort": antwort}


def chef_antworten(job):
    """Eine Antwort des Chefs (Biko-Chef im Gespräch mit Niko), ohne Werkzeuge von Claude Code: Biko führt die
    Werkzeuge selbst aus, die in der JSON-Antwort stehen."""
    ordner = HIER / ".chef"   # immer derselbe Ordner, sonst findet --resume die Sitzung nicht
    ordner.mkdir(exist_ok=True)
    antwort, session, fehler, grenze = strukturiert(job, [], 4, 170, str(ordner))
    if grenze:
        return {"id": job["id"], "grenze": True}
    if antwort is None:
        return {"id": job["id"], "ok": False, "fehler": fehler}
    return {"id": job["id"], "ok": True, "antwort": antwort, "session": session}


def mergen(job):
    pr = str(job.get("pr") or "")
    if not re.fullmatch(r"https://github\.com/[\w.-]+/[\w.-]+/pull/\d+", pr):
        return {"id": job["id"], "ok": False, "fehler": "Ungültiger PR-Link."}
    code, aus, fehler = lauf([programm("gh"), "pr", "merge", pr, "--squash", "--delete-branch"], str(HIER), 180)
    return {"id": job["id"], "ok": code == 0, "fehler": (fehler or aus)[:300]}


# ---------- Hauptschleife ----------
def main():
    e = einstellungen()
    for p in ("git", "claude", "gh"):
        programm(p)
    if os.environ.get("ANTHROPIC_API_KEY"):
        print("Hinweis: ANTHROPIC_API_KEY ist gesetzt. Für Claude Code nehme ich ihn weg, damit dein Abo zählt.")
    print(f"Biko-Arbeiter {VERSION} läuft. Repos: {', '.join(e['repos'])}. Beenden mit Strg+C.", flush=True)
    fehler_gemeldet = False
    # Chef-Antworten, eine Code-Aufgabe und bis zu TEXT_GLEICHZEITIG andere Aufgaben laufen nebeneinander
    faeden = {"chef": [], "code": [], "text": []}
    grenze = {"chef": 1, "code": 1, "text": int(e.get("gleichzeitig") or TEXT_GLEICHZEITIG)}

    def frei(art):
        faeden[art] = [f for f in faeden[art] if f.is_alive()]
        return len(faeden[art]) < grenze[art]

    while True:
        try:
            job = biko(e, "/api/abo/abholen", {"repos": list(e["repos"]), "version": VERSION,
                                               "chef_frei": frei("chef"), "code_frei": frei("code"),
                                               "text_frei": frei("text")}).get("auftrag")
            fehler_gemeldet = False
        except urllib.error.HTTPError as f:
            if f.code == 401:
                sys.exit("Biko sagt: falscher Schlüssel. Prüf \"token\" in einstellungen.json und CHEF_ABO_TOKEN in Railway.")
            job = None
            if not fehler_gemeldet:
                print(f"Biko antwortet mit Fehler {f.code}, ich versuche es weiter.", flush=True)
                fehler_gemeldet = True
        except (urllib.error.URLError, OSError, ValueError) as f:
            job = None
            if not fehler_gemeldet:
                print(f"Biko nicht erreichbar ({f}), ich versuche es weiter.", flush=True)
                fehler_gemeldet = True
        if not job:
            time.sleep(e["takt"])
            continue
        art = job.get("art") if job.get("art") in ("chef", "text") else "code"
        f = threading.Thread(target=erledigen, args=(e, job), daemon=True)
        faeden[art].append(f)
        f.start()


def erledigen(e, job):
    if job.get("art") == "chef":
        start = time.time()
        ergebnis = chef_antworten(job)
        print(f"Chef hat geantwortet ({time.time() - start:.0f} s)" if ergebnis.get("ok") else
              f"Chef-Antwort ging nicht: {ergebnis.get('fehler', 'Abo-Grenze')}", flush=True)
        melden(e, "/api/abo/chef", ergebnis)
        return
    if job.get("art") == "text":
        start = time.time()
        print(f"Aufgabe: {job.get('titel')}", flush=True)
        ergebnis = text_aufgabe(e, job)
        print(f"  fertig ({time.time() - start:.0f} s)" if ergebnis.get("ok") else
              f"  ging nicht: {ergebnis.get('fehler', 'Abo-Grenze')}", flush=True)
        melden(e, "/api/abo/text", ergebnis)
        return
    if job.get("art") == "mergen":
        print(f"Mergen: {job.get('pr')}", flush=True)
        melden(e, "/api/abo/gemergt", mergen(job))
        return
    print(f"Aufgabe: {job.get('titel')} ({job.get('repo')})", flush=True)
    ergebnis = code_aufgabe(e, job)
    print("  " + ("Abo-Grenze erreicht, Pause." if ergebnis.get("grenze") else
                  f"PR: {ergebnis['pr']}" if ergebnis.get("pr") else
                  "Fertig, ohne Änderung am Code." if ergebnis.get("ok") else f"Fehler: {ergebnis.get('fehler')}"),
          flush=True)
    melden(e, "/api/abo/fertig", ergebnis)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nBiko-Arbeiter beendet.")
