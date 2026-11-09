#!/usr/bin/env bash
# Biko Bot: Ein-Zeilen-Installation auf einem eigenen Linux-Server (Ubuntu/Debian).
# Startet im Testmodus (Dry-Run, nur Spielgeld, keine Börsen-Keys). Echtgeld nur, wenn in der .env
# BIKO_MODUS=live steht und die Prüfungen unten passen (siehe TODO.md).
#
#   curl -fsSL https://raw.githubusercontent.com/n1kob1ko/biko-bot/main/install.sh | sudo bash
#
# Nochmal ausführen = Bot-Code aktualisieren und neu starten. .env und Trades bleiben erhalten.
#
# Zweiter Bot auf demselben Server (z. B. für jemand anderen, nur Spielgeld):
#   curl -fsSL https://raw.githubusercontent.com/n1kob1ko/biko-bot/main/install.sh | BIKO_NAME=cousin bash
# Jeder Bot hat seinen eigenen Ordner (/opt/<name>-bot), eigene Ports, eigenes Login und eigenes Maskottchen.
# Aktualisieren: dieselbe Zeile mit demselben BIKO_NAME nochmal ausführen.
set -euo pipefail

REPO="n1kob1ko/biko-bot"
BRANCH="${BIKO_BRANCH:-main}"
INSTANZ="${BIKO_NAME:-biko}"
INSTANZ="$(printf '%s' "$INSTANZ" | tr 'A-Z' 'a-z')"
case "$INSTANZ" in
  ''|*[!a-z0-9-]*|-*) echo "FEHLER: BIKO_NAME darf nur a-z, 0-9 und - enthalten (z. B. cousin)." >&2; exit 1 ;;
esac
if [ "$INSTANZ" = "biko" ]; then ZIEL="${BIKO_DIR:-/opt/biko-bot}"; else ZIEL="${BIKO_DIR:-/opt/$INSTANZ-bot}"; fi

# Maskottchen, die die App kennt (ui/web/biko.js): id:Standardname
MASKOTTCHEN_LISTE="biko:Biko yojji:Yojji"

fehler() { echo; echo "FEHLER: $1" >&2; exit 1; }
schritt() { echo; echo "==> $1"; }

# Fragen auch dann stellen können, wenn das Skript per "curl | bash" läuft
frage() {
  local antwort=""
  if [ -r /dev/tty ]; then read -r -p "$1" antwort </dev/tty || true; fi
  printf '%s' "$antwort"
}

zufall() {
  if command -v openssl >/dev/null 2>&1; then openssl rand -hex "$1"
  else LC_ALL=C tr -dc 'a-f0-9' </dev/urandom | head -c "$(( $1 * 2 ))"; fi
}

echo "=============================================="
echo "  Biko Bot - Installation"
echo "  Bot: $INSTANZ  ->  $ZIEL"
echo "=============================================="

[ "$(id -u)" -eq 0 ] || fehler "Bitte mit Administratorrechten starten (sudo bash ... oder als root)."
[ "$(uname -s)" = "Linux" ] || fehler "Dieses Skript ist für Linux-Server. Auf Windows/Mac siehe ANLEITUNG-TESTEN.md."

# 1. Docker
schritt "Docker prüfen"
if ! command -v docker >/dev/null 2>&1; then
  echo "Docker fehlt, wird installiert (dauert 1-3 Minuten) ..."
  command -v curl >/dev/null 2>&1 || { apt-get update -qq && apt-get install -y -qq curl; }
  curl -fsSL https://get.docker.com | sh
fi
docker compose version >/dev/null 2>&1 || fehler "'docker compose' fehlt. Bitte Docker neu installieren: curl -fsSL https://get.docker.com | sh"
systemctl enable --now docker >/dev/null 2>&1 || true
echo "[OK] $(docker --version)"

# 2. Bot-Code holen (ohne git, als Archiv von GitHub)
schritt "Bot-Code herunterladen nach $ZIEL"
mkdir -p "$ZIEL"
curl -fsSL "https://codeload.github.com/$REPO/tar.gz/refs/heads/$BRANCH" \
  | tar -xz -C "$ZIEL" --strip-components=1 \
  || fehler "Download von GitHub fehlgeschlagen."
