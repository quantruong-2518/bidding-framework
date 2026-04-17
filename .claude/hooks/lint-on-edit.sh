#!/bin/bash
# Auto-format after Claude edits a file
# Triggered by PostToolUse on Write|Edit

FILE="$1"
EXT="${FILE##*.}"

cd "$CLAUDE_PROJECT_DIR" 2>/dev/null || exit 0

case "$EXT" in
  py)
    # Python: black + ruff
    if command -v black &>/dev/null; then
      black --quiet "$FILE" 2>/dev/null
    fi
    if command -v ruff &>/dev/null; then
      ruff check --fix --quiet "$FILE" 2>/dev/null
    fi
    ;;
  ts|tsx|js|jsx)
    # TypeScript/JavaScript: prettier + eslint
    if command -v prettier &>/dev/null; then
      prettier --write "$FILE" 2>/dev/null
    fi
    if command -v eslint &>/dev/null; then
      eslint --fix "$FILE" 2>/dev/null
    fi
    ;;
esac

exit 0
