# Workspace panel validation

The v0.2.0 checks use synthetic accounts and temporary databases. They do not open or
edit any installed account's history, files or notes.

## Automated HTTP regression tests

Run `python3 -m unittest discover -s tests`. The suite includes the existing role,
class, policy, tutoring and teaching-file checks, plus these pocket-related cases:

- Notes remains available when a legacy installation has `notes=0` in its experimental
  flags. Initial notes, reads, saves and personal model context continue working.
- The retired Notes toggle cannot disable Notes. Non-admin feature changes remain denied.
- Inline personal PDF responses retain ownership checks. The owner receives PDF bytes
  with an inline disposition and same-origin frame permission; another user receives 404.
- Normal downloads remain attachments. Text files cannot opt into active inline content.

Existing workspace tests also cover note ownership, sanitised formatting, account-specific
model context and read-only staff access within the assigned roster.

## Browser regression check

Install the optional tools and browser once:

```bash
npm ci
npx playwright-core install chromium
npm run check:workspace
# Or use an installed Chromium:
CHROMIUM_PATH=/path/to/chromium npm run check:workspace
# Optional screenshots:
WORKSPACE_SCREENSHOTS=/tmp/school-workspace-check npm run check:workspace
```

The runner starts `scripts/workspace-fixture.py`, which creates a temporary SQLite
installation, synthetic accounts and a three-page teaching PDF. It selects a free
loopback port, runs the browser checks and shuts down its server. No model generation
is needed. This check is separate from the HTTP suite; it requires Chromium and Node.

The browser check covers:

- Empty versus typed Send state.
- Notes autosave and composer drafts across Notes/Files switches.
- Reusing the same editor and preview DOM, rather than rebuilding on each switch.
- Rapid repeated switching and a single final visible card.
- Desktop chat width increasing when the card is minimised.
- Uploaded text preview, course PDF access and retained page selection.
- Theme switching while a source remains open.
- Mobile touch targets, typing in the overlay, backdrop/minimise/Escape dismissal.
- Reduced motion and no horizontal page overflow.
- No uncaught browser errors during these interactions.

During visual review, also inspect card alignment, bookmark hover label spacing and the
fold/slide transition at normal speed. A hidden parent must be set before clearing the
sheet's final folded transform; otherwise a full-height flash can reappear on exit.

## What these checks establish

They check UI behaviour, persistence and access boundaries. They do not establish that
all generated answers are factually correct, and they do not replace the real-model
teaching evaluation described in the README. The source cleanup keeps existing CSS rule
order and script dependency order; vendor libraries are excluded from formatting.
