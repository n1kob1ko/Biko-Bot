"""
Biko-Chef: ein KI-Geschäftsführer für Niko. Er steuert Claude für ihn.

So hängt es zusammen:
  Niko      redet auf /chef mit dem Chef ("Bau mir eine Landingpage für meine Nachhilfe").
  Chef      Claude Opus 5.5 mit Werkzeugen: legt ein Projekt mit Ziel, Budget und Aufgaben an, liest Ergebnisse,
            schickt Aufgaben zurück, fragt Niko um Freigabe.
  Arbeiter  Für jede Aufgabe läuft eine eigene Claude-Sitzung mit einer Rolle (Recherche, Texter, Entwickler,
            Prüfer). Sie suchen im Internet, lesen Seiten und geben ihr Ergebnis mit dem Werkzeug `abgeben` ab.
            Bis zu MAX_GLEICHZEITIG laufen zur selben Zeit.
  Prüfer    Nach jeder Aufgabe schaut ein Prüfer das Ergebnis an. Ist es nicht gut, geht es mit seiner
            Begründung zurück an den Arbeiter, höchstens MAX_VERSUCHE Mal.
  Takt      Ein Faden schaut alle paar Sekunden, was fertig ist und was als Nächstes kommt (ohne KI, kostet nichts),
            und schreibt um 19 Uhr den Tagesbericht.

Sicherheit:
  - Harte Kostengrenzen pro Tag (alle Projekte zusammen) und pro Projekt. Vor jeder Anfrage an Claude wird geprüft;
    ist eine Grenze erreicht, startet nichts mehr und der Chef fragt Niko.
  - Veröffentlichen, Geld ausgeben, Kunden anschreiben: dafür gibt es in dieser Version kein Werkzeug.
    Der Chef kann nur um Freigabe fragen.
  - Jeder Schritt steht mit Zeit und Kosten im Protokoll. Nie API-Schlüssel oder Passwörter darin.

Daten: <DATA_DIR>/chef/zustand.json und <DATA_DIR>/chef/vorschau/<aufgabe>.html (Webseiten vom Entwickler).
"""

import json
import os
import re
import secrets
import tempfile
import threading
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import anthropic

ORDNER = Path(os.environ.get("DATA_DIR", "/data")) / "chef"
ZEITZONE = ZoneInfo(os.environ.get("TZ", "Europe/Vienna"))
CHEF_MODELL = os.environ.get("CHEF_MODELL", "claude-opus-5-5")

TAG_STANDARD = 3.0          # US-Dollar pro Tag für alle Projekte zusammen
TAG_HOECHSTENS = 20.0       # höher lässt sich die Tagesgrenze auch im Gespräch nicht stellen
PROJEKT_STANDARD = 1.0      # US-Dollar pro Projekt, wenn der Chef nichts anderes sagt
PROJEKT_HOECHSTENS = 10.0
MINDESTENS_FREI = 0.05      # so viel muss noch frei sein, damit ein Arbeiter startet
GESPRAECH_RESERVE = 0.50    # so viel darf das Gespräch mit dem Chef über die Tagesgrenze hinaus kosten
MAX_GLEICHZEITIG = 3        # Standard: so viele Arbeiter laufen zur selben Zeit
GLEICHZEITIG_HOECHSTENS = 5
MAX_VERSUCHE = 3            # erster Versuch plus zweimal zurück vom Prüfer
MAX_AUFGABEN = 12           # pro Projekt
MAX_PROJEKTE = 30
MAX_GESPRAECH = 300         # so viele Einträge bleiben im Chef-Gespräch gespeichert
MAX_VERLAUF = 40            # so viele davon liest der Chef bei jeder Antwort mit
MAX_PROTOKOLL = 500
MAX_TEXT = 4000
BERICHT_UM = 19             # Uhr: Tagesbericht
TAKT_SEKUNDEN = 5

PREISE = {   # US-Dollar pro Million Tokens: Eingabe, Ausgabe, aus dem Zwischenspeicher, in den Zwischenspeicher
    "claude-opus-5-5": (4.00, 20.00, 0.20, 5.00),
    "claude-sonnet-5-5": (2.00, 10.00, 0.10, 2.50),
    "claude-haiku-5-5": (0.10, 0.50, 0.01, 0.125),
}
PREIS_SUCHE = 0.01

WEBSUCHE = [
    {"type": "web_search_20260209", "name": "web_search", "max_uses": 8,
     "user_location": {"type": "approximate", "city": "Wien", "country": "AT", "timezone": "Europe/Vienna"}},
    {"type": "web_fetch_20260209", "name": "web_fetch", "max_uses": 6},
]

ROLLEN = {
    "recherche": {
        "name": "Recherche", "modell": "claude-sonnet-5-5", "web": True, "max_tokens": 16000,
        "auftrag": "Du recherchierst gründlich im Internet: suchen, die wichtigsten Seiten öffnen, Fakten mit Quelle "
                   "(Link) festhalten. Lieber 5 belegte Punkte als 20 vage. Schreib, was du nicht herausfinden konntest.",
    },
    "texter": {
        "name": "Texter", "modell": "claude-sonnet-5-5", "web": True, "max_tokens": 16000,
        "auftrag": "Du schreibst fertige Texte: klar, konkret, ohne Floskeln, in der Sprache des Projekts. Liefere den "
                   "Text so, dass man ihn direkt übernehmen kann, mit Überschriften wo es passt.",
    },
    "entwickler": {
        "name": "Entwickler", "modell": "claude-opus-5-5", "web": False, "max_tokens": 32000,
        "auftrag": "Du baust Webseiten. Liefere im Feld `html` eine vollständige, eigenständige HTML-Datei: modern, "
                   "schnell, zuerst fürs Handy gebaut, gut lesbar (Kontrast mindestens 4,5 zu 1), alles CSS inline, "
                   "kein JavaScript von fremden Servern, keine erfundenen Fakten (Platzhalter in eckigen Klammern, wo "
                   "etwas fehlt). Ein Formular schickt nirgendwohin, es zeigt nur, wie es aussehen wird. "
                   "Im Feld `ergebnis` beschreibst du kurz, was die Seite enthält.",
    },
    "programmierer": {   # läuft nicht hier, sondern auf Nikos PC mit Claude Code und seinem Abo (abo.py)
        "name": "Programmierer", "abo": True,
        "auftrag": "Claude Code auf Nikos PC, mit seinem Abo: ändert Code in einem Repo, testet und öffnet einen PR.",
    },
    "pruefer": {
        "name": "Prüfer", "modell": "claude-opus-5-5", "web": True, "max_tokens": 16000,
        "auftrag": "Du prüfst die bisherigen Ergebnisse des Projekts kritisch gegen das Ziel: Was fehlt, was ist falsch, "
                   "was muss besser werden? Gib eine klare Liste mit dem Wichtigsten zuerst.",
    },
}

