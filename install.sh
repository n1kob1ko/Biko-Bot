#!/usr/bin/env bash
# Biko Bot: Ein-Zeilen-Installation auf einem eigenen Linux-Server (Ubuntu/Debian).
# Startet IMMER im Testmodus (Dry-Run, nur Spielgeld, keine Börsen-Keys).
#
#   curl -fsSL https://raw.githubusercontent.com/n1kob1ko/biko-bot/main/install.sh | sudo bash
#
# Nochmal ausführen = Bot-Code aktualisieren und neu starten. .env und Trades bleiben erhalten.
set -euo pipefail

REPO="n1kob1ko/biko-bot"
BRANCH="${BIKO_BRANCH:-main}"
ZIEL="${BIKO_DIR:-/opt/biko-bot}"
URL="http://127.0.0.1:8080"
APP_URL="http://127.0.0.1:8081"

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
echo "  Biko Bot - Installation (Testmodus, Spielgeld)"
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

# 3. .env mit zufälligen Zugangsdaten (nur beim ersten Mal)
schritt "Zugangsdaten"
if [ ! -f .env ]; then
  PASSWORT="$(zufall 8)"
  TG_TOKEN="$(frage 'Telegram-Bot-Token (leer lassen = ohne Telegram): ')"
  TG_CHAT=""
  [ -n "$TG_TOKEN" ] && TG_CHAT="$(frage 'Telegram-Chat-ID: ')"
  TG_AN=false
  [ -n "$TG_TOKEN" ] && [ -n "$TG_CHAT" ] && TG_AN=true

  awk -v pw="$PASSWORT" -v jwt="$(zufall 32)" -v ws="$(zufall 32)" \
      -v tgan="$TG_AN" -v tgtok="$TG_TOKEN" -v tgchat="$TG_CHAT" '
    /^FREQTRADE__DRY_RUN=/                    { print "FREQTRADE__DRY_RUN=true"; next }
    /^FREQTRADE__TELEGRAM__ENABLED=/          { print "FREQTRADE__TELEGRAM__ENABLED=" tgan; next }
    /^FREQTRADE__TELEGRAM__TOKEN=/            { print "FREQTRADE__TELEGRAM__TOKEN=" tgtok; next }
    /^FREQTRADE__TELEGRAM__CHAT_ID=/          { print "FREQTRADE__TELEGRAM__CHAT_ID=" tgchat; next }
    /^FREQTRADE__API_SERVER__USERNAME=/       { print "FREQTRADE__API_SERVER__USERNAME=biko"; next }
    /^FREQTRADE__API_SERVER__PASSWORD=/       { print "FREQTRADE__API_SERVER__PASSWORD=" pw; next }
    /^FREQTRADE__API_SERVER__JWT_SECRET_KEY=/ { print "FREQTRADE__API_SERVER__JWT_SECRET_KEY=" jwt; next }
    /^FREQTRADE__API_SERVER__WS_TOKEN=/       { print "FREQTRADE__API_SERVER__WS_TOKEN=" ws; next }
    { print }
  ' .env.example > .env
  chmod 600 .env
  printf 'Biko Bot\nBiko-App: %s (einfache Ansicht, nur über SSH-Tunnel)\nFreqUI:   %s (Profi-Ansicht, nur über SSH-Tunnel)\nBenutzer: biko\nPasswort: %s\n' "$APP_URL" "$URL" "$PASSWORT" > ZUGANGSDATEN.txt
  chmod 600 ZUGANGSDATEN.txt
  echo "[OK] .env angelegt (Telegram: $TG_AN)"
else
  echo "[OK] Vorhandene .env bleibt unverändert"
fi

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

# Der Container läuft als Benutzer 1000 und muss in user_data schreiben dürfen
mkdir -p user_data/logs user_data/data
chown -R 1000:1000 user_data

# 4. Starten, immer mit Testmodus-Datei
schritt "Bot starten (der erste Download ist ca. 1 GB)"
COMPOSE=(docker compose -f docker-compose.yml -f docker-compose.testmodus.yml)
"${COMPOSE[@]}" pull
"${COMPOSE[@]}" up -d

schritt "Warten, bis der Bot antwortet"
for _ in $(seq 1 60); do
  curl -fs "$URL/api/v1/ping" >/dev/null 2>&1 && break
  sleep 2
done
if ! curl -fs "$URL/api/v1/ping" >/dev/null 2>&1; then
  "${COMPOSE[@]}" logs --tail 50 || true
  fehler "Der Bot antwortet nicht. Die Meldungen oben bitte an Niko schicken."
fi

# 5. Biko-App am Handy: privat über Tailscale (optional)
#    Die App bleibt am Server nur auf 127.0.0.1 gebunden. "tailscale serve" macht sie mit HTTPS
#    ausschließlich für die eigenen Tailscale-Geräte erreichbar, nicht für das Internet.
#    Ohne Frage: BIKO_TAILSCALE=ja (optional TS_AUTHKEY=tskey-... statt Anmelde-Link)
schritt "Biko-App am Handy (Tailscale)"
TS_URL=""
TS="${BIKO_TAILSCALE:-}"
if [ -z "$TS" ]; then
  if command -v tailscale >/dev/null 2>&1 && tailscale serve status 2>/dev/null | grep -q '8081'; then
    TS="ja"   # schon eingerichtet
  else
    TS="$(frage 'Biko-App am Handy über Tailscale einrichten? (j/N): ')"
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
    echo "Biko-App für deine Tailscale-Geräte freigeben ..."
    echo "(Falls ein Link zum Aktivieren von HTTPS erscheint: öffnen, bestätigen, dann geht es weiter.)"
    tailscale serve --bg 8081 \
      || echo "Hinweis: Freigabe hat nicht geklappt. Später nochmal: sudo tailscale serve --bg 8081"
    TS_URL="$(tailscale serve status 2>/dev/null | grep -o 'https://[^ ]*' | head -n1 || true)"
    [ -n "$TS_URL" ] && echo "[OK] Biko-App am Handy: $TS_URL"
    ;;
  *)
    echo "[--] Übersprungen. Später einrichten: install.sh nochmal ausführen und mit j antworten."
    ;;
esac

echo
echo "=============================================="
echo "  Läuft! Der Bot handelt NUR mit Spielgeld."
echo
if [ -n "$TS_URL" ]; then
  echo "  Biko-App: $TS_URL  (am Handy, Tailscale-App muss an sein)"
else
  echo "  Biko-App: $APP_URL (vom eigenen PC: ssh -L 8081:127.0.0.1:8081 <server>)"
fi
echo "  Telegram: schreib dem Bot /status oder /profit"
echo "  Logs:     cd $ZIEL && docker compose logs --tail 100"
echo "  Stoppen:  cd $ZIEL && docker compose down"
echo "=============================================="
