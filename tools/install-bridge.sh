#!/bin/sh
# Install and start the Arch84 bridge as a systemd USER service (no root needed).
#   tools/install-bridge.sh            install + enable + start
#   tools/install-bridge.sh --remove   stop, disable and remove it
# To keep it running when you are logged out:  loginctl enable-linger "$USER"
set -e
REPO="$(cd "$(dirname "$0")/.." && pwd)"
UNIT="$HOME/.config/systemd/user/arch84-bridge.service"
if [ "$1" = "--remove" ]; then
    systemctl --user disable --now arch84-bridge.service 2>/dev/null || true
    rm -f "$UNIT"
    systemctl --user daemon-reload
    echo "arch84-bridge removed"
    exit 0
fi
PYTHON="$(command -v python3)"
mkdir -p "$(dirname "$UNIT")"
sed -e "s|@REPO@|$REPO|g" -e "s|@PYTHON@|$PYTHON|g" "$REPO/tools/systemd/arch84-bridge.service" > "$UNIT"
systemctl --user daemon-reload
systemctl --user enable --now arch84-bridge.service
echo "installed $UNIT"
echo "status:  systemctl --user status arch84-bridge"
echo "logs:    journalctl --user -u arch84-bridge -f"
