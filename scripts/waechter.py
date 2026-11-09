"""
Biko-Wächter: passt auf den Bot auf, auch wenn niemand in die App schaut.

Alle 5 Minuten:
- Arbeitet der Bot noch? (/api/v1/health: letzter Durchlauf jünger als 10 Minuten)
- Hat jeder offene Trade einen Stop-Loss an der Börse? (sonst wäre ein Crash ungebremst)
- Meldet Probleme (und die Entwarnung) per Telegram, wenn Token und Chat-ID in der .env stehen.
- Pingt HEALTHCHECK_URL (z. B. healthchecks.io), wenn alles gut ist. Bleibt der Ping aus,
  weil der ganze Server weg ist, schlägt healthchecks.io Alarm (per E-Mail/App).

Einmal am Tag:
- Sichert alle Trade-Datenbanken (user_data/tradesv3*.sqlite) nach user_data/backups/<datum>/,
  hebt 14 Tage auf. Für ein Backup außerhalb des Servers siehe TODO.md.

Nur Python-Standardbibliothek.
"""

import base64
import glob
import json
import os
import shutil
import sqlite3
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

FREQTRADE = os.environ.get("FREQTRADE_URL", "http://freqtrade:8080")
USER = os.environ.get("BOT_USER", "")
PASS = os.environ.get("BOT_PASS", "")
NAME = os.environ.get("BOT_NAME", "biko")
TG_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
TG_CHAT = os.environ.get("TELEGRAM_CHAT_ID", "")
HC_URL = os.environ.get("HEALTHCHECK_URL", "")
USER_DATA = os.environ.get("USER_DATA", "/freqtrade/user_data")

INTERVAL = 300            # alle 5 Minuten prüfen
MAX_STILL = 600           # Bot gilt als hängend, wenn er 10 Minuten nichts getan hat
STOP_GRACE = 600          # so lange darf ein neuer Trade ohne Stop an der Börse sein
BACKUP_KEEP_DAYS = 14
START_GRACE = 300         # nach dem Start erst 5 Minuten warten (Bot lädt Kerzen)


def log(msg):
    print(f"{datetime.now(timezone.utc):%Y-%m-%d %H:%M:%S} {msg}", flush=True)


def api(path):
    token = base64.b64encode(f"{USER}:{PASS}".encode()).decode()
    req = urllib.request.Request(FREQTRADE + path, headers={"Authorization": f"Basic {token}"})
    with urllib.request.urlopen(req, timeout=20) as res:
        return json.loads(res.read() or b"null")


def telegram(text):
    if not (TG_TOKEN and TG_CHAT):
        return
    data = urllib.parse.urlencode({"chat_id": TG_CHAT, "text": text}).encode()
    try:
        urllib.request.urlopen(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage", data=data, timeout=20)
    except (urllib.error.URLError, OSError) as e:
        log(f"Telegram geht nicht: {e}")


def healthcheck(ok, info=""):
    if not HC_URL:
        return
    url = HC_URL.rstrip("/") + ("" if ok else "/fail")
    try:
        urllib.request.urlopen(urllib.request.Request(url, data=info.encode()[:1000]), timeout=20)
    except (urllib.error.URLError, OSError) as e:
        log(f"Healthcheck-Ping geht nicht: {e}")


def parse_ts(value):
    """Freqtrade liefert Zeiten als ms-Zeitstempel oder als Text."""
    if isinstance(value, (int, float)):
        return value / 1000 if value > 1e11 else value
    if isinstance(value, str) and value:
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
        except ValueError:
            return None
    return None


def check():
    """Liefert eine Liste von Problemen (leer = alles gut)."""
    problems = []
    try:
        health = api("/api/v1/health") or {}
    except urllib.error.HTTPError as e:
        return [f"Bot-API lehnt ab ({e.code}). Stimmen Benutzer/Passwort in der .env?"]
    except (urllib.error.URLError, OSError, ValueError):
        return ["Bot antwortet nicht (Container aus oder abgestürzt)."]

    last = parse_ts(health.get("last_process_ts") or health.get("last_process"))
    if last is None or time.time() - last > MAX_STILL:
        problems.append("Bot hängt: seit über 10 Minuten keine Runde mehr gerechnet.")

    try:
        trades = api("/api/v1/status") or []
    except (urllib.error.URLError, OSError, ValueError):
        trades = []
    for t in trades if isinstance(trades, list) else []:
        opened = parse_ts(t.get("open_timestamp") or t.get("open_date"))
        if opened and time.time() - opened < STOP_GRACE:
            continue
        if not t.get("is_open", True):
            continue
        orders = t.get("orders") or []
        if any(o.get("is_open") and o.get("ft_order_side") != "stoploss" for o in orders):
            continue  # Kauf/Verkauf läuft gerade, der Stop kommt danach (wieder)
        has_stop = any(
            o.get("ft_order_side") == "stoploss" and o.get("is_open") for o in orders
        )
        # Ältere/andere API-Formate: stoploss_order_id direkt am Trade
        has_stop = has_stop or bool(t.get("stoploss_order_id"))
        if not has_stop:
            problems.append(f"{t.get('pair')}: offener Trade OHNE Stop-Loss an der Börse.")
    return problems


def backup():
    root = os.path.join(USER_DATA, "backups")
    today = os.path.join(root, datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    if os.path.isdir(today):
        return
    dbs = sorted(glob.glob(os.path.join(USER_DATA, "tradesv3*.sqlite")))
    if not dbs:
        return
    tmp = today + ".tmp"
    shutil.rmtree(tmp, ignore_errors=True)
    os.makedirs(tmp)
    for db in dbs:
        # sqlite-Backup-API: sicher, auch während der Bot schreibt
        src = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        dst = sqlite3.connect(os.path.join(tmp, os.path.basename(db)))
        with dst:
            src.backup(dst)
        src.close()
        dst.close()
    for f in os.listdir(tmp):
        os.chmod(os.path.join(tmp, f), 0o600)
    os.replace(tmp, today)
    log(f"Backup: {len(dbs)} Datenbank(en) nach {today}")
    # Alte Backups löschen
    cutoff = time.time() - BACKUP_KEEP_DAYS * 86400
    for d in glob.glob(os.path.join(root, "????-??-??")):
        if os.path.getmtime(d) < cutoff:
            shutil.rmtree(d, ignore_errors=True)


def main():
    log(f"Wächter für {NAME} läuft. Telegram: {'ja' if TG_TOKEN and TG_CHAT else 'nein'}, "
        f"Healthcheck: {'ja' if HC_URL else 'nein'}")
    if not (USER and PASS):
        log("Hinweis: BOT_USER/BOT_PASS fehlen, der Bot kann nicht geprüft werden.")
    time.sleep(START_GRACE)
    last_problems = []
    while True:
        try:
            problems = check()
        except Exception as e:  # der Wächter selbst soll nie sterben
            problems = [f"Wächter-Fehler: {e}"]
        if problems != last_problems:
            if problems:
                text = f"⚠️ {NAME}: " + " ".join(problems)
                log(text)
                telegram(text)
            elif last_problems:
                log("Wieder alles gut.")
                telegram(f"✅ {NAME}: wieder alles gut.")
        last_problems = problems
        healthcheck(not problems, " ".join(problems))
        try:
            backup()
        except Exception as e:
            log(f"Backup fehlgeschlagen: {e}")
            telegram(f"⚠️ {NAME}: Backup der Datenbank fehlgeschlagen: {e}")
        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
