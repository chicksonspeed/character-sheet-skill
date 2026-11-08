---
name: character-sheet
description: "Generate professional character reference sheets. Use when the user wants a character sheet, reference sheet, or model sheet from photos and info about a person."
type: workflow
lifecycle: active
---

# RefSheet

Interactive workflow to collect character info and reference photos, then generate a strict-layout professional character reference sheet matching the Will-style format.

## Workflow

### Path A — User drops a zip or folder from the web app

If the user uploads a zip or drops a folder that contains `prompt.txt` (and usually a `photos/` folder):

1. Read `prompt.txt` — it already has the filled character information.
2. Use the images in `photos/` (or any images in the upload) as the reference photos.
3. **Skip the questions.** Do not ask for name, height, weight, appearance, style, or vibe.
4. Go straight to generation using the content of `prompt.txt` as the prompt and the uploaded photos as references.

### Path B — No pre-filled package (manual)

1. **Collect information** — Use the `ask_user_question` tool to gather required details in one call with these questions (use the exact structure below). Do not proceed until answers are received.

2. **Request photos** — After answers arrive, tell the user exactly which photos to upload:
   - At least one clear face close-up (front, good lighting)
   - One or more body shots (full body or torso preferred)
   - Optional: additional lifestyle or outfit photos
   Wait for the user to upload the images before continuing.

3. **Generate the sheet** — Once info and images are available:
   - Use the strict layout prompt below, filling in the bracketed values from the user's answers.
   - Attach the uploaded photos as references.
   - Generate the image with the image generation tool / render component using that prompt + references.

## Questions to ask (via ask_user_question) — only for Path B

Ask all of these in a single `ask_user_question` call:

- Name of the character / person
- Height (e.g. 182 cm / 6'0")
- Weight (e.g. 73 kg / 161 lbs)
- Appearance notes (build, skin tone, hair, beard, distinctive features)
- Personal style (how they dress, accessories)
- Vibe / personality (short description)
- Any extra notes for the NOTES section

## Strict layout prompt (fill in brackets)

```
STRICT CHARACTER REFERENCE SHEET LAYOUT. Black background. Do not deviate from this structure.

LEFT SIDEBAR (narrow vertical panel, black background):
- Very large bold white text: "[NAME]"
- Small yellow text underneath: "CHARACTER SHEET"
- Status block: "ONLINE" + time + distance
- Section titled "STATS" with two lines (height, weight) with small icons
- Section titled "APPEARANCE" with 6–8 bullet points
- Section titled "PERSONAL STYLE" with 3–4 bullet points
- Section titled "VIBE" with one short paragraph
- Section titled "COLOR PALETTE" with exactly four color squares labeled Hair / Eyes / Skin / Beard
- Section titled "STYLE PALETTE" with exactly four color squares

TOP RIGHT (three photos in a row, labeled 01, 02, 03 in the top-left corner of each photo):
- Photo 01, Photo 02, Photo 03 using the uploaded reference images

BOTTOM CENTER (white background turnaround):
- Four full-body views side by side labeled exactly: FRONT | LEFT PROFILE | RIGHT PROFILE | BACK
- Same person across all four angles, shirtless, black pants, consistent face and body from the uploaded references

FAR RIGHT PANEL:
- Section titled "DETAILS" with three stacked close-up crops (hair, eyes, lower face)
- Section titled "NOTES" with a short paragraph

Use the uploaded photos as the primary visual reference for face, body, and appearance. Keep the character highly consistent across every view. Clean modern sans-serif typography, high contrast white and yellow text on black, professional character sheet aesthetic, sharp, photorealistic.

Character information:
Name: [NAME]
Height: [HEIGHT]
Weight: [WEIGHT]
Appearance: [build, skin tone, hair, beard, features]
Style: [clothing/style notes]
Vibe: [personality/energy]
```

After generating, show the result and offer to regenerate or adjust any section.
