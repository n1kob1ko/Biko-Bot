"""
Biko Assistent: kleiner KI-Helfer für den Alltag, vor allem für ältere Menschen.

Funktionen, alle über das Gespräch (POST /api/chat):
  1. Reden und fragen   Biko antwortet, sucht bei Bedarf im Internet und merkt sich das Gespräch.
  2. Gespräche          Jede Sitzung ist ein eigenes Gespräch. Man kann ein neues beginnen und frühere wieder
                        öffnen (GET /api/gespraeche, GET /api/gespraech?id=..., POST /api/gespraech/loeschen).
  3. Nachrichten        "Schreib Anna, dass ..." – Biko stellt den fertigen Text zum Kopieren ins Gespräch.
  4. Links              Findet Biko etwas im Internet, stellt er den Link als Knopf ins Gespräch.
  5. Erinnerungen       Biko schreibt sie sich im Gespräch selbst auf ("erinnere mich um 8 an die Tablette").
                        Die App meldet sich zur Uhrzeit. GET/POST /api/erinnerungen sind nur zum Nachsehen und Löschen da.
  6. Gedächtnis         Erzählt die Person etwas Bleibendes über sich ("ich hab Diabetes", "mein Enkel heißt Niko"),
                        schreibt Biko es sich selbst auf und denkt beim nächsten Mal daran. GET /api/wissen zeigt die
                        Liste, POST /api/wissen/loeschen streicht einen Eintrag.
  7. Morgenrunde        "Meld dich jeden Morgen um 8": Biko bereitet kurz vorher Wetter, Nachrichten nach Interesse und
                        die Termine des Tages vor (Hausmeister-Faden) und stellt sie als eigenes Gespräch bereit.
                        Die Android-App meldet sich zur Uhrzeit mit einer Mitteilung und Biko liest vor
                        (GET /api/morgenrunde).
Nachrichten, Links, Erinnerungen, das Gedächtnis und die Morgenrunde sind Werkzeuge, die Claude selbst aufruft.

Stimme: Mit einem Schlüssel für den Sprachdienst (ELEVENLABS_API_KEY) redet man mit Biko wie am Telefon:
  - Die App hört durchgehend zu. Dafür holt sie sich einen Zugang für 15 Minuten (POST /api/live-zugang) und schickt
    das Mikrofon direkt an das Live-Zuhören von ElevenLabs. Der Dienst merkt selbst, wann ein Satz fertig ist.
  - Die Antwort kommt stückweise (POST /api/chat mit "strom": true, als Server-Sent Events), die App spricht
    Satz für Satz, während Biko noch schreibt (POST /api/stimme liefert den Ton roh als PCM, 24 kHz, sobald er entsteht).
  - Fällt man Biko ins Wort, hört er auf zu sprechen.
Daneben gibt es noch das Vorlesen einer ganzen Antwort als MP3 (POST /api/vorlesen) und das Verstehen einer ganzen
Aufnahme (POST /api/zuhoeren), falls das Live-Zuhören an einem Handy nicht geht.
Ohne Schlüssel sprechen und hören die Browser der Handys selbst, so gut sie können.

Dazu ein Profil (GET/POST /api/profil): nur Name, Du/Sie und Sprache, also was Biko schon vor dem ersten Satz braucht.

Anmelden: ein Passwort (APP_PASSWORT in der .env). Danach bleibt das Handy ein Jahr angemeldet (Cookie).
Daten liegen als JSON in DATA_DIR (Standard /data). Nach außen gehen nur die Texte an die Claude-API und, wenn
der Sprachdienst eingerichtet ist, vorzulesende Texte und Aufnahmen an ElevenLabs.
Nur Python-Standardbibliothek plus das offizielle anthropic-Paket.
"""

import base64
from collections import OrderedDict
import hashlib
import hmac
import json
import os
import re
import secrets
import tempfile
import threading
import time
import urllib.error
import urllib.request
import uuid
from datetime import date, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, urlparse
from zoneinfo import ZoneInfo

import anthropic

PORT = int(os.environ.get("PORT", "8092"))
DATA = Path(os.environ.get("DATA_DIR", "/data"))
WEB = Path(os.environ.get("WEB_DIR", Path(__file__).parent / "web"))
PASSWORT = os.environ.get("APP_PASSWORT", "")
MODELL = os.environ.get("ASSISTENT_MODELL", "claude-opus-5-5")             # für Wichtiges: Briefe, Betrug, Gesundheit, Bildschirm
EINFACH_MODELL = os.environ.get("ASSISTENT_MODELL_EINFACH", "claude-sonnet-5-5")  # für Plaudern und einfache Fragen: halb so teuer, schneller
ZEITZONE = ZoneInfo(os.environ.get("TZ", "Europe/Vienna"))
MAX_VERLAUF = 30          # so viele Nachrichten eines Gesprächs liest Biko bei jeder Antwort mit
MAX_GESPRAECHE = 40       # so viele Gespräche bleiben im Verlauf, das älteste fällt weg
MAX_GESPEICHERT = 200     # so viele Nachrichten bleiben pro Gespräch gespeichert
MAX_TEXT = 2000           # längere Eingaben werden abgelehnt
# Sprachdienst (ElevenLabs): natürliche Stimme zum Vorlesen, Zuhören in jeder Sprache. Ein Schlüssel für beides.
SPRACH_KEY = os.environ.get("ELEVENLABS_API_KEY", "")
SPRACH_STIMME = os.environ.get("SPRACH_STIMME", "")              # Nummer der Stimme (voice_id); leer: die erste des Kontos
SPRACH_MODELL = os.environ.get("SPRACH_MODELL", "eleven_v4_turbo")   # spricht über 90 Sprachen, antwortet schnell
SPRACH_HOEREN = "scribe_v2"                                      # erkennt die gesprochene Sprache selbst
SPRACH_LIVE = "scribe_v2_realtime"                              # hört live zu, für das Gespräch wie am Telefon
LIVE_ADRESSE = "wss://api.elevenlabs.io"                         # dorthin schickt die App das Mikrofon beim Live-Zuhören
MAX_VORLESEN = 2500       # so viele Zeichen werden höchstens vorgelesen
MAX_SATZ = 600            # so viele Zeichen hat ein Stück, das im Gespräch auf einmal gesprochen wird
MAX_AUFNAHME = 6_000_000  # Bytes; eine Minute Sprechen ist etwa 1 MB
COOKIE = "biko_assistent"
COOKIE_TAGE = 365

DATA.mkdir(parents=True, exist_ok=True)
_lock = threading.RLock()   # RLock: wissen_lesen() darf auch innerhalb einer Sperre aufgerufen werden
# Bildschirmfoto aus der Android-App (Biko als Assistent): gilt ein paar Minuten für alle Fragen, nur im Speicher
_bildschirm = {"bild": None, "zeit": 0.0}
MAX_BILDSCHIRM = 3_000_000    # Bytes
BILDSCHIRM_GILT = 300         # Sekunden
_client = None

STANDARD_PROFIL = {
    "name": "",
    "anrede": "du",          # "du" oder "Sie"
    "sprache": "de-AT",      # Sprache für Sprechen/Vorlesen und wenn unklar ist, wie Biko antworten soll
}
# Alles andere über die Person (Diät, Familie, Vorlieben) merkt sich Biko im Gespräch selbst, siehe wissen_lesen().
MAX_WISSEN = 60

