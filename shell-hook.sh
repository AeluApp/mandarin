#!/usr/bin/env bash
# Mandarin Learning System — shell hook
#
# Source this in your .bashrc or .zshrc:
#   source ~/mandarin/shell-hook.sh
#
# Shows a brief reminder when you open a new terminal
# if you have items due for review.

_mandarin_hook() {
    local VENV="$HOME/mandarin/venv"
    local DB="$HOME/mandarin/data/mandarin.db"

    # Only run if DB exists and venv is set up
    [ -f "$DB" ] && [ -d "$VENV" ] || return

    # Query items due (fast — single SELECT)
    local due
    due=$("$VENV/bin/python3" -c "
import sqlite3, sys
conn = sqlite3.connect('$DB')
try:
    row = conn.execute('''
        SELECT COUNT(*) FROM progress
        WHERE next_review_date <= date(\"now\")
          AND mastery_stage NOT IN (\"durable\")
    ''').fetchone()
    print(row[0] if row else 0)
except Exception:
    print(0)
conn.close()
" 2>/dev/null)

    if [ "$due" -gt 0 ] 2>/dev/null; then
        echo "  漫 $due items due for review  →  ./run"
    fi
}

# Run on shell startup (non-interactive shells skip this)
if [[ $- == *i* ]]; then
    _mandarin_hook
fi
