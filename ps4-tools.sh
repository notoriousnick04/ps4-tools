#!/usr/bin/env bash
# Start the PS4 Tools web UI.
#
#   ./ps4-tools.sh                 # http://127.0.0.1:8765
#   ./ps4-tools.sh --port 9000     # custom port
#   ./ps4-tools.sh --no-browser    # print the URL only
#   ./ps4-tools.sh --host 0.0.0.0  # expose to your LAN (opt-in)
#
# Missing dependencies are offered for install on the first launch.
set -euo pipefail

cd -- "$(dirname -- "${BASH_SOURCE[0]}")"

die() {
    printf 'ps4-tools: %s\n' "$*" >&2
    exit 1
}

python_for_pillow() {
    if [ -x .venv/bin/python ] && .venv/bin/python -c 'import PIL' >/dev/null 2>&1; then
        printf '%s' .venv/bin/python
    else
        printf '%s' python3
    fi
}

deps_ok() {
    command -v python3 >/dev/null 2>&1 || return 1
    local py
    py=$(python_for_pillow)
    "$py" -c 'import PIL' >/dev/null 2>&1 || return 1
    command -v magick >/dev/null 2>&1 || command -v convert >/dev/null 2>&1
}

if ! deps_ok; then
    printf 'ps4-tools: dependencies are missing (Pillow and/or ImageMagick).\n' >&2
    if [ -t 0 ] && [ -x ./install.sh ]; then
        printf 'Run ./install.sh now? [Y/n] '
        read -r reply || reply=""
        case "$reply" in
            ""|y|Y|yes|YES) ./install.sh ;;
            *) die "run ./install.sh first" ;;
        esac
    else
        die "run ./install.sh first"
    fi
    deps_ok || die "dependencies are still missing; run ./install.sh and try again"
fi

exec "$(python_for_pillow)" server.py "$@"