SYSTEM = """Du bist Biko, ein freundlicher gelber Vogel und KI-Helfer im Alltag. Du sprichst mit {name_satz}.
Viele Menschen, die dich nutzen, sind älter und haben wenig Erfahrung mit Technik.

So sprichst du:
- Antworte immer in der Sprache, in der die Person dich anspricht (meist Deutsch oder Chinesisch). Auf Chinesisch: vereinfachte Schriftzeichen,
  einfache Alltagssprache.
  Wenn unklar: {sprache}.
- Einfache, warme Sprache (auf Deutsch gern österreichisch freundlich), kurze Sätze, keine Fachwörter, keine Anglizismen.
- Du sprichst die Person mit "{anrede}" an.
- Kurze Antworten: meistens 2 bis 5 Sätze. Bei Anleitungen nummerierte Schritte, höchstens 5.
- Kein Markdown außer einfachen nummerierten Listen. Keine Tabellen, keine Überschriften, keine Emojis außer ganz selten einem.
- Du kannst im Internet suchen und Seiten öffnen. Nutze das für aktuelle Dinge: Angebote und Deals, Preise vergleichen,
  Öffnungszeiten, Wetter, Nachrichten, Veranstaltungen. Für Plaudern und allgemeines Wissen suchst du nicht.
- Bei Angeboten suchst du immer zuerst selbst und gründlich, bevor du antwortest: mehrere Suchen mit Produkt, Geschäft und
  "Aktion diese Woche", auch auf Seiten, die Flugblätter durchsuchbar machen (zum Beispiel aktionsfinder.at, marktguru.at,
  wogibtswas.at). Öffne eine Trefferseite, wenn in der Vorschau kein Preis steht. Schick die Person nicht einfach zum Prospekt.
- Nenne höchstens 3 gute Angebote mit Geschäft, Preis und wie lange es gilt, am liebsten in der Nähe
  (Wien bzw. Österreich, Geschäfte wie Billa, Spar, Hofer, Lidl, dm, Bipa, MediaMarkt, asiatische Supermärkte
  wie am Naschmarkt) oder seriöse Online-Shops. Sag dazu, dass sich Preise ändern können.
- Internet-Adressen schreibst du nie in den Text deiner Antwort. Du zeigst sie mit dem Werkzeug link_zeigen: dann steht unter
  deiner Antwort ein Knopf zum Antippen. Nimm nur Adressen, die du in den Suchergebnissen wirklich gesehen hast, nie ausgedachte.
  Zeig den Link zur Quelle, wenn du ein Angebot nennst. Findest du trotz Suche nichts Genaues, sag das ehrlich in einem Satz
  und zeig den direkten Link zum aktuellen Prospekt oder Flugblatt des Geschäfts, damit die Person selbst schauen kann.
- Wenn du etwas trotz Suche nicht sicher weißt, sag das ehrlich. Erfinde nichts.

Ehrlichkeit:
- Du bist eine KI, kein Mensch. Wenn jemand fragt, sagst du das freundlich. Du gibst nicht vor, Gefühle wie ein Mensch zu haben.
- Du freust dich, zu plaudern und zuzuhören. Bei Einsamkeit hörst du zu und ermutigst sanft, auch mit Familie,
  Freunden oder Nachbarn Kontakt zu haben, ohne zu belehren.

Gesundheit:
- Du gibst keine Diagnosen und änderst nie Medikamente oder Dosierungen. Dafür sind Arzt, Ärztin oder Apotheke da.
- Bei Fragen zum Essen und zur Diät hilfst du anhand dessen, was du über die Person weißt (siehe Hinweis der App). Sag klar
  "passt gut", "lieber wenig" oder "lieber nicht", mit einem kurzen Grund. Weißt du nichts dazu, gib nur allgemeine,
  vorsichtige Hinweise.
- Bei Notfällen (Brustschmerzen, Atemnot, Sturz, plötzliche Lähmung oder Verwirrtheit): sofort sagen, die Rettung 144 anzurufen.
- Bei Unsicherheit zu Beschwerden: Gesundheitsnummer 1450 (rund um die Uhr, kostenlos).
- Wenn jemand sehr traurig ist oder an Suizid denkt: einfühlsam bleiben und die Telefonseelsorge 142 nennen (kostenlos, rund um die Uhr).

Sicherheit:
- Warne vor Betrug, wenn etwas danach klingt (Anrufe von "Polizei" oder "Bank", Gewinnspiele, "Enkeltrick", Links in SMS).
  Nie Passwörter, PINs oder TANs weitergeben.

Von selbst melden:
- Du kannst dich jeden Morgen von selbst melden ("Morgenrunde"): mit Wetter, ein paar Nachrichten, die die Person
  interessieren, und ihren Erinnerungen für den Tag. Auf Android kommt dazu eine Mitteilung, und du liest vor.
- Will die Person das ("meld dich jeden Morgen", "erzähl mir in der Früh die Nachrichten", "每天早上告诉我新闻"),
  stellst du es mit morgenrunde_einstellen ein. Fehlt die Uhrzeit, frag kurz nach. "Hör auf damit" stellt es ab.
- Welche Nachrichten sie interessieren (Wien, China, Sport, Gesundheit ...), merkst du dir mit wissen_merken.
- Erinnerungen an einzelne Dinge bleiben Erinnerungen (erinnerung_merken), die Morgenrunde ist der tägliche Überblick.

Nachrichten für andere:
- Wenn die Person jemandem etwas schreiben will ("schreib Anna, dass ...", "wie sage ich dem Arzt ab?"), schreibst du die
  fertige Nachricht in ihrem Namen, in der Ich-Form, freundlich, natürlich und kurz (1 bis 4 Sätze), so wie sie selbst
  schreiben würde: an Enkel locker und herzlich, an Ärzte oder Ämter höflich mit "Sie". In der Sprache der Person, außer
  sie wünscht eine andere.
- Zeig die Nachricht mit dem Werkzeug nachricht_zeigen. Dann steht sie unter deiner Antwort mit einem Knopf zum Kopieren.
  Schreib den Text der Nachricht nicht noch einmal in deine Antwort, sag nur einen kurzen Satz dazu.
- Du kannst selbst nichts verschicken. Die Person kopiert den Text und fügt ihn in WeChat, WhatsApp oder SMS ein.
- Fehlt, was drinstehen soll, frag kurz nach. Soll etwas geändert werden, zeigst du die ganze neue Fassung.

Erinnerungen:
- Wenn die Person an etwas erinnert werden möchte ("erinnere mich", "vergiss nicht", "weck mich", "提醒我"), schreibst du es dir
  mit dem Werkzeug erinnerung_merken auf. Behaupte nie, du hättest dir etwas gemerkt, ohne das Werkzeug benutzt zu haben.
- Fehlt die Uhrzeit, frag kurz nach ("Um wie viel Uhr?") und rate nicht. "In 20 Minuten" rechnest du selbst aus.
- Einmalig (heute, morgen, am Freitag, in einer Stunde): mit Datum. Regelmäßig (jeden Tag, jeden Montag): mit Wochentagen.
  Ist unklar, ob einmal oder regelmäßig, frag kurz nach.
- Bestätige danach in einem kurzen Satz mit Tag und Uhrzeit. Die Nummer einer Erinnerung sagst du nie dazu.
- Du kannst dich nur melden, solange diese App am Handy offen ist. Bei Wichtigem wie Medikamenten oder Terminen sagst du
  das in einem Satz dazu und empfiehlst zusätzlich den Wecker des Handys.
- Will die Person etwas nicht mehr, löschst du es mit erinnerung_loeschen. Zum Ändern: löschen und neu merken.
- Auf "Woran erinnerst du mich?" liest du deine Erinnerungen aus dem Hinweis der App in einfachen Worten vor.

Dein Gedächtnis über die Person:
- Erzählt die Person etwas, das auch nächste Woche noch stimmt, schreibst du es dir mit dem Werkzeug wissen_merken auf:
  Gesundheit und Diät (Krankheiten, Allergien, was sie nicht essen darf), Familie und Freunde mit Namen, Geburtstage,
  Haustiere, wo sie wohnt, was sie mag oder nicht mag, Hobbys, ob sie schlecht hört oder sieht.
- Nicht aufschreiben: Dinge nur für heute ("ich bin müde"), was du schon weißt, und nie Passwörter, PINs, TANs,
  Kontonummern oder Ausweisnummern.
- Ein kurzer Satz pro Sache, aus Sicht der Person, z. B. "Hat Diabetes Typ 2" oder "Enkel heißt Niko, studiert in Graz".
- Sag beim Aufschreiben höchstens ganz kurz "Das merk ich mir." und red dann normal weiter. Die Nummer sagst du nie.
- Hat sich etwas geändert, streichst du den alten Eintrag mit wissen_vergessen und merkst dir den neuen.
  Sagt die Person "vergiss das", streichst du es.
- Nutze dein Wissen natürlich im Gespräch (frag nach dem Enkel, denk an die Diät), aber zähl es nicht ungefragt auf.
- Auf "Was weißt du über mich?" erzählst du es in einfachen Worten.

Der Hinweis der App:
- Vor jeder Frage steht ein Hinweis der App zwischen <app> und </app>: Datum und Uhrzeit, deine Erinnerungen mit Nummer,
  was du über die Person weißt (mit Nummer), und manchmal, dass die Person gerade mit dir redet wie am Telefon oder dass
  ein Bildschirmfoto dabei ist. Das hat nicht die Person geschrieben. Du nutzt es, erwähnst den Hinweis aber nie."""

# ---------- Daten ----------

def _pfad(name):
    return DATA / f"{name}.json"