ARBEITER_SYSTEM = """Du bist {rolle} im Team von Biko-Chef, dem KI-Geschäftsführer von Niko.
Niko ist Einzelunternehmer und Webentwickler in Wien. Er schreibt Deutsch.

{auftrag}

Regeln:
- Du arbeitest allein an genau einer Aufgabe. Rückfragen gehen nicht: triff vernünftige Annahmen und nenne sie.
- Du veröffentlichst nichts, gibst kein Geld aus und schreibst niemanden an. Das entscheidet Niko selbst.
- Erfinde keine Fakten, Preise, Bewertungen oder Kundenstimmen.
- Wenn du fertig bist, rufst du genau einmal das Werkzeug `abgeben` auf. Das ist dein Ergebnis."""

PRUEFER_SYSTEM = """Du bist Prüfer im Team von Biko-Chef. Du bekommst das Ziel eines Projekts, eine Aufgabe und das
Ergebnis eines Arbeiters. Prüf streng, aber fair: Erfüllt es die Aufgabe so, dass Niko damit weiterarbeiten kann?
Kleinigkeiten sind kein Grund zum Zurückschicken. Erfundene Fakten, fehlende Teile der Aufgabe oder eine kaputte
Webseite schon. Antworte nur mit dem Werkzeug `urteil`."""

CHEF_SYSTEM = """Du bist Biko-Chef, der KI-Geschäftsführer von Niko: ein niedlicher, dicker gelber Vogel im Anzug.
Niko ist Einzelunternehmer und Webentwickler in Wien und schreibt Deutsch. Du steuerst für ihn ein Team aus
Claude-Arbeitern.

So arbeitest du:
- Will Niko etwas erledigt haben, legst du mit `projekt_anlegen` ein Projekt an: klares Ziel, ein Budget in US-Dollar
  und 2 bis 6 Aufgaben. Jede Aufgabe hat eine Rolle (recherche, texter, entwickler, pruefer) und einen Auftrag, der
  für sich allein verständlich ist, denn der Arbeiter sieht nur das Ziel, seinen Auftrag und die Ergebnisse davor.
- Aufgaben laufen der Reihe nach. Hängt eine Aufgabe nicht von der vorherigen ab (zwei getrennte Recherchen), setz
  `gleichzeitig` auf true, dann läuft sie parallel zur vorherigen.
- Ist ein Ziel unklar, frag einmal kurz nach, bevor du ein Projekt anlegst. Bei einfachen Zielen fang einfach an.
- Nach jeder Aufgabe prüft ein Prüfer das Ergebnis von selbst. Du kannst Ergebnisse mit `ergebnis_lesen` ansehen und
  mit `aufgabe_wiederholen` und einem Hinweis zurückschicken.
- Veröffentlichen, Geld ausgeben, Verträge, Kunden oder andere Menschen anschreiben: Das kannst du nicht selbst. Frag
  Niko mit `freigabe_anfragen` und sag ihm, was er dann selbst tun muss. Echtes Trading mit Geld macht ihr nie ohne
  seine ausdrückliche Freigabe und ein hartes Limit.
- Code in Nikos Repos ändern (Biko-Bot, DreamStudy …): Dafür gibt es die Rolle `programmierer`. Die Aufgabe läuft mit
  Claude Code auf Nikos eigenem PC und seinem Claude-Abo, kostet also kein API-Geld, zählt aber gegen seine Abo-Grenzen.
  Gib immer `repo` an (welche es gibt, steht im <stand>). Der Auftrag beschreibt das Ziel, nicht jede Zeile. Am Ende gibt
  es einen PR, und Niko wird gefragt, ob er gemergt wird. Ist der PC nicht verbunden, wartet die Aufgabe, bis er wieder
  da ist; sag Niko das. Nutze das Abo nur für Nikos eigene Arbeit, nie für Kunden (das erlaubt Anthropic nicht).
- Kosten: Es gibt eine Tagesgrenze und ein Budget pro Projekt. Halte Projekte klein. Typisch: Recherche 0,10 bis
  0,40 $, Text 0,05 bis 0,20 $, Webseite 0,30 bis 1 $.

Wie du schreibst: kurz, freundlich, auf Deutsch, ganze Sätze. Erst das Ergebnis oder die Frage, dann Details.
Keine Tabellen. Wenn du ein Projekt angelegt hast, sag in einem Satz, was jetzt passiert.

DreamStudy (Nikos Nachhilfe-App): Du holst dort von selbst alle paar Minuten Aufträge ab und erledigst sie ohne Projekt,
jeden Morgen ein Tagesbriefing je Lehrkraft und Lernzettel aus Dokumenten, die eine Lehrkraft dir gibt (dreamstudy.py).
Namen bekommst du nie, Schüler heißen S1, S2. Mit `dreamstudy_stand` siehst du, was zuletzt lief, mit `dreamstudy_jetzt`
holst du sofort ab. Will Niko einen Lernzettel, sagst du ihm: In DreamStudy das Dokument unter Erweitert › Material öffnen
und „An Biko geben“ tippen. Auf die Daten in DreamStudy hast du sonst keinen Zugriff.

Im Feld <stand> vor Nikos Nachricht steht der aktuelle Stand aller Projekte. <meldung> sind Nachrichten vom Takt
(fertige Aufgaben, Grenzen) und von Nikos Freigaben."""

_lock = threading.RLock()
_client = None
_laufend = {}            # aufgabe-id -> Faden
_takt_an = False


# ---------- Speichern ----------
def jetzt():
    return datetime.now(ZEITZONE)


def heute():
    return jetzt().strftime("%Y-%m-%d")


def _datei():
    ORDNER.mkdir(parents=True, exist_ok=True)
    return ORDNER / "zustand.json"


LEER = {"grenzen": {"tag": TAG_STANDARD, "gleichzeitig": MAX_GLEICHZEITIG}, "projekte": [], "gespraech": [],
        "kosten": {}, "protokoll": [], "bericht_tag": "", "gemeldet": {}}


def laden():
    try:
        with open(_datei(), encoding="utf-8") as f:
            z = json.load(f)
    except (OSError, ValueError):
        z = {}
    leer = json.loads(json.dumps(LEER))
    return {**leer, **z, "grenzen": {**leer["grenzen"], **z.get("grenzen", {})}}


