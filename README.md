# Character Sheet Generator

Interactive Grok skill that generates professional character reference sheets (Will-style layout) from uploaded photos + character info.

It asks you the right questions, tells you which photos to upload, then builds a strict-layout character sheet.

## Quick Install

### One-liner (recommended)
```bash
bash <(curl -sL https://raw.githubusercontent.com/chicksonspeed/character-sheet-skill/main/install.sh)
```

### Manual
```bash
# Clone into your skills folder
git clone https://github.com/chicksonspeed/character-sheet-skill.git ~/.grok/skills/character-sheet

# Or if you use the server skills path:
git clone https://github.com/chicksonspeed/character-sheet-skill.git /root/.grok/server-skills/character-sheet
```

Then restart Grok or start a new chat so it picks up the new skill.

## How to use

Just say any of these in chat:

- “Make a character sheet”
- “Generate a reference sheet for this person”
- “Create a model sheet”

The skill will:
1. Ask you for name, height, weight, role, appearance, style, vibe, and notes
2. Tell you exactly which photos to upload
3. Generate the full character sheet

## Files

- `SKILL.md` — Main skill instructions
- `install.sh` — One-click installer
- `CHANGELOG.md`
- `evals/` — Test cases and triggers