def lesen(name, standard):
    try:
        with open(_pfad(name), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return standard


def schreiben(name, daten):
    fd, tmp = tempfile.mkstemp(dir=DATA, suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(daten, f, ensure_ascii=False, indent=2)
    os.replace(tmp, _pfad(name))


def geheimnis():
    """Schlüssel zum Signieren des Login-Cookies, wird einmal erzeugt."""
    p = DATA / "geheimnis.txt"
    if not p.exists():
        p.write_text(secrets.token_hex(32))
        p.chmod(0o600)
    return p.read_text().strip()


SPRACHEN = {"de-AT": "Deutsch", "zh-CN": "Chinesisch (vereinfachte Schriftzeichen)"}


def profil():
    p = lesen("profil", {})
    return {k: p.get(k, v) for k, v in STANDARD_PROFIL.items()}


def wissen_lesen():
    """Was Biko über die Person weiß. Beim ersten Mal kommen die alten Felder Diät und Notizen aus dem Profil hinein."""
    if not _pfad("wissen").exists():
        with _lock:
            if not _pfad("wissen").exists():
                alt = lesen("profil", {})
                zeit = jetzt().isoformat(timespec="seconds")
                liste = [{"id": uuid.uuid4().hex[:10], "text": f"{vorne}{str(alt[k]).strip()}"[:400], "zeit": zeit}
                         for k, vorne in (("diaet", "Diät: "), ("notizen", "")) if str(alt.get(k) or "").strip()]
                schreiben("wissen", liste)
                if "diaet" in alt or "notizen" in alt:
                    schreiben("profil", {k: v for k, v in alt.items() if k not in ("diaet", "notizen")})
    return lesen("wissen", [])


# ---------- Claude ----------

def client():
    global _client
    if _client is None:
        _client = anthropic.Anthropic()  # liest ANTHROPIC_API_KEY
    return _client


# Websuche für Deals, Öffnungszeiten, aktuelle Fragen. Läuft bei Anthropic. Mit web_fetch kann Biko eine
# Trefferseite auch öffnen, zum Beispiel wenn der Preis nicht in der Vorschau steht.
WEBSUCHE = [
    {"type": "web_search_20260209", "name": "web_search", "max_uses": 5,
     "user_location": {"type": "approximate", "city": "Wien", "country": "AT", "timezone": "Europe/Vienna"}},
    {"type": "web_fetch_20260209", "name": "web_fetch", "max_uses": 3},
]
_seiten_oeffnen = True   # wird False, falls die API das Öffnen von Seiten ablehnt: dann sucht Biko nur


def protokoll(text):
    """Eine Zeile ins Server-Protokoll. Nie Inhalte aus Gesprächen, nur was technisch passiert ist."""
    print(text, flush=True)


def claude_anfrage(**kw):
    """Der eine Aufruf der Claude-API. Die Tests ersetzen ihn durch ein Drehbuch."""
    return client().beta.messages.create(**kw)


def claude_strom(beim_text, **kw):
    """Wie claude_anfrage, aber jedes neue Stück Text geht sofort an `beim_text`. Damit kann Biko schon sprechen,
    während er noch schreibt. Liefert am Ende die ganze Antwort, genau wie claude_anfrage."""
    with client().beta.messages.stream(**kw) as strom:
        for ereignis in strom:
            if ereignis.type == "content_block_delta" and getattr(ereignis.delta, "type", "") == "text_delta":
                beim_text(ereignis.delta.text)
        return strom.get_final_message()


def werkzeug_ergebnis(block, werkzeuge):
    """Führt ein von Claude gewünschtes Werkzeug aus. Fehler gehen als Text zurück, damit Claude nachfragen kann."""
    try:
        if block.name not in werkzeuge:
            raise ValueError("Dieses Werkzeug gibt es nicht.")
        inhalt = werkzeuge[block.name]["tun"](block.input if isinstance(block.input, dict) else {})
        return {"type": "tool_result", "tool_use_id": block.id, "content": inhalt}
    except ValueError as e:
        return {"type": "tool_result", "tool_use_id": block.id, "content": f"Fehler: {e}", "is_error": True}


# Preise in US-Dollar pro Million Tokens (Stand November 2026, laut Anthropic): Eingabe, Ausgabe, aus dem
# Zwischenspeicher gelesen, in den Zwischenspeicher geschrieben (5 Minuten). Eine Websuche kostet 1 Cent.
PREISE = {
    "claude-opus-5-5": (4.00, 20.00, 0.20, 5.00),
    "claude-sonnet-5-5": (2.00, 10.00, 0.10, 2.50),
    "claude-haiku-5-5": (0.10, 0.50, 0.01, 0.125),
}
PREIS_SUCHE = 0.01


def verbrauch_zaehlen(summe, r, modell):
    """Zählt, was eine Anfrage verbraucht hat, und rechnet es in Dollar um (nur Zahlen, nie Inhalte)."""
    u = getattr(r, "usage", None)
    if u is None:
        return
    zahl = lambda x: x if isinstance(x, int) else 0
    neu = {"eingabe": zahl(getattr(u, "input_tokens", 0)), "ausgabe": zahl(getattr(u, "output_tokens", 0)),
           "gelesen": zahl(getattr(u, "cache_read_input_tokens", 0)),
           "geschrieben": zahl(getattr(u, "cache_creation_input_tokens", 0)),
           "suchen": zahl(getattr(getattr(u, "server_tool_use", None), "web_search_requests", 0))}
    preis = PREISE.get(getattr(r, "model", None) if isinstance(getattr(r, "model", None), str) else modell) or PREISE.get(modell)
    if preis:
        neu["dollar"] = (neu["eingabe"] * preis[0] + neu["ausgabe"] * preis[1] + neu["gelesen"] * preis[2]
                         + neu["geschrieben"] * preis[3]) / 1e6 + neu["suchen"] * PREIS_SUCHE
    for k, v in neu.items():
        summe[k] = summe.get(k, 0) + v


def verbrauch_text(v):
    alle = v.get("eingabe", 0) + v.get("gelesen", 0) + v.get("geschrieben", 0)
    text = (f"Eingabe {alle} Tokens (davon {v.get('gelesen', 0)} aus dem Zwischenspeicher, {v.get('geschrieben', 0)} neu"
            f" gespeichert), Ausgabe {v.get('ausgabe', 0)}, Suchen {v.get('suchen', 0)}")
    if "dollar" in v:
        heute = kosten_dazu(ki=v["dollar"])
        text += (f", Kosten {v['dollar'] * 100:.2f} US-Cent, heute bisher {heute['ki'] * 100:.1f} US-Cent"
                 f" bei {heute['antworten']} Antworten")
    return text


def kosten_dazu(ki=0.0, zeichen=0):
    """Tagessumme in kosten.json: KI-Kosten in Dollar, Zahl der Antworten, vorgelesene Zeichen. Die letzten 62 Tage."""
    tag = jetzt().strftime("%Y-%m-%d")
    with _lock:
        alle = lesen("kosten", {})
        heute = {"ki": 0.0, "antworten": 0, "zeichen": 0, **alle.get(tag, {})}
        heute["ki"] = round(heute["ki"] + ki, 6)
        heute["antworten"] += 1 if ki else 0
        heute["zeichen"] += zeichen
        alle[tag] = heute
        schreiben("kosten", {k: alle[k] for k in sorted(alle)[-62:]})
    return heute


def frage_claude(system, messages, max_tokens=4000, websuche=False, werkzeuge=None, beim_text=None, modell=None):
    """Eine Antwort von Claude als Text. Wirft RuntimeError mit freundlicher Meldung.
    `werkzeuge`: {name: {"schema": ..., "tun": funktion(eingabe) -> text}}, Claude darf sie selbst aufrufen.
    `beim_text`: bekommt jedes Stück Text, sobald es da ist (für das Gespräch wie am Telefon)."""
    global _seiten_oeffnen
    werkzeuge = werkzeuge or {}
    web = [w for w in WEBSUCHE if _seiten_oeffnen or w["name"] != "web_fetch"] if websuche else []
    tools = web + [w["schema"] for w in werkzeuge.values()]
    messages = list(messages)
    benutzt = []
    verbrauch = {}
    # Zwischen zwei Runden (etwa "Ich schau kurz nach." und danach die Suche) beginnt ein neuer Satz
    runde_offen = {"gesagt": False, "trennen": False}

    def weiterreichen(stueck):
        if not stueck:
            return
        if runde_offen["trennen"]:
            stueck, runde_offen["trennen"] = "\n" + stueck, False
        runde_offen["gesagt"] = True
        beim_text(stueck)

    def anfrage(tools):
        kw = dict(
            model=modell or MODELL,
            max_tokens=max_tokens,
            # Die Anleitung bleibt gleich und kommt aus dem Zwischenspeicher. Das obere cache_control nimmt dazu bei
            # jeder Runde alles bis zum Schluss mit: Suchergebnisse und Werkzeug-Runden zahlt Biko so nur einmal voll.
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            cache_control={"type": "ephemeral"},
            messages=messages,
            # Alltagsgespräch: wenig Nachdenken reicht, ist schneller und günstiger
            output_config={"effort": "low"},
            # Falls eine Sicherheitsprüfung die Anfrage ablehnt, springt ein anderes Modell ein
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            **({"tools": tools} if tools else {}),
        )
        return claude_strom(weiterreichen, **kw) if beim_text else claude_anfrage(**kw)

    try:
        for runde in range(1, 9):  # Werkzeug-Aufrufe und lange Websuchen (pause_turn) werden fortgesetzt
            try:
                r = anfrage(tools)
            except anthropic.BadRequestError:
                # Lehnt die API die Anfrage ab, solange "Seiten öffnen" dabei ist, versucht Biko es einmal nur mit
                # der Suche: lieber eine Antwort ohne geöffnete Seite als gar keine.
                ohne = [w for w in tools if w.get("name") != "web_fetch"]
                if runde > 1 or len(ohne) == len(tools):
                    raise
                r = anfrage(ohne)
                tools, _seiten_oeffnen = ohne, False
                protokoll("Seiten öffnen (web_fetch) wurde abgelehnt, Biko sucht ab jetzt ohne.")
            benutzt += [b.name for b in r.content if b.type in ("tool_use", "server_tool_use")]
            verbrauch_zaehlen(verbrauch, r, modell or MODELL)
            runde_offen["trennen"] = runde_offen["gesagt"]
            if r.stop_reason == "pause_turn":
                messages = messages + [{"role": "assistant", "content": r.content}]
            elif r.stop_reason == "tool_use":
                ergebnisse = [werkzeug_ergebnis(b, werkzeuge) for b in r.content if b.type == "tool_use"]
                messages = messages + [{"role": "assistant", "content": r.content}, {"role": "user", "content": ergebnisse}]
            else:
                break
    except anthropic.AuthenticationError:
        raise RuntimeError("Der Schlüssel für die KI fehlt oder stimmt nicht. Bitte Niko Bescheid geben.")
    except anthropic.RateLimitError:
        raise RuntimeError("Gerade sind zu viele Anfragen. Bitte in einer Minute nochmal probieren.")
    except anthropic.APIStatusError as e:
        protokoll(f"Claude-Fehler: {e.status_code} {e.message}")
        raise RuntimeError("Biko kann gerade nicht antworten. Bitte gleich nochmal probieren.")
    except anthropic.APIConnectionError:
        raise RuntimeError("Keine Verbindung zur KI. Ist das Internet am Server da?")
    protokoll(f"Claude ({modell or MODELL}): {runde} Anfragen, Ende {r.stop_reason}, Werkzeuge: {', '.join(benutzt) or 'keine'}"
              f" | {verbrauch_text(verbrauch)}")
    if r.stop_reason == "refusal":
        return "Dabei kann ich leider nicht helfen. Magst du mich etwas anderes fragen?"
    text = "".join(b.text for b in r.content if b.type == "text").strip()
    return text or "Entschuldige, da ist mir nichts eingefallen. Magst du es anders sagen?"


def jetzt():
    return datetime.now(ZEITZONE)


# ---------- Sprachdienst ----------

def sprach_anfrage(pfad, daten=None, kopf=None):
    """Der eine Aufruf des Sprachdienstes. Die Tests ersetzen ihn. Liefert die Antwort als Bytes."""
    req = urllib.request.Request("https://api.elevenlabs.io" + pfad, data=daten, method="GET" if daten is None else "POST",
                                 headers={"xi-api-key": SPRACH_KEY, **(kopf or {})})
    with urllib.request.urlopen(req, timeout=40) as r:
        return r.read()


def sprach_strom(pfad, daten, kopf=None):
    """Wie sprach_anfrage, liefert die Antwort aber in Stücken, sobald sie ankommen. Die Tests ersetzen ihn."""
    req = urllib.request.Request("https://api.elevenlabs.io" + pfad, data=daten, method="POST",
                                 headers={"xi-api-key": SPRACH_KEY, **(kopf or {})})
    r = urllib.request.urlopen(req, timeout=40)

    def stuecke():
        with r:
            while True:
                stueck = r.read1(8192) if hasattr(r, "read1") else r.read(8192)
                if not stueck:
                    return
                yield stueck
    return stuecke()


def sprachdienst(pfad, daten=None, kopf=None, strom=False):
    """Fragt den Sprachdienst. Wirft RuntimeError mit freundlicher Meldung.
    `strom`: die Antwort kommt als Folge von Stücken (Fehler beim Verbinden kommen trotzdem gleich hier an)."""
    if not SPRACH_KEY:
        raise RuntimeError("Der Sprachdienst ist nicht eingerichtet.")
    try:
        return sprach_strom(pfad, daten, kopf) if strom else sprach_anfrage(pfad, daten, kopf)
    except urllib.error.HTTPError as e:
        try:
            grund = e.read()[:300].decode("utf-8", "replace")   # die Fehlermeldung des Dienstes, kein Inhalt aus Gesprächen
        except Exception:
            grund = ""
        protokoll(f"Sprachdienst-Fehler: {e.code} bei {pfad.split('?')[0]} {grund}")
        if e.code in (401, 403):
            raise RuntimeError("Der Schlüssel für die Stimme fehlt, stimmt nicht oder das Guthaben ist aufgebraucht. Bitte Niko Bescheid geben.")
        raise RuntimeError("Die Stimme geht gerade nicht. Bitte gleich nochmal probieren.")
    except OSError:
        protokoll(f"Sprachdienst-Fehler: keine Verbindung bei {pfad.split('?')[0]}")
        raise RuntimeError("Der Sprachdienst ist gerade nicht erreichbar.")


_stimme = None


def stimme():
    """Mit welcher Stimme Biko spricht: die festgelegte (SPRACH_STIMME), sonst die erste Stimme des Kontos."""
    global _stimme
    if SPRACH_STIMME:
        return SPRACH_STIMME
    if _stimme is None:
        liste = json.loads(sprachdienst("/v2/voices?page_size=20")).get("voices") or []
        if not liste:
            raise RuntimeError("Die Stimme geht gerade nicht. Bitte gleich nochmal probieren.")
        _stimme = str(liste[0]["voice_id"])
        protokoll(f"Sprachdienst: Biko spricht mit der Stimme {liste[0].get('name')!r}")
    return _stimme


def ton_holen(text):
    """Der Text als gesprochener Ton (MP3)."""
    text = text[:MAX_VORLESEN]
    ton = sprachdienst(f"/v1/text-to-speech/{quote(stimme(), safe='')}?output_format=mp3_44100_128",
                       json.dumps({"text": text, "model_id": SPRACH_MODELL}).encode(), {"Content-Type": "application/json"})
    heute = kosten_dazu(zeichen=len(text))
    protokoll(f"Sprachdienst: {len(text)} Zeichen vorgelesen, heute bisher {heute['zeichen']} Zeichen")
    return ton


def ton_strom(text, vorher=""):
    """Ein Stück einer Antwort als Ton, roh als PCM (16 Bit, 24 kHz, mono), Stück für Stück, sobald es entsteht.
    `vorher`: was Biko davor gesagt hat, damit die Stimme im Satzfluss bleibt."""
    text = text[:MAX_SATZ]
    # Kurze Sätze am Anfang einer Antwort ("Moment, ich schau kurz nach.", "Gerne!") kommen oft wieder. Die hat
    # Biko schon einmal gesagt: dann kommt der Ton sofort aus dem Speicher, klingt gleich und kostet nichts.
    schluessel = (stimme(), SPRACH_MODELL, text) if not vorher and len(text) <= MAX_GEMERKT_SATZ else None
    if schluessel:
        with _lock:
            gemerkt = _toene.get(schluessel)
            if gemerkt is not None:
                _toene.move_to_end(schluessel)
        if gemerkt is not None:
            protokoll(f"Sprachdienst: {len(text)} Zeichen aus dem Speicher gesprochen")
            return iter(gemerkt)
    body = {"text": text, "model_id": SPRACH_MODELL}
    if vorher:
        body["previous_text"] = vorher[-500:]
    stuecke = sprachdienst(f"/v1/text-to-speech/{quote(stimme(), safe='')}/stream?output_format=pcm_24000",
                           json.dumps(body).encode(), {"Content-Type": "application/json"}, strom=True)
    heute = kosten_dazu(zeichen=len(text))
    protokoll(f"Sprachdienst: {len(text)} Zeichen gesprochen, heute bisher {heute['zeichen']} Zeichen")
    return ton_merken(schluessel, stuecke) if schluessel else stuecke


MAX_GEMERKT_SATZ = 80     # so kurze Sätze merkt sich Biko als fertigen Ton
MAX_TOENE = 100           # so viele Sätze, der älteste fällt weg (zusammen höchstens etwa 25 MB)
_toene = OrderedDict()


def ton_merken(schluessel, stuecke):
    """Reicht den Ton weiter und merkt ihn sich, aber nur, wenn er ganz angekommen ist (nicht nach Unterbrechen)."""
    alle = []
    for stueck in stuecke:
        alle.append(stueck)
        yield stueck
    with _lock:
        _toene[schluessel] = alle
        while len(_toene) > MAX_TOENE:
            _toene.popitem(last=False)


def live_zugang():
    """Ein Zugang für 15 Minuten, mit dem die App selbst live beim Sprachdienst zuhören lassen kann.
    Der eigentliche Schlüssel verlässt den Server nie."""
    j = json.loads(sprachdienst("/v1/single-use-token/realtime_scribe", b""))
    zugang = str(j.get("token") or "")
    if not zugang:
        raise RuntimeError("Die Stimme geht gerade nicht. Bitte gleich nochmal probieren.")
    protokoll("Sprachdienst: Live-Zuhören begonnen")
    return {"token": zugang, "modell": SPRACH_LIVE}


AUFNAHME_ARTEN = {"audio/webm": "webm", "audio/mp4": "mp4", "audio/ogg": "ogg", "audio/wav": "wav",
                  "audio/mpeg": "mp3", "audio/aac": "aac", "audio/x-m4a": "m4a"}


def text_hoeren(ton, art):
    """Die Aufnahme als Text. Die Sprache wird nicht vorgegeben: der Dienst erkennt selbst, ob Deutsch oder
    Chinesisch gesprochen wurde."""
    grenze = "biko" + secrets.token_hex(16)
    felder = {"model_id": SPRACH_HOEREN, "tag_audio_events": "false", "timestamps_granularity": "none"}
    teile = [f'--{grenze}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode() for k, v in felder.items()]
    teile.append(f'--{grenze}\r\nContent-Disposition: form-data; name="file"; filename="aufnahme.{AUFNAHME_ARTEN[art]}"\r\n'
                 f'Content-Type: {art}\r\n\r\n'.encode() + ton + b"\r\n")
    teile.append(f"--{grenze}--\r\n".encode())
    j = json.loads(sprachdienst("/v1/speech-to-text", b"".join(teile),
                                {"Content-Type": f"multipart/form-data; boundary={grenze}"}))
    sprache = str(j.get("language_code") or "")
    protokoll(f"Sprachdienst: {len(ton) // 1000} kB zugehört, Sprache {sprache or 'unbekannt'}")
    return {"text": str(j.get("text") or "").strip(), "sprache": sprache}


BILDSCHIRM = """Zu dieser Frage siehst du ein Bildschirmfoto vom Handy oder Tablet der Person: das, was sie gerade vor sich hat
(zum Beispiel einen WeChat-Chat, eine Webseite oder einen Brief). Fragt sie "was steht da", "was schreibt sie",
"übersetz das" oder "was soll ich antworten", geht es um dieses Bild. Lies vor, erkläre oder übersetze in einfachen Worten.
Eine Antwort für jemanden schreibst du wie sonst auch mit nachricht_zeigen. Sag nicht "auf dem Bildschirmfoto",
sondern einfach "da steht" oder "Mei schreibt". Hat die Frage nichts mit dem Bild zu tun, beachte es nicht."""


# Worum es geht, wenn Biko gründlich sein soll: dann nimmt er das stärkere Modell
WICHTIG = re.compile(
    r"brief|rechnung|mahnung|behörde|amt\b|finanzamt|magistrat|vertrag|kündig|betrug|betrüg|fake|phishing|abzocke|echt\?"
    r"|bank|konto|überweis|zahlen|bezahl|pin\b|passwort|tan\b|versicherung|pension|rente|steuer|frist|anwalt|gericht|polizei"
    r"|medikament|tablette|arzt|ärztin|krank|schmerz|blutdruck|zucker|allergie|notfall|spital|krankenhaus"
    r"|诈骗|骗|银行|转账|密码|合同|账单|信件|药|医生|医院|病|疼|保险|税|警察|紧急",
    re.IGNORECASE)


def modell_fuer(text, bild=None):
    """Plaudern und einfache Fragen gehen an das günstigere Modell, Wichtiges und alles mit Bildschirm an das stärkere."""
    if bild or len(text) > 400 or WICHTIG.search(text):
        return MODELL
    return EINFACH_MODELL


def bildschirm_merken(bild):
    with _lock:
        _bildschirm.update(bild=bild, zeit=time.time())


def bildschirm_frisch():
    """Das Bildschirmfoto, solange es noch gilt, sonst None."""
    with _lock:
        if _bildschirm["bild"] and time.time() - _bildschirm["zeit"] < BILDSCHIRM_GILT:
            return _bildschirm["zeit"], _bildschirm["bild"]
        return None


GESPROCHEN = """Gerade redet die Person mit dir wie am Telefon: sie hört deine Antwort, statt sie zu lesen.
- Antworte so, wie man am Telefon redet: kurz, meistens 1 bis 3 Sätze, natürlich und herzlich. Keine Listen, keine Nummern.
  Bei einer Anleitung sagst du nur den ersten Schritt oder zwei und fragst, ob es weitergehen soll.
- Frag höchstens eine Sache auf einmal.
- Musst du im Internet suchen, sag vorher einen ganz kurzen Satz wie "Moment, ich schau kurz nach." und such dann.
- Was du hörst, wurde automatisch mitgeschrieben. Ist etwas unverständlich oder passt nicht zusammen, frag freundlich nach."""


def system_prompt():
    """Der gleichbleibende Teil der Anleitung. Er ändert sich nur, wenn die Familie Name, Anrede oder Sprache ändert,
    und kommt deshalb fast immer aus dem Zwischenspeicher von Anthropic (ein Zehntel des Preises bzw. weniger).
    Was sich bei jeder Frage ändert, steht im Hinweis der App (hinweis()), direkt vor der Frage."""
    p = profil()
    return SYSTEM.format(
        name_satz=p["name"].strip() or "einer Person, deren Namen du noch nicht kennst",
        anrede="Sie" if p.get("anrede") == "Sie" else "du",
        sprache=SPRACHEN.get(p.get("sprache"), "Deutsch"),
    )


def hinweis(gesprochen=False, bild=False):
    """Was sich bei jeder Frage ändert: Uhrzeit, Erinnerungen, Wissen, ob man gerade redet, ob ein Bildschirmfoto dabei ist."""
    t = jetzt()
    tage = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]
    teile = [
        f"Heute ist {tage[t.weekday()]}, {t.day}.{t.month}.{t.year}, es ist {t.strftime('%H:%M')} Uhr.",
        "Deine Erinnerungen:\n" + ("\n".join(f"- Nummer {e['id']}: {erinnerung_wann(e)}: {e['text']}"
                                             for e in erinnerungen_lesen()) or "- noch nichts"),
        "Was du über die Person weißt:\n" + ("\n".join(f"- Nummer {w['id']}: {w['text']}" for w in wissen_lesen())
                                             or "- noch nichts"),
    ]
    zeit = morgenrunde_zeit()
    teile.append(f"Morgenrunde: jeden Tag um {zeit} Uhr." if zeit else "Morgenrunde: nicht eingestellt.")
    if gesprochen:
        teile.append(GESPROCHEN)
    if bild:
        teile.append(BILDSCHIRM)
    return "<app>\n" + "\n\n".join(teile) + "\n</app>"


# ---------- Funktionen ----------

# ---------- Gespräche: jede Sitzung für sich, zum Weiterreden und Nachlesen ----------

def titel_aus(text):
    t = " ".join(str(text).split())
    return t if len(t) <= 60 else t[:60] + "…"


def gespraech_neu(nachrichten):
    zeit = jetzt().isoformat(timespec="seconds")
    erste = next((m["text"] for m in nachrichten if m["von"] == "ich"), "")
    return {"id": secrets.token_hex(4), "titel": titel_aus(erste), "begonnen": zeit, "zuletzt": zeit,
            "nachrichten": nachrichten}


def gespraeche_lesen():
    """Alle Gespräche, das zuletzt benutzte zuerst. Nur mit _lock aufrufen.
    Der eine Verlauf der ersten Version wird beim ersten Mal als ein Gespräch übernommen."""
    liste = lesen("gespraeche", None)
    if liste is None:
        alt = [{"von": "ich" if m.get("role") == "user" else "biko", "text": m["content"]}
               for m in lesen("verlauf", []) if isinstance(m, dict) and isinstance(m.get("content"), str)]
        liste = [gespraech_neu(alt)] if alt else []
        schreiben("gespraeche", liste)
        _pfad("verlauf").unlink(missing_ok=True)
    return liste


def gespraech_finden(liste, nr):
    return next((g for g in liste if g["id"] == nr), None)


def uebersicht(g):
    return {"id": g["id"], "titel": g["titel"], "zuletzt": g["zuletzt"], "anzahl": len(g["nachrichten"])}


def fuer_claude(nachrichten, bild=None):
    """Das bisherige Gespräch so, wie Claude es lesen soll. Eine Nachricht, die Biko für jemanden geschrieben hat,
    steht wieder als Werkzeug-Aufruf da: so weiß er bei "mach sie kürzer" noch, was drinstand.
    Biko liest mindestens die letzten MAX_VERLAUF - 1 Nachrichten. Der Anfang rückt in Zehnerschritten weiter, damit er
    über mehrere Fragen gleich bleibt: nur dann kommt der Verlauf aus dem Zwischenspeicher.
    `bild`: das noch gültige Bildschirmfoto als (Zeit, Bytes). Es bleibt bei der Frage, mit der es geschickt wurde."""
    zuviel = len(nachrichten) - (MAX_VERLAUF - 1)
    if zuviel > 0:
        nachrichten = nachrichten[zuviel // 10 * 10:]   # 29 bis 38 Nachrichten
    messages = []
    if nachrichten and nachrichten[0].get("vonselbst"):
        # Biko hat sich von selbst gemeldet (Morgenrunde): Claude braucht trotzdem eine Nachricht der Person davor
        messages.append({"role": "user", "content": "<app>Du hast dich von selbst gemeldet (Morgenrunde).</app>"})
    while not messages and nachrichten and nachrichten[0]["von"] != "ich":   # muss mit der Person beginnen
        nachrichten = nachrichten[1:]
    for i, m in enumerate(nachrichten):
        if m["von"] == "ich":
            if bild and m.get("bildschirm") == bild[0]:
                messages.append({"role": "user", "content": [bild_block(bild[1]), {"type": "text", "text": m["text"]}]})
            else:
                messages.append({"role": "user", "content": m["text"]})
            continue
        entwuerfe = m.get("nachrichten") or []
        if entwuerfe:
            messages.append({"role": "assistant", "content": [
                {"type": "tool_use", "id": f"frueher_{i}_{k}", "name": "nachricht_zeigen", "input": e}
                for k, e in enumerate(entwuerfe)]})
            messages.append({"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": f"frueher_{i}_{k}", "content": NACHRICHT_GEZEIGT}
                for k in range(len(entwuerfe))]})
        messages.append({"role": "assistant", "content": m["text"]})
    return messages


def bild_block(bild):
    return {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": base64.b64encode(bild).decode()}}


def zwischenspeichern(messages):
    """Markiert das Ende des bisherigen Verlaufs: bis dahin liest Anthropic bei der nächsten Frage aus dem Zwischenspeicher."""
    if not messages:
        return messages
    letzte = dict(messages[-1])
    inhalt = letzte["content"]
    bloecke = [{"type": "text", "text": inhalt}] if isinstance(inhalt, str) else [dict(b) for b in inhalt]
    bloecke[-1]["cache_control"] = {"type": "ephemeral"}
    letzte["content"] = bloecke
    return messages[:-1] + [letzte]


NACHRICHT_GEZEIGT = "Die Nachricht steht jetzt unter deiner Antwort, mit einem Knopf zum Kopieren."
LINK = re.compile(r"^https://[A-Za-z0-9.-]+\.[A-Za-z]{2,}(/\S*)?$")
MAX_ZEIGEN = 3   # so viele Nachrichten und so viele Links passen unter eine Antwort


def zeige_werkzeuge():
    """Die zwei Werkzeuge, mit denen Biko etwas unter seine Antwort stellt, und die Listen, in denen es landet."""
    entwuerfe, links = [], []

    def nachricht_zeigen(eingabe):
        text = str(eingabe.get("text") or "").strip()[:1500]
        if not text:
            raise ValueError("Der Text der Nachricht fehlt. Frag nach, was drinstehen soll.")
        if len(entwuerfe) >= MAX_ZEIGEN:
            raise ValueError(f"Höchstens {MAX_ZEIGEN} Nachrichten pro Antwort.")
        entwuerfe.append({"an": " ".join(str(eingabe.get("an") or "").split())[:80], "text": text})
        return NACHRICHT_GEZEIGT

    def link_zeigen(eingabe):
        url = str(eingabe.get("url") or "").strip()
        if len(url) > 500 or not LINK.match(url):
            raise ValueError("Das ist keine sichere Internet-Adresse. Sie muss vollständig sein und mit https:// beginnen.")
        if len(links) >= MAX_ZEIGEN:
            raise ValueError(f"Höchstens {MAX_ZEIGEN} Links pro Antwort.")
        if url not in [l["url"] for l in links]:
            titel = " ".join(str(eingabe.get("titel") or "").split())[:60]
            links.append({"titel": titel or urlparse(url).hostname, "url": url})
        return "Der Link steht jetzt als Knopf unter deiner Antwort."

    werkzeuge = {
        "nachricht_zeigen": {"tun": nachricht_zeigen, "schema": {
            "name": "nachricht_zeigen",
            "description": "Stellt eine fertige Nachricht, die die Person jemandem schicken will, unter deine Antwort, "
                           "mit einem Knopf zum Kopieren. Verschickt nichts.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "an": {"type": "string", "description": "Für wen die Nachricht ist, z. B. 'Anna' oder 'Dr. Huber'."},
                    "text": {"type": "string", "description": "Die ganze Nachricht, fertig zum Verschicken, ohne Anführungszeichen."},
                },
                "required": ["text"],
            },
        }},
        "link_zeigen": {"tun": link_zeigen, "schema": {
            "name": "link_zeigen",
            "description": "Stellt einen Link als großen Knopf unter deine Antwort, zum Beispiel zur Quelle eines Angebots "
                           "oder zum aktuellen Prospekt eines Geschäfts. Nur Adressen aus deinen Suchergebnissen.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "titel": {"type": "string", "description": "Kurze Beschriftung in der Sprache der Person, z. B. 'Billa Flugblatt'."},
                    "url": {"type": "string", "description": "Die vollständige Adresse, beginnt mit https://"},
                },
                "required": ["titel", "url"],
            },
        }},
    }
    return werkzeuge, entwuerfe, links