cd "$ZIEL"
echo "[OK] Code liegt in $ZIEL"

# Wert aus .env lesen bzw. setzen
env_get() { [ -f .env ] && grep -E "^$1=" .env | tail -n1 | cut -d= -f2- || true; }
env_set() {
  if grep -qE "^$1=" .env; then sed -i "s|^$1=.*|$1=$2|" .env; else printf '%s=%s\n' "$1" "$2" >> .env; fi
}
# Ist ein Port schon belegt (laufender Dienst oder ein anderer Biko-Bot auf diesem Server)?
port_belegt() {
  local p="$1" d
  if command -v ss >/dev/null 2>&1 && ss -ltnH 2>/dev/null | awk '{print $4}' | grep -qE "[:.]$p\$"; then return 0; fi
  for d in /opt/*-bot; do
    [ -f "$d/.env" ] && [ "$(cd "$d" && pwd)" != "$(pwd)" ] || continue
    grep -qE "^(API_PORT|APP_PORT|TS_PORT)=$p\$" "$d/.env" && return 0
    # ältere Installationen ohne Port-Einträge nutzen 8080/8081
    if ! grep -qE '^API_PORT=' "$d/.env" && { [ "$p" = 8080 ] || [ "$p" = 8081 ]; }; then return 0; fi
  done
  return 1
}

# 3. .env mit zufälligen Zugangsdaten (nur beim ersten Mal)
schritt "Zugangsdaten"
if [ ! -f .env ]; then
  PASSWORT="$(zufall 8)"
  TG_TOKEN="$(frage 'Telegram-Bot-Token (leer lassen = ohne Telegram): ')"
  TG_CHAT=""
  [ -n "$TG_TOKEN" ] && TG_CHAT="$(frage 'Telegram-Chat-ID: ')"
  TG_AN=false
  [ -n "$TG_TOKEN" ] && [ -n "$TG_CHAT" ] && TG_AN=true

  awk -v pw="$PASSWORT" -v jwt="$(zufall 32)" -v ws="$(zufall 32)" -v user="$INSTANZ" \
      -v tgan="$TG_AN" -v tgtok="$TG_TOKEN" -v tgchat="$TG_CHAT" '
    /^INSTANZ=/                               { print "INSTANZ=" user; next }
    /^(API_PORT|APP_PORT|MASKOTTCHEN|MASKOTTCHEN_NAME)=/ { split($0, kv, "="); print kv[1] "="; next }
    /^FREQTRADE__DRY_RUN=/                    { print "FREQTRADE__DRY_RUN=true"; next }
    /^FREQTRADE__TELEGRAM__ENABLED=/          { print "FREQTRADE__TELEGRAM__ENABLED=" tgan; next }
    /^FREQTRADE__TELEGRAM__TOKEN=/            { print "FREQTRADE__TELEGRAM__TOKEN=" tgtok; next }
    /^FREQTRADE__TELEGRAM__CHAT_ID=/          { print "FREQTRADE__TELEGRAM__CHAT_ID=" tgchat; next }
    /^FREQTRADE__API_SERVER__USERNAME=/       { print "FREQTRADE__API_SERVER__USERNAME=" user; next }
    /^FREQTRADE__API_SERVER__PASSWORD=/       { print "FREQTRADE__API_SERVER__PASSWORD=" pw; next }
    /^FREQTRADE__API_SERVER__JWT_SECRET_KEY=/ { print "FREQTRADE__API_SERVER__JWT_SECRET_KEY=" jwt; next }
    /^FREQTRADE__API_SERVER__WS_TOKEN=/       { print "FREQTRADE__API_SERVER__WS_TOKEN=" ws; next }
    { print }
  ' .env.example > .env
  chmod 600 .env
  echo "[OK] .env angelegt (Telegram: $TG_AN)"
else
  echo "[OK] Vorhandene .env bleibt unverändert"
fi

# Instanz und Ports: beim ersten Mal festlegen, danach aus der .env übernehmen.
# Der erste Bot (biko) nutzt 8080/8081 und Tailscale-Port 443, jeder weitere die nächsten freien.
[ -n "$(env_get INSTANZ)" ] || env_set INSTANZ "$INSTANZ"
[ "$(env_get INSTANZ)" = "$INSTANZ" ] || fehler "In $ZIEL läuft der Bot '$(env_get INSTANZ)', nicht '$INSTANZ'. Anderen BIKO_NAME oder BIKO_DIR wählen."
API_PORT="$(env_get API_PORT)"; APP_PORT="$(env_get APP_PORT)"; TS_PORT="$(env_get TS_PORT)"
if [ -z "$API_PORT" ] || [ -z "$APP_PORT" ]; then
  if [ "$INSTANZ" = "biko" ]; then
    API_PORT=8080; APP_PORT=8081   # wie bisher (auch bei älteren Installationen ohne Port-Einträge)
  else
    API_PORT=8082
    while port_belegt "$API_PORT" || port_belegt "$((API_PORT + 1))"; do API_PORT=$((API_PORT + 2)); done
    APP_PORT=$((API_PORT + 1))
  fi
  env_set API_PORT "$API_PORT"; env_set APP_PORT "$APP_PORT"
fi
if [ -z "$TS_PORT" ]; then
  if [ "$INSTANZ" = "biko" ]; then TS_PORT=443; else TS_PORT=8443; while port_belegt "$TS_PORT"; do TS_PORT=$((TS_PORT + 1)); done; fi
  env_set TS_PORT "$TS_PORT"
fi
URL="http://127.0.0.1:$API_PORT"
APP_URL="http://127.0.0.1:$APP_PORT"
echo "[OK] Bot '$INSTANZ': App-Port $APP_PORT, API-Port $API_PORT (nur am Server)"

# Maskottchen (nur beim ersten Mal fragen; ohne Frage: BIKO_MASKOTTCHEN=id, BIKO_MASKOTTCHEN_NAME=Name)
MASK="$(env_get MASKOTTCHEN)"; MASK_NAME="$(env_get MASKOTTCHEN_NAME)"
if [ -n "${BIKO_MASKOTTCHEN:-}" ]; then MASK="$BIKO_MASKOTTCHEN"; MASK_NAME=""; fi
if [ -z "$MASK" ]; then
  if [ "$(printf '%s\n' $MASKOTTCHEN_LISTE | wc -l)" -gt 1 ]; then
    echo "Welches Maskottchen?"
    i=1; for m in $MASKOTTCHEN_LISTE; do echo "  $i = ${m#*:}"; i=$((i + 1)); done
    W="$(frage "Nummer (Enter = 1): ")"
    [ -n "$W" ] || W=1
    MASK="$(printf '%s\n' $MASKOTTCHEN_LISTE | sed -n "${W}p" | cut -d: -f1)"
  fi
  [ -n "$MASK" ] || MASK="biko"
fi
printf '%s\n' $MASKOTTCHEN_LISTE | cut -d: -f1 | grep -qx "$MASK" || { echo "Hinweis: Maskottchen '$MASK' unbekannt, nehme Biko."; MASK="biko"; }
STANDARD_NAME="$(printf '%s\n' $MASKOTTCHEN_LISTE | grep "^$MASK:" | cut -d: -f2)"
[ -n "${BIKO_MASKOTTCHEN_NAME:-}" ] && MASK_NAME="$BIKO_MASKOTTCHEN_NAME"
if [ -z "$MASK_NAME" ] && [ "$INSTANZ" != "biko" ]; then
  MASK_NAME="$(frage "Wie soll das Maskottchen heißen? (Enter = $STANDARD_NAME): ")"
  [ -n "$MASK_NAME" ] || MASK_NAME="$STANDARD_NAME"
fi
MASK_NAME="$(printf '%s' "$MASK_NAME" | tr -cd 'A-Za-z0-9ÄÖÜäöüß .-' | cut -c1-20)"
[ -n "$MASK_NAME" ] || MASK_NAME="$STANDARD_NAME"
env_set MASKOTTCHEN "$MASK"; env_set MASKOTTCHEN_NAME "$MASK_NAME"
# Die App liest das aus ui/web/instanz.js (wird bei jedem Lauf neu geschrieben, auch nach einem Update)
printf "// Von install.sh geschrieben (aus der .env). Nicht von Hand ändern.\nwindow.BIKO_INSTANZ = { instanz: '%s', maskottchen: '%s', name: '%s' };\n" \
  "$INSTANZ" "$MASK" "$MASK_NAME" > ui/web/instanz.js
sed -i "s|\"name\": \"[^\"]*\"|\"name\": \"$MASK_NAME\"|; s|\"short_name\": \"[^\"]*\"|\"short_name\": \"$MASK_NAME\"|" ui/web/manifest.webmanifest
# Symbol (Kopfzeile, Home-Bildschirm) passend zum Maskottchen
[ -f "ui/web/icon-$MASK.svg" ] && cp "ui/web/icon-$MASK.svg" ui/web/icon.svg
echo "[OK] Maskottchen: $MASK_NAME"

# Zugangsdaten-Zettel (Passwort steht nur in der .env)
PASSWORT_JETZT="$(env_get FREQTRADE__API_SERVER__PASSWORD)"
BENUTZER_JETZT="$(env_get FREQTRADE__API_SERVER__USERNAME)"
printf '%s (Bot %s)\nApp:      %s (am Server; am Handy über Tailscale, siehe unten)\nFreqUI:   %s (Profi-Ansicht, nur über SSH-Tunnel)\nBenutzer: %s\nPasswort: %s\n' \
  "$MASK_NAME" "$INSTANZ" "$APP_URL" "$URL" "$BENUTZER_JETZT" "$PASSWORT_JETZT" > ZUGANGSDATEN.txt
chmod 600 ZUGANGSDATEN.txt

# Börse: Kraken oder Binance (steuert BOT_CONFIG in .env). Ohne Frage: BIKO_BOERSE=kraken|binance
schritt "Börse wählen"
AKTUELL="$(grep -E '^BOT_CONFIG=' .env | tail -n1 | cut -d= -f2- || true)"
[ -n "$AKTUELL" ] || AKTUELL="config.json"
[ "$AKTUELL" = "config.binance.json" ] && AKTUELL_NAME="Binance" || AKTUELL_NAME="Kraken"
case "${BIKO_BOERSE:-}" in
  kraken|Kraken)   WAHL=1 ;;
  binance|Binance) WAHL=2 ;;
  *) WAHL="$(frage "Welche Börse? 1 = Kraken, 2 = Binance (Enter = $AKTUELL_NAME): ")" ;;
esac
case "$WAHL" in
  1) NEU="config.json" ;;
  2) NEU="config.binance.json" ;;
  *) NEU="$AKTUELL" ;;
esac
if grep -qE '^BOT_CONFIG=' .env; then
  sed -i "s|^BOT_CONFIG=.*|BOT_CONFIG=$NEU|" .env
else
  printf '\nBOT_CONFIG=%s\n' "$NEU" >> .env
fi
if [ "$NEU" = "config.binance.json" ]; then
  echo "[OK] Börse: Binance"
  echo "     Hinweis: Binance hat in der EU keine MiCA-Lizenz (siehe README). Für Echtgeld lieber Kraken."
else
  echo "[OK] Börse: Kraken"
fi

# Einstellungen der Biko-App (Strategie, Coins, Takt, Risiko, max. Trades). Nur beim ersten Mal anlegen,
# danach ändert man sie in der App. Freqtrade lädt die Datei als zweite --config.
if [ ! -f user_data/biko-settings.json ]; then
  cat > user_data/biko-settings.json <<'JSON'
{
  "strategy": "EmaTrendStrategy",
  "timeframe": "4h",
  "max_open_trades": 3,
  "exchange": { "pair_whitelist": ["BTC/EUR", "ETH/EUR", "SOL/EUR"] },
  "biko": { "risk_per_trade": 0.01 }
}
JSON
fi

# Der Container läuft als Benutzer 1000 und muss in user_data schreiben dürfen
mkdir -p user_data/logs user_data/data
chown -R 1000:1000 user_data

# 4. Modus: Testmodus (Standard) oder Echtgeld (BIKO_MODUS=live in der .env, siehe TODO.md)
schritt "Modus prüfen"
MODUS="$(env_get BIKO_MODUS)"
[ -n "$MODUS" ] || MODUS="test"
# Offene Echtgeld-Trades in der Live-Datenbank zählen (0, wenn es sie nicht gibt)
live_offen() {
  [ -f user_data/tradesv3.live.sqlite ] && command -v python3 >/dev/null 2>&1 || { echo 0; return; }
  python3 -c 'import sqlite3,sys; print(sqlite3.connect(sys.argv[1]).execute("select count(*) from trades where is_open=1").fetchone()[0])' \
    user_data/tradesv3.live.sqlite 2>/dev/null || echo 0
}
case "$MODUS" in
  live)
    [ "$INSTANZ" = "biko" ] || fehler "Echtgeld nur für den eigenen Bot (biko). Andere Bots auf diesem Server bleiben im Testmodus."
    [ -n "$(env_get FREQTRADE__EXCHANGE__KEY)" ] && [ -n "$(env_get FREQTRADE__EXCHANGE__SECRET)" ] \
      || fehler "BIKO_MODUS=live, aber FREQTRADE__EXCHANGE__KEY/SECRET fehlen in der .env."
    [ "$(env_get FREQTRADE__TELEGRAM__ENABLED)" = "true" ] && [ -n "$(env_get FREQTRADE__TELEGRAM__TOKEN)" ] \
      || fehler "Echtgeld nur mit Telegram-Meldungen. Bitte FREQTRADE__TELEGRAM__* in der .env ausfüllen."
    if [ ! -f user_data/tradesv3.live.sqlite ] && [ "${BIKO_LIVE_OK:-}" != "ja" ]; then
      echo
      echo "  !!! ACHTUNG: Ab jetzt handelt der Bot mit ECHTEM GELD auf deinem Börsenkonto. !!!"
      echo "  Vorher die Liste in TODO.md (Abschnitt 'Vor dem ersten echten Euro') abhaken."
      [ "$(frage 'Zum Bestätigen LIVE eintippen: ')" = "LIVE" ] || fehler "Abgebrochen, nichts geändert. Für Testmodus: BIKO_MODUS=test in der .env."
    fi
    COMPOSE=(docker compose -f docker-compose.yml -f docker-compose.live.yml)
    echo "[OK] ECHTGELD-Modus (Datenbank tradesv3.live.sqlite)"
    ;;
  test)
    OFFEN="$(live_offen)"
    if [ "${OFFEN:-0}" != "0" ]; then
      echo "Warnung: In der Echtgeld-Datenbank sind noch $OFFEN Trade(s) offen. Im Testmodus kümmert sich"
      echo "der Bot NICHT um sie (der Stop-Loss an der Börse bleibt aber stehen). Besser erst verkaufen."
      [ "$(frage 'Trotzdem in den Testmodus wechseln? (j/N): ')" = "j" ] || fehler "Abgebrochen. Für Echtgeld: BIKO_MODUS=live in der .env."
    fi
    COMPOSE=(docker compose -f docker-compose.yml -f docker-compose.testmodus.yml)
    echo "[OK] Testmodus (Spielgeld)"
    ;;
  *) fehler "BIKO_MODUS in der .env muss test oder live sein (ist: $MODUS)." ;;
esac

# 5. Starten
schritt "Bot starten (der erste Download ist ca. 1 GB)"
"${COMPOSE[@]}" pull
# --force-recreate: sonst behält die Biko-App nach einem Update die alte nginx.conf
# (eingebundene Datei) und neue Bereiche wie /settings-api/ fehlen.
"${COMPOSE[@]}" up -d --force-recreate --remove-orphans

schritt "Warten, bis der Bot antwortet"
for _ in $(seq 1 60); do
  curl -fs "$URL/api/v1/ping" >/dev/null 2>&1 && break
  sleep 2
done
if ! curl -fs "$URL/api/v1/ping" >/dev/null 2>&1; then
  "${COMPOSE[@]}" logs --tail 50 || true
  fehler "Der Bot antwortet nicht. Die Meldungen oben bitte an Niko schicken."
fi

# 6. App am Handy: privat über Tailscale (optional)
#    Die App bleibt am Server nur auf 127.0.0.1 gebunden. "tailscale serve" macht sie mit HTTPS
#    ausschließlich für die eigenen Tailscale-Geräte erreichbar, nicht für das Internet.
#    Ohne Frage: BIKO_TAILSCALE=ja (optional TS_AUTHKEY=tskey-... statt Anmelde-Link)
schritt "App am Handy (Tailscale)"
TS_URL=""
TS="${BIKO_TAILSCALE:-}"
if [ -z "$TS" ]; then
  if command -v tailscale >/dev/null 2>&1 && tailscale serve status 2>/dev/null | grep -q "127.0.0.1:$APP_PORT"; then
    TS="ja"   # schon eingerichtet
  else
    TS="$(frage 'App am Handy über Tailscale einrichten? (j/N): ')"
  fi
fi
case "$TS" in
  j|J|ja|Ja|JA|y|Y|yes|1)
    if ! command -v tailscale >/dev/null 2>&1; then
      echo "Tailscale wird installiert ..."
      curl -fsSL https://tailscale.com/install.sh | sh || fehler "Tailscale-Installation fehlgeschlagen."
    fi
    systemctl enable --now tailscaled >/dev/null 2>&1 || true
    if ! tailscale status >/dev/null 2>&1; then
      if [ -n "${TS_AUTHKEY:-}" ]; then
        tailscale up --authkey "$TS_AUTHKEY" --hostname biko
      else
        echo "Gleich erscheint ein Link. Öffne ihn und melde dich mit DEMSELBEN Konto an wie in der Tailscale-App am Handy."
        tailscale up --hostname biko
      fi
    fi
    echo "App für deine Tailscale-Geräte freigeben ..."
    echo "(Falls ein Link zum Aktivieren von HTTPS erscheint: öffnen, bestätigen, dann geht es weiter.)"
    tailscale serve --bg --https="$TS_PORT" "$APP_PORT" \
      || echo "Hinweis: Freigabe hat nicht geklappt. Später nochmal: sudo tailscale serve --bg --https=$TS_PORT $APP_PORT"
    # Adresse dieses Bots: Port 443 steht nicht in der Adresse, andere schon (z. B. :8443)
    if [ "$TS_PORT" = 443 ]; then
      TS_URL="$(tailscale serve status 2>/dev/null | grep -oE 'https://[A-Za-z0-9.-]+(:[0-9]+)?' | grep -vE ':[0-9]+$' | head -n1 || true)"
    else
      TS_URL="$(tailscale serve status 2>/dev/null | grep -oE "https://[A-Za-z0-9.-]+:$TS_PORT" | head -n1 || true)"
    fi
    [ -n "$TS_URL" ] && echo "[OK] $MASK_NAME am Handy: $TS_URL"
    ;;
  *)
    echo "[--] Übersprungen. Später einrichten: install.sh nochmal ausführen und mit j antworten."
    ;;
esac

echo
echo "=============================================="
if [ "$MODUS" = "live" ]; then
  echo "  Läuft! $MASK_NAME handelt mit ECHTEM GELD."
else
  echo "  Läuft! $MASK_NAME handelt NUR mit Spielgeld."
fi
echo
if [ -n "$TS_URL" ]; then
  echo "  App:      $TS_URL  (am Handy, Tailscale-App muss an sein)"
else
  echo "  App:      $APP_URL (vom eigenen PC: ssh -L $APP_PORT:127.0.0.1:$APP_PORT <server>)"
fi
echo "  Login:    Benutzer $BENUTZER_JETZT, Passwort steht in $ZIEL/ZUGANGSDATEN.txt"
echo "  Logs:     cd $ZIEL && docker compose logs --tail 100"
echo "  Notaus:   sudo $ZIEL/scripts/notaus.sh   (nichts Neues kaufen, alles verkaufen)"
echo "  Stoppen:  cd $ZIEL && docker compose down"
if [ "$INSTANZ" != "biko" ]; then
  echo
  echo "  Für jemand anderen? Teile den Server in Tailscale mit seinem Konto:"
  echo "  https://login.tailscale.com/admin/machines -> Server -> ... -> Share"
  echo "  Er installiert die Tailscale-App, nimmt die Einladung an und öffnet die Adresse oben."
fi
echo "=============================================="
