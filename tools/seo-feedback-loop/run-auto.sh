#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
export PYTHONPATH="$SCRIPT_DIR:/srv/seo-feedback/vendor${PYTHONPATH:+:$PYTHONPATH}"
exec python3 -m seo_feedback.automation "$@"
