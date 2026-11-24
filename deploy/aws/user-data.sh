#!/bin/bash
# First boot of the Pino machine on AWS (Ubuntu 24.04, ARM). AWS runs it only once.
# No secrets in here: the OpenAI key and the token are read from SSM at every boot.
# crea.sh replaces __REPO__, __BUCKET__ and __PARAMS__ before handing it to AWS.
set -euxo pipefail
export DEBIAN_FRONTEND=noninteractive

REPO="__REPO__"
BUCKET="__BUCKET__"
PARAMS="__PARAMS__"

apt-get update
apt-get install -y python3 python3-venv python3-pip git sqlite3 curl unzip

# AWS CLI v2 (needed to read the secrets and copy the backup)
curl -fsSL "https://awscli.amazonaws.com/awscli-exe-linux-aarch64.zip" -o /tmp/awscli.zip
unzip -q /tmp/awscli.zip -d /tmp && /tmp/aws/install && rm -rf /tmp/aws /tmp/awscli.zip

# Tailscale: the only way in. The network owner does the login.
curl -fsSL https://tailscale.com/install.sh | sh

# Service user and directories
id pino >/dev/null 2>&1 || useradd --create-home --shell /bin/bash pino
install -d -o pino -g pino /var/lib/pino /opt/pino
install -d -m 750 -o root -g pino /etc/pino

# Code
sudo -u pino git clone "$REPO" /opt/pino
sudo -u pino python3 -m venv /opt/pino/server/.venv
sudo -u pino /opt/pino/server/.venv/bin/pip install --quiet --upgrade pip
sudo -u pino /opt/pino/server/.venv/bin/pip install --quiet -e /opt/pino/server

# Claude Code for the service user: the subscription owner does the /login.
sudo -u pino bash -c 'curl -fsSL https://claude.ai/install.sh | bash'

# Non-secret settings
cat >/etc/pino/config <<EOF
PINO_DATA=/var/lib/pino
PINO_HOST=0.0.0.0
PINO_PORT=4390
PINO_TZ=Europe/Rome
PINO_MODEL=claude-haiku-5-5
PINO_EFFORT=low
PINO_LANG=it
PINO_CONNECTORS=WhatsApp,Gmail,Google Calendar,Google Drive
PINO_STT=openai
PINO_TTS=openai
PINO_OPENAI_VOICE=ash
EOF
echo "$BUCKET" >/etc/pino/backup-bucket
echo "$PARAMS" >/etc/pino/params

# Secrets from SSM at every boot, in memory only (/run is wiped at shutdown)
cat >/usr/local/bin/pino-secrets <<'EOF'
#!/bin/bash
set -euo pipefail
PARAMS=$(cat /etc/pino/params)
TOKEN=$(curl -s -X PUT http://169.254.169.254/latest/api/token -H 'X-aws-ec2-metadata-token-ttl-seconds: 60')
REGION=$(curl -s -H "X-aws-ec2-metadata-token: $TOKEN" http://169.254.169.254/latest/meta-data/placement/region)
install -d -m 750 -o root -g pino /run/pino
umask 027
aws ssm get-parameters-by-path --region "$REGION" --path "$PARAMS" --with-decryption \
  --query 'Parameters[].[Name,Value]' --output text \
  | awk -F'\t' '{n=$1; sub(".*/","",n); print n"="$2}' >/run/pino/secrets
chgrp pino /run/pino/secrets
EOF
chmod 755 /usr/local/bin/pino-secrets

cat >/etc/systemd/system/pino-secrets.service <<'EOF'
[Unit]
Description=Pino: secrets from SSM
Wants=network-online.target
After=network-online.target

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/usr/local/bin/pino-secrets
EOF

cat >/etc/systemd/system/pino.service <<'EOF'
[Unit]
Description=Pino
Requires=pino-secrets.service
After=pino-secrets.service tailscaled.service

[Service]
User=pino
WorkingDirectory=/opt/pino/server
EnvironmentFile=/etc/pino/config
EnvironmentFile=/run/pino/secrets
Environment=PATH=/home/pino/.local/bin:/usr/local/bin:/usr/bin:/bin
ExecStart=/opt/pino/server/.venv/bin/python -m pino
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

# Nightly copy of the database to S3: one per weekday, overwritten each week.
cat >/usr/local/bin/pino-backup <<'EOF'
#!/bin/bash
set -euo pipefail
DB=/var/lib/pino/pino.db
[ -f "$DB" ] || exit 0
OUT=$(mktemp --suffix=.db)
sqlite3 "$DB" ".backup '$OUT'"
aws s3 cp --quiet "$OUT" "s3://$(cat /etc/pino/backup-bucket)/pino-$(date +%u).db"
rm -f "$OUT"
EOF
chmod 755 /usr/local/bin/pino-backup

cat >/etc/systemd/system/pino-backup.service <<'EOF'
[Unit]
Description=Pino: database copy to S3

[Service]
Type=oneshot
ExecStart=/usr/local/bin/pino-backup
EOF

cat >/etc/systemd/system/pino-backup.timer <<'EOF'
[Unit]
Description=Pino: nightly database copy

[Timer]
OnCalendar=*-*-* 03:30:00
Persistent=true

[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload
systemctl enable pino.service pino-backup.timer
systemctl start pino-backup.timer
# Pino starts, but it really answers only after the Claude /login and with the secrets in SSM.
systemctl start pino.service || true
touch /var/lib/pino/.pronto
