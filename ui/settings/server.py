"""
Biko-Einstellungsdienst: speichert die Einstellungen aus der Biko-App und lädt den Bot neu.

- Kein eigenes Passwort: jede Anfrage muss das Freqtrade-Token der App mitschicken.
  Der Dienst prüft es, indem er damit /api/v1/show_config beim Bot abfragt.
- Schreibt nur user_data/biko-settings.json (wird von Freqtrade als zweite --config geladen)
  und ruft danach /api/v1/reload_config auf.
- Nur erlaubte Werte (Strategie und Coins aus fester Liste, Takt, Risiko bis 3 %, 1 bis 6 Trades).
  Stop-Loss, Kill-Switch und Testmodus lassen sich hier bewusst NICHT ändern.
Nur Python-Standardbibliothek.
"""

import json
import os
import tempfile
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

FREQTRADE = os.environ.get("FREQTRADE_URL", "http://freqtrade:8080")
SETTINGS = os.environ.get("BIKO_SETTINGS", "/freqtrade/user_data/biko-settings.json")
PORT = int(os.environ.get("PORT", "8090"))

# Klassennamen in user_data/strategies. Alle erben von BikoBase (gleiche Risikoschranken).
STRATEGIES = ["EmaTrendStrategy", "BreakoutStrategy", "DipBuyStrategy"]
COINS = ["BTC", "ETH", "SOL", "XRP", "ADA", "LINK", "DOT", "AVAX", "LTC", "DOGE"]
TIMEFRAMES = ["15m", "1h", "4h"]
RISKS = [0.005, 0.01, 0.02, 0.03]
MAX_TRADES = (1, 6)
DEFAULT = {
    "strategy": "EmaTrendStrategy",
    "coins": ["BTC", "ETH", "SOL"],
    "timeframe": "4h",
    "risk_per_trade": 0.01,
    "max_open_trades": 3,
}


def read_settings(stake="EUR"):
    try:
        with open(SETTINGS, encoding="utf-8") as f:
            raw = json.load(f)
    except (OSError, ValueError):
        return dict(DEFAULT)
    pairs = raw.get("exchange", {}).get("pair_whitelist", [])
    coins = [p.split("/")[0] for p in pairs if isinstance(p, str)]
    strategy = raw.get("strategy")
    return {
        "strategy": strategy if strategy in STRATEGIES else DEFAULT["strategy"],
        "coins": [c for c in coins if c in COINS] or DEFAULT["coins"],
        "timeframe": raw.get("timeframe", DEFAULT["timeframe"]),
        "risk_per_trade": raw.get("biko", {}).get("risk_per_trade", DEFAULT["risk_per_trade"]),
        "max_open_trades": raw.get("max_open_trades", DEFAULT["max_open_trades"]),
    }


def write_settings(s, stake):
    data = {
        "_hinweis": "Wird von der Biko-App geschrieben. Von Hand ändern geht auch, danach Bot neu laden.",
        "strategy": s["strategy"],
        "timeframe": s["timeframe"],
        "max_open_trades": s["max_open_trades"],
        "exchange": {"pair_whitelist": [f"{c}/{stake}" for c in s["coins"]]},
        "biko": {"risk_per_trade": s["risk_per_trade"]},
    }
    folder = os.path.dirname(SETTINGS)
    fd, tmp = tempfile.mkstemp(dir=folder, prefix=".biko-settings-")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
    os.chmod(tmp, 0o644)
    os.replace(tmp, SETTINGS)


