#!/bin/bash
# Installs or updates Pino on a Linux server you reach over Tailscale (Ubuntu, any user with
# `loginctl enable-linger`). Run it ON the server, as the user Pino will run as:
#
#   curl -fsSL https://raw.githubusercontent.com/alessio-ragni/pino/main/deploy/vps/installa.sh | bash
#   # or, with the repo already there:  bash ~/pino/deploy/vps/installa.sh
#
# The first time it writes ~/.config/pino/env with a fresh token and an empty OpenAI key: fill
# the key in, then run it again. Claude Code must be logged in with your subscription (`claude`,
# then /login); never set ANTHROPIC_API_KEY. Running it again updates the code and restarts.
set -euo pipefail

REPO="${PINO_REPO:-https://github.com/alessio-ragni/pino.git}"
HOME_DIR="${PINO_HOME:-$HOME/pino}"
CONF="$HOME/.config/pino/env"
DATA="${PINO_DATA:-$HOME/.local/share/pino}"
export PATH="$HOME/.local/bin:$PATH"

echo "› code in $HOME_DIR"
if [ -d "$HOME_DIR/.git" ]; then
  git -C "$HOME_DIR" pull --ff-only
else
  git clone "$REPO" "$HOME_DIR"
fi

echo "› Python environment"
command -v uv >/dev/null || curl -LsSf https://astral.sh/uv/install.sh | sh
uv venv --quiet --allow-existing "$HOME_DIR/server/.venv"
uv pip install --quiet --python "$HOME_DIR/server/.venv/bin/python" -e "$HOME_DIR/server"

echo "› settings in $CONF"
mkdir -p "$(dirname "$CONF")" "$DATA"
if [ ! -f "$CONF" ]; then
  umask 077
  cat >"$CONF" <<EOF
PINO_DATA=$DATA
PINO_HOST=0.0.0.0
PINO_PORT=4390
PINO_TOKEN=$(openssl rand -hex 24)
PINO_TZ=Europe/Rome
PINO_MODEL=claude-haiku-5-5
PINO_EFFORT=low
PINO_LANG=it
PINO_CONNECTORS=WhatsApp,Gmail,Google Calendar,Google Drive
PINO_STT=openai
PINO_TTS=openai
PINO_OPENAI_VOICE=ash
OPENAI_API_KEY=
EOF
  echo "  written: put the OpenAI key in OPENAI_API_KEY, then run this again"
fi
chmod 600 "$CONF"

if grep -q '^ANTHROPIC_API_KEY=' "$CONF" || [ -n "${ANTHROPIC_API_KEY:-}" ]; then
  echo "ANTHROPIC_API_KEY is set: Claude would bill per use instead of your subscription. Remove it." >&2
  exit 1
fi
command -v claude >/dev/null || echo "  warning: Claude Code is not installed for this user (curl -fsSL https://claude.ai/install.sh | bash)"

echo "› service"
mkdir -p "$HOME/.config/systemd/user"
cat >"$HOME/.config/systemd/user/pino.service" <<EOF
[Unit]
Description=Pino
After=network-online.target

[Service]
WorkingDirectory=$HOME_DIR/server
EnvironmentFile=$CONF
Environment=PATH=$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin
ExecStart=$HOME_DIR/server/.venv/bin/python -m pino
Restart=always
RestartSec=5

[Install]
WantedBy=default.target
EOF
systemctl --user daemon-reload
if grep -q '^OPENAI_API_KEY=.\+' "$CONF"; then
  systemctl --user enable --now pino.service
  systemctl --user restart pino.service
  sleep 3
  systemctl --user --no-pager status pino.service | head -5
else
  echo "  not started: the OpenAI key is still empty in $CONF"
fi
