#!/usr/bin/env bash
# Server absichern (Ubuntu/Debian), einmal ausführen, mehrfach ausführen schadet nicht:
#   sudo bash /opt/biko-bot/scripts/server-haerten.sh
#
# Macht:
# 1. Automatische Sicherheitsupdates (unattended-upgrades), Neustart falls nötig um 04:30 UTC.
#    Der Bot startet danach von selbst wieder, der Stop-Loss liegt sowieso an der Börse.
# 2. Firewall (ufw): von außen nur SSH. Die App läuft nur über Tailscale.
# 3. fail2ban: sperrt IPs, die SSH-Passwörter durchprobieren.
# 4. SSH nur noch mit Schlüssel, ABER nur wenn schon ein Schlüssel hinterlegt ist
#    (sonst würdest du dich aussperren). Anleitung dazu siehe TODO.md.
# 5. 2 GB Swap, falls keiner da ist (der Server hat nur 1 GB RAM).
set -euo pipefail
[ "$(id -u)" -eq 0 ] || { echo "Bitte mit sudo starten." >&2; exit 1; }
export DEBIAN_FRONTEND=noninteractive

echo "==> Pakete"
apt-get update -qq
apt-get install -y -qq unattended-upgrades ufw fail2ban >/dev/null

echo "==> Automatische Sicherheitsupdates"
cat > /etc/apt/apt.conf.d/20auto-upgrades <<'CONF'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
APT::Periodic::AutocleanInterval "7";
CONF
cat > /etc/apt/apt.conf.d/52biko-upgrades <<'CONF'
Unattended-Upgrade::Automatic-Reboot "true";
Unattended-Upgrade::Automatic-Reboot-Time "04:30";
CONF
systemctl enable --now unattended-upgrades >/dev/null 2>&1 || true
echo "[OK] Sicherheitsupdates laufen automatisch"

echo "==> Firewall"
ufw default deny incoming >/dev/null
ufw default allow outgoing >/dev/null
ufw allow OpenSSH >/dev/null
ufw allow 41641/udp >/dev/null          # Tailscale (direkte Verbindung)
if ip link show tailscale0 >/dev/null 2>&1; then ufw allow in on tailscale0 >/dev/null; fi
ufw --force enable >/dev/null
echo "[OK] Firewall an: von außen nur SSH (und Tailscale)"

echo "==> fail2ban"
systemctl enable --now fail2ban >/dev/null 2>&1 || true
echo "[OK] fail2ban läuft"

echo "==> SSH"
if [ -s /root/.ssh/authorized_keys ] || ls /home/*/.ssh/authorized_keys >/dev/null 2>&1; then
  cat > /etc/ssh/sshd_config.d/99-biko.conf <<'CONF'
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitRootLogin prohibit-password
CONF
  sshd -t && (systemctl reload ssh 2>/dev/null || systemctl reload sshd)
  echo "[OK] SSH nur noch mit Schlüssel"
else
  echo "[!!] Noch kein SSH-Schlüssel hinterlegt. Passwort-Login bleibt AN (sonst sperrst du dich aus)."
  echo "     Schlüssel hinterlegen (siehe TODO.md), dann dieses Skript nochmal ausführen."
fi

echo "==> Swap"
if [ "$(swapon --show --noheadings | wc -l)" -eq 0 ]; then
  fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile >/dev/null && swapon /swapfile
  grep -q '^/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
  echo "[OK] 2 GB Swap angelegt"
else
  echo "[OK] Swap ist schon da"
fi
echo
echo "Fertig. Zeit am Server: $(date -u) (Bot rechnet in UTC, das passt so)."
