#!/usr/bin/env bash
# Launch the objdump GUI from a source checkout without installing.
set -euo pipefail
cd "$(dirname "$0")"
exec python3 -m objdump_gui "$@"
