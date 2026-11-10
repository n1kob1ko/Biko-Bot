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
Nachrichten, Links und Erinnerungen sind Werkzeuge, die Claude selbst aufruft.

Stimme: Mit einem Schlüssel für den Sprachdienst (ELEVENLABS_API_KEY) liest Biko mit einer natürlichen Stimme vor
(POST /api/vorlesen) und versteht Gesprochenes in jeder Sprache (POST /api/zuhoeren, die Aufnahme als Ton).
Ohne Schlüssel sprechen und hören die Browser der Handys selbst, so gut sie können.

Dazu ein Profil (GET/POST /api/profil): Name, Diät-Regeln, Notizen. Biko liest es bei jeder Antwort mit.

Anmelden: ein Passwort (APP_PASSWORT in der .env). Danach bleibt das Handy ein Jahr angemeldet (Cookie).
Daten liegen als JSON in DATA_DIR (Standard /data). Nach außen gehen nur die Texte an die Claude-API und, wenn
der Sprachdienst eingerichtet ist, vorzulesende Texte und Aufnahmen an ElevenLabs.
Nur Python-Standardbibliothek plus das offizielle anthropic-Paket.
"""

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
MODELL = os.environ.get("ASSISTENT_MODELL", "claude-opus-5-5")
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
MAX_VORLESEN = 2500       # so viele Zeichen werden höchstens vorgelesen
MAX_AUFNAHME = 6_000_000  # Bytes; eine Minute Sprechen ist etwa 1 MB
COOKIE = "biko_assistent"
COOKIE_TAGE = 365

DATA.mkdir(parents=True, exist_ok=True)
_lock = threading.Lock()
_client = None

STANDARD_PROFIL = {
    "name": "",
    "anrede": "du",          # "du" oder "Sie"
    "sprache": "de-AT",      # Sprache für Sprechen/Vorlesen und wenn unklar ist, wie Biko antworten soll
    "diaet": "",             # z. B. "wenig Zucker, kein Weißbrot, viel Gemüse"
    "notizen": "",           # z. B. "Enkel heißt Niko, Hund heißt Bello, hört schlecht"
}

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
- Bei Fragen zum Essen und zur Diät hilfst du anhand der Diät-Regeln unten. Sag klar "passt gut", "lieber wenig" oder
  "lieber nicht", mit einem kurzen Grund. Wenn keine Regeln hinterlegt sind, gib nur allgemeine, vorsichtige Hinweise.
- Bei Notfällen (Brustschmerzen, Atemnot, Sturz, plötzliche Lähmung oder Verwirrtheit): sofort sagen, die Rettung 144 anzurufen.
- Bei Unsicherheit zu Beschwerden: Gesundheitsnummer 1450 (rund um die Uhr, kostenlos).
- Wenn jemand sehr traurig ist oder an Suizid denkt: einfühlsam bleiben und die Telefonseelsorge 142 nennen (kostenlos, rund um die Uhr).

Sicherheit:
- Warne vor Betrug, wenn etwas danach klingt (Anrufe von "Polizei" oder "Bank", Gewinnspiele, "Enkeltrick", Links in SMS).
  Nie Passwörter, PINs oder TANs weitergeben.

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
- Auf "Woran erinnerst du mich?" liest du die Liste unten in einfachen Worten vor.
Das hast du dir schon gemerkt:
{erinnerungen}

Was du über die Person weißt (von der Familie eingetragen):
- Diät-Regeln: {diaet}
- Notizen: {notizen}

Heute ist {datum}, es ist {uhrzeit} Uhr."""

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
    return {**STANDARD_PROFIL, **lesen("profil", {})}


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


def werkzeug_ergebnis(block, werkzeuge):
    """Führt ein von Claude gewünschtes Werkzeug aus. Fehler gehen als Text zurück, damit Claude nachfragen kann."""
    try:
        if block.name not in werkzeuge:
            raise ValueError("Dieses Werkzeug gibt es nicht.")
        inhalt = werkzeuge[block.name]["tun"](block.input if isinstance(block.input, dict) else {})
        return {"type": "tool_result", "tool_use_id": block.id, "content": inhalt}
    except ValueError as e:
        return {"type": "tool_result", "tool_use_id": block.id, "content": f"Fehler: {e}", "is_error": True}


def frage_claude(system, messages, max_tokens=4000, websuche=False, werkzeuge=None):
    """Eine Antwort von Claude als Text. Wirft RuntimeError mit freundlicher Meldung.
    `werkzeuge`: {name: {"schema": ..., "tun": funktion(eingabe) -> text}}, Claude darf sie selbst aufrufen."""
    global _seiten_oeffnen
    werkzeuge = werkzeuge or {}
    web = [w for w in WEBSUCHE if _seiten_oeffnen or w["name"] != "web_fetch"] if websuche else []
    tools = web + [w["schema"] for w in werkzeuge.values()]
    messages = list(messages)
    benutzt = []

    def anfrage(tools):
        return claude_anfrage(
            model=MODELL,
            max_tokens=max_tokens,
            system=system,
            messages=messages,
            # Alltagsgespräch: wenig Nachdenken reicht, ist schneller und günstiger
            output_config={"effort": "low"},
            # Falls eine Sicherheitsprüfung die Anfrage ablehnt, springt ein anderes Modell ein
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            **({"tools": tools} if tools else {}),
        )

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
    protokoll(f"Claude: {runde} Anfragen, Ende {r.stop_reason}, Werkzeuge: {', '.join(benutzt) or 'keine'}")
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


