#!/bin/sh
set -eu

export PYTHONPATH="/srv/seo-feedback/vendor${PYTHONPATH:+:$PYTHONPATH}"
exec /usr/bin/python3 -m seo_feedback "$@"
