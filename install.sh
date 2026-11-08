#!/usr/bin/env bash
set -euo pipefail

echo "Installing character-sheet skill..."

# Try common skill locations
TARGETS=(
  "$HOME/.grok/skills/character-sheet"
  "/root/.grok/server-skills/character-sheet"
  "/root/.grok/skills/character-sheet"
)

INSTALLED=0

for TARGET in "${TARGETS[@]}"; do
  PARENT=$(dirname "$TARGET")
  if [ -d "$PARENT" ] || mkdir -p "$PARENT" 2>/dev/null; then
    echo "Installing to $TARGET"
    rm -rf "$TARGET"
    git clone --depth 1 https://github.com/chicksonspeed/character-sheet-skill.git "$TARGET"
    INSTALLED=1
    break
  fi
done

if [ "$INSTALLED" -eq 0 ]; then
  echo "Could not find a writable skills directory."
  echo "Clone manually:"
  echo "  git clone https://github.com/chicksonspeed/character-sheet-skill.git ~/.grok/skills/character-sheet"
  exit 1
fi

echo ""
echo "Done. Start a new Grok chat and say:"
echo "  Make a character sheet"
echo ""