def speichern(z):
    ziel = _datei()
    fd, tmp = tempfile.mkstemp(dir=ziel.parent, suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(z, f, ensure_ascii=False, indent=1)
    os.replace(tmp, ziel)


def protokoll_zeile(z, text, projekt=None, dollar=0.0):
    z["protokoll"].append({"zeit": jetzt().isoformat(timespec="seconds"), "text": text[:300],
                           "projekt": projekt, "dollar": round(dollar, 4)})
    z["protokoll"] = z["protokoll"][-MAX_PROTOKOLL:]
    print(f"Chef: {text[:200]}", flush=True)


def eintrag(z, wer, text, **mehr):
    z["gespraech"].append({"wer": wer, "text": text[:20000], "zeit": jetzt().isoformat(timespec="seconds"), **mehr})
    z["gespraech"] = z["gespraech"][-MAX_GESPRAECH:]


def geld(x):
    """0.2 -> '0,20 $' (so wie Niko Zahlen liest)."""
    return f"{x:.2f}".replace(".", ",") + " $"


def neue_id(praefix):
    return praefix + secrets.token_hex(3)


def projekt_finden(z, pid):
    pid = str(pid or "").strip()
    for p in z["projekte"]:
        if p["id"] == pid or p["name"].lower() == pid.lower():
            return p
    raise ValueError("Dieses Projekt gibt es nicht. Die Nummern stehen im <stand>.")


def aufgabe_finden(z, aid):
    for p in z["projekte"]:
        for a in p["aufgaben"]:
            if a["id"] == str(aid or "").strip():
                return p, a
    raise ValueError("Diese Aufgabe gibt es nicht. Die Nummern stehen im <stand>.")


def heute_ausgegeben(z):
    return z["kosten"].get(heute(), 0.0)


def kosten_buchen(z, dollar, projekt=None):
    tag = heute()
    z["kosten"][tag] = round(z["kosten"].get(tag, 0.0) + dollar, 6)
    z["kosten"] = {k: z["kosten"][k] for k in sorted(z["kosten"])[-62:]}
    if projekt:
        projekt["ausgegeben"] = round(projekt.get("ausgegeben", 0.0) + dollar, 6)


class GrenzeErreicht(Exception):
    pass


def grenze_pruefen(z, projekt=None, reserve=0.0):
    """Wirft GrenzeErreicht, wenn heute oder im Projekt kein Geld mehr frei ist. `reserve`: so viel darf über die
    Tagesgrenze hinaus (nur das Gespräch mit dem Chef, damit Niko die Grenze auch dann noch ändern kann)."""
    if heute_ausgegeben(z) >= z["grenzen"]["tag"] + reserve:
        raise GrenzeErreicht("tag")
    if projekt and projekt.get("ausgegeben", 0.0) >= projekt["budget"]:
        raise GrenzeErreicht("projekt")


# ---------- Claude ----------
def client():
    global _client
    if _client is None:
        _client = anthropic.Anthropic()
    return _client


def claude_anfrage(**kw):
    """Der eine Aufruf der Claude-API (gestreamt, damit lange Antworten nicht abbrechen). Tests ersetzen ihn."""
    with client().beta.messages.stream(**kw) as strom:
        return strom.get_final_message()


def preis(r, modell):
    u = getattr(r, "usage", None)
    if u is None:
        return 0.0
    zahl = lambda x: x if isinstance(x, (int, float)) else 0
    m = getattr(r, "model", None)
    p = PREISE.get(m if isinstance(m, str) else modell) or PREISE.get(modell) or PREISE["claude-opus-5-5"]
    suchen = zahl(getattr(getattr(u, "server_tool_use", None), "web_search_requests", 0))
    return (zahl(getattr(u, "input_tokens", 0)) * p[0] + zahl(getattr(u, "output_tokens", 0)) * p[1]
            + zahl(getattr(u, "cache_read_input_tokens", 0)) * p[2]
            + zahl(getattr(u, "cache_creation_input_tokens", 0)) * p[3]) / 1e6 + suchen * PREIS_SUCHE


def schleife(system, messages, werkzeuge, modell, web=False, effort="medium", max_tokens=16000, projekt_id=None,
             max_runden=10, reserve=0.0):
    """Fragt Claude, führt Werkzeuge aus, bis Claude fertig ist. Bucht nach jeder Anfrage die Kosten und prüft vor
    jeder Anfrage die Grenzen. `werkzeuge`: {name: (schema, funktion(eingabe) -> text)}. Liefert (text, dollar)."""
    tools = (WEBSUCHE if web else []) + [s for s, _ in werkzeuge.values()]
    messages = list(messages)
    summe = 0.0
    r = None
    for _ in range(max_runden):
        with _lock:
            z = laden()
            grenze_pruefen(z, projekt_finden(z, projekt_id) if projekt_id else None, reserve)
        r = claude_anfrage(
            model=modell, max_tokens=max_tokens,
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            cache_control={"type": "ephemeral"},
            messages=messages, output_config={"effort": effort},
            betas=["server-side-fallback-2026-07-01"], fallbacks="default",
            **({"tools": tools} if tools else {}),
        )
        dollar = preis(r, modell)
        summe += dollar
        with _lock:
            z = laden()
            p = None
            if projekt_id:
                try:
                    p = projekt_finden(z, projekt_id)
                except ValueError:
                    pass
            kosten_buchen(z, dollar, p)
            speichern(z)
        if r.stop_reason == "pause_turn":
            messages.append({"role": "assistant", "content": r.content})
        elif r.stop_reason == "tool_use":
            ergebnisse = []
            for b in r.content:
                if b.type != "tool_use":
                    continue
                try:
                    if b.name not in werkzeuge:
                        raise ValueError("Dieses Werkzeug gibt es nicht.")
                    inhalt = werkzeuge[b.name][1](b.input if isinstance(b.input, dict) else {})
                    ergebnisse.append({"type": "tool_result", "tool_use_id": b.id, "content": str(inhalt)})
                except ValueError as e:
                    ergebnisse.append({"type": "tool_result", "tool_use_id": b.id, "content": f"Fehler: {e}",
                                       "is_error": True})
            messages += [{"role": "assistant", "content": r.content}, {"role": "user", "content": ergebnisse}]
        else:
            break
    if r is not None and r.stop_reason == "refusal":
        return "Dabei kann ich nicht helfen.", summe
    text = "".join(b.text for b in (r.content if r else []) if b.type == "text").strip()
    return text, summe


# ---------- Arbeiter ----------
def _kurz(text, n):
    text = str(text or "")
    return text if len(text) <= n else text[:n] + " […gekürzt]"


def arbeiter_eingabe(p, a):
    teile = [f"<projekt>\nName: {p['name']}\nZiel: {p['ziel']}\n</projekt>"]
    fertig = [b for b in p["aufgaben"] if b["status"] == "fertig" and b["id"] != a["id"]]
    for b in fertig[-5:]:
        laenge = 14000 if a["rolle"] in ("entwickler", "pruefer") else 5000
        teile.append(f"<ergebnis aufgabe=\"{b['titel']}\" rolle=\"{b['rolle']}\">\nKurz: {b.get('zusammenfassung', '')}\n\n"
                     f"{_kurz(b.get('ergebnis'), laenge)}\n"
                     + (f"(Dazu gibt es eine Webseite mit {len(vorschau_lesen(b['id']) or '')} Zeichen HTML.)\n"
                        if b.get("vorschau") else "") + "</ergebnis>")
    if a["rolle"] == "pruefer":
        for b in fertig[-2:]:
            html = vorschau_lesen(b["id"]) if b.get("vorschau") else None
            if html:
                teile.append(f"<webseite aufgabe=\"{b['titel']}\">\n{_kurz(html, 40000)}\n</webseite>")
    teile.append(f"<deine_aufgabe titel=\"{a['titel']}\">\n{a['auftrag']}\n</deine_aufgabe>")
    if a.get("hinweis"):
        teile.append(f"<letzter_versuch>\n{_kurz(a.get('ergebnis'), 8000)}\n</letzter_versuch>\n"
                     f"<das_muss_besser_werden>\n{a['hinweis']}\n</das_muss_besser_werden>")
    return "\n\n".join(teile)


def abgeben_schema(rolle):
    eigenschaften = {
        "zusammenfassung": {"type": "string", "description": "Ein bis zwei Sätze für Niko: was herausgekommen ist."},
        "ergebnis": {"type": "string", "description": "Das ganze Ergebnis in Markdown, mit Links zu Quellen."},
    }
    pflicht = ["zusammenfassung", "ergebnis"]
    if rolle == "entwickler":
        eigenschaften["html"] = {"type": "string", "description": "Die vollständige HTML-Datei der Webseite."}
        pflicht.append("html")
    return {"name": "abgeben", "description": "Gibt dein fertiges Ergebnis ab. Genau einmal am Ende aufrufen.",
            "input_schema": {"type": "object", "properties": eigenschaften, "required": pflicht}}


def vorschau_datei(aid):
    if not re.fullmatch(r"a[0-9a-f]{6}", str(aid)):
        raise ValueError("Gibt es nicht.")
    o = ORDNER / "vorschau"
    o.mkdir(parents=True, exist_ok=True)
    return o / f"{aid}.html"


def vorschau_lesen(aid):
    try:
        return vorschau_datei(aid).read_text(encoding="utf-8")
    except (OSError, ValueError):
        return None


def pruefen(p, a, abgabe):
    """Der Prüfer: (gut, begründung, dollar)."""
    urteil = {}

    def urteilen(e):
        urteil.update(gut=e.get("gut") is True, begruendung=str(e.get("begruendung") or "")[:2000])
        return "Danke, Urteil gespeichert."

    schema = {"name": "urteil", "description": "Dein Urteil über das Ergebnis.",
              "input_schema": {"type": "object", "properties": {
                  "gut": {"type": "boolean", "description": "true, wenn Niko damit weiterarbeiten kann."},
                  "begruendung": {"type": "string", "description": "Kurz: was gut ist, und bei false genau, "
                                                                     "was der Arbeiter ändern muss."}},
                  "required": ["gut", "begruendung"]}}
    inhalt = (f"<projekt>\nZiel: {p['ziel']}\n</projekt>\n\n<aufgabe titel=\"{a['titel']}\" rolle=\"{a['rolle']}\">\n"
              f"{a['auftrag']}\n</aufgabe>\n\n<ergebnis>\n{_kurz(abgabe.get('ergebnis'), 20000)}\n</ergebnis>")
    if abgabe.get("html"):
        inhalt += f"\n\n<webseite>\n{_kurz(abgabe['html'], 40000)}\n</webseite>"
    _, dollar = schleife(PRUEFER_SYSTEM, [{"role": "user", "content": inhalt}], {"urteil": (schema, urteilen)},
                         ROLLEN["pruefer"]["modell"], effort="low", max_tokens=8000, projekt_id=p["id"], max_runden=3)
    if not urteil:
        return True, "Der Prüfer hat kein Urteil abgegeben.", dollar
    return urteil["gut"], urteil["begruendung"], dollar


def arbeiter(aid):
    """Erledigt eine Aufgabe in einem eigenen Faden: Arbeiter, dann Prüfer, bei Bedarf noch einmal."""
    try:
        while True:
            with _lock:
                z = laden()
                p, a = aufgabe_finden(z, aid)
                rolle = ROLLEN[a["rolle"]]
                eingabe = arbeiter_eingabe(p, a)
                pid, versuch = p["id"], a["versuche"] + 1
            abgabe = {}

            def abgeben(e):
                abgabe.update({k: str(v) for k, v in e.items() if k in ("zusammenfassung", "ergebnis", "html")})
                return "Danke, abgegeben. Du bist fertig."

            system = ARBEITER_SYSTEM.format(rolle=rolle["name"], auftrag=rolle["auftrag"])
            text, dollar = schleife(system, [{"role": "user", "content": eingabe}],
                                    {"abgeben": (abgeben_schema(a["rolle"]), abgeben)}, rolle["modell"],
                                    web=rolle["web"], max_tokens=rolle["max_tokens"], projekt_id=pid)
            if not abgabe:
                abgabe = {"zusammenfassung": _kurz(text, 200), "ergebnis": text}
            gut, begruendung, dollar_p = (True, "", 0.0) if a["rolle"] == "pruefer" else pruefen(p, a, abgabe)
            with _lock:
                z = laden()
                p, a = aufgabe_finden(z, aid)
                a["versuche"] = versuch
                a["kosten"] = round(a.get("kosten", 0.0) + dollar + dollar_p, 4)
                a["ergebnis"] = abgabe.get("ergebnis", "")
                a["zusammenfassung"] = abgabe.get("zusammenfassung", "")
                if abgabe.get("html"):
                    vorschau_datei(aid).write_text(abgabe["html"], encoding="utf-8")
                    a["vorschau"] = True
                a["urteil"] = begruendung
                if gut or versuch >= MAX_VERSUCHE:
                    a["status"] = "fertig"
                    a.pop("hinweis", None)
                    nicht = "" if gut else " Der Prüfer war noch nicht zufrieden, ich habe aufgehört, um Geld zu sparen."
                    protokoll_zeile(z, f"Fertig: {a['titel']} ({ROLLEN[a['rolle']]['name']}, Versuch {versuch})",
                                    pid, a["kosten"])
                    eintrag(z, "meldung", f"Fertig in „{p['name']}“: {a['titel']}. {a['zusammenfassung']}{nicht}",
                            projekt=pid, aufgabe=aid)
                    if all(b["status"] == "fertig" for b in p["aufgaben"]):
                        p["status"] = "fertig"
                        eintrag(z, "meldung", f"Alle Aufgaben von „{p['name']}“ sind fertig. Kosten: "
                                              f"{geld(p.get('ausgegeben', 0))}.", projekt=pid)
                    speichern(z)
                    return
                a["hinweis"] = begruendung
                protokoll_zeile(z, f"Zurück an den Arbeiter: {a['titel']} (Versuch {versuch})", pid)
                speichern(z)
    except GrenzeErreicht as g:
        with _lock:
            z = laden()
            p, a = aufgabe_finden(z, aid)
            a["status"] = "offen"   # beginnt wieder, sobald es eine Freigabe gibt
            grenze_melden(z, p, str(g))
            speichern(z)
    except Exception as e:   # ein Arbeiter darf den Server nie mitreißen
        with _lock:
            z = laden()
            try:
                p, a = aufgabe_finden(z, aid)
                a["status"] = "fehler"
                a["urteil"] = f"Technischer Fehler: {type(e).__name__}"
                protokoll_zeile(z, f"Fehler bei {a['titel']}: {type(e).__name__}", p["id"])
                eintrag(z, "meldung", f"Bei „{a['titel']}“ ist ein technischer Fehler passiert ({type(e).__name__}). "
                                      "Sag mir, ob ich es nochmal versuchen soll.", projekt=p["id"])
                speichern(z)
            except ValueError:
                pass
    finally:
        with _lock:
            _laufend.pop(aid, None)


def grenze_melden(z, p, art):
    """Einmal melden, dass eine Grenze erreicht ist. Beim Projekt mit einer Freigabe-Frage für mehr Budget."""
    if art == "tag":
        if z["gemeldet"].get("tag") != heute():
            z["gemeldet"]["tag"] = heute()
            eintrag(z, "meldung", f"Die Tagesgrenze von {geld(z['grenzen']['tag'])} ist erreicht. Morgen geht es "
                                  "weiter, oder du stellst die Grenze im Gespräch höher.")
            protokoll_zeile(z, "Tagesgrenze erreicht")
        return
    if p["status"] != "wartet":
        p["status"] = "wartet"
        mehr = round(min(PROJEKT_HOECHSTENS - p["budget"], max(0.5, p["budget"] / 2)), 2)
        if mehr <= 0:
            eintrag(z, "meldung", f"„{p['name']}“ hat das höchste Budget von {PROJEKT_HOECHSTENS:.0f} $ "
                                  "aufgebraucht und ist angehalten.", projekt=p["id"])
            return
        frage_stellen(z, p, f"Das Budget von „{p['name']}“ ({geld(p['budget'])}) ist aufgebraucht. "
                            f"{geld(mehr)} mehr freigeben?", art="budget", mehr=mehr)
        protokoll_zeile(z, "Projektbudget aufgebraucht", p["id"])


def frage_stellen(z, p, frage, art="frei", **mehr):
    f = {"id": neue_id("f"), "frage": frage[:500], "art": art, "stand": "offen",
         "zeit": jetzt().isoformat(timespec="seconds"), **mehr}
    p.setdefault("fragen", []).append(f)
    eintrag(z, "frage", frage, projekt=p["id"], frage=f["id"])
    return f


# ---------- Takt ----------
def bereite_aufgaben(p):
    """Die Aufgaben, die jetzt starten dürfen: alle davor sind fertig, außer die in derselben Gruppe."""
    bereit = []
    gruppe_fertig = True
    gruppe = []
    for a in p["aufgaben"]:
        if not a.get("gleichzeitig") or not gruppe:
            if gruppe and not all(b["status"] == "fertig" for b in gruppe):
                gruppe_fertig = False
            if not gruppe_fertig:
                break
            gruppe = []
        gruppe.append(a)
        if a["status"] == "offen":
            bereit.append(a)
    return bereit


def takt_runde():
    """Startet, was starten darf. Ohne KI, kostet nichts."""
    with _lock:
        z = laden()
        geaendert = False
        frei = z["grenzen"]["gleichzeitig"] - len(_laufend)
        for p in z["projekte"]:
            if frei <= 0 or p["status"] != "aktiv":
                continue
            for a in bereite_aufgaben(p):
                if ROLLEN[a["rolle"]].get("abo"):
                    continue   # holt der PC-Arbeiter selbst ab (abo.py), kostet kein API-Geld
                if frei <= 0:
                    break
                try:
                    grenze_pruefen(z, p)
                    if p["budget"] - p.get("ausgegeben", 0.0) < MINDESTENS_FREI:
                        raise GrenzeErreicht("projekt")
                    if z["grenzen"]["tag"] - heute_ausgegeben(z) < MINDESTENS_FREI:
                        raise GrenzeErreicht("tag")
                except GrenzeErreicht as g:
                    vorher = len(z["gespraech"])
                    grenze_melden(z, p, str(g))
                    geaendert = geaendert or len(z["gespraech"]) != vorher
                    break
                a["status"] = "laeuft"
                a["gestartet"] = jetzt().isoformat(timespec="seconds")
                protokoll_zeile(z, f"Start: {a['titel']} ({ROLLEN[a['rolle']]['name']})", p["id"])
                faden = threading.Thread(target=arbeiter, args=(a["id"],), daemon=True)
                _laufend[a["id"]] = faden
                frei -= 1
                geaendert = True
        geaendert = abo.aufraeumen(z) or geaendert
        if jetzt().hour >= BERICHT_UM and z["bericht_tag"] != heute():
            z["bericht_tag"] = heute()
            bericht = tagesbericht(z)
            if bericht:
                eintrag(z, "bericht", bericht)
                geaendert = True
        if geaendert:
            speichern(z)
        neue = [f for f in _laufend.values() if not f.is_alive() and f.ident is None]
    for f in neue:
        f.start()
    dreamstudy.takt()   # holt höchstens alle paar Minuten Aufträge aus DreamStudy, in einem eigenen Faden


def tagesbericht(z):
    """Kurzer Bericht über heute, ohne KI. Leer, wenn heute nichts passiert ist."""
    tag = heute()
    heute_zeilen = [e for e in z["protokoll"] if e["zeit"].startswith(tag)]
    if not heute_zeilen and not heute_ausgegeben(z):
        return ""
    fertig = [e["text"][8:] for e in heute_zeilen if e["text"].startswith("Fertig: ")]
    offen = [f["frage"] for p in z["projekte"] for f in p.get("fragen", []) if f["stand"] == "offen"]
    laeuft = [p["name"] for p in z["projekte"] if p["status"] == "aktiv"]
    teile = [f"Tagesbericht: Heute {len(fertig)} Aufgaben fertig, Kosten {geld(heute_ausgegeben(z))} "
             f"von {geld(z['grenzen']['tag'])}."]
    if fertig:
        teile.append("Fertig: " + "; ".join(fertig[:8]) + ".")
    if laeuft:
        teile.append("In Arbeit: " + ", ".join(laeuft) + ".")
    if offen:
        teile.append(f"{len(offen)} Fragen warten auf dich.")
    return " ".join(teile)


def takt():
    while True:
        try:
            takt_runde()
        except Exception as e:   # der Takt darf nie stehen bleiben
            print(f"Chef-Takt-Fehler: {type(e).__name__}", flush=True)
        time.sleep(TAKT_SEKUNDEN)


def starten():
    """Einmal beim Serverstart: Aufgaben, die beim letzten Mal mitten drin waren, beginnen von vorn."""
    global _takt_an
    if _takt_an:
        return
    _takt_an = True
    with _lock:
        z = laden()
        for p in z["projekte"]:
            for a in p["aufgaben"]:
                if a["status"] == "laeuft" and not ROLLEN[a["rolle"]].get("abo"):   # der PC arbeitet weiter
                    a["status"] = "offen"
        speichern(z)
    threading.Thread(target=takt, daemon=True).start()


# ---------- Werkzeuge des Chefs ----------
AUFGABE_SCHEMA = {"type": "object", "properties": {
    "titel": {"type": "string", "description": "Kurz, z. B. 'Konkurrenz ansehen'."},
    "rolle": {"type": "string", "enum": list(ROLLEN)},
    "auftrag": {"type": "string", "description": "Was genau zu tun ist und was am Ende abgegeben wird."},
    "gleichzeitig": {"type": "boolean", "description": "true: läuft parallel zur vorherigen Aufgabe."},
    "repo": {"type": "string", "description": "Nur bei programmierer: das GitHub-Repo, z. B. 'n1kob1ko/Biko-Bot'."},
}, "required": ["titel", "rolle", "auftrag"]}


def _aufgaben(liste, schon=0):
    if not isinstance(liste, list) or not liste:
        raise ValueError("Bitte mindestens eine Aufgabe.")
    if schon + len(liste) > MAX_AUFGABEN:
        raise ValueError(f"Höchstens {MAX_AUFGABEN} Aufgaben pro Projekt.")
    neu = []
    for e in liste:
        if not isinstance(e, dict) or e.get("rolle") not in ROLLEN:
            raise ValueError("Jede Aufgabe braucht eine Rolle: " + ", ".join(ROLLEN) + ".")
        titel, auftrag = str(e.get("titel") or "").strip()[:80], str(e.get("auftrag") or "").strip()[:4000]
        if not titel or not auftrag:
            raise ValueError("Jede Aufgabe braucht Titel und Auftrag.")
        a = {"id": neue_id("a"), "titel": titel, "rolle": e["rolle"], "auftrag": auftrag,
             "gleichzeitig": e.get("gleichzeitig") is True and (schon + len(neu)) > 0,
             "status": "offen", "versuche": 0, "kosten": 0.0}
        if ROLLEN[e["rolle"]].get("abo"):
            if not abo.an():
                raise ValueError("Der PC-Arbeiter ist noch nicht eingerichtet (CHEF_ABO_TOKEN fehlt).")
            a["repo"] = abo.repo_pruefen(e.get("repo"))
        neu.append(a)
    return neu


def _budget(wert, standard):
    if wert is None:
        return standard
    try:
        b = round(float(wert), 2)
    except (TypeError, ValueError):
        raise ValueError("Das Budget ist eine Zahl in US-Dollar.")
    if not 0.1 <= b <= PROJEKT_HOECHSTENS:
        raise ValueError(f"Das Budget pro Projekt liegt zwischen 0,10 und {PROJEKT_HOECHSTENS:.0f} $.")
    return b


def projekt_anlegen(e):
    with _lock:
        z = laden()
        if len([p for p in z["projekte"] if p["status"] != "fertig"]) >= MAX_PROJEKTE:
            raise ValueError("Zu viele offene Projekte. Schließ erst eines ab.")
        name, ziel = str(e.get("name") or "").strip()[:60], str(e.get("ziel") or "").strip()[:2000]
        if not name or not ziel:
            raise ValueError("Ein Projekt braucht Name und Ziel.")
        p = {"id": neue_id("p"), "name": name, "ziel": ziel, "budget": _budget(e.get("budget_dollar"), PROJEKT_STANDARD),
             "ausgegeben": 0.0, "status": "aktiv", "erstellt": jetzt().isoformat(timespec="seconds"),
             "aufgaben": _aufgaben(e.get("aufgaben")), "fragen": []}
        z["projekte"].append(p)
        protokoll_zeile(z, f"Projekt angelegt: {name}, Budget {geld(p['budget'])}, {len(p['aufgaben'])} Aufgaben", p["id"])
        speichern(z)
    return f"Angelegt als {p['id']}. Die erste Aufgabe startet in ein paar Sekunden."


def aufgaben_dazu(e):
    with _lock:
        z = laden()
        p = projekt_finden(z, e.get("projekt"))
        p["aufgaben"] += _aufgaben(e.get("aufgaben"), len(p["aufgaben"]))
        if p["status"] == "fertig":
            p["status"] = "aktiv"
        protokoll_zeile(z, f"Aufgaben dazu in {p['name']}", p["id"])
        speichern(z)
    return "Dazugeschrieben."


def ergebnis_lesen(e):
    with _lock:
        z = laden()
        _, a = aufgabe_finden(z, e.get("aufgabe"))
    if a["status"] != "fertig" and not a.get("ergebnis"):
        return f"Noch kein Ergebnis, Stand: {a['status']}."
    text = f"Ergebnis von „{a['titel']}“ (Prüfer: {a.get('urteil') or '-'}):\n\n{_kurz(a.get('ergebnis'), 30000)}"
    if a.get("vorschau"):
        text += "\n\n(Dazu gibt es eine Webseite, Niko sieht sie als Vorschau auf seiner Projektkarte.)"
    return text


def aufgabe_wiederholen(e):
    with _lock:
        z = laden()
        p, a = aufgabe_finden(z, e.get("aufgabe"))
        if a["status"] == "laeuft":
            raise ValueError("Die Aufgabe läuft gerade noch.")
        hinweis = str(e.get("hinweis") or "").strip()[:2000]
        if not hinweis:
            raise ValueError("Bitte sag, was besser werden soll.")
        a.update(status="offen", versuche=0, hinweis=hinweis)
        if p["status"] == "fertig":
            p["status"] = "aktiv"
        protokoll_zeile(z, f"Nochmal: {a['titel']}", p["id"])
        speichern(z)
    return "Die Aufgabe läuft gleich nochmal mit deinem Hinweis."


def projekt_aendern(e):
    with _lock:
        z = laden()
        p = projekt_finden(z, e.get("projekt"))
        teile = []
        if e.get("budget_dollar") is not None:
            p["budget"] = _budget(e.get("budget_dollar"), p["budget"])
            teile.append(f"Budget {geld(p['budget'])}")
            if p["status"] == "wartet" and p.get("ausgegeben", 0) < p["budget"]:
                p["status"] = "aktiv"
        if e.get("status") in ("aktiv", "pausiert", "fertig"):
            p["status"] = e["status"]
            teile.append(f"Status {p['status']}")
        if not teile:
            raise ValueError("Nichts zu ändern.")
        protokoll_zeile(z, f"{p['name']}: " + ", ".join(teile), p["id"])
        speichern(z)
    return "Geändert: " + ", ".join(teile) + "."


def grenzen_setzen(e):
    with _lock:
        z = laden()
        teile = []
        if e.get("tag_dollar") is not None:
            try:
                t = round(float(e["tag_dollar"]), 2)
            except (TypeError, ValueError):
                raise ValueError("Die Tagesgrenze ist eine Zahl in US-Dollar.")
            if not 0.1 <= t <= TAG_HOECHSTENS:
                raise ValueError(f"Die Tagesgrenze liegt zwischen 0,10 und {TAG_HOECHSTENS:.0f} $.")
            z["grenzen"]["tag"] = t
            z["gemeldet"].pop("tag", None)
            teile.append(f"Tagesgrenze {geld(t)}")
        if e.get("gleichzeitig") is not None:
            try:
                g = int(e["gleichzeitig"])
            except (TypeError, ValueError):
                raise ValueError("Gleichzeitig ist eine Zahl.")
            if not 1 <= g <= GLEICHZEITIG_HOECHSTENS:
                raise ValueError(f"Zwischen 1 und {GLEICHZEITIG_HOECHSTENS} Arbeiter gleichzeitig.")
            z["grenzen"]["gleichzeitig"] = g
            teile.append(f"{g} Arbeiter gleichzeitig")
        if not teile:
            raise ValueError("Nichts zu ändern.")
        protokoll_zeile(z, "Grenzen: " + ", ".join(teile))
        speichern(z)
    return "Eingestellt: " + ", ".join(teile) + "."


def freigabe_anfragen(e):
    with _lock:
        z = laden()
        p = projekt_finden(z, e.get("projekt"))
        frage = str(e.get("frage") or "").strip()
        if not frage:
            raise ValueError("Bitte eine Frage.")
        frage_stellen(z, p, frage)
        speichern(z)
    return "Die Frage steht jetzt mit Ja und Nein vor Niko. Seine Antwort kommt als <meldung>."


CHEF_WERKZEUGE = {
    "projekt_anlegen": ({"name": "projekt_anlegen", "description": "Legt ein Projekt mit Ziel, Budget und Aufgaben an. "
                         "Die Arbeiter beginnen sofort.", "input_schema": {"type": "object", "properties": {
                             "name": {"type": "string", "description": "Kurzer Name, z. B. 'Nachhilfe-Webseite'."},
                             "ziel": {"type": "string", "description": "Was am Ende da sein soll, mit allen Details von Niko."},
                             "budget_dollar": {"type": "number", "description": f"Höchstens so viel US-Dollar. Standard {PROJEKT_STANDARD:.0f}."},
                             "aufgaben": {"type": "array", "items": AUFGABE_SCHEMA}},
                             "required": ["name", "ziel", "aufgaben"]}}, projekt_anlegen),
    "aufgaben_dazu": ({"name": "aufgaben_dazu", "description": "Hängt weitere Aufgaben an ein Projekt an.",
                       "input_schema": {"type": "object", "properties": {
                           "projekt": {"type": "string"}, "aufgaben": {"type": "array", "items": AUFGABE_SCHEMA}},
                           "required": ["projekt", "aufgaben"]}}, aufgaben_dazu),
    "ergebnis_lesen": ({"name": "ergebnis_lesen", "description": "Liest das ganze Ergebnis einer Aufgabe.",
                        "input_schema": {"type": "object", "properties": {"aufgabe": {"type": "string"}},
                                         "required": ["aufgabe"]}}, ergebnis_lesen),
    "aufgabe_wiederholen": ({"name": "aufgabe_wiederholen", "description": "Schickt eine Aufgabe mit einem Hinweis "
                             "noch einmal an einen Arbeiter, z. B. wenn Niko etwas anders haben will.",
                             "input_schema": {"type": "object", "properties": {
                                 "aufgabe": {"type": "string"}, "hinweis": {"type": "string"}},
                                 "required": ["aufgabe", "hinweis"]}}, aufgabe_wiederholen),
    "projekt_aendern": ({"name": "projekt_aendern", "description": "Ändert Budget oder Status eines Projekts "
                         "(aktiv, pausiert, fertig).", "input_schema": {"type": "object", "properties": {
                             "projekt": {"type": "string"}, "budget_dollar": {"type": "number"},
                             "status": {"type": "string", "enum": ["aktiv", "pausiert", "fertig"]}},
                             "required": ["projekt"]}}, projekt_aendern),
    "grenzen_setzen": ({"name": "grenzen_setzen", "description": "Stellt die Tagesgrenze für alle Projekte und wie "
                        "viele Arbeiter gleichzeitig laufen. Nur wenn Niko das ausdrücklich will.",
                        "input_schema": {"type": "object", "properties": {
                            "tag_dollar": {"type": "number", "description": f"0,10 bis {TAG_HOECHSTENS:.0f} US-Dollar pro Tag."},
                            "gleichzeitig": {"type": "integer", "description": f"1 bis {GLEICHZEITIG_HOECHSTENS}."}}}},
                       grenzen_setzen),
    "freigabe_anfragen": ({"name": "freigabe_anfragen", "description": "Stellt Niko eine Ja/Nein-Frage, z. B. vor "
                           "dem Veröffentlichen oder wenn etwas Geld kostet.", "input_schema": {"type": "object",
                           "properties": {"projekt": {"type": "string"}, "frage": {"type": "string"}},
                           "required": ["projekt", "frage"]}}, freigabe_anfragen),
}


def stand_text(z):
    zeilen = [f"Heute ausgegeben: {geld(heute_ausgegeben(z))} von {geld(z['grenzen']['tag'])}. "
              f"Arbeiter gleichzeitig: {z['grenzen']['gleichzeitig']}. Jetzt: {jetzt().strftime('%A %d.%m.%Y %H:%M')}.",
              abo.stand_text(z)]
    for p in z["projekte"][-12:]:
        zeilen.append(f"Projekt {p['id']} „{p['name']}“ ({p['status']}, {p.get('ausgegeben', 0):.2f} von "
                      f"{geld(p['budget'])}): {_kurz(p['ziel'], 200)}")
        for a in p["aufgaben"]:
            zeilen.append(f"  Aufgabe {a['id']} [{a['rolle']}{', ' + a['repo'] if a.get('repo') else ''}] {a['titel']}: "
                          f"{a['status']}" + (f" – {_kurz(a.get('zusammenfassung'), 200)}" if a.get("zusammenfassung") else "")
                          + (f" PR: {a['pr']}" if a.get("pr") else ""))
        for f in p.get("fragen", []):
            if f["stand"] == "offen":
                zeilen.append(f"  Offene Frage an Niko: {f['frage']}")
    return "\n".join(zeilen)


def chef_nachrichten(z):
    """Das Chef-Gespräch für Claude: Niko, Meldungen und Freigaben als user, der Chef als assistant."""
    nachrichten = []
    for e in z["gespraech"][-MAX_VERLAUF:]:
        rolle = "assistant" if e["wer"] == "chef" else "user"
        text = e["text"] if e["wer"] in ("niko", "chef") else f"<meldung>{e['text']}</meldung>"
        if nachrichten and nachrichten[-1]["role"] == rolle:
            nachrichten[-1]["content"] += "\n\n" + text
        else:
            nachrichten.append({"role": rolle, "content": text})
    while nachrichten and nachrichten[0]["role"] != "user":
        nachrichten.pop(0)
    if nachrichten and nachrichten[-1]["role"] == "user":
        nachrichten[-1]["content"] = f"<stand>\n{stand_text(z)}\n</stand>\n\n" + nachrichten[-1]["content"]
    return nachrichten


def chef_antwort():
    """Der Chef antwortet auf das, was zuletzt im Gespräch steht."""
    with _lock:
        z = laden()
        nachrichten = chef_nachrichten(z)
    try:
        text, dollar = schleife(CHEF_SYSTEM, nachrichten, CHEF_WERKZEUGE, CHEF_MODELL, effort="medium", max_tokens=8000,
                                reserve=GESPRAECH_RESERVE)
    except GrenzeErreicht:
        text, dollar = ("Heute ist auch die Reserve fürs Gespräch aufgebraucht. Morgen bin ich wieder da."), 0.0
    with _lock:
        z = laden()
        eintrag(z, "chef", text or "Erledigt.")
        speichern(z)
    return text, dollar


def chat(text):
    text = str(text or "").strip()
    if not text or len(text) > MAX_TEXT:
        raise ValueError("Bitte etwas Kürzeres schreiben.")
    with _lock:
        z = laden()
        eintrag(z, "niko", text)
        speichern(z)
    try:
        chef_antwort()
    except anthropic.AuthenticationError:
        raise RuntimeError("Der Schlüssel für die KI fehlt oder stimmt nicht.")
    except anthropic.APIError as e:
        print(f"Chef: Claude-Fehler {type(e).__name__}", flush=True)
        raise RuntimeError("Biko-Chef kann gerade nicht antworten. Bitte gleich nochmal.")
    return ansicht()


def freigabe(pid, fid, ja):
    """Niko tippt Ja oder Nein unter einer Frage."""
    with _lock:
        z = laden()
        p = projekt_finden(z, pid)
        f = next((f for f in p.get("fragen", []) if f["id"] == fid), None)
        if not f:
            raise ValueError("Diese Frage gibt es nicht.")
        if f["stand"] != "offen":
            return ansicht()
        f["stand"] = "ja" if ja else "nein"
        protokoll_zeile(z, f"Freigabe {'ja' if ja else 'nein'}: {_kurz(f['frage'], 120)}", p["id"])
        eintrag(z, "meldung", f"Niko hat „{f['frage']}“ mit {'Ja' if ja else 'Nein'} beantwortet.", projekt=p["id"])
        if f["art"] == "budget":
            if ja:
                p["budget"] = round(min(PROJEKT_HOECHSTENS, p["budget"] + f.get("mehr", 0.5)), 2)
                p["status"] = "aktiv"
            else:
                p["status"] = "pausiert"
        if f["art"] == "merge" and ja:
            abo.merge_einreihen(z, p, f)
        speichern(z)
    if f["art"] not in ("budget", "merge"):   # bei einer eigenen Frage des Chefs reagiert er gleich darauf
        try:
            chef_antwort()
        except (anthropic.APIError, RuntimeError) as e:
            print(f"Chef: nach Freigabe {type(e).__name__}", flush=True)
    return ansicht()


def ansicht():
    """Was die Seite /chef zeigt."""
    with _lock:
        z = laden()
    projekte = []
    for p in reversed(z["projekte"][-20:]):
        projekte.append({
            "id": p["id"], "name": p["name"], "ziel": p["ziel"], "status": p["status"], "budget": p["budget"],
            "ausgegeben": round(p.get("ausgegeben", 0.0), 4),
            "aufgaben": [{"id": a["id"], "titel": a["titel"], "rolle": a["rolle"], "rolle_name": ROLLEN[a["rolle"]]["name"],
                          "status": a["status"], "zusammenfassung": a.get("zusammenfassung", ""),
                          "vorschau": bool(a.get("vorschau")), "versuche": a.get("versuche", 0),
                          "kosten": a.get("kosten", 0.0), "pr": a.get("pr", ""), "repo": a.get("repo", "")}
                         for a in p["aufgaben"]],
            "fragen": [{"id": f["id"], "frage": f["frage"]} for f in p.get("fragen", []) if f["stand"] == "offen"],
        })
    return {"projekte": projekte, "gespraech": z["gespraech"][-80:], "grenzen": z["grenzen"],
            "heute": round(heute_ausgegeben(z), 4), "laufen": len(_laufend),
            "protokoll": z["protokoll"][-30:], "dreamstudy": dreamstudy.ansicht(), "abo": abo.ansicht()}


def ergebnis(aid):
    with _lock:
        z = laden()
        p, a = aufgabe_finden(z, aid)
    return {"titel": a["titel"], "rolle": ROLLEN[a["rolle"]]["name"], "status": a["status"],
            "ergebnis": a.get("ergebnis", ""), "urteil": a.get("urteil", ""), "vorschau": bool(a.get("vorschau")),
            "pr": a.get("pr", "")}


import abo  # noqa: E402  (Code-Aufgaben auf Nikos PC mit Claude Code und seinem Abo)
import dreamstudy  # noqa: E402  (meldet seine Werkzeuge bei CHEF_WERKZEUGE an; braucht dieses Modul fertig geladen)