def chat(text, gespraech_nr="", beim_text=None, gesprochen=False):
    """Eine Frage im Gespräch. `beim_text` bekommt die Antwort stückweise, `gesprochen`: man redet gerade wie am Telefon."""
    with _lock:
        g = gespraech_finden(gespraeche_lesen(), gespraech_nr)
    verlauf = g["nachrichten"] if g else []
    bild = bildschirm_frisch()   # (Zeit, Bytes) oder None
    # Ein Bildschirmfoto geht nur einmal mit, bei der ersten Frage danach. Danach steht es im Verlauf bei dieser
    # Frage und kommt, solange es gilt, günstig aus dem Zwischenspeicher, statt jedes Mal neu bezahlt zu werden.
    schon_da = bool(bild) and any(m.get("bildschirm") == bild[0] for m in verlauf)
    neu_bild = bool(bild) and not schon_da
    frage = [{"type": "text", "text": hinweis(gesprochen, bild=bool(bild))}]
    if neu_bild:
        frage.append(bild_block(bild[1]))
    frage.append({"type": "text", "text": text})
    messages = zwischenspeichern(fuer_claude(verlauf, bild)) + [{"role": "user", "content": frage}]
    zeigen, entwuerfe, links = zeige_werkzeuge()
    vorher, wusste = erinnerungen_lesen(), wissen_lesen()
    antwort = frage_claude(system_prompt(), messages, websuche=True, werkzeuge={**WERKZEUGE, **zeigen},
                           modell=modell_fuer(text, bild),
                           **({"beim_text": beim_text} if beim_text else {}))
    # Was Biko in dieser Antwort wirklich getan hat: die App zeigt es unter der Antwort, auch beim Wiederöffnen
    nachher, weiss = erinnerungen_lesen(), wissen_lesen()
    alt, neu = {e["id"] for e in vorher}, {e["id"] for e in nachher}
    kannte = {w["id"] for w in wusste}
    getan = {"gemerkt": [e for e in nachher if e["id"] not in alt],
             "vergessen": [e for e in vorher if e["id"] not in neu],
             "gelernt": [w for w in weiss if w["id"] not in kannte],
             "nachrichten": entwuerfe, "links": links}
    zeit = jetzt().isoformat(timespec="seconds")
    with _lock:   # erst jetzt speichern: geht die Antwort schief, bleibt das Gespräch, wie es war
        liste = gespraeche_lesen()
        g = gespraech_finden(liste, gespraech_nr) or gespraech_neu([])
        g["nachrichten"] = (g["nachrichten"] + [
            {"von": "ich", "text": text, "zeit": zeit, **({"bildschirm": bild[0]} if neu_bild else {})},
            {"von": "biko", "text": antwort, "zeit": zeit, **{k: v for k, v in getan.items() if v}},
        ])[-MAX_GESPEICHERT:]
        g["titel"] = g["titel"] or titel_aus(text)
        g["zuletzt"] = zeit
        schreiben("gespraeche", ([g] + [x for x in liste if x["id"] != g["id"]])[:MAX_GESPRAECHE])
    return {"antwort": antwort, "gespraech": uebersicht(g), "erinnerungen": nachher, "wissen": weiss,
            "morgenrunde": morgenrunde_zeit(), **getan}


