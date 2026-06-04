#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE_DIR="${LEAF_WORKSPACE_DIR:-$(cd "$SCRIPT_DIR/../.." && pwd)}"
LEAF_SCRIPT="$WORKSPACE_DIR/Leaf/scripts/$(basename "$0")"

if [ ! -x "$LEAF_SCRIPT" ]; then
    echo "Leaf deploy helper not found: $LEAF_SCRIPT" >&2
    echo "Run this helper from Leaf/scripts or set LEAF_WORKSPACE_DIR." >&2
    exit 1
fi

exec "$LEAF_SCRIPT" "$@"
