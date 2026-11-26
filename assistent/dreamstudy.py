"""
Biko-Chef arbeitet für DreamStudy, Nikos Nachhilfe-App (https://dreamstudy.at).

So hängt es zusammen:
  DreamStudy  legt Aufträge an: jeden Morgen ein Tagesbriefing je Lehrkraft, und einen Lernzettel, wenn eine Lehrkraft ein
              Dokument „an Biko gibt“. Die App baut den Text selbst und ersetzt vorher alle Namen: Schüler heißen S1, S2 …,
              die Zuordnung bleibt in DreamStudy. Biko bekommt nie einen Namen.
  Biko        fragt alle ABSTAND Sekunden nach (GET /api/biko/auftraege), erledigt jeden Auftrag mit einer Claude-Anfrage
              (Anleitung, Text und Antwort-Schema kommen von DreamStudy, beim Dokument die Datei dazu) und schickt das
              Ergebnis mit den Kosten zurück (POST /api/biko/auftraege/<id>). DreamStudy prüft es und zeigt es an.

Kosten zählen in die Tagesgrenze von Biko-Chef. Ist sie erreicht, holt Biko nichts ab. Ohne DREAMSTUDY_TOKEN ist alles aus.
Im Zustand steht nur, welcher Auftrag wann wie viel gekostet hat, nie ein Text aus DreamStudy.

Einstellungen (Umgebung): DREAMSTUDY_TOKEN (derselbe Wert wie BIKO_TOKEN in DreamStudy, mindestens 24 Zeichen),
DREAMSTUDY_URL (Standard https://dreamstudy.at), DREAMSTUDY_MODELL (Standard claude-sonnet-5-5),
DREAMSTUDY_TAKT (Sekunden zwischen zwei Abrufen, Standard 120).
"""

import base64
import json
import os
import threading
import time
import urllib.error
import urllib.request

import chef

MODELL = os.environ.get("DREAMSTUDY_MODELL", "claude-sonnet-5-5")
AGENT = "Biko-Chef/1.0 (+dreamstudy)"
MAX_JE_RUNDE = 4
MAX_DATEI = 15 * 1024 * 1024
MAX_ERLEDIGT = 30
BILDER = ("image/jpeg", "image/png", "image/webp")

_laeuft = False
_zuletzt = 0.0
_faden_lock = threading.Lock()


def url():
    return os.environ.get("DREAMSTUDY_URL", "https://dreamstudy.at").strip().rstrip("/")


def token():
    return os.environ.get("DREAMSTUDY_TOKEN", "").strip()


def abstand():
    try:
        return max(30, int(os.environ.get("DREAMSTUDY_TAKT", "120")))
    except ValueError:
        return 120


def an():
    return len(token()) >= 24


def _anfrage(methode, pfad, daten=None, roh=False, timeout=30):
    """Die eine HTTP-Anfrage an DreamStudy. Tests ersetzen sie. `roh`: (bytes, Content-Type) statt JSON."""
    kopf = {"Authorization": f"Bearer {token()}", "User-Agent": AGENT, "Accept": "application/json"}
    if daten is not None:
        kopf["Content-Type"] = "application/json"
    req = urllib.request.Request(url() + pfad, method=methode, headers=kopf,
                                 data=json.dumps(daten).encode("utf-8") if daten is not None else None)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        body = r.read(MAX_DATEI + 1)
        if roh:
            return body, r.headers.get("Content-Type", "")
        return json.loads(body or b"{}")


# ---------- Zustand (nur Nummern, Zeiten und Kosten) ----------
def _stand(z):
    return z.setdefault("dreamstudy", {"zuletzt": "", "fehler": "", "erledigt": []})


def _merken(art, aid, dollar, ok, fehler=""):
    with chef._lock:
        z = chef.laden()
        s = _stand(z)
        s["erledigt"].append({"id": aid, "art": art, "zeit": chef.jetzt().isoformat(timespec="seconds"),
                              "dollar": round(dollar, 4), "ok": ok, "fehler": fehler[:120]})
        s["erledigt"] = s["erledigt"][-MAX_ERLEDIGT:]
        name = "Tagesbriefing" if art == "briefing" else "Lernzettel"
        if ok:
            chef.protokoll_zeile(z, f"Fertig: DreamStudy-{name} (Auftrag {aid})", dollar=dollar)
            if art == "material":
                chef.eintrag(z, "meldung", f"DreamStudy: Lernzettel aus einem Dokument ist fertig ({chef.geld(dollar)}). "
                                           "Die Lehrkraft prüft ihn in DreamStudy unter Erweitert › Biko.")
        else:
            chef.protokoll_zeile(z, f"DreamStudy-{name} (Auftrag {aid}) ging nicht: {fehler[:80]}", dollar=dollar)
        chef.speichern(z)