UHRZEIT = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
TAGE = {"mo", "di", "mi", "do", "fr", "sa", "so"}


MAX_ERINNERUNGEN = 30
TAG_NAMEN = {"mo": "Montag", "di": "Dienstag", "mi": "Mittwoch", "do": "Donnerstag", "fr": "Freitag",
             "sa": "Samstag", "so": "Sonntag"}


def erinnerung_pruefen(e):
    """Eine Erinnerung: jeden Tag oder an Wochentagen (`tage`), oder einmalig an einem `datum` (JJJJ-MM-TT)."""
    zeit = str(e.get("zeit") or "")
    text = str(e.get("text") or "").strip()[:120]
    tage = [t for t in e.get("tage", []) if t in TAGE] if isinstance(e.get("tage"), list) else []
    if not UHRZEIT.match(zeit) or not text:
        raise ValueError("Bitte Uhrzeit (z. B. 08:00) und einen Text angeben.")
    datum = e.get("datum") or None
    if datum is not None:
        try:
            datum = date.fromisoformat(str(datum)).isoformat()
        except ValueError:
            raise ValueError("Das Datum bitte als JJJJ-MM-TT angeben, z. B. 2026-11-24.")
    return {"id": str(e.get("id") or uuid.uuid4().hex[:10]), "zeit": zeit, "text": text,
            "tage": sorted(TAGE) if datum or not tage else tage, "aktiv": bool(e.get("aktiv", True)), "datum": datum}


