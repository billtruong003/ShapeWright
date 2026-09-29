#!/usr/bin/env sh
# Shapewright CLI launcher: works from a fresh clone without installing the package.
DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHONPATH="$DIR${PYTHONPATH:+:$PYTHONPATH}" exec python3 -m shapewright "$@"
