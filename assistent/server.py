"""
Biko Assistent: kleiner KI-Helfer für den Alltag, vor allem für ältere Menschen.

Drei Funktionen in der ersten Version:
  1. Reden und fragen   (POST /api/chat)       Gespräch mit Biko, merkt sich die letzten Nachrichten
  2. Nachricht schreiben (POST /api/nachricht) macht aus ein paar Stichworten eine nette SMS/WhatsApp
  3. Erinnerungen       (GET/POST /api/erinnerungen) Medikamente, Termine; die App meldet sich zur Uhrzeit

Dazu ein Profil (GET/POST /api/profil): Name, Diät-Regeln, Notizen. Biko liest es bei jeder Antwort mit.

Anmelden: ein Passwort (APP_PASSWORT in der .env). Danach bleibt das Handy ein Jahr angemeldet (Cookie).
Daten liegen als JSON in DATA_DIR (Standard /data), nichts geht außer an die Claude-API raus.
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
import uuid
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from zoneinfo import ZoneInfo

import anthropic

PORT = int(os.environ.get("PORT", "8092"))
DATA = Path(os.environ.get("DATA_DIR", "/data"))
WEB = Path(os.environ.get("WEB_DIR", Path(__file__).parent / "web"))
PASSWORT = os.environ.get("APP_PASSWORT", "")
MODELL = os.environ.get("ASSISTENT_MODELL", "claude-opus-5-5")
ZEITZONE = ZoneInfo(os.environ.get("TZ", "Europe/Vienna"))
MAX_VERLAUF = 30          # so viele Nachrichten merkt sich Biko im Gespräch
MAX_TEXT = 2000           # längere Eingaben werden abgelehnt
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
- Einfache, warme Sprache (auf Deutsch gern österreichisch freundlich) (österreichisch freundlich ist gut), kurze Sätze, keine Fachwörter, keine Anglizismen.
- Du sprichst die Person mit "{anrede}" an.
- Kurze Antworten: meistens 2 bis 5 Sätze. Bei Anleitungen nummerierte Schritte, höchstens 5.
- Kein Markdown außer einfachen nummerierten Listen. Keine Tabellen, keine Überschriften, keine Emojis außer ganz selten einem.
- Du kannst im Internet suchen. Nutze das für aktuelle Dinge: Angebote und Deals, Preise vergleichen,
  Öffnungszeiten, Wetter, Nachrichten, Veranstaltungen. Für Plaudern und allgemeines Wissen suchst du nicht.
- Bei Deals: nenne höchstens 3 gute Angebote mit Geschäft, Preis und wie lange es gilt, am liebsten in der Nähe
  (Wien bzw. Österreich, Geschäfte wie Billa, Spar, Hofer, Lidl, dm, Bipa, MediaMarkt, asiatische Supermärkte
  wie am Naschmarkt) oder seriöse Online-Shops.
  Sag dazu, dass sich Preise ändern können. Keine langen Links vorlesen: nenne den Namen des Geschäfts.
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

Was du über die Person weißt (von der Familie eingetragen):
- Diät-Regeln: {diaet}
- Notizen: {notizen}

Heute ist {datum}, es ist {uhrzeit} Uhr."""

NACHRICHT_SYSTEM = """Du hilfst einem älteren Menschen, eine kurze Nachricht (SMS oder WhatsApp) zu schreiben.
Die Person sagt dir grob, an wen und was. Schreibe in der Sprache, in der die Person dir schreibt,
außer sie wünscht eine andere. Du schreibst die fertige Nachricht in ihrem Namen, in der Ich-Form,
freundlich, natürlich und kurz (1 bis 4 Sätze), so wie diese Person selbst schreiben würde. Passend zur Person:
an Enkel locker und herzlich, an Ärzte oder Ämter höflich mit "Sie".
Gib NUR den Text der Nachricht zurück, ohne Anführungszeichen, ohne Erklärung, ohne Betreff.
Notizen über die Person: {notizen}"""


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


# Websuche für Deals, Öffnungszeiten, aktuelle Fragen. Läuft bei Anthropic, höchstens 3 Suchen pro Frage.
WEBSUCHE = {
    "type": "web_search_20260209",
    "name": "web_search",
    "max_uses": 3,
    "user_location": {"type": "approximate", "city": "Wien", "country": "AT", "timezone": "Europe/Vienna"},
}


def frage_claude(system, messages, max_tokens=4000, websuche=False):
    """Eine Antwort von Claude als Text. Wirft RuntimeError mit freundlicher Meldung."""
    extra = {"tools": [WEBSUCHE]} if websuche else {}
    messages = list(messages)
    try:
        for _ in range(4):  # pause_turn: lange Websuche wird fortgesetzt
            r = client().beta.messages.create(
                model=MODELL,
                max_tokens=max_tokens,
                system=system,
                messages=messages,
                # Alltagsgespräch: wenig Nachdenken reicht, ist schneller und günstiger
                output_config={"effort": "low"},
                # Falls eine Sicherheitsprüfung die Anfrage ablehnt, springt ein anderes Modell ein
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
                **extra,
            )
            if r.stop_reason != "pause_turn":
                break
            messages = messages + [{"role": "assistant", "content": r.content}]
    except anthropic.AuthenticationError:
        raise RuntimeError("Der Schlüssel für die KI fehlt oder stimmt nicht. Bitte Niko Bescheid geben.")
    except anthropic.RateLimitError:
        raise RuntimeError("Gerade sind zu viele Anfragen. Bitte in einer Minute nochmal probieren.")
    except anthropic.APIStatusError as e:
        print("Claude-Fehler:", e.status_code, e.message, flush=True)
        raise RuntimeError("Biko kann gerade nicht antworten. Bitte gleich nochmal probieren.")
    except anthropic.APIConnectionError:
        raise RuntimeError("Keine Verbindung zur KI. Ist das Internet am Server da?")
    if r.stop_reason == "refusal":
        return "Dabei kann ich leider nicht helfen. Magst du mich etwas anderes fragen?"
    text = "".join(b.text for b in r.content if b.type == "text").strip()
    return text or "Entschuldige, da ist mir nichts eingefallen. Magst du es anders sagen?"