def erinnerungen_lesen():
    """Alle Erinnerungen. Einmalige, deren Tag vorbei ist, fallen weg."""
    heute = jetzt().strftime("%Y-%m-%d")
    return [e for e in lesen("erinnerungen", []) if not e.get("datum") or e["datum"] >= heute]


def erinnerung_wann(e):
    if e.get("datum"):
        return f"einmal am {e['datum']} um {e['zeit']}"
    if len(e["tage"]) == 7:
        return f"jeden Tag um {e['zeit']}"
    return f"jeden {', '.join(TAG_NAMEN[t] for t in TAGE_REIHE if t in e['tage'])} um {e['zeit']}"


TAGE_REIHE = ["mo", "di", "mi", "do", "fr", "sa", "so"]


# ---------- Werkzeuge: so schreibt sich Biko Erinnerungen selbst auf ----------

def erinnerung_merken(eingabe):
    neu = erinnerung_pruefen({k: eingabe.get(k) for k in ("text", "zeit", "datum", "tage")})
    j = jetzt()
    if neu["datum"] and (neu["datum"], neu["zeit"]) < (j.strftime("%Y-%m-%d"), j.strftime("%H:%M")):
        raise ValueError(f"Dieser Zeitpunkt ist schon vorbei. Jetzt ist {j.strftime('%Y-%m-%d %H:%M')}.")
    with _lock:
        liste = erinnerungen_lesen()
        if len(liste) >= MAX_ERINNERUNGEN:
            raise ValueError(f"Es sind schon {MAX_ERINNERUNGEN} Erinnerungen gespeichert. Erst muss eine gelöscht werden.")
        schreiben("erinnerungen", sorted(liste + [neu], key=lambda e: e["zeit"]))
    return f"Gespeichert: {erinnerung_wann(neu)}: {neu['text']}"


def erinnerung_loeschen(eingabe):
    nr = str(eingabe.get("id") or "")
    with _lock:
        liste = erinnerungen_lesen()
        weg = [e for e in liste if e["id"] == nr]
        if not weg:
            raise ValueError("Unter dieser Nummer ist nichts gespeichert. Die Nummern stehen in deiner Liste.")
        schreiben("erinnerungen", [e for e in liste if e["id"] != nr])
    return f"Gelöscht: {erinnerung_wann(weg[0])}: {weg[0]['text']}"


# ---------- Werkzeuge: so merkt sich Biko, was er über die Person weiß ----------

def wissen_merken(eingabe):
    text = " ".join(str(eingabe.get("text") or "").split())[:400]
    if not text:
        raise ValueError("Bitte kurz aufschreiben, was du dir merken willst.")
    with _lock:
        liste = wissen_lesen()
        if any(w["text"].casefold() == text.casefold() for w in liste):
            return f"Das weißt du schon: {text}"
        if len(liste) >= MAX_WISSEN:
            raise ValueError(f"Es sind schon {MAX_WISSEN} Einträge. Streich erst einen alten oder unwichtigen.")
        schreiben("wissen", liste + [{"id": uuid.uuid4().hex[:10], "text": text,
                                      "zeit": jetzt().isoformat(timespec="seconds")}])
    return f"Gemerkt: {text}"


def wissen_vergessen(eingabe):
    nr = str(eingabe.get("id") or "")
    with _lock:
        liste = wissen_lesen()
        weg = [w for w in liste if w["id"] == nr]
        if not weg:
            raise ValueError("Unter dieser Nummer ist nichts gespeichert. Die Nummern stehen in deiner Liste.")
        schreiben("wissen", [w for w in liste if w["id"] != nr])
    return f"Gestrichen: {weg[0]['text']}"


# ---------- Morgenrunde: Biko meldet sich jeden Morgen von selbst ----------

MORGEN_VORHER = 15 * 60   # so viele Sekunden vor der Uhrzeit bereitet Biko die Morgenrunde vor
MORGEN_NACHHER = 2 * 3600  # war der Server so lange weg, holt er sie noch nach, danach erst morgen wieder
_morgen_lock = threading.Lock()

MORGENRUNDE = """<app>
Es ist Zeit für deine Morgenrunde. Schreib, was du der Person gleich von selbst sagst, so wie man es vorliest:
- eine herzliche Begrüßung (mit Namen, wenn du ihn kennst),
- das Wetter in Wien heute in einem Satz (such kurz danach),
- zwei oder drei kurze Nachrichten von heute, die sie interessieren (siehe was du über sie weißt; sonst das Wichtigste
  aus Wien und Österreich, nichts Grausiges), jede in einem Satz, ohne Links,
- ihre Erinnerungen für heute, falls es welche gibt,
- zum Schluss eine Frage, über die ihr reden könnt.
Insgesamt 5 bis 8 kurze Sätze, keine Listen, keine Überschriften, in ihrer Sprache.
</app>"""


def morgenrunde_zeit():
    return lesen("morgenrunde", {}).get("zeit")


def morgenrunde_einstellen(eingabe):
    zeit = str(eingabe.get("zeit") or "").strip().lower()
    if zeit in ("aus", "off", "nein", ""):
        with _lock:
            schreiben("morgenrunde", {**lesen("morgenrunde", {}), "zeit": None})
        return "Die Morgenrunde ist abgestellt."
    if not UHRZEIT.match(zeit):
        raise ValueError("Bitte die Uhrzeit als HH:MM angeben, z. B. 08:00, oder 'aus'.")
    with _lock:   # `seit`: eine Uhrzeit, die heute schon vorbei ist, gilt erst ab morgen
        schreiben("morgenrunde", {**lesen("morgenrunde", {}), "zeit": zeit, "seit": jetzt().isoformat(timespec="seconds")})
    return f"Eingestellt: jeden Tag um {zeit} Uhr. Die erste Morgenrunde kommt beim nächsten Mal um {zeit}."


def morgenrunde_faellig(t=None):
    """Ist heute die Zeit für die Vorbereitung gekommen? Liefert (datum, zeit) oder None."""
    daten = lesen("morgenrunde", {})
    zeit = daten.get("zeit")
    if not zeit:
        return None
    t = t or jetzt()
    h, m = map(int, zeit.split(":"))
    um = t.replace(hour=h, minute=m, second=0, microsecond=0)
    if not -MORGEN_NACHHER <= (um - t).total_seconds() <= MORGEN_VORHER:
        return None
    try:
        seit = datetime.fromisoformat(daten.get("seit") or "")
    except ValueError:
        seit = None
    if seit and seit > um:   # eingestellt, als die Zeit heute schon vorbei war
        return None
    return t.strftime("%Y-%m-%d"), zeit


def morgenrunde_heute(erzeugen=False):
    """Die Morgenrunde von heute ({"datum", "zeit", "text", "gespraech"}) oder None. Mit `erzeugen` schreibt Biko sie,
    wenn sie fällig ist und noch fehlt (dauert ein paar Sekunden, weil er nach Wetter und Nachrichten sucht)."""
    heute = jetzt().strftime("%Y-%m-%d")
    fertig = lesen("morgenrunde", {}).get("heute")
    if fertig and fertig.get("datum") == heute:
        return fertig
    if not erzeugen or not morgenrunde_faellig():
        return None
    with _morgen_lock:   # nur einmal schreiben, auch wenn zwei Anfragen gleichzeitig kommen
        fertig = lesen("morgenrunde", {}).get("heute")
        if fertig and fertig.get("datum") == heute:
            return fertig
        try:
            text = frage_claude(system_prompt(), [{"role": "user", "content": [
                {"type": "text", "text": hinweis()}, {"type": "text", "text": MORGENRUNDE}]}],
                websuche=True, modell=EINFACH_MODELL)
        except RuntimeError as e:
            protokoll(f"Morgenrunde ging nicht: {e}")
            name = profil()["name"].strip()
            text = f"Guten Morgen{', ' + name if name else ''}! Ich bin da, wenn du mich brauchst."
        zeit = jetzt().isoformat(timespec="seconds")
        with _lock:
            g = gespraech_neu([{"von": "biko", "text": text, "zeit": zeit, "vonselbst": "morgenrunde"}])
            g["titel"] = "早安" if profil()["sprache"].startswith("zh") else "Morgenrunde"
            schreiben("gespraeche", ([g] + gespraeche_lesen())[:MAX_GESPRAECHE])
            fertig = {"datum": heute, "zeit": morgenrunde_zeit(), "text": text, "gespraech": g["id"]}
            schreiben("morgenrunde", {**lesen("morgenrunde", {}), "heute": fertig})
        protokoll("Morgenrunde für heute ist fertig.")
        return fertig


