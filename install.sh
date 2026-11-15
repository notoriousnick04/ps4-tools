#!/usr/bin/env bash
# Install the dependencies for PS4 Tools.
#
#   ./install.sh          # asks before installing anything
#   ./install.sh --yes    # non-interactive
#
# Installs Pillow and ImageMagick with the system package manager. If the
# system Pillow package is unavailable, it falls back to a local .venv.
set -euo pipefail

cd -- "$(dirname -- "${BASH_SOURCE[0]}")"

ASSUME_YES=0

usage() {
    cat <<'EOF'
Usage: ./install.sh [--yes]

Installs Pillow and ImageMagick for PS4 Tools.
  -y, --yes   do not ask for confirmation
  -h, --help  show this help
EOF
}

for arg in "$@"; do
    case "$arg" in
        -y|--yes) ASSUME_YES=1 ;;
        -h|--help) usage; exit 0 ;;
        *) printf 'install.sh: unknown option: %s\n' "$arg" >&2; exit 2 ;;
    esac
done

say() { printf '%s\n' "$*"; }
warn() { printf 'warning: %s\n' "$*" >&2; }
die() { printf 'error: %s\n' "$*" >&2; exit 1; }

have() { command -v "$1" >/dev/null 2>&1; }

as_root() {
    if [ "$(id -u)" -eq 0 ]; then
        "$@"
    elif have sudo; then
        sudo "$@"
    else
        die "root privileges are required to install system packages, and sudo is not available"
    fi
}

# Prefer an existing local virtualenv, otherwise the system interpreter.
PY=python3
if [ -x .venv/bin/python ] && .venv/bin/python -c 'import PIL' >/dev/null 2>&1; then
    PY=.venv/bin/python
fi

have_pillow() { "$PY" -c 'import PIL' >/dev/null 2>&1; }
have_magick() { have magick || have convert; }

magick_version() {
    if have magick; then
        magick -version | head -n 1
    else
        convert -version | head -n 1
    fi
}

detect_pm() {
    if have pacman; then echo pacman
    elif have apt-get; then echo apt
    elif have dnf; then echo dnf
    elif have zypper; then echo zypper
    elif have apk; then echo apk
    else echo none
    fi
}

pm_packages() {
    case "$1:$2" in
        pacman:magick) echo imagemagick ;;
        pacman:pillow) echo python-pillow ;;
        apt:magick) echo imagemagick ;;
        apt:pillow) echo python3-pil ;;
        dnf:magick) echo ImageMagick ;;
        dnf:pillow) echo python3-pillow ;;
        zypper:magick) echo ImageMagick ;;
        zypper:pillow) echo python3-Pillow ;;
        apk:magick) echo imagemagick ;;
        apk:pillow) echo py3-pillow ;;
    esac
}

pm_install() {
    local pm="$1"
    shift
    case "$pm" in
        pacman) as_root pacman -S --needed --noconfirm "$@" ;;
        apt)
            as_root apt-get update >/dev/null 2>&1 || warn "apt-get update failed; continuing"
            as_root apt-get install -y "$@"
            ;;
        dnf) as_root dnf install -y "$@" ;;
        zypper) as_root zypper --non-interactive install "$@" ;;
        apk) as_root apk add --no-cache "$@" ;;
    esac
}

confirm() {
    [ "$ASSUME_YES" -eq 1 ] && return 0
    [ -t 0 ] || return 1
    printf '%s [Y/n] ' "$1"
    local reply
    read -r reply || return 1
    case "$reply" in
        ""|y|Y|yes|YES) return 0 ;;
        *) return 1 ;;
    esac
}

# ---------------------------------------------------------------------------

have python3 || die "python3 is required; install it first (e.g. sudo pacman -S python)"

missing=()
have_pillow || missing+=("Pillow")
have_magick || missing+=("ImageMagick")

if [ ${#missing[@]} -eq 0 ]; then
    say "All dependencies are already installed."
    say "Start the web UI with: ./ps4-tools.sh"
    exit 0
fi

say "PS4 Tools needs: ${missing[*]}"

pm=$(detect_pm)
if [ "$pm" = none ]; then
    die "no supported package manager found; install these manually: Pillow (pip install Pillow) and ImageMagick"
fi

packages=()
have_magick || packages+=("$(pm_packages "$pm" magick)")
have_pillow || packages+=("$(pm_packages "$pm" pillow)")

say "Package manager: $pm"
say "Command: $( [ "$(id -u)" -eq 0 ] || echo "sudo " )$pm install ${packages[*]}"
say ""

if ! confirm "Install now?"; then
    say "Cancelled. Nothing was changed."
    say "Manual install: ${packages[*]}"
    exit 1
fi

say ""
say "Installing ${packages[*]}…"
pm_install "$pm" "${packages[@]}"

if ! have_magick; then
    die "ImageMagick is still missing. Install it manually and run this script again."
fi

if ! have_pillow; then
    say ""
    say "System Pillow is not available; creating a local virtualenv…"
    python3 -m venv .venv \
        || die "could not create .venv (on Debian/Ubuntu install python3-venv)"
    .venv/bin/python -m pip install --quiet --upgrade pip \
        || warn "could not upgrade pip; continuing"
    .venv/bin/python -m pip install --quiet Pillow \
        || die "could not install Pillow with pip"
    PY=.venv/bin/python
    have_pillow || die "Pillow is still missing"
fi

say ""
say "Done."
say "  Pillow:      $("$PY" -c 'import PIL; print(PIL.__version__)')"
say "  ImageMagick: $(magick_version)"
say ""
say "Start the web UI with: ./ps4-tools.sh"