def jetzt():
    return datetime.now(ZEITZONE)


def system_prompt():
    p = profil()
    t = jetzt()
    tage = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]
    return SYSTEM.format(
        name_satz=p["name"].strip() or "einer Person, deren Namen du noch nicht kennst",
        anrede="Sie" if p.get("anrede") == "Sie" else "du",
        sprache=SPRACHEN.get(p.get("sprache"), "Deutsch"),
        diaet=p["diaet"].strip() or "keine eingetragen",
        notizen=p["notizen"].strip() or "keine",
        datum=f"{tage[t.weekday()]}, {t.day}.{t.month}.{t.year}",
        uhrzeit=t.strftime("%H:%M"),
    )


# ---------- Funktionen ----------

def chat(text):
    with _lock:
        verlauf = lesen("verlauf", [])
    verlauf.append({"role": "user", "content": text})
    verlauf = verlauf[-MAX_VERLAUF:]
    while verlauf and verlauf[0]["role"] != "user":   # muss mit der Person beginnen
        verlauf.pop(0)
    antwort = frage_claude(system_prompt(), verlauf, websuche=True)
    verlauf.append({"role": "assistant", "content": antwort})
    with _lock:
        schreiben("verlauf", verlauf[-MAX_VERLAUF:])
    return antwort


def nachricht(an, was):
    system = NACHRICHT_SYSTEM.format(notizen=profil()["notizen"].strip() or "keine")
    return frage_claude(system, [{"role": "user", "content": f"An: {an or 'jemanden'}\nWas ich sagen will: {was}"}], 600)


UHRZEIT = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
TAGE = {"mo", "di", "mi", "do", "fr", "sa", "so"}


def erinnerung_pruefen(e):
    zeit = str(e.get("zeit", ""))
    text = str(e.get("text", "")).strip()[:120]
    tage = [t for t in e.get("tage", []) if t in TAGE] if isinstance(e.get("tage"), list) else []
    if not UHRZEIT.match(zeit) or not text:
        raise ValueError("Bitte Uhrzeit (z. B. 08:00) und einen Text angeben.")
    return {"id": str(e.get("id") or uuid.uuid4().hex[:10]), "zeit": zeit, "text": text,
            "tage": tage or sorted(TAGE), "aktiv": bool(e.get("aktiv", True))}


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
    "Was soll in der Nachricht stehen?": "消息里要写什么？",
    "Höchstens 30 Erinnerungen.": "最多 30 个提醒。",
    "Zu viele Versuche. Bitte in 15 Minuten nochmal.": "尝试次数太多。请 15 分钟后再试。",
    "Am Server ist noch kein Passwort eingestellt (APP_PASSWORT).": "服务器还没有设置密码（APP_PASSWORT）。",
    "Das Passwort stimmt nicht.": "密码不对。",
}

TYPEN = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
         ".css": "text/css; charset=utf-8", ".svg": "image/svg+xml",
         ".webmanifest": "application/manifest+json", ".png": "image/png", ".woff2": "font/woff2"}

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
        if typ.startswith("application/json"):
            cache = "no-store"
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
                         "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
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
            return self.senden(200, {"angemeldet": self.angemeldet(), "passwort_gesetzt": bool(PASSWORT)})
        if pfad.startswith("/api/"):
            if not self.angemeldet():
                return self.senden(401, {"fehler": "Bitte anmelden."})
            if pfad == "/api/profil":
                return self.senden(200, profil())
            if pfad == "/api/erinnerungen":
                return self.senden(200, lesen("erinnerungen", []))
            if pfad == "/api/verlauf":
                return self.senden(200, lesen("verlauf", [])[-MAX_VERLAUF:])
            return self.senden(404, {"fehler": "Gibt es nicht."})
        return self.datei(pfad)

    def do_POST(self):
        pfad = self.path.split("?")[0]
        try:
            daten = self.json_body()
            if pfad == "/api/login":
                return self.login(daten)
            if not self.angemeldet():
                return self.senden(401, {"fehler": "Bitte anmelden."})
            if pfad == "/api/chat":
                text = str(daten.get("text", "")).strip()
                if not text or len(text) > MAX_TEXT:
                    raise ValueError("Bitte etwas Kürzeres schreiben.")
                return self.senden(200, {"antwort": chat(text)})
            if pfad == "/api/nachricht":
                was = str(daten.get("was", "")).strip()
                an = str(daten.get("an", "")).strip()[:80]
                if not was or len(was) > MAX_TEXT:
                    raise ValueError("Was soll in der Nachricht stehen?")
                return self.senden(200, {"nachricht": nachricht(an, was)})
            if pfad == "/api/verlauf/loeschen":
                with _lock:
                    schreiben("verlauf", [])
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
                if not isinstance(liste, list) or len(liste) > 30:
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
