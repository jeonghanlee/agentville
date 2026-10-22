#!/usr/bin/env bash
# Install or upgrade AgentVille for the login user (docs/install.md Sections 2 to 4).
#
#   curl -fsSL https://raw.githubusercontent.com/jeonghanlee/agentville/master/install.sh | bash -s -- [options]

set -euo pipefail

REPO_URL="${AGENTVILLE_REPO:-https://github.com/jeonghanlee/agentville.git}"
SRC_DIR="$HOME/.local/src/agentville"
VENV_DIR="$HOME/.local/opt/agentville"
BIN_DIR="$HOME/.local/bin"
UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
CONFIG_FILE="${XDG_CONFIG_HOME:-$HOME/.config}/agentville/config.yaml"

usage() {
    cat <<'EOF'
Usage: install.sh [options]

Install or upgrade AgentVille for the login user.

  --hq               also install HQ (agentville-hq and its service)
  --ref REF          release tag, branch, or commit (default: latest release tag)
  --hq-url URL       set hq.url in the Collector configuration
  --token-file FILE  set hq.token in the Collector configuration from FILE
  --no-start         install the services without enabling or restarting them
  -h, --help         show this help
EOF
}

die() {
    printf 'install.sh: %s\n' "$*" >&2
    exit 1
}

info() {
    printf '==> %s\n' "$*"
}

find_python() {
    local candidate
    for candidate in python3 python3.14 python3.13 python3.12; do
        if command -v "$candidate" >/dev/null 2>&1 \
            && "$candidate" -c 'import sys, venv, ensurepip; sys.exit(sys.version_info < (3, 12))' >/dev/null 2>&1; then
            printf '%s\n' "$candidate"
            return 0
        fi
    done
    return 1
}

has_user_systemd() {
    command -v systemctl >/dev/null 2>&1 && systemctl --user show-environment >/dev/null 2>&1
}

fetch_source() {
    local ref="$1"
    if [[ -d "$SRC_DIR/.git" ]]; then
        if [[ -n "$(git -C "$SRC_DIR" status --porcelain --untracked-files=no)" ]]; then
            die "$SRC_DIR has local changes; commit, stash, or discard them first"
        fi
        info "Updating $SRC_DIR"
        git -C "$SRC_DIR" fetch --quiet --tags --force origin
    else
        info "Cloning $REPO_URL into $SRC_DIR"
        mkdir -p "$(dirname "$SRC_DIR")"
        git clone --quiet "$REPO_URL" "$SRC_DIR"
    fi
    if [[ -z "$ref" ]]; then
        ref="$(git -C "$SRC_DIR" tag --list '[0-9]*.[0-9]*.[0-9]*' --sort=-v:refname | head -n 1)"
        [[ -n "$ref" ]] || ref="origin/HEAD"
    fi
    # A branch name resolves to the fetched remote branch; local branches are never updated.
    local commit
    commit="$(git -C "$SRC_DIR" rev-parse --verify --quiet "origin/${ref}^{commit}" \
        || git -C "$SRC_DIR" rev-parse --verify --quiet "${ref}^{commit}")" \
        || die "unknown ref: $ref"
    info "Checking out $ref"
    git -C "$SRC_DIR" checkout --quiet --detach "$commit"
}

install_package() {
    local python="$1" with_hq="$2" target="$SRC_DIR"
    [[ "$with_hq" == 1 ]] && target="${SRC_DIR}[hq]"
    if [[ ! -x "$VENV_DIR/bin/python" ]]; then
        info "Creating $VENV_DIR with $python"
        "$python" -m venv "$VENV_DIR"
    fi
    info "Installing $target"
    "$VENV_DIR/bin/pip" install --quiet --disable-pip-version-check "$target"
    mkdir -p "$BIN_DIR"
    ln -sf "$VENV_DIR/bin/agentville-collector" "$BIN_DIR/"
    if [[ "$with_hq" == 1 ]]; then
        ln -sf "$VENV_DIR/bin/agentville-hq" "$BIN_DIR/"
    fi
}

configure_collector() {
    local hq_url="$1" token_file="$2"
    if [[ ! -e "$CONFIG_FILE" ]]; then
        info "Writing $CONFIG_FILE"
        "$VENV_DIR/bin/agentville-collector" --once --output /dev/null
    fi
    [[ -n "$hq_url" || -n "$token_file" ]] || return 0
    info "Setting the HQ connection in $CONFIG_FILE"
    "$VENV_DIR/bin/python" - "$CONFIG_FILE" "$hq_url" "$token_file" <<'EOF'
import os
import sys

import yaml

path, url, token_file = sys.argv[1:4]
with open(path, encoding="utf-8") as fh:
    document = yaml.safe_load(fh) or {}
hq = document.setdefault("hq", {})
if url:
    hq["url"] = url
if token_file:
    with open(token_file, encoding="utf-8") as fh:
        hq["token"] = fh.read().strip()
os.chmod(path, 0o600)
with open(path, "w", encoding="utf-8") as fh:
    yaml.safe_dump(document, fh, sort_keys=False)
EOF
}

install_services() {
    local with_hq="$1" start="$2" unit
    local -a units=(agentville-collector)
    [[ "$with_hq" == 1 ]] && units=(agentville-hq agentville-collector)
    mkdir -p "$UNIT_DIR"
    for unit in "${units[@]}"; do
        # An existing unit may carry local ExecStart edits (TLS, tokens); keep it.
        if [[ ! -e "$UNIT_DIR/$unit.service" ]]; then
            cp "$SRC_DIR/deploy/systemd/$unit.service" "$UNIT_DIR/"
        fi
    done
    systemctl --user daemon-reload
    if [[ "$start" == 1 ]]; then
        info "Starting ${units[*]}"
        systemctl --user enable --quiet "${units[@]}"
        systemctl --user restart "${units[@]}"
        sleep 2
        for unit in "${units[@]}"; do
            systemctl --user is-active --quiet "$unit" \
                || die "$unit did not start; see: journalctl --user -u $unit"
        done
    fi
}

main() {
    local with_hq=0 ref="" hq_url="" token_file="" start=1
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --hq) with_hq=1 ;;
            --ref) ref="${2:?--ref needs a value}"; shift ;;
            --hq-url) hq_url="${2:?--hq-url needs a value}"; shift ;;
            --token-file) token_file="${2:?--token-file needs a value}"; shift ;;
            --no-start) start=0 ;;
            -h | --help) usage; exit 0 ;;
            *) usage >&2; die "unknown option: $1" ;;
        esac
        shift
    done
    if [[ -n "$token_file" && ! -r "$token_file" ]]; then
        die "cannot read token file: $token_file"
    fi

    command -v git >/dev/null 2>&1 || die "git is required"
    local python
    python="$(find_python)" || die "Python 3.12 or later with venv is required; see https://jeonghanlee.github.io/agentville/install.html"

    fetch_source "$ref"
    install_package "$python" "$with_hq"
    configure_collector "$hq_url" "$token_file"

    if has_user_systemd; then
        install_services "$with_hq" "$start"
    else
        info "No systemd user instance; run in the foreground:"
        [[ "$with_hq" == 1 ]] && printf '    %s\n' "$BIN_DIR/agentville-hq --host 127.0.0.1 --port 8470"
        printf '    %s\n' "$BIN_DIR/agentville-collector"
    fi

    info "Installed $("$VENV_DIR/bin/agentville-collector" --version)"
    case ":$PATH:" in
        *":$BIN_DIR:"*) ;;
        *) info "Add $BIN_DIR to PATH: export PATH=\"\$HOME/.local/bin:\$PATH\"" ;;
    esac
}

main "$@"
