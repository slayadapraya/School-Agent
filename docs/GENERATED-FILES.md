# Generated files and code artifacts

Permitted users can ask School Agent for a downloadable text file, such as “Create a
Python file that reads this CSV” or “Create a single HTML page with embedded CSS.”
The **Create file** composer shortcut helps start a request. A completed reply adds
file buttons beneath the answer and opens the first file in **Files → Generated**.

The panel docks against the right edge and supports syntax-coloured editing, explicit
Save changes, downloads, a wider editor, and sandboxed HTML/CSS/SVG previews. Code and
Preview are separate tabs; Preview expands into a large, full-height browser surface.
Opening Files folds away Notes, and the composer stays aligned with the chat column.
The file actions use labelled icons. Browse files reveals the file list when needed. Files remain with their conversation. Switching between
Notes and Files preserves the editor and unsaved changes. Opening another file or
leaving the chat prompts before discarding an unsaved edit. Reloading warns about
unsaved changes; save before reloading. Version checks prevent two open windows
from silently overwriting each other.

## Resizing and navigation

Drag the divider along the **left edge of Files/Preview** to resize it. The chat
and composer resize together; the preview iframe and editor stay mounted. Widths
are remembered per account for this browser-tab session. The first Preview opens
wide; later previews keep your adjusted width. Reloading retains that session
choice, while a new tab session or signing out starts fresh. There is no separate
Expand/Compact button; use the divider. Focus the divider and use Left/Right to adjust it, Home to reset, or End for
the widest allowed view. A double-click resets the current view's width too.

The Chat files / Generated / Course files navigation remains visible in Code and
Preview. Clicking a collection opens its file browser; Browse files can collapse
the search/list again. Notes stays capped at its previous 680px card height while
Files uses the full available height. The edge tabs sit at the panel’s top edge, with Notes aligned exactly to the
Notes card and the selected tab joined to the card border.

Administrator home and sidebar render personal chats immediately after login.
Initial bootstrap waits for the deferred feature scripts, and its fallback never
substitutes the subject catalogue into an administrator's personal navigation.

## Permissions and boundaries

Administrators always have file generation. To grant another account access, open
**Admin controls → People → Edit account → Tools**, enable **Generate and edit
downloadable files**, and save. Existing sessions may need to sign in again after
permission changes. **Run Python / JavaScript** is a separate permission and also
requires generation permission and a configured runner.

File generation does not remove student tutoring restrictions. Only complete code
fences in the final accepted assistant reply are exported; cancelled or rejected
candidates are not exported. Student preview does not export artifacts. Revoking
file generation prevents new exports and edits while retaining access to the
account's previously saved files. Personal artifact endpoints require ownership of
both the file and its active conversation; knowing a file ID grants no access.

Supported text formats include Python, JavaScript, TypeScript, Java, C/C++, HTML,
CSS, SVG, JSON, CSV, Markdown, YAML, XML, SQL, R and shell scripts. Saving a file does
not execute it. Binary PDF, Word and image generation are not implemented. Ask for
Markdown or CSV when an editable document or data export is suitable.

## Memory and storage

- File lists return metadata, not file bodies. The browser fetches one selected
  artifact for editing and uses a native text area over a highlighted text layer,
  without another editor library or background worker. The existing bundled
  highlighter updates after a short pause in typing; inactive Preview tabs do not
  perform syntax highlighting.
- Maximum saved file size: **128 KiB UTF-8**, up to **six files per reply** and
  **60 files per conversation**. Existing model response limits still apply; long
  programs may need to be split into smaller requests. Incomplete fences are not
  saved as broken files.
- Model filenames are sanitized download labels. Bodies live in SQLite, never at
  model-selected paths on the server filesystem.
- Previews are created only when requested. Closing a preview removes its iframe.
  HTML/CSS/SVG previews use an opaque sandbox and a content security policy that
  blocks forms, external resources and network requests. Permitted generation previews allow isolated browser JavaScript; other saved-file previews remain static.
  Download generated applications for testing that needs network access or host capabilities.
- Uploaded-document text previews fetch the extracted text without also loading the
  original binary file into Python memory. These changes do not alter model
  loading, context size, quantization or host-terminal behaviour.

## Optional code execution

**Execution is disabled by default.** Generating, editing, previewing and downloading
files work without Docker or an additional running service. The included demo
explicitly disables execution.

The optional adapter supports one saved Python or JavaScript file, using these
pre-pulled images: `python:3.12-alpine` and `node:22-alpine`. It never downloads an
image while serving a request and never falls back to running generated code in the
host shell or the administrator's embedded terminal.

