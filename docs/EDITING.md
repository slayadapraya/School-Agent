# Editing School Agent

This guide is the starting point for changing the application. All application Python,
JavaScript, CSS, HTML and configuration JSON is stored as editable source. No frontend
build or minification step is required. Third-party code under `app/static/vendor/` is
kept as supplied, with its licences.

## Where to make a change

| Change                                                                     | Main files                                                                  |
| -------------------------------------------------------------------------- | --------------------------------------------------------------------------- |
| Page shell, sidebar, chat messages and navigation                          | `app/static/app.js`                                                         |
| Colours, typography, common layout, mobile navigation                      | `app/static/style.css`                                                      |
| Notes/Files edge buttons, shared card layout, folding, mobile overlay      | `app/static/workspace-panels.js`, `app/static/workspace-panels.css`         |
| Note editing, autosave, formatting, colours, floating windows              | `app/static/notes.js`, `app/static/notes.css`                               |
| Send/Stop, attachment tools, input height, model picker                    | `app/static/composer.js`                                                    |
| Class/account management, policies, assignment and monitoring              | `app/static/admin.js`                                                       |
| Larger class/account editors and subject filters                           | `app/static/admin-editors.js`, `app/static/admin-editors.css`               |
| Memories, prompt settings, personal categories, uploads, workspace restore | `app/static/preferences.js`                                                 |
| Teaching-file upload/library and standalone passage readers                | `app/static/materials.js`, `app/static/materials.css`                       |
| Host terminal rendering and input                                          | `app/static/terminal.js`, `app/static/terminal.css`                         |
| HTML entry point and exact script/style load order                         | `app/static/index.html`                                                     |
| HTTP routes, authentication, database startup and chat orchestration       | `app/server.py`                                                             |
| Note ownership, versioned saves, personal model context, staff review      | `app/notes.py`                                                              |
| Personal file extraction, ownership checks, download/preview responses     | `app/files.py`                                                              |
| Class-scoped teaching-file extraction, search and passage access           | `app/course_materials.py`                                                   |
| Roles, classes, subjects and policy inheritance                            | `app/administration.py`, `app/oversight.py`                                 |
| Student tutoring/context and output review                                 | `app/student_tutor.py`, `app/student_context.py`, `app/model_output.py`     |
| Online retrieval and reference formatting                                  | `app/research.py`, `app/references.py`                                      |
| Model loading, cancellation and host PTYs                                  | `app/model_manager.py`, `app/generation_control.py`, `app/host_terminal.py` |
| Saved preferences, memories, chat recovery and categories                  | `app/preferences.py`, `app/chat_archive.py`, `app/personal_categories.py`   |
| Hardware readings and application diagnostics                              | `app/hardware.py`, `app/error_logging.py`                                   |
| Base model instructions and subject catalogues                             | `config/`                                                                   |
| Startup, services, evaluations and releases                                | `scripts/`, `deploy/`, `.github/workflows/`                                 |
| Isolated behaviour and access-control checks                               | `tests/`                                                                    |

## Styles and themes

Start with the named comment sections in `style.css`. Its early rules define the base;
later sections refine typography, theme surfaces, navigation, mobile controls and the
composer. **Order matters:** this cleanup preserves the existing cascade. Component CSS
loads afterwards, with `workspace-panels.css` last for the shared pocket layout.

Use existing theme variables rather than adding fixed page colours:

- `--bg`: main surface; `--panel`: sidebar/panels; `--card`: raised controls.
- `--text`, `--muted`: primary and secondary text.
- `--line`, `--accent`, `--soft`: borders, actions and selected surfaces.
- `--font-ui`: theme typography. Code and terminals deliberately use monospace.
- `--workspace-card-radius` and `--workspace-tab-size`: pocket geometry.
- `--note-accent`, `--note-header-ink`, `--note-font-size`: individual saved notes.

Search for `.theme-studio` to adjust Research Studio. Put a change in its relevant
section or component file, keeping its mobile and reduced-motion rules nearby. Avoid
appending another unrelated override at the end of the shared stylesheet.

