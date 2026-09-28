#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
ENV_FILE=/srv/seo-feedback/secrets/runtime.env
if [ -f "$ENV_FILE" ]; then
    set -a
    . "$ENV_FILE"
    set +a
fi
export PYTHONPATH="$SCRIPT_DIR:/srv/seo-feedback/vendor${PYTHONPATH:+:$PYTHONPATH}"
exec /usr/bin/python3 -m seo_feedback "$@"