Before enabling it, arrange a working container service and review the extra PC
resource use. A rootless runtime is preferable. After approval, an operator can pull
those images, set `"code_execution_enabled": true` in `config/settings.json`, restart
the server, and grant execution permission to selected accounts. Dependencies,
network access, multi-file projects and persistent processes are not supported.
Do not enable this setting simply to make the Run button appear active.

Each run uses a read-only root filesystem and source mount, an unprivileged user,
no network, no added capabilities, no privilege escalation, a 16 MiB temporary
filesystem, 128 MiB RAM/swap limit, half a CPU, 32 processes, an eight-second timeout
and a 32 KiB output cap. A process-wide lock admits one run at a time; additional
requests receive a busy response. The adapter attempts container cleanup on every
exit, including timeouts and errors. Container-service failures still require an
operator to check for leftover containers. Execution results are displayed below the
editor and do not become claimed model observations.

A container adapter is included and tested with controlled process fixtures. It has
not been validated against a running Docker daemon on the current installation,
where the container service is unavailable. Keep execution disabled until that
validation and resource approval are complete.

## Current-request handling

Standalone greetings, thanks, acknowledgements and cancellations get short social
replies before inference. They cannot resume an earlier coding task or export new
files. File-generation guidance is enabled for the current request or an explicit
edit follow-up, rather than persisting merely because history contains a program.
Normal questions still go to the tutor. Regression checks cover a greeting after
website generation and an unrelated maths question after a coding task.

## Verification and source map

- `app/artifacts.py`: extraction, limits, ownership, versioned saves, downloads,
  sandboxed preview responses.
- `app/code_runner.py`: optional container runner and resource bounds.
- `app/static/artifact-editor.js`, `app/static/artifacts.css`: generated file editor.
- `app/static/workspace-panels.js`: shared Notes/Files pocket and collections.
- `app/static/sidebar-resize.js`: desktop sidebar drag/keyboard resizing, with a
  saved per-account browser preference. Arrow keys adjust width; Home or a double
  click resets it. Mobile keeps the existing touch drawer.
- `tests/test_artifacts.py`: isolated storage, permission, output and runner checks.
- `scripts/check-artifacts.cjs`: disposable browser checks for generation, editing,
  downloads, sandbox previews, Notes switching, resizing and mobile layout.

Run the Python suite with `python3 -m unittest discover -s tests`. For browser checks,
install the optional development dependencies with `npm ci`, select an installed
Chromium through `CHROMIUM_PATH` if necessary, then run `npm run check:artifacts` and
`npm run check:workspace`. These tests use disposable accounts and databases and do
not inspect the installed application's chats.

## Inline code tools

Assistant code blocks have Copy and Download icons. Their labels expand on hover
or keyboard focus. The code toolbar stays pinned below the page header while
scrolling through its code block. Download uses the exact source in that block, even when a saved
file has since been edited. File export controls require the account's generated
files permission (administrators have it); incomplete or oversized blocks keep Copy.
HTML, CSS and SVG blocks also offer Preview at the bottom right. The source stays
above the website preview. Pop out preview moves it into a draggable, resizable
window inside School Agent, with the same focus stack as Notes, Terminal and Admin.
The window can minimise, restore and close. One floating preview is kept at a time.

Previews use an authenticated response under thread ownership so generated CSS is
not blocked by the app shell's stricter style policy. Linked CSS and JavaScript
are bundled from that reply or explicitly referenced files in the same owned chat;
current saved edits take precedence. No server filesystem paths are resolved.
HTML/CSS/SVG blocks are capped at 128 KiB each and the bundled preview at 512 KiB.
Only six linked assets are considered. No persistent preview copies are stored.

Generated JavaScript runs only in the browser iframe, with `allow-scripts` and an
opaque origin. It has no same-origin access to School Agent, cookies, local storage,
forms, popups or the top-level page. Its content policy disallows fetches and remote
scripts, styles and images; data images and embedded styles work. This allows local
section switches and animations without enabling the server-side code runner.
Without generation permission, previously saved artifact previews remain static.
The inline preview route requires generation permission and true thread ownership,
including for administrators. Scripts never execute on the host PC through Preview.

The iframe is created only on request and removed when hidden or closed. Downloads
use a short-lived browser Blob URL, with no server copies or background jobs.
Browser JavaScript previews and the optional Python/Node container runner are
separate features; server execution stays disabled unless explicitly configured.

Edit the inline tools in `app/static/app.js` (markup), `preferences.js` (actions)
and the labelled Code tools section of `style.css` (appearance). The right-side
workspace remains independent. Notes and Files share a top-right minimise button;
their bookmarks close their borders during folding/sliding and join the settled card.
