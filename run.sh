#!/bin/sh
# Launcher for Linux and macOS.  Any arguments are passed through to the game,
# e.g.  ./run.sh --low --software
set -e
cd "$(dirname "$0")"
for PY in python3 python; do
    if command -v "$PY" >/dev/null 2>&1; then
        exec "$PY" main.py "$@"
    fi
done
echo "Python 3 was not found. Install it from https://www.python.org/downloads/" >&2
exit 1
