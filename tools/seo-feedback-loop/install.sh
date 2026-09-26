#!/bin/sh
set -eu

if [ "$(id -u)" -ne 0 ]; then
    echo "Run as root." >&2
    exit 1
fi

SOURCE_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
INSTALL_ROOT=/srv/seo-feedback
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
RELEASE_DIR="$INSTALL_ROOT/releases/$STAMP"

mkdir -p "$INSTALL_ROOT/releases" "$INSTALL_ROOT/data" "$INSTALL_ROOT/logs"
mkdir -p "$INSTALL_ROOT/secrets" "$RELEASE_DIR"
chmod 0755 "$INSTALL_ROOT/releases" "$INSTALL_ROOT/data" "$INSTALL_ROOT/logs" "$RELEASE_DIR"
chmod 0700 "$INSTALL_ROOT/secrets"
cp -R "$SOURCE_DIR/seo_feedback" "$RELEASE_DIR/seo_feedback"
cp "$SOURCE_DIR/requirements.txt" "$RELEASE_DIR/requirements.txt"
cp "$SOURCE_DIR/README.md" "$RELEASE_DIR/README.md"

if [ ! -x "$INSTALL_ROOT/venv/bin/python" ]; then
    python3 -m venv "$INSTALL_ROOT/venv"
fi
"$INSTALL_ROOT/venv/bin/python" -m pip install --disable-pip-version-check -r "$RELEASE_DIR/requirements.txt"
ln -sfn "$RELEASE_DIR" "$INSTALL_ROOT/current"

echo "Installed release: $RELEASE_DIR"
echo "Current release: $(readlink "$INSTALL_ROOT/current")"
echo "Crontab was not modified."