def sprachdienst(pfad, daten=None, kopf=None):
    """Fragt den Sprachdienst. Wirft RuntimeError mit freundlicher Meldung."""
    if not SPRACH_KEY:
        raise RuntimeError("Der Sprachdienst ist nicht eingerichtet.")
    try:
        return sprach_anfrage(pfad, daten, kopf)
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
    protokoll(f"Sprachdienst: {len(text)} Zeichen vorgelesen")
    return ton


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


def system_prompt():
    p = profil()
    t = jetzt()
    tage = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]
    return SYSTEM.format(
        name_satz=p["name"].strip() or "einer Person, deren Namen du noch nicht kennst",
        anrede="Sie" if p.get("anrede") == "Sie" else "du",
        sprache=SPRACHEN.get(p.get("sprache"), "Deutsch"),
        erinnerungen="\n".join(f"- Nummer {e['id']}: {erinnerung_wann(e)}: {e['text']}" for e in erinnerungen_lesen())
                     or "- noch nichts",
        diaet=p["diaet"].strip() or "keine eingetragen",
        notizen=p["notizen"].strip() or "keine",
        datum=f"{tage[t.weekday()]}, {t.day}.{t.month}.{t.year}",
        uhrzeit=t.strftime("%H:%M"),
    )


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


def fuer_claude(nachrichten):
    """Das bisherige Gespräch so, wie Claude es lesen soll. Eine Nachricht, die Biko für jemanden geschrieben hat,
    steht wieder als Werkzeug-Aufruf da: so weiß er bei "mach sie kürzer" noch, was drinstand."""
    nachrichten = nachrichten[-(MAX_VERLAUF - 1):]
    while nachrichten and nachrichten[0]["von"] != "ich":   # muss mit der Person beginnen
        nachrichten = nachrichten[1:]
    messages = []
    for i, m in enumerate(nachrichten):
        if m["von"] == "ich":
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


def chat(text, gespraech_nr=""):
    with _lock:
        g = gespraech_finden(gespraeche_lesen(), gespraech_nr)
    messages = fuer_claude(g["nachrichten"] if g else []) + [{"role": "user", "content": text}]
    zeigen, entwuerfe, links = zeige_werkzeuge()
    vorher = erinnerungen_lesen()
    antwort = frage_claude(system_prompt(), messages, websuche=True, werkzeuge={**WERKZEUGE, **zeigen})
    # Was Biko in dieser Antwort wirklich getan hat: die App zeigt es unter der Antwort, auch beim Wiederöffnen
    nachher = erinnerungen_lesen()
    alt, neu = {e["id"] for e in vorher}, {e["id"] for e in nachher}
    getan = {"gemerkt": [e for e in nachher if e["id"] not in alt],
             "vergessen": [e for e in vorher if e["id"] not in neu],
             "nachrichten": entwuerfe, "links": links}
    zeit = jetzt().isoformat(timespec="seconds")
    with _lock:   # erst jetzt speichern: geht die Antwort schief, bleibt das Gespräch, wie es war
        liste = gespraeche_lesen()
        g = gespraech_finden(liste, gespraech_nr) or gespraech_neu([])
        g["nachrichten"] = (g["nachrichten"] + [
            {"von": "ich", "text": text, "zeit": zeit},
            {"von": "biko", "text": antwort, "zeit": zeit, **{k: v for k, v in getan.items() if v}},
        ])[-MAX_GESPEICHERT:]
        g["titel"] = g["titel"] or titel_aus(text)
        g["zuletzt"] = zeit
        schreiben("gespraeche", ([g] + [x for x in liste if x["id"] != g["id"]])[:MAX_GESPRAECHE])
    return {"antwort": antwort, "gespraech": uebersicht(g), "erinnerungen": nachher, **getan}


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


WERKZEUGE = {
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
    def senden(self, status, daten=None, typ="application/json; charset=utf-8", extra=None):
        if isinstance(daten, dict) and "fehler" in daten and (self.headers.get("X-Sprache") or "").startswith("zh"):
            daten = {**daten, "fehler": ZH.get(daten["fehler"], daten["fehler"])}
        body = daten if isinstance(daten, bytes) else json.dumps(daten, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", typ)
        self.send_header("Content-Length", str(len(body)))
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
                         "connect-src 'self'; media-src 'self' blob:; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

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
            daten = self.json_body()
            if pfad == "/api/login":
                return self.login(daten)
            if not self.angemeldet():
                return self.senden(401, {"fehler": "Bitte anmelden."})
            if pfad == "/api/chat":
                text = str(daten.get("text", "")).strip()
                if not text or len(text) > MAX_TEXT:
                    raise ValueError("Bitte etwas Kürzeres schreiben.")
                return self.senden(200, chat(text, str(daten.get("gespraech") or "")))
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
            if pfad == "/api/profil":
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
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
