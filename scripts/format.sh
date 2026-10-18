#!/usr/bin/env bash
# Run from anywhere. --check reports drift without changing source files.
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ "${1:-}" == "--check" ]]; then
  python3 -m black --check app scripts tests
  npx --yes prettier@3.6.2 --check 'app/static/*.{js,css,html}' 'scripts/*.cjs' 'package*.json' 'config/*.json' '*.md' 'docs/**/*.md' '.github/**/*.yml' '.prettierrc.json'
else
  python3 -m black app scripts tests
  npx --yes prettier@3.6.2 --write 'app/static/*.{js,css,html}' 'scripts/*.cjs' 'package*.json' 'config/*.json' '*.md' 'docs/**/*.md' '.github/**/*.yml' '.prettierrc.json'
fi
