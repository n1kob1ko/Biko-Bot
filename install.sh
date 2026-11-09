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
  printf 'Biko Bot - FreqUI\nAdresse:  %s (nur über SSH-Tunnel)\nBenutzer: biko\nPasswort: %s\n' "$URL" "$PASSWORT" > ZUGANGSDATEN.txt
  chmod 600 ZUGANGSDATEN.txt
  echo "[OK] .env angelegt (Telegram: $TG_AN)"
else
  echo "[OK] Vorhandene .env bleibt unverändert"
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

echo
echo "=============================================="
echo "  Läuft! Der Bot handelt NUR mit Spielgeld."
echo
echo "  Telegram: schreib dem Bot /status oder /profit"
echo "  Logs:     cd $ZIEL && docker compose logs --tail 100"
echo "  Stoppen:  cd $ZIEL && docker compose down"
echo "=============================================="
