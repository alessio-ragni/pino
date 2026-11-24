#!/bin/bash
# One-off, ON the machine, as root: renames the service user, folders, database, settings and
# services from <old> to <new>, keeping data and the Claude login. Called by migra-a-pino.sh.
#
#   bash deploy/aws/migra-macchina.sh frankino pino
#
# Every step checks whether it has already been done, so it can run twice.
set -euo pipefail
OLD="${1:?old name}"
NEW="${2:?new name}"
UP_OLD=$(echo "$OLD" | tr a-z A-Z)
UP_NEW=$(echo "$NEW" | tr a-z A-Z)

echo "› stop $OLD"
for unit in "$OLD.service" "$OLD-backup.timer" "$OLD-secrets.service"; do
  systemctl stop "$unit" 2>/dev/null || true
  systemctl disable "$unit" 2>/dev/null || true
  rm -f "/etc/systemd/system/$unit"
done
rm -f "/etc/systemd/system/$OLD-backup.service" "/usr/local/bin/$OLD-secrets" "/usr/local/bin/$OLD-backup"
rm -rf "/run/$OLD"
systemctl daemon-reload

echo "› user $OLD → $NEW"
if id "$OLD" >/dev/null 2>&1; then
  pkill -u "$OLD" || true
  sleep 2
  usermod -l "$NEW" -d "/home/$NEW" -m "$OLD"
  groupmod -n "$NEW" "$OLD"
fi
# Claude Code's launcher is a link with the old home in it.
for link in /home/"$NEW"/.local/bin/*; do
  [ -L "$link" ] || continue
  target=$(readlink "$link")
  case "$target" in */home/"$OLD"/*) ln -sfn "${target//\/home\/$OLD\//\/home\/$NEW\/}" "$link" ;; esac
done

echo "› folders and database"
if [ -d "/opt/$OLD" ]; then mv "/opt/$OLD" "/opt/$NEW"; fi
if [ -d "/var/lib/$OLD" ]; then mv "/var/lib/$OLD" "/var/lib/$NEW"; fi
for ext in "" -wal -shm; do
  if [ -f "/var/lib/$NEW/$OLD.db$ext" ]; then mv "/var/lib/$NEW/$OLD.db$ext" "/var/lib/$NEW/$NEW.db$ext"; fi
done
if [ -d "/etc/$OLD" ]; then mv "/etc/$OLD" "/etc/$NEW"; fi
sed -i -e "s/^${UP_OLD}_/${UP_NEW}_/" -e "s#/var/lib/$OLD#/var/lib/$NEW#" "/etc/$NEW/config"
echo "/$NEW/" >"/etc/$NEW/params"
chown -R "$NEW:$NEW" "/opt/$NEW" "/var/lib/$NEW"
chown root:"$NEW" "/etc/$NEW"

echo "› code and its environment (the old one has the old paths inside)"
cd "/opt/$NEW"
sudo -u "$NEW" git remote set-url origin "https://github.com/alessio-ragni/$NEW.git"
sudo -u "$NEW" git pull --ff-only
rm -rf "/opt/$NEW/server/.venv"
sudo -u "$NEW" python3 -m venv "/opt/$NEW/server/.venv"
sudo -u "$NEW" "/opt/$NEW/server/.venv/bin/pip" install --quiet --upgrade pip
sudo -u "$NEW" "/opt/$NEW/server/.venv/bin/pip" install --quiet -e "/opt/$NEW/server"

echo "› services, the same as on a new machine"
sed -n '/^# Secrets from SSM/,$p' "/opt/$NEW/deploy/aws/user-data.sh" | bash

echo "› Tailscale name"
tailscale set --hostname="$NEW" || echo "tailscale set failed: rename the machine by hand in the Tailscale admin"

sleep 3
systemctl --no-pager status "$NEW" | head -5