# ---------- Ein Auftrag ----------
def _datei_block(job):
    d = job.get("datei")
    if not d:
        return None
    pfad, mime = str(d.get("pfad") or ""), str(d.get("mime") or "")
    if not pfad.startswith("/api/biko/auftraege/"):
        raise ValueError("Unerwarteter Pfad für die Datei.")
    if mime != "application/pdf" and mime not in BILDER:
        raise ValueError("Diese Dateiart kann Biko nicht lesen.")
    daten, _ = _anfrage("GET", pfad, roh=True, timeout=60)
    if len(daten) > MAX_DATEI:
        raise ValueError("Die Datei ist zu groß.")
    b64 = base64.standard_b64encode(daten).decode("ascii")
    art = "document" if mime == "application/pdf" else "image"
    return {"type": art, "source": {"type": "base64", "media_type": mime, "data": b64}}


def _eingabe_aus(r):
    """Die Eingabe des Werkzeugs `abgeben`; sonst ein JSON-Objekt im Text, sonst None."""
    for b in r.content:
        if b.type == "tool_use" and b.name == "abgeben" and isinstance(b.input, dict):
            return b.input
    text = "".join(b.text for b in r.content if b.type == "text")
    a, e = text.find("{"), text.rfind("}")
    if 0 <= a < e:
        try:
            return json.loads(text[a:e + 1])
        except ValueError:
            return None
    return None


def bearbeiten(job):
    """Erledigt einen Auftrag und schickt das Ergebnis zurück. Wirft chef.GrenzeErreicht, wenn heute kein Geld frei ist."""
    aid = int(job["id"])
    art = "briefing" if job.get("art") == "briefing" else "material"
    dollar = 0.0
    try:
        inhalt = []
        block = _datei_block(job)
        if block:
            inhalt.append(block)
        inhalt.append({"type": "text", "text": str(job.get("anfrage") or "")[:200000]})
        schema = job.get("schema") if isinstance(job.get("schema"), dict) else {"type": "object"}
        werkzeug = {"name": "abgeben", "description": "Gibt das fertige Ergebnis ab. Genau einmal aufrufen.",
                    "input_schema": schema}
        with chef._lock:
            chef.grenze_pruefen(chef.laden())
        r = chef.claude_anfrage(
            model=MODELL, max_tokens=max(1000, min(int(job.get("max_tokens") or 8000), 16000)),
            system=[{"type": "text", "text": str(job.get("system") or ""), "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": inhalt}], tools=[werkzeug],
            output_config={"effort": "medium"}, betas=["server-side-fallback-2026-07-01"], fallbacks="default",
        )
        dollar = chef.preis(r, MODELL)
        with chef._lock:
            z = chef.laden()
            chef.kosten_buchen(z, dollar)
            chef.speichern(z)
        u = getattr(r, "usage", None)
        zahl = lambda x: x if isinstance(x, int) else 0
        ein = zahl(getattr(u, "input_tokens", 0)) + zahl(getattr(u, "cache_read_input_tokens", 0)) + zahl(getattr(u, "cache_creation_input_tokens", 0))
        aus = zahl(getattr(u, "output_tokens", 0))
        modell = getattr(r, "model", MODELL)
        modell = modell if isinstance(modell, str) else MODELL
        eingabe = _eingabe_aus(r) if r.stop_reason != "refusal" else None
        rueck = {"kosten_usd": round(dollar, 6), "modell": modell, "tokens_ein": ein, "tokens_aus": aus}
        if eingabe is None:
            rueck["fehler"] = "Claude hat kein Ergebnis abgegeben." if r.stop_reason != "refusal" else "Claude hat abgelehnt."
        else:
            rueck["ergebnis"] = eingabe
        try:
            _anfrage("POST", f"/api/biko/auftraege/{aid}", rueck)
        except urllib.error.HTTPError as e:
            if e.code != 422:   # 422: DreamStudy hat das Ergebnis geprüft und als Fehler gespeichert
                raise
            eingabe = None
            rueck["fehler"] = "DreamStudy: Ergebnis passte nicht zum Schema"
        _merken(art, aid, dollar, eingabe is not None, rueck.get("fehler", ""))
    except chef.GrenzeErreicht:
        raise
    except Exception as e:   # ein Auftrag darf Biko nie mitreißen
        grund = f"Biko: {type(e).__name__}"
        print(f"DreamStudy: Auftrag {aid} ging nicht ({type(e).__name__})", flush=True)
        try:
            _anfrage("POST", f"/api/biko/auftraege/{aid}", {"fehler": grund, "kosten_usd": round(dollar, 6), "modell": MODELL})
        except Exception:
            pass   # DreamStudy gibt ihn nach 20 Minuten noch einmal heraus
        _merken(art, aid, dollar, False, grund)


