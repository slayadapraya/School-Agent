# School Agent

A local chat and tutoring application built with Python, SQLite and a browser interface. It connects to downloaded models through LM Studio.

## Features

- Student tutoring with conversation context, course material and restrictions on completed exercise answers.
- Teacher tools for assigned students, weekly activity, conversation review and read-only student notes.
- Administrator controls for accounts, classes, model access, prompts, diagnostics and an authenticated host terminal.
- Personal admin chat categories with drag-and-drop ordering and recoverable chat deletion.
- Downloaded-model selection, per-model admin instructions and server-enforced Teacher view.
- Account memories, saved conversation files, syntax-highlighted code and cancellable replies.
- Experimental autosaving notes with colour, formatting, floating windows and staff review.
- Server telemetry and rolling graphs on the admin home page.

Student restrictions are enforced by server-side policy and reviewed model responses. Model output can still be incorrect or disclose answers; evaluate the intended subjects and prompts before using this with real students. Image generation is not connected.

## Run locally

Requires Python 3.11+, the packages in `requirements.txt`, and LM Studio with a compatible local model. PDF text extraction also uses `pdftotext` when available.

```bash
python3 -m pip install -r requirements.txt
# Configure the model URL, identifier and transport in config/settings.json.
./scripts/start-model.sh
./scripts/start.sh
```

The private listener defaults to `http://127.0.0.1:8137`. The optional public listener and Tailscale proxy require separate host configuration. Login is required on either listener.

Initial login credentials are generated under `.local/credentials.json`. Password resets must be performed through account administration; that initial file does not track later password changes.

## Configuration and data

- `config/settings.json`: local model connection, listeners and retention.
- `config/courses.json`: course material and subject rules.
- `config/student-*.txt`: student context, tutoring and review instructions. Staff prompt edits are stored locally and can override these defaults.
- `.local/`: private database, account data, files, notes and diagnostic logs. This directory is excluded from Git.

Disabling experimental notes hides the feature without deleting its saved data. Chat deletion is recoverable through Settings. Automatic age-based retention is disabled when `retention_days` is `null`.

Administrators can switch to Teacher view from the profile menu; admin-only APIs are denied while that session uses the teacher role. The Student view preview uses the main tutor and student restrictions. Previewing a role does not select or impersonate a particular student or teacher account.

## Development

```bash
python3 -m unittest discover -s tests
node --check app/static/app.js
```

Restart the service after Python changes and refresh the browser after frontend changes:

```bash
systemctl --user restart school-agent.service
journalctl --user -u school-agent.service
```

This is a pilot application. Validate access rules, curriculum accuracy, answer leakage, accessibility and expected concurrent usage before an institutional deployment. Keep the host model API and operating-system credentials separate from student access.