## JavaScript structure

The frontend uses plain deferred scripts sharing functions and state, rather than an
npm application framework. Keep the order in `index.html`: later feature scripts extend
some earlier functions. For example `composer.js` supplies the active composer, and
`workspace-panels.js` connects existing file actions to the shared pocket. The base
composer in `app.js` is retained for the earlier script layer. This is an existing
architecture, not a conversion to ES modules.

Searchable section comments mark the major features. Functions named `...Before...`
retain the previous implementation before an extension wraps it; do not remove a
wrapper without checking its callers and the script load order. Long HTML template
strings contain user-visible whitespace, especially in chat messages; changing their
line breaks can change rendering where `white-space: pre-wrap` applies.

Use `esc(value)` when inserting plain text into HTML, and `api(path, data)` for JSON
requests. Use `textContent` for file excerpts. File previews accept only authenticated
local file endpoints. A visible admin button is never an authorization check; enforce
ownership and role checks in the backend too.

## Notes and Files lifecycle

`notes.js` owns the note cache and one autosave queue per note. Local drafts survive
request failures; optimistic version numbers prevent a stale save from silently
replacing another edit. Notes is permanent. `/api/features` keeps `notes: true` for old
clients, ignoring a legacy disabled flag without deleting any saved content.

`workspace-panels.js` owns the selected pocket, a single animation queue and the file
preview. It detaches and reattaches the same card DOM during a same-thread render, so
note carets, scroll positions and file/page selection survive. Closing folds the sheet,
slides the card out, then hides its parent **before** clearing transforms. Keep that
order to avoid a flash of unfolded content. Rapid clicks change the target of one queue.
A main render or resize invalidates old transitions and settles the latest selection.

The desktop slot changes width to release space to the chat. On phones the pocket is
an overlay with a dismiss backdrop, Escape handling and keyboard focus containment.
Background chat/composer controls become inert while it is open. Reduced-motion
preferences skip the animation. Notes may still pop out into independent windows.

Personal files and course files use different server access checks. PDF originals can
be embedded from the same origin; text/office uploads use escaped text previews. Only
PDF responses permit same-origin framing. Regular HTML pages retain frame protection.

## Python and database edits

The server calls feature modules with the server helpers and authenticated user. Read
the module docstring and existing access checks before editing a handler. SQL uses
parameters for supplied values. Database changes belong in idempotent startup migrations
that preserve existing rows. Runtime prompt overrides may supersede `config/*.txt`.

Private runtime state is in `.local/` or `SCHOOL_AGENT_STATE`. It is separate from source
and excluded from Git/release archives. Do not use live student records as test fixtures.

## Format, test and run

Python uses Black; JavaScript/CSS/HTML/JSON/Markdown use Prettier. The repository includes
formatting configuration and a repeatable command. Install optional development tools
in a virtual environment if your system Python is externally managed:

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt -r requirements-dev.txt
# Node/npm is needed only for formatting and JavaScript syntax checks.
./scripts/format.sh
./scripts/format.sh --check
python3 -m unittest discover -s tests
for file in app/static/*.js; do node --check "$file"; done
```

The tests use temporary databases and synthetic accounts. The real-model evaluation
script also uses disposable data; see the README for running it. Browser regression
checks for the pocket are documented in `docs/WORKSPACE-VALIDATION.md`.

Static frontend edits appear after a browser refresh. Restart the user service after
Python changes with `systemctl --user restart school-agent.service`. For a separate local
test instance, set `SCHOOL_AGENT_STATE` to a temporary directory and choose an unused
port; see `python3 -m app.server --help` for server options.

## Release

Update `VERSION`, add short notes in `docs/releases/v<VERSION>.md`, run the checks, then
push the reviewed source changes to `main`. The Actions workflow validates the source
before publishing that version. Existing releases are left unchanged. Model weights,
accounts, databases, logs and student uploads must never be included in a source release.