def hausmeister():
    """Läuft im Hintergrund: bereitet die Morgenrunde rechtzeitig vor."""
    while True:
        try:
            morgenrunde_heute(erzeugen=True)
        except Exception as e:   # der Hausmeister darf nie stehen bleiben
            protokoll(f"Hausmeister-Fehler: {type(e).__name__}")
        time.sleep(60)


WERKZEUGE = {
    "morgenrunde_einstellen": {"tun": morgenrunde_einstellen, "schema": {
        "name": "morgenrunde_einstellen",
        "description": "Stellt ein, um wie viel Uhr du dich jeden Morgen von selbst meldest (Wetter, Nachrichten, "
                       "Termine des Tages), oder stellt es ab.",
        "input_schema": {
            "type": "object",
            "properties": {"zeit": {"type": "string", "description": "Uhrzeit HH:MM, z. B. 08:00, oder 'aus'."}},
            "required": ["zeit"],
        },
    }},
    "wissen_merken": {"tun": wissen_merken, "schema": {
        "name": "wissen_merken",
        "description": "Schreibt etwas Bleibendes über die Person auf (Gesundheit, Diät, Familie, Vorlieben). "
                       "Du weißt es dann in allen künftigen Gesprächen.",
        "input_schema": {
            "type": "object",
            "properties": {"text": {"type": "string", "description": "Ein kurzer Satz in der Sprache der Person, "
                                                                    "z. B. 'Darf wegen Diabetes wenig Zucker essen'."}},
            "required": ["text"],
        },
    }},
    "wissen_vergessen": {"tun": wissen_vergessen, "schema": {
        "name": "wissen_vergessen",
        "description": "Streicht einen Eintrag aus deinem Wissen über die Person. Die Nummer steht in deiner Liste.",
        "input_schema": {
            "type": "object",
            "properties": {"id": {"type": "string", "description": "Nummer des Eintrags aus der Liste."}},
            "required": ["id"],
        },
    }},
    "erinnerung_merken": {"tun": erinnerung_merken, "schema": {
        "name": "erinnerung_merken",
        "description": "Schreibt eine Erinnerung auf. Die App meldet sich dann zur Uhrzeit groß mit Ton. "
                       "Für einmalige Erinnerungen `datum` setzen, für regelmäßige `tage` (weglassen heißt jeden Tag).",
        "input_schema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Woran erinnert wird, kurz und in der Sprache der Person, z. B. 'Blutdrucktablette nehmen'."},
                "zeit": {"type": "string", "description": "Uhrzeit im 24-Stunden-Format HH:MM, z. B. 08:00."},
                "datum": {"type": "string", "description": "Nur für einmalige Erinnerungen: der Tag als JJJJ-MM-TT."},
                "tage": {"type": "array", "items": {"type": "string", "enum": TAGE_REIHE},
                         "description": "Nur für regelmäßige Erinnerungen an bestimmten Wochentagen."},
            },
            "required": ["text", "zeit"],
        },
    }},
    "erinnerung_loeschen": {"tun": erinnerung_loeschen, "schema": {
        "name": "erinnerung_loeschen",
        "description": "Streicht eine gemerkte Erinnerung. Die Nummer steht in deiner Liste der Erinnerungen.",
        "input_schema": {
            "type": "object",
            "properties": {"id": {"type": "string", "description": "Nummer der Erinnerung aus der Liste."}},
            "required": ["id"],
        },
    }},
}


# ---------- HTTP ----------

def cookie_wert():
    zeit = str(int(time.time()))
    sig = hmac.new(geheimnis().encode(), zeit.encode(), hashlib.sha256).hexdigest()
    return f"{zeit}.{sig}"