def validate(body):
    if not isinstance(body, dict):
        raise ValueError("Ungültige Daten.")
    strategy = body.get("strategy")
    if strategy not in STRATEGIES:
        raise ValueError("Unbekannte Strategie.")
    coins = body.get("coins")
    if not isinstance(coins, list) or not coins:
        raise ValueError("Mindestens ein Coin muss ausgewählt sein.")
    if not all(isinstance(c, str) for c in coins) or not set(coins) <= set(COINS):
        raise ValueError("Unbekannter Coin.")
    coins = [c for c in COINS if c in coins]  # feste Reihenfolge, ohne Doppelte
    tf = body.get("timeframe")
    if tf not in TIMEFRAMES:
        raise ValueError("Unbekannter Takt.")
    risk = body.get("risk_per_trade")
    if risk not in RISKS:
        raise ValueError("Risiko muss 0,5 %, 1 %, 2 % oder 3 % sein.")
    mot = body.get("max_open_trades")
    if not isinstance(mot, int) or isinstance(mot, bool) or not MAX_TRADES[0] <= mot <= MAX_TRADES[1]:
        raise ValueError("Gleichzeitige Trades: 1 bis 6.")
    return {"strategy": strategy, "coins": coins, "timeframe": tf, "risk_per_trade": risk, "max_open_trades": mot}


def freqtrade(path, auth, method="GET"):
    req = urllib.request.Request(FREQTRADE + path, method=method, headers={"Authorization": auth})
    if method == "POST":
        req.data = b"{}"
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=15) as res:
        return json.loads(res.read() or b"{}")


class Handler(BaseHTTPRequestHandler):
    server_version = "biko-settings"

    def log_message(self, fmt, *args):  # knapp loggen
        print("%s %s" % (self.command, self.path), flush=True)

    def reply(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def auth_config(self):
        """Prüft das Token beim Bot und liefert dessen Config (oder None)."""
        auth = self.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            self.reply(401, {"detail": "Nicht angemeldet."})
            return None, None
        try:
            return auth, freqtrade("/api/v1/show_config", auth)
        except urllib.error.HTTPError as e:
            self.reply(401 if e.code == 401 else 502, {"detail": "Bot lehnt ab." if e.code == 401 else "Bot antwortet nicht."})
        except (urllib.error.URLError, OSError, ValueError):
            self.reply(502, {"detail": "Bot antwortet nicht."})
        return None, None

    def do_GET(self):
        if self.path != "/settings-api/settings":
            return self.reply(404, {"detail": "Nicht gefunden."})
        auth, cfg = self.auth_config()
        if not cfg:
            return
        stake = cfg.get("stake_currency", "EUR")
        self.reply(200, {
            "settings": read_settings(stake),
            "options": {
                "strategies": STRATEGIES,
                "coins": COINS,
                "timeframes": TIMEFRAMES,
                "risks": RISKS,
                "max_open_trades": list(MAX_TRADES),
            },
            "stake_currency": stake,
            "stoploss": cfg.get("stoploss"),
            # Was der Bot gerade wirklich fährt (nach einem Neuladen gleich den Einstellungen)
            "active": {"strategy": cfg.get("strategy"), "timeframe": cfg.get("timeframe")},
        })

    def do_POST(self):
        if self.path != "/settings-api/settings":
            return self.reply(404, {"detail": "Nicht gefunden."})
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return self.reply(400, {"detail": "Ungültige Anfrage."})
        if not 0 <= length <= 4096:
            return self.reply(413, {"detail": "Zu groß."})
        try:
            body = json.loads(self.rfile.read(length) or b"null")
        except ValueError:
            return self.reply(400, {"detail": "Ungültiges JSON."})
        auth, cfg = self.auth_config()
        if not cfg:
            return
        try:
            s = validate(body)
        except ValueError as e:
            return self.reply(400, {"detail": str(e)})
        stake = cfg.get("stake_currency", "EUR")
        write_settings(s, stake)
        try:
            freqtrade("/api/v1/reload_config", auth, method="POST")
        except (urllib.error.URLError, OSError, ValueError):
            return self.reply(202, {"settings": s, "detail": "Gespeichert. Der Bot übernimmt es beim nächsten Neustart."})
        self.reply(200, {"settings": s, "detail": "Gespeichert, Bot lädt neu."})


def ensure_file():
    if not os.path.exists(SETTINGS):
        write_settings(DEFAULT, os.environ.get("STAKE_CURRENCY", "EUR"))
        print("Standard-Einstellungen angelegt:", SETTINGS, flush=True)


if __name__ == "__main__":
    ensure_file()
    print(f"Biko-Einstellungsdienst auf Port {PORT}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
