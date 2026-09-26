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
mkdir -p "$INSTALL_ROOT/secrets" "$INSTALL_ROOT/vendor" "$RELEASE_DIR"
chmod 0755 "$INSTALL_ROOT/releases" "$INSTALL_ROOT/data" "$INSTALL_ROOT/logs" "$INSTALL_ROOT/vendor" "$RELEASE_DIR"
chmod 0700 "$INSTALL_ROOT/secrets"
cp -R "$SOURCE_DIR/seo_feedback" "$RELEASE_DIR/seo_feedback"
cp "$SOURCE_DIR/requirements.txt" "$RELEASE_DIR/requirements.txt"
cp "$SOURCE_DIR/README.md" "$RELEASE_DIR/README.md"
cp "$SOURCE_DIR/run.sh" "$RELEASE_DIR/run"
chmod 0755 "$RELEASE_DIR/run"

python3 -m pip install \
    --disable-pip-version-check \
    --upgrade \
    --target "$INSTALL_ROOT/vendor" \
    -r "$RELEASE_DIR/requirements.txt"
ln -sfn "$RELEASE_DIR" "$INSTALL_ROOT/current"

echo "Installed release: $RELEASE_DIR"
echo "Current release: $(readlink "$INSTALL_ROOT/current")"
echo "Crontab was not modified."