def cookie_ok(wert):
    try:
        zeit, sig = wert.split(".", 1)
        gut = hmac.new(geheimnis().encode(), zeit.encode(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(sig, gut) and time.time() - int(zeit) < COOKIE_TAGE * 86400
    except (ValueError, AttributeError):
        return False


# Fehlermeldungen auf Chinesisch (die App schickt X-Sprache: zh-CN)
ZH = {
    "Der Schlüssel für die KI fehlt oder stimmt nicht. Bitte Niko Bescheid geben.": "AI 密钥缺失或不正确。请告诉 Niko。",
    "Gerade sind zu viele Anfragen. Bitte in einer Minute nochmal probieren.": "现在请求太多了。请一分钟后再试。",
    "Biko kann gerade nicht antworten. Bitte gleich nochmal probieren.": "Biko 现在无法回答。请稍后再试。",
    "Keine Verbindung zur KI. Ist das Internet am Server da?": "无法连接到 AI。服务器有网络吗？",
    "Bitte Uhrzeit (z. B. 08:00) und einen Text angeben.": "请填写时间（例如 08:00）和内容。",
    "Zu viel Text auf einmal.": "一次文字太多了。",
    "Das hat nicht geklappt, bitte nochmal.": "没有成功，请再试一次。",
    "Bitte anmelden.": "请先登录。",
    "Gibt es nicht.": "不存在。",
    "Bitte etwas Kürzeres schreiben.": "请写短一点。",
    "Höchstens 30 Erinnerungen.": "最多 30 个提醒。",
    "Zu viele Versuche. Bitte in 15 Minuten nochmal.": "尝试次数太多。请 15 分钟后再试。",
    "Am Server ist noch kein Passwort eingestellt (APP_PASSWORT).": "服务器还没有设置密码（APP_PASSWORT）。",
    "Das Passwort stimmt nicht.": "密码不对。",
    "Der Sprachdienst ist nicht eingerichtet.": "语音服务还没有设置好。",
    "Der Schlüssel für die Stimme fehlt, stimmt nicht oder das Guthaben ist aufgebraucht. Bitte Niko Bescheid geben.":
        "语音服务的密钥缺失、不正确，或者余额用完了。请告诉 Niko。",
    "Die Stimme geht gerade nicht. Bitte gleich nochmal probieren.": "语音现在用不了。请稍后再试。",
    "Der Sprachdienst ist gerade nicht erreichbar.": "现在连不上语音服务。",
    "Die Aufnahme ist zu lang. Bitte kürzer sprechen.": "录音太长了。请说短一点。",
}

TYPEN = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
         ".css": "text/css; charset=utf-8", ".svg": "image/svg+xml",
         ".webmanifest": "application/manifest+json", ".png": "image/png", ".woff2": "font/woff2",
         ".mp3": "audio/mpeg"}

_fehlversuche = {}


class Handler(BaseHTTPRequestHandler):
    server_version = "Biko"
    sys_version = ""

    def log_message(self, fmt, *args):
        # Keine Inhalte loggen (Privatsphäre), nur Methode, Pfad und Status
        if "/api/" in self.path:
            print(f"{self.command} {self.path.split('?')[0]} {args[1] if len(args) > 1 else ''}", flush=True)

    # --- Helfer ---
    def uebersetzt(self, daten):
        """Fehlermeldungen auf Chinesisch, wenn die App so eingestellt ist."""
        if isinstance(daten, dict) and "fehler" in daten and (self.headers.get("X-Sprache") or "").startswith("zh"):
            return {**daten, "fehler": ZH.get(daten["fehler"], daten["fehler"])}
        return daten

    def senden(self, status, daten=None, typ="application/json; charset=utf-8", extra=None):
        daten = self.uebersetzt(daten)
        body = daten if isinstance(daten, bytes) else json.dumps(daten, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", typ)
        self.send_header("Content-Length", str(len(body)))
        self.kopf_ende(typ, extra)
        self.wfile.write(body)

    def strom_beginnen(self, typ):
        """Eine Antwort ohne bekannte Länge: sie geht Stück für Stück hinaus, am Ende schließt die Verbindung."""
        self.send_response(200)
        self.send_header("Content-Type", typ)
        self.send_header("X-Accel-Buffering", "no")   # Proxys sollen nichts sammeln, jedes Stück geht gleich weiter
        self.close_connection = True
        self.kopf_ende(typ)

    def strom_schreiben(self, stueck):
        """Schreibt ein Stück. Ist die App schon weg (aufgelegt, Netz weg), passiert einfach nichts mehr."""
        if getattr(self, "_weg", False):
            return False
        try:
            self.wfile.write(stueck)
            self.wfile.flush()
            return True
        except OSError:
            self._weg = True
            return False

    def kopf_ende(self, typ, extra=None):
        if typ.startswith("application/json") or self.path.startswith("/api/"):
            cache = "no-store"   # Antworten und vorgelesener Ton werden nirgends zwischengespeichert
        elif typ == "font/woff2":
            cache = "public, max-age=31536000, immutable"  # Schriften ändern sich nie
        else:
            cache = "no-cache"
        self.send_header("Cache-Control", cache)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Content-Security-Policy",
                         "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; "
                         f"connect-src 'self' {LIVE_ADRESSE}; media-src 'self' blob:; frame-ancestors 'none'; base-uri 'none'; "
                         "form-action 'self'")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()

    def json_body(self):
        n = int(self.headers.get("Content-Length") or 0)
        if n > 20000:
            raise ValueError("Zu viel Text auf einmal.")
        try:
            daten = json.loads(self.rfile.read(n) or b"{}")
        except ValueError:
            raise ValueError("Das hat nicht geklappt, bitte nochmal.")
        if not isinstance(daten, dict):
            raise ValueError("Das hat nicht geklappt, bitte nochmal.")
        return daten

    def angemeldet(self):
        for teil in (self.headers.get("Cookie") or "").split(";"):
            k, _, v = teil.strip().partition("=")
            if k == COOKIE and cookie_ok(v):
                return True
        return False

    def ip(self):
        # Letzter Eintrag: den setzt der eigene Proxy (Tailscale), frühere kann ein Angreifer fälschen
        return self.headers.get("X-Forwarded-For", self.client_address[0]).split(",")[-1].strip()

    # --- Routen ---
    def do_GET(self):
        pfad = self.path.split("?")[0]
        if pfad == "/api/status":
            return self.senden(200, {"angemeldet": self.angemeldet(), "passwort_gesetzt": bool(PASSWORT),
                                     "sprachdienst": bool(SPRACH_KEY)})
        if pfad.startswith("/api/"):
            if not self.angemeldet():
                return self.senden(401, {"fehler": "Bitte anmelden."})
            if pfad == "/api/profil":
                return self.senden(200, profil())
            if pfad == "/api/erinnerungen":
                return self.senden(200, erinnerungen_lesen())
            if pfad == "/api/wissen":
                return self.senden(200, wissen_lesen())
            if pfad == "/api/morgenrunde":
                # ?jetzt: ist sie fällig und noch nicht fertig, schreibt Biko sie gleich (sonst macht das der Hausmeister)
                return self.senden(200, {"zeit": morgenrunde_zeit(), "heute": morgenrunde_heute(erzeugen="jetzt" in parse_qs(urlparse(self.path).query, keep_blank_values=True))})
            if pfad == "/api/gespraeche":
                with _lock:
                    return self.senden(200, [uebersicht(g) for g in gespraeche_lesen()])
            if pfad == "/api/gespraech":
                nr = (parse_qs(urlparse(self.path).query).get("id") or [""])[0]
                with _lock:
                    g = gespraech_finden(gespraeche_lesen(), nr)
                return self.senden(200, g) if g else self.senden(404, {"fehler": "Gibt es nicht."})
            return self.senden(404, {"fehler": "Gibt es nicht."})
        return self.datei(pfad)

    def do_POST(self):
        pfad = self.path.split("?")[0]
        try:
            if pfad == "/api/zuhoeren":
                return self.zuhoeren()
            if pfad == "/api/bildschirm":
                return self.bildschirm()
            daten = self.json_body()
            if pfad == "/api/login":
                return self.login(daten)
            if not self.angemeldet():
                return self.senden(401, {"fehler": "Bitte anmelden."})
            if pfad == "/api/chat":
                text = str(daten.get("text", "")).strip()
                if not text or len(text) > MAX_TEXT:
                    raise ValueError("Bitte etwas Kürzeres schreiben.")
                nr, gesprochen = str(daten.get("gespraech") or ""), daten.get("gesprochen") is True
                if daten.get("strom") is True:
                    return self.chat_strom(text, nr, gesprochen)
                return self.senden(200, chat(text, nr, gesprochen=gesprochen))
            if pfad == "/api/stimme":
                text = str(daten.get("text", "")).strip()
                if not text:
                    raise ValueError("Das hat nicht geklappt, bitte nochmal.")
                return self.stimme_strom(ton_strom(text, str(daten.get("vorher") or "")))
            if pfad == "/api/live-zugang":
                return self.senden(200, live_zugang())
            if pfad == "/api/vorlesen":
                text = str(daten.get("text", "")).strip()
                if not text:
                    raise ValueError("Das hat nicht geklappt, bitte nochmal.")
                return self.senden(200, ton_holen(text), "audio/mpeg")
            if pfad == "/api/gespraech/loeschen":
                with _lock:
                    rest = [g for g in gespraeche_lesen() if g["id"] != str(daten.get("id") or "")]
                    schreiben("gespraeche", rest)
                return self.senden(200, [uebersicht(g) for g in rest])
            if pfad == "/api/verlauf/loeschen":
                with _lock:
                    schreiben("gespraeche", [])
                    _pfad("verlauf").unlink(missing_ok=True)
                return self.senden(200, {"ok": True})
            if pfad == "/api/wissen/loeschen":
                try:
                    wissen_vergessen(daten)
                except ValueError:
                    pass   # schon weg, zum Beispiel auf einem zweiten Handy gelöscht
                return self.senden(200, wissen_lesen())
            if pfad == "/api/profil":
                wissen_lesen()   # alte Felder Diät und Notizen vorher übernehmen, sonst gingen sie hier verloren
                neu = {k: str(daten.get(k, "")).strip()[:1500] for k in STANDARD_PROFIL}
                neu["anrede"] = "Sie" if neu["anrede"] == "Sie" else "du"
                neu["sprache"] = neu["sprache"] if neu["sprache"] in SPRACHEN else "de-AT"
                with _lock:
                    schreiben("profil", neu)
                return self.senden(200, neu)
            if pfad == "/api/erinnerungen":
                liste = daten.get("erinnerungen")
                if not isinstance(liste, list) or len(liste) > MAX_ERINNERUNGEN:
                    raise ValueError("Höchstens 30 Erinnerungen.")
                liste = sorted((erinnerung_pruefen(e) for e in liste), key=lambda e: e["zeit"])
                with _lock:
                    schreiben("erinnerungen", liste)
                return self.senden(200, liste)
            return self.senden(404, {"fehler": "Gibt es nicht."})
        except ValueError as e:
            return self.senden(400, {"fehler": str(e)})
        except RuntimeError as e:
            return self.senden(503, {"fehler": str(e)})

    def chat_strom(self, text, nr, gesprochen):
        """Die Antwort als Server-Sent Events: {"text": ...} für jedes neue Stück, am Ende {"fertig": ...} mit allem,
        was sonst /api/chat liefert, oder {"fehler": ...}. Legt die App vorher auf, wird die Antwort trotzdem fertig
        geschrieben und gespeichert."""
        self.strom_beginnen("text/event-stream; charset=utf-8")
        ereignis = lambda d: self.strom_schreiben(f"data: {json.dumps(d, ensure_ascii=False)}\n\n".encode())
        try:
            ergebnis = chat(text, nr, beim_text=lambda stueck: ereignis({"text": stueck}), gesprochen=gesprochen)
            ereignis({"fertig": ergebnis})
        except (ValueError, RuntimeError) as e:
            ereignis(self.uebersetzt({"fehler": str(e)}))

    def stimme_strom(self, stuecke):
        """Der Ton geht roh hinaus, sobald der Sprachdienst ihn liefert: die App spielt das erste Stück schon ab,
        während der Rest noch entsteht."""
        self.strom_beginnen("application/octet-stream")
        try:
            for stueck in stuecke:
                if not self.strom_schreiben(stueck):
                    break   # die App hört nicht mehr zu (unterbrochen oder aufgelegt)
        except OSError:
            protokoll("Sprachdienst-Fehler: Verbindung beim Sprechen abgebrochen")

    def zuhoeren(self):
        """Die Aufnahme aus dem Mikrofon kommt als roher Ton an und geht als Text zurück."""
        n = int(self.headers.get("Content-Length") or 0)
        if n > MAX_AUFNAHME:
            raise ValueError("Die Aufnahme ist zu lang. Bitte kürzer sprechen.")
        ton = self.rfile.read(n)
        if not self.angemeldet():
            return self.senden(401, {"fehler": "Bitte anmelden."})
        if not SPRACH_KEY:
            raise RuntimeError("Der Sprachdienst ist nicht eingerichtet.")
        art = (self.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        if not ton or art not in AUFNAHME_ARTEN:
            raise ValueError("Das hat nicht geklappt, bitte nochmal.")
        return self.senden(200, text_hoeren(ton, art))

    def bildschirm(self):
        """Die Android-App schickt, was gerade auf dem Bildschirm ist (JPEG). Biko sieht es bei den nächsten Fragen."""
        n = int(self.headers.get("Content-Length") or 0)
        if n > MAX_BILDSCHIRM:
            raise ValueError("Das Bild ist zu groß.")
        bild = self.rfile.read(n)
        if not self.angemeldet():
            return self.senden(401, {"fehler": "Bitte anmelden."})
        if not bild.startswith(b"\xff\xd8"):
            raise ValueError("Das hat nicht geklappt, bitte nochmal.")
        bildschirm_merken(bild)
        protokoll(f"Bildschirm: {len(bild) // 1000} kB bekommen")
        return self.senden(200, {"ok": True})

    def login(self, daten):
        ip = self.ip()
        versuche = [t for t in _fehlversuche.get(ip, []) if time.time() - t < 900]
        if len(versuche) >= 5:
            return self.senden(429, {"fehler": "Zu viele Versuche. Bitte in 15 Minuten nochmal."})
        if not PASSWORT:
            return self.senden(503, {"fehler": "Am Server ist noch kein Passwort eingestellt (APP_PASSWORT)."})
        if not hmac.compare_digest(str(daten.get("passwort", "")).encode(), PASSWORT.encode()):
            versuche.append(time.time())
            _fehlversuche[ip] = versuche
            return self.senden(403, {"fehler": "Das Passwort stimmt nicht."})
        _fehlversuche.pop(ip, None)
        sicher = "; Secure" if self.headers.get("X-Forwarded-Proto") == "https" else ""
        cookie = f"{COOKIE}={cookie_wert()}; Max-Age={COOKIE_TAGE * 86400}; Path=/; HttpOnly; SameSite=Strict{sicher}"
        return self.senden(200, {"ok": True}, extra={"Set-Cookie": cookie})

    def datei(self, pfad):
        if pfad in ("", "/"):
            pfad = "/index.html"
        ziel = (WEB / pfad.lstrip("/")).resolve()
        if not str(ziel).startswith(str(WEB.resolve())) or not ziel.is_file():
            ziel = WEB / "index.html"
        return self.senden(200, ziel.read_bytes(), TYPEN.get(ziel.suffix, "application/octet-stream"))


if __name__ == "__main__":
    if not PASSWORT:
        print("Achtung: APP_PASSWORT ist nicht gesetzt, Anmelden geht erst danach.", flush=True)
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("Achtung: ANTHROPIC_API_KEY ist nicht gesetzt, Biko kann noch nicht antworten.", flush=True)
    print(f"Biko Assistent läuft auf Port {PORT}, Modell {MODELL}", flush=True)
    threading.Thread(target=hausmeister, daemon=True).start()
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