def runde():
    """Ein Abruf: holen, erledigen, zurückschicken. Läuft in einem eigenen Faden."""
    global _laeuft
    try:
        with chef._lock:
            z = chef.laden()
            chef.grenze_pruefen(z)
            if z["grenzen"]["tag"] - chef.heute_ausgegeben(z) < chef.MINDESTENS_FREI:
                return
        antwort = _anfrage("GET", "/api/biko/auftraege")
        auftraege = [a for a in (antwort.get("auftraege") or []) if isinstance(a, dict) and "id" in a][:MAX_JE_RUNDE]
        for job in auftraege:
            bearbeiten(job)
        with chef._lock:
            z = chef.laden()
            s = _stand(z)
            s["zuletzt"], s["fehler"] = chef.jetzt().isoformat(timespec="seconds"), ""
            chef.speichern(z)
    except chef.GrenzeErreicht:
        pass   # morgen weiter; DreamStudy gibt offene Aufträge dann noch einmal heraus
    except Exception as e:
        grund = f"{e.code}" if isinstance(e, urllib.error.HTTPError) else type(e).__name__
        print(f"DreamStudy: Abruf ging nicht ({grund})", flush=True)
        with chef._lock:
            z = chef.laden()
            s = _stand(z)
            s["fehler"] = {"401": "Der Schlüssel passt nicht (DREAMSTUDY_TOKEN und BIKO_TOKEN vergleichen).",
                           "404": "DreamStudy hat die Biko-Tür nicht an (BIKO_TOKEN fehlt dort)."}.get(grund, f"Nicht erreichbar ({grund}).")
            chef.speichern(z)
    finally:
        with _faden_lock:
            _laeuft = False


def takt(jetzt=None):
    """Vom Takt des Chefs aufgerufen: startet höchstens alle ABSTAND Sekunden einen Abruf, nie zwei zugleich."""
    global _laeuft, _zuletzt
    if not an():
        return False
    jetzt = time.time() if jetzt is None else jetzt
    with _faden_lock:
        if _laeuft or jetzt - _zuletzt < abstand():
            return False
        _laeuft, _zuletzt = True, jetzt
    threading.Thread(target=runde, daemon=True).start()
    return True


def ansicht():
    with chef._lock:
        s = _stand(chef.laden())
    heute = chef.heute()
    return {"an": an(), "zuletzt": s.get("zuletzt", ""), "fehler": s.get("fehler", ""),
            "heute": len([e for e in s.get("erledigt", []) if e["zeit"].startswith(heute) and e["ok"]])}


# ---------- Werkzeuge des Chefs ----------
def dreamstudy_stand(_e):
    if not an():
        return "DreamStudy ist nicht verbunden: DREAMSTUDY_TOKEN fehlt hier am Server."
    with chef._lock:
        s = _stand(chef.laden())
    zeilen = [f"Verbunden mit {url()}. Zuletzt abgeholt: {s.get('zuletzt') or 'noch nie'}."]
    if s.get("fehler"):
        zeilen.append(f"Letzter Fehler: {s['fehler']}")
    for e in s.get("erledigt", [])[-10:]:
        zeilen.append(f"- {e['zeit']} Auftrag {e['id']} ({e['art']}): {'fertig' if e['ok'] else 'ging nicht: ' + e['fehler']}, "
                      f"{chef.geld(e['dollar'])}")
    return "\n".join(zeilen)


def dreamstudy_jetzt(_e):
    global _zuletzt
    if not an():
        return "DreamStudy ist nicht verbunden: DREAMSTUDY_TOKEN fehlt hier am Server."
    with _faden_lock:
        _zuletzt = 0.0
    return "Ich hole in ein paar Sekunden ab, was in DreamStudy wartet."


WERKZEUGE = {
    "dreamstudy_stand": ({"name": "dreamstudy_stand", "description": "Zeigt, ob DreamStudy verbunden ist und welche Aufträge "
                          "(Tagesbriefings, Lernzettel) zuletzt erledigt wurden, mit Kosten.",
                          "input_schema": {"type": "object", "properties": {}}}, dreamstudy_stand),
    "dreamstudy_jetzt": ({"name": "dreamstudy_jetzt", "description": "Holt sofort ab, was in DreamStudy wartet, statt bis zum "
                          "nächsten Abruf zu warten.", "input_schema": {"type": "object", "properties": {}}}, dreamstudy_jetzt),
}
chef.CHEF_WERKZEUGE.update(WERKZEUGE)
