'use strict';

/** Account-owned note data, versioned autosave, rich-text editing and floating windows.
 * workspace-panels.js owns the dock layout and transitions, not the save queues.
 */
const initialNoteThreads = new WeakMap();
const notePresets = ['#bed6ab', '#9bc9e8', '#d5b4e8', '#edb7ad', '#ecd38f', '#b8c4ce'];
// Note data outlives page renders; each save queue belongs to one note, never the active chat.
const noteData = new Map(),
  noteSelection = new Map();
let noteIndex = [],
  noteIndexOwner = null,
  noteIndexPromise = null,
  notesRestoredOwner = null,
  noteZ = 1100;
// -----------------------------------------------------------------------------
// Note cache, local drafts and versioned saves
// -----------------------------------------------------------------------------
function notesEnabled() {
  return !!state.user;
}
function noteDraftKey(id) {
  return 'school-note-draft-' + (noteData.get(id)?.user_id || state.user?.id) + '-' + id;
}
function rememberDraft(n) {
  try {
    localStorage.setItem(
      noteDraftKey(n.id),
      JSON.stringify({
        title: n.title,
        body: n.body,
        body_html: n.body_html || '',
        text_size: n.text_size || 14,
        colour: n.colour || '#bed6ab',
        version: n.version,
      }),
    );
  } catch (e) {}
}
function noteState(n, message) {
  n.status = message;
  document
    .querySelectorAll(`[data-note-status="${n.id}"]`)
    .forEach((el) => (el.textContent = message));
}
function syncNote(n) {
  applyNoteColour(n);
  document
    .querySelectorAll(`[data-note-title="${n.id}"]`)
    .forEach((el) => (el.textContent = n.title.trim() || 'Untitled note'));
  document.querySelectorAll(`[data-note-editor="${n.id}"]`).forEach((root) => {
    for (const key of ['title', 'body']) {
      const el = root.querySelector('[data-note-field="' + key + '"]');
      if (el && document.activeElement !== el) {
        if (key === 'body') el.innerHTML = safeNoteHTML(n.body_html) || esc(n.body);
        else el.value = n.title === 'Untitled note' ? '' : n.title;
      }
    }
  });
  noteState(n, n.status || 'Saved');
}
async function ensureNote(id) {
  if (noteData.has(id)) return noteData.get(id);
  const owner = state.user?.id;
  const result = await api('/api/notes/' + id);
  if (state.user?.id !== owner) throw Error('Account changed');
  const n = { ...result.note, revision: 0, dirty: false, saving: false, status: 'Saved' };
  let draft;
  try {
    draft = JSON.parse(localStorage.getItem(noteDraftKey(id)) || 'null');
  } catch (e) {}
  if (
    draft &&
    (draft.body !== n.body ||
      draft.title !== n.title ||
      (draft.body_html || '') !== (n.body_html || '') ||
      (draft.text_size && draft.text_size !== n.text_size) ||
      (draft.colour && draft.colour !== n.colour))
  ) {
    n.title = draft.title;
    n.body = draft.body;
    n.body_html = draft.body_html || '';
    n.text_size = draft.text_size || n.text_size;
    n.colour = draft.colour || n.colour;
    n.dirty = true;
    n.status =
      draft.version === n.version
        ? 'Unsaved draft restored'
        : 'Changed elsewhere · local draft kept';
    n.conflict = draft.version !== n.version;
  } else if (draft) {
    try {
      localStorage.removeItem(noteDraftKey(id));
    } catch (e) {}
  }
  noteData.set(id, n);
  if (n.dirty && !n.conflict) queueNote(n);
  return n;
}
async function loadNoteIndex(force = false) {
  const owner = state.user?.id;
  if (!owner) return;
  if (noteIndexOwner !== owner) {
    noteIndex = [];
    noteData.clear();
    noteSelection.clear();
    noteIndexOwner = owner;
    noteIndexPromise = null;
  }
  if (!force && noteIndexPromise) return noteIndexPromise;
  noteIndexPromise = api('/api/notes')
    .then((result) => {
      if (state.user?.id === owner) {
        noteIndex = result.notes;
        return noteIndex;
      }
    })
    .catch((err) => {
      noteIndexPromise = null;
      throw err;
    });
  return noteIndexPromise;
}
function queueNote(n) {
  n.dirty = true;
  rememberDraft(n);
  clearTimeout(n.timer);
  noteState(n, 'Saving…');
  n.timer = setTimeout(() => saveNote(n), 600);
}
async function saveNote(n) {
  if (n.saving || !n.dirty || n.conflict) return;
  n.saving = true;
  const revision = n.revision,
    payload = {
      title: n.title.trim() || 'Untitled note',
      body: n.body,
      body_html: n.body_html || '',
      text_size: n.text_size || 14,
      colour: n.colour || '#bed6ab',
      version: n.version,
    };
  try {
    const result = await api('/api/notes/' + n.id, payload);
    n.version = result.note.version;
    const summary = noteIndex.find((x) => x.id === n.id);
    if (summary)
      Object.assign(summary, {
        title: payload.title,
        preview: payload.body.slice(0, 140),
        colour: payload.colour,
        updated: result.note.updated,
        version: n.version,
      });
    if (revision === n.revision) {
      n.dirty = false;
      try {
        localStorage.removeItem(noteDraftKey(n.id));
      } catch (e) {}
      noteState(n, 'Saved');
    } else {
      rememberDraft(n);
      noteState(n, 'Saving…');
    }
  } catch (err) {
    if (/changed elsewhere/i.test(err.message)) n.conflict = true;
    noteState(
      n,
      n.conflict
        ? 'Changed elsewhere · local draft kept'
        : 'Save failed · ' + err.message + ' · draft kept',
    );
  } finally {
    n.saving = false;
    if (n.dirty && !n.conflict && n.revision !== revision) queueNote(n);
  }
}
// -----------------------------------------------------------------------------
// Dock editor and note library
// -----------------------------------------------------------------------------
function editorHTML(n) {
  return `<div class="note-editor" data-note-editor="${n.id}"><input class="note-title" data-note-field="title" maxlength="100" aria-label="Note title" placeholder="Untitled note" value="${esc(n.title === 'Untitled note' ? '' : n.title)}"><div class="note-body" data-note-field="body" contenteditable="true" role="textbox" aria-multiline="true" aria-label="Note text" data-placeholder="Your thoughts, questions and reminders…">${safeNoteHTML(n.body_html) || esc(n.body)}</div>${noteFormattingControls(n)}${noteColourControls(n)}<footer><span data-note-status="${n.id}" role="status">${esc(n.status || 'Saved')}</span><button type="button" data-note-retry="${n.id}" title="Retry saving this draft">Save</button><button type="button" data-note-pop="${n.id}" title="Open as a floating note">↗ Pop out</button></footer></div>`;
}
function notesDockHTML() {
  if (!notesEnabled()) return '';
  return '<aside class="chat-notes-rail"><header><b>Chat notes</b><button type="button" data-workspace-close="1" aria-label="Minimise notes" title="Minimise notes">−</button></header><div class="note-rail-controls"><button type="button" data-note-create="1">＋ New note</button><button type="button" data-notes-library="1">All notes</button></div><div id="note-dock-content"><p class="note-rail-empty">Open or create a note for this chat.</p></div></aside>';
}
async function refreshNoteDock() {
  if (active?.draft && notesEnabled()) {
    try {
      await ensureDraftNoteThread();
    } catch (err) {}
    return;
  }
  const dock = $('#note-dock-content'),
    tid = active?.id;
  if (!dock || !notesEnabled()) return;
  try {
    await loadNoteIndex();
    if (!dock.isConnected || active?.id !== tid) return;
    let list = noteIndex.filter((n) => n.thread_id === tid);
    if (!list.length) {
      // A newly created thread has a server-created note that may postdate our cache.
      await loadNoteIndex(true);
      if (!dock.isConnected || active?.id !== tid) return;
      list = noteIndex.filter((n) => n.thread_id === tid);
    }
    if (!list.length) {
      dock.innerHTML =
        '<p class="note-rail-empty">Keep your own notes here. They autosave to this conversation.</p>';
      return;
    }
    const selected = noteSelection.get(tid) || list[0].id;
    const note = await ensureNote(selected);
    if (!dock.isConnected || active?.id !== tid) return;
    noteSelection.set(tid, selected);
    if (dock.querySelector(`[data-note-editor="${selected}"]`)) return;
    dock.innerHTML =
      `<details class="note-picker-popover"><summary><span class="note-picker-dot" data-note-dot="${note.id}"></span><span data-note-title="${note.id}">${esc(note.title || 'Untitled note')}</span><svg viewBox="0 0 16 16" aria-hidden="true"><path d="m4 6 4 4 4-4"/></svg></summary><div class="note-picker-options">${list.map((n) => `<button type="button" data-note-choose="${n.id}" aria-pressed="${n.id === selected}"><span class="note-picker-dot" data-note-dot="${n.id}"></span><span data-note-title="${n.id}">${esc(noteData.get(n.id)?.title || n.title)}</span><span>${n.id === selected ? '✓' : ''}</span></button>`).join('')}</div></details>` +
      editorHTML(note);
    list.forEach((item) => applyNoteColour(noteData.get(item.id) || item));
    applyNoteColour(note);
  } catch (err) {
    if (dock.isConnected)
      dock.innerHTML = '<p class="note-rail-empty">' + esc(err.message) + '</p>';
  }
}
async function newChatNote() {
  if (!notesEnabled() || !active) return;
  const target = active;
  if (target.draft) {
    await ensureDraftNoteThread();
    const first = noteIndex.find((n) => n.thread_id === active?.id);
    if (first) return ensureNote(first.id);
    return;
  }
  const tid = target.id;
  const result = await api('/api/notes', { thread_id: tid });
  const n = { ...result.note, revision: 0, dirty: false, saving: false, status: 'Saved' };
  noteData.set(n.id, n);
  noteSelection.set(tid, n.id);
  await loadNoteIndex(true);
  const draft = $('#message')?.value || '';
  const scroll = $('#content')?.scrollTop || 0;
  render();
  if ($('#message')) $('#message').value = draft;
  if ($('#content')) $('#content').scrollTop = scroll;
  await refreshNoteDock();
  document
    .querySelector(`[data-note-editor="${n.id}"] .note-title`)
    ?.focus({ preventScroll: true });
  return n;
}
async function notesLibrary() {
  if (!notesEnabled()) return;
  await loadNoteIndex(true);
  modal(
    'Your notes',
    `<div class="notes-library-heading">${active ? '<button type="button" class="secondary" data-note-create-library="1">＋ New note for this chat</button>' : ''}</div><label>Search notes<input class="notes-search" id="notes-search" placeholder="Search title, text or conversation"></label><div id="notes-library-list"></div><p class="muted">Notes stay with their original chat. Pop out several cards and arrange them anywhere.</p>`,
  );
  const show = () => {
    const query = $('#notes-search').value.toLowerCase();
    $('#notes-library-list').innerHTML =
      noteIndex
        .filter((n) =>
          [n.title, n.preview, n.chat_title, n.course_id].join(' ').toLowerCase().includes(query),
        )
        .map(
          (n) =>
            `<article class="notes-library-row" data-note-card="${n.id}"><div><b>${esc(noteData.get(n.id)?.title || n.title)}</b><small>${esc(n.course_id)} · ${esc(n.chat_title)}</small><p>${esc((noteData.get(n.id)?.body || n.preview || 'Empty note').slice(0, 110))}</p></div><button type="button" data-note-pop="${n.id}">↗ Open</button></article>`,
        )
        .join('') || '<p class="muted">No notes yet. Create one from a chat’s notes rail.</p>';
    noteIndex.forEach((n) => applyNoteColour(noteData.get(n.id) || n));
  };
  $('#notes-search').oninput = show;
  show();
}
// -----------------------------------------------------------------------------
// Floating windows and saved positions
// -----------------------------------------------------------------------------
function noteWindowPosition(win) {
  if (win.hidden || win.classList.contains('note-hidden-by-user')) return;
  const r = win.getBoundingClientRect();
  win.style.left = Math.max(0, Math.min(innerWidth - r.width, r.left)) + 'px';
  win.style.top = Math.max(0, Math.min(innerHeight - 36, r.top)) + 'px';
}
function persistNoteWindows() {
  if (!state.user) return;
  try {
    const cards = [...document.querySelectorAll('.note-window')]
      .filter((win) => !win.classList.contains('note-closing'))
      .map((win) => ({
        id: win.dataset.noteId,
        left: parseFloat(win.style.left) || win.offsetLeft,
        top: parseFloat(win.style.top) || win.offsetTop,
        width: win.style.width || '',
        height: win.style.height || '',
        userHidden:
          win.classList.contains('note-hidden-by-user') || win.classList.contains('note-hiding'),
        minimised: win.classList.contains('is-minimised'),
      }));
    localStorage.setItem('school-note-windows-' + state.user.id, JSON.stringify(cards));
  } catch (e) {}
}
async function popNote(id, position) {
  let win = document.querySelector(`.note-window[data-note-id="${id}"]`);
  if (win) {
    clearTimeout(win.noteHideTimer);
    win.classList.remove('note-hiding', 'note-closing', 'is-minimised', 'note-hidden-by-user');
    syncNoteWindowToggle(win);
    bringNoteToFront(win);
    noteWindowPosition(win);
    return;
  }
  const n = await ensureNote(id);
  const source = noteIndex.find((x) => x.id === id);
  win = document.createElement('section');
  win.className = 'note-window';
  win.dataset.noteId = id;
  win.style.cssText = noteColourStyle(n);
  win.setAttribute('aria-label', 'Floating note');
  const count = document.querySelectorAll('.note-window').length;
  win.style.left =
    (position?.left ?? Math.max(12, Math.min(innerWidth - 350, 230 + count * 28))) + 'px';
  win.style.top = (position?.top ?? 100 + count * 26) + 'px';
  bringNoteToFront(win);
  if (position?.width) win.style.width = position.width;
  if (position?.height) win.style.height = position.height;
  win.innerHTML = `<header class="terminal-window-bar"><span>Note · ${esc(source?.course_id || 'Chat')}</span><div><button type="button" data-note-minimise="${id}" aria-label="Minimise note">−</button><button type="button" data-note-close="${id}" aria-label="Close note"><svg viewBox="0 0 16 16" aria-hidden="true"><path d="m4 4 8 8M12 4l-8 8"/></svg></button></div></header><div class="note-origin" title="${esc(source?.chat_title || '')}">${esc(source?.chat_title || 'Original conversation')}</div>${editorHTML(n)}`;
  document.body.append(win);
  bringNoteToFront(win);
  win.hidden = !notesEnabled() || screen !== 'chat' || !active;
  applyNoteColour(n);
  makeTerminalDraggable(win);
  win.addEventListener('pointerdown', () => bringNoteToFront(win));
  win.addEventListener('pointerup', persistNoteWindows);
  if (position?.userHidden) win.classList.add('note-hidden-by-user');
  if (position?.minimised) win.classList.add('is-minimised');
  syncNoteWindowToggle(win);
  noteWindowPosition(win);
  persistNoteWindows();
}
function notesWindowHost() {
  const host = document.body;
  document.querySelectorAll('.note-window').forEach((win) => {
    if (win.parentElement !== host) host.append(win);
  });
}
new MutationObserver(notesWindowHost).observe(document.getElementById('modal'), {
  attributes: true,
  attributeFilter: ['open'],
});
async function restoreNoteWindows() {
  if (!notesEnabled() || notesRestoredOwner === state.user.id) return;
  notesRestoredOwner = state.user.id;
  let saved;
  try {
    saved = JSON.parse(localStorage.getItem('school-note-windows-' + state.user.id) || '[]');
  } catch (e) {
    return;
  }
  await loadNoteIndex();
  for (const position of saved.slice(0, 15)) {
    if (noteIndex.some((n) => n.id === position.id))
      try {
        await popNote(position.id, position);
      } catch (e) {}
  }
}
// -----------------------------------------------------------------------------
// Application integration and experimental options
// -----------------------------------------------------------------------------
function attachNotesUI() {
  if (typeof workspacePanels !== 'undefined') workspacePanels.mount();
  // Startup may reach this before the final deferred script has loaded.
  // The entry-point rail is sufficient until workspacePanels.mount() takes over.
  else refreshNoteDock();
  restoreNoteWindows();
}
const notesContentObserver = new ResizeObserver((entries) => {
  for (const entry of entries)
    document.documentElement.style.setProperty(
      '--notes-rail-height',
      Math.max(100, entry.contentRect.height - 28) + 'px',
    );
});
const attachNotesBeforeSizing = attachNotesUI;
attachNotesUI = function () {
  attachNotesBeforeSizing();
  notesContentObserver.disconnect();
  const content = $('#content');
  if (content) notesContentObserver.observe(content);
};
const renderBeforeNotes = render;
render = function () {
  const result = renderBeforeNotes();
  attachNotesUI();
  return result;
};
const settingsBeforeNotes = settingsModal;
settingsModal = async function () {
  await settingsBeforeNotes();
  if (state.user.role === 'admin' && !studentView)
    $('#modal-content')?.insertAdjacentHTML(
      'beforeend',
      '<div class="source-block"><h3>Experimental features</h3><button class="secondary" type="button" data-notes-experimental="1">Manage experimental features</button></div>',
    );
};
async function experimentalSettings() {
  modal(
    'Experimental features',
    '<p class="muted">No experimental options are currently available.</p><p>Notes and Files are standard features, available in every chat.</p>',
  );
}
document.addEventListener(
  'input',
  (e) => {
    const field = e.target.closest('[data-note-field]'),
      root = field?.closest('[data-note-editor]');
    if (!root) return;
    const n = noteData.get(root.dataset.noteEditor);
    if (!n) return;
    if (field.dataset.noteField === 'body') {
      n.body = field.innerText;
      n.body_html = safeNoteHTML(field.innerHTML);
    } else n.title = field.value;
    n.revision++;
    syncNote(n);
    queueNote(n);
  },
  true,
);
document.addEventListener('change', (e) => {
  if (!e.target.matches('[data-note-dock-picker]')) return;
  noteSelection.set(active.id, e.target.value);
  refreshNoteDock();
});
document.addEventListener('click', async (e) => {
  const b = e.target.closest('button');
  if (!b) return;
  try {
    if (b.dataset.notesLibrary) await notesLibrary();
    if (b.dataset.noteCreate || b.dataset.noteCreateLibrary) {
      b.disabled = true;
      try {
        const n = await newChatNote();
        if (b.dataset.noteCreateLibrary && n) {
          $('#modal').close();
          await popNote(n.id);
        }
      } finally {
        if (b.isConnected) b.disabled = false;
      }
    }
    if (b.dataset.notePop) {
      if ($('#modal')?.open && $('#modal-content h2')?.textContent === 'Your notes')
        $('#modal').close();
      await popNote(b.dataset.notePop);
    }
    if (b.dataset.noteMinimise) {
      const win = document.querySelector(`.note-window[data-note-id="${b.dataset.noteMinimise}"]`);
      if (win) {
        win.classList.toggle('is-minimised');
        syncNoteWindowToggle(win);
        noteWindowPosition(win);
      }
    }
    if (b.dataset.noteRestore) {
      const win = document.querySelector(`.note-window[data-note-id="${b.dataset.noteRestore}"]`);
      win?.classList.remove('is-minimised');
      if (win) noteWindowPosition(win);
    }
    if (b.dataset.noteClose) {
      const n = noteData.get(b.dataset.noteClose);
      if (n?.dirty) saveNote(n);
      closeNoteWindow(
        document.querySelector(`.note-window[data-note-id="${b.dataset.noteClose}"]`),
      );
    }
    if (b.dataset.noteMinimise || b.dataset.noteRestore || b.dataset.noteClose)
      persistNoteWindows();
    if (b.dataset.noteRetry) {
      const n = noteData.get(b.dataset.noteRetry);
      if (n) {
        if (n.conflict) {
          const current = await api('/api/notes/' + n.id);
          n.version = current.note.version;
          n.conflict = false;
        }
        n.dirty = true;
        await saveNote(n);
      }
    }
    if (b.dataset.notesExperimental) await experimentalSettings();
    if (b.dataset.action === 'logout') {
      persistNoteWindows();
      document.querySelectorAll('.note-window').forEach((win) => win.remove());
      noteIndexOwner = null;
      notesRestoredOwner = null;
    }
  } catch (err) {
    toast(err.message);
  }
});
window.addEventListener('pagehide', () => {
  persistNoteWindows();
  for (const n of noteData.values()) {
    if (!n.dirty) continue;
    rememberDraft(n);
    if (!n.saving && !n.conflict)
      fetch('/api/notes/' + n.id, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-School-Agent': '1' },
        body: JSON.stringify({
          title: n.title.trim() || 'Untitled note',
          body: n.body,
          body_html: n.body_html || '',
          text_size: n.text_size || 14,
          colour: n.colour || '#bed6ab',
          version: n.version,
        }),
        keepalive: true,
      });
  }
});
window.addEventListener('resize', () =>
  document.querySelectorAll('.note-window').forEach(noteWindowPosition),
);
// Send only after pending account-note edits reach the server snapshot.
// -----------------------------------------------------------------------------
// Send-time save barrier
// -----------------------------------------------------------------------------
async function flushNoteSaves() {
  captureNoteEditors();
  for (const n of noteData.values()) {
    if (n.user_id !== state.user?.id) continue;
    clearTimeout(n.timer);
    const deadline = Date.now() + 5000;
    while (n.saving && Date.now() < deadline)
      await new Promise((resolve) => setTimeout(resolve, 60));
    if (n.dirty && !n.conflict) await saveNote(n);
    if (n.dirty) throw Error('A note has unsaved changes. Retry its Save button before sending.');
  }
}

// The body stays pale green; the header and outline share the selected accent.

// -----------------------------------------------------------------------------
// Note appearance, formatting and draft capture
// -----------------------------------------------------------------------------
function noteColourStyle(n) {
  const c = /^#[0-9a-f]{6}$/i.test(n.colour || '') ? n.colour : '#bed6ab';
  const rgb = c
    .slice(1)
    .match(/../g)
    .map((x) => parseInt(x, 16));
  return `--note-accent:${c};--note-font-size:${n.text_size || 14}px;--note-header-ink:${rgb[0] * 0.299 + rgb[1] * 0.587 + rgb[2] * 0.114 > 150 ? '#25382c' : '#ffffff'};`;
}
function noteColourControls(n) {
  return `<div class="note-colours" aria-label="Note colour">${notePresets.map((c) => `<button type="button" data-note-colour="${n.id}" data-colour="${c}" aria-label="Use ${c}" aria-pressed="${(n.colour || '#bed6ab') === c}"></button>`).join('')}<label title="Custom header and outline colour">Custom<input type="color" data-note-custom="${n.id}" value="${n.colour || '#bed6ab'}" aria-label="Custom note colour"></label></div>`;
}
function applyNoteColour(n) {
  document
    .querySelectorAll(`[data-note-dot="${n.id}"]`)
    .forEach((el) => (el.style.backgroundColor = n.colour || '#bed6ab'));
  document
    .querySelectorAll(
      `[data-note-editor="${n.id}"],.note-window[data-note-id="${n.id}"],[data-note-card="${n.id}"]`,
    )
    .forEach((el) => {
      const probe = document.createElement('span');
      probe.style.cssText = noteColourStyle(n);
      for (const k of ['--note-accent', '--note-header-ink', '--note-font-size'])
        el.style.setProperty(k, probe.style.getPropertyValue(k));
    });
  document
    .querySelectorAll(`[data-note-colour="${n.id}"]`)
    .forEach((b) => b.setAttribute('aria-pressed', b.dataset.colour === n.colour));
  document
    .querySelectorAll(`[data-note-custom="${n.id}"]`)
    .forEach((el) => (el.value = n.colour || '#bed6ab'));
}
function setNoteColour(id, colour) {
  const n = noteData.get(id);
  if (!n) return;
  n.colour = colour;
  n.revision++;
  applyNoteColour(n);
  queueNote(n);
}
document.addEventListener('click', (e) => {
  const b = e.target.closest('[data-note-colour]');
  if (b) setNoteColour(b.dataset.noteColour, b.dataset.colour);
});
document.addEventListener('input', (e) => {
  if (e.target.matches('[data-note-custom]'))
    setNoteColour(e.target.dataset.noteCustom, e.target.value);
});
function captureNoteEditors() {
  document.querySelectorAll('[data-note-editor]').forEach((root) => {
    const n = noteData.get(root.dataset.noteEditor);
    if (!n) return;
    let changed = false;
    for (const key of ['title', 'body']) {
      const field = root.querySelector(`[data-note-field="${key}"]`);
      if (field) {
        const value = key === 'body' ? field.innerText : field.value;
        if (value !== (key === 'title' && n.title === 'Untitled note' ? '' : n[key])) {
          n[key] = value;
          if (key === 'body') n.body_html = safeNoteHTML(field.innerHTML);
          changed = true;
        }
      }
    }
    if (changed) {
      n.revision++;
      queueNote(n);
      syncNote(n);
    }
  });
}

// One consistent collapse/expand control; the note keeps its saved window size.
function syncNoteWindowToggle(win) {
  const button = win.querySelector('[data-note-minimise]');
  if (!button) return;
  const collapsed = win.classList.contains('is-minimised');
  button.innerHTML = `<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M3 8h10${collapsed ? 'M8 3v10' : ''}"/></svg>`;
  button.setAttribute('aria-label', collapsed ? 'Expand note' : 'Minimise note');
  button.setAttribute('aria-expanded', String(!collapsed));
  button.title = collapsed ? 'Expand note' : 'Minimise note';
}

function safeNoteHTML(html) {
  const template = document.createElement('template');
  template.innerHTML = html || '';
  for (const el of [...template.content.querySelectorAll('*')]) {
    if (!['B', 'STRONG', 'I', 'EM', 'BR', 'DIV', 'P'].includes(el.tagName)) {
      el.replaceWith(...el.childNodes);
      continue;
    }
    for (const attr of [...el.attributes]) el.removeAttribute(attr.name);
  }
  return template.innerHTML;
}
function noteFormattingControls(n) {
  return `<div class="note-formatting" aria-label="Text formatting"><button type="button" data-note-size="${n.id}" data-step="-1" aria-label="Smaller text">A−</button><button type="button" data-note-size="${n.id}" data-step="1" aria-label="Larger text">A+</button><span aria-hidden="true">|</span><button type="button" data-note-format="bold" aria-label="Bold"><b>B</b></button><button type="button" data-note-format="italic" aria-label="Italic"><i>I</i></button></div>`;
}
// Keep the editing selection when clicking a formatting button.
document.addEventListener('mousedown', (e) => {
  if (e.target.closest('[data-note-format]')) e.preventDefault();
});
document.addEventListener('click', (e) => {
  const size = e.target.closest('[data-note-size]');
  if (size) {
    const n = noteData.get(size.dataset.noteSize);
    if (!n) return;
    n.text_size = Math.max(12, Math.min(24, (n.text_size || 14) + Number(size.dataset.step)));
    n.revision++;
    applyNoteColour(n);
    queueNote(n);
  }
  const button = e.target.closest('[data-note-format]');
  if (button) {
    const root = button.closest('[data-note-editor]'),
      body = root?.querySelector('.note-body');
    if (!body) return;
    const selection = getSelection();
    if (!selection?.anchorNode || !body.contains(selection.anchorNode)) body.focus();
    document.execCommand(button.dataset.noteFormat, false);
    const n = noteData.get(root.dataset.noteEditor);
    n.body = body.innerText;
    n.body_html = safeNoteHTML(body.innerHTML);
    n.revision++;
    queueNote(n);
    syncNote(n);
  }
});
document.addEventListener('paste', (e) => {
  const body = e.target.closest('.note-body[contenteditable]');
  if (!body) return;
  e.preventDefault();
  document.execCommand('insertText', false, e.clipboardData.getData('text/plain'));
});

// Separate staff review UI: student notes never enter the staff member's note cache or model context.
const panelBeforeStudentNotes = renderAdminPanel;
renderAdminPanel = async function () {
  if (adminTab === 'student-notes') {
    clearTimeout(monitorTimer);
    return renderStudentNotes($('#admin-panel'));
  }
  if (adminTab === 'experimental') {
    clearTimeout(monitorTimer);
    return renderExperimentalFeatures($('#admin-panel'));
  }
  return panelBeforeStudentNotes();
};
async function renderExperimentalFeatures(panel) {
  if (state.user.role !== 'admin' || !panel) return;
  panel.innerHTML =
    '<h1>Experimental features</h1><p class="muted">No experimental options are currently available.</p><p>Notes and Files are standard features, available in every chat.</p>';
}
// -----------------------------------------------------------------------------
// Read-only staff review
// -----------------------------------------------------------------------------
async function renderStudentNotes(panel) {
  if (!panel || !['admin', 'teacher'].includes(state.user.role)) return;
  panel.innerHTML =
    '<h1>Student notes</h1><p class="muted">Read-only review of saved student notes within your assigned access.</p><label>Search student notes<input id="staff-notes-search" class="notes-search" placeholder="Student, subject, title or note text"></label><div id="staff-notes-list">Loading…</div>';
  try {
    const data = await api('/api/staff/notes');
    if (!panel.querySelector('#staff-notes-list')) return;
    const show = () => {
      const q = panel.querySelector('#staff-notes-search').value.toLowerCase();
      panel.querySelector('#staff-notes-list').innerHTML =
        data.notes
          .filter((n) =>
            [n.student, n.title, n.preview, n.course_id, n.chat_title]
              .join(' ')
              .toLowerCase()
              .includes(q),
          )
          .map(
            (n) =>
              `<button class="record staff-note-record" data-review-note="${n.id}"><b>${esc(n.title)}</b><small>${esc(n.student)} · ${esc(n.course_id)} · ${esc(n.chat_title)}</small><span>${esc(n.preview || 'Empty note')}</span></button>`,
          )
          .join('') || '<p class="muted">No saved student notes within your access.</p>';
      for (const n of data.notes) {
        const el = panel.querySelector(`[data-review-note="${n.id}"]`);
        if (el) el.style.borderLeftColor = n.colour;
      }
    };
    panel.querySelector('#staff-notes-search').oninput = show;
    show();
  } catch (err) {
    if (panel.querySelector('#staff-notes-list'))
      panel.querySelector('#staff-notes-list').textContent = err.message;
  }
}
document.addEventListener('click', async (e) => {
  const button = e.target.closest('[data-review-note]');
  if (!button) return;
  try {
    const { note: n } = await api('/api/staff/notes/' + button.dataset.reviewNote);
    modal(
      'Student note · ' + n.student,
      `<p class="muted">${esc(n.course_id)} · ${esc(n.chat_title)} · Read only</p><article class="staff-note-preview"><h3>${esc(n.title)}</h3><div>${safeNoteHTML(n.body_html) || esc(n.body) || 'Empty note'}</div></article>`,
    );
    const card = $('.staff-note-preview');
    card.style.cssText = noteColourStyle(n);
    card.style.backgroundColor = n.colour;
    card.style.color = 'var(--note-header-ink)';
  } catch (err) {
    toast(err.message);
  }
});

document.addEventListener('click', (e) => {
  if (!e.target.closest('[data-notes-hide-all]')) return;
  document.querySelectorAll('.note-window').forEach((win) => {
    if (
      win.hidden ||
      win.classList.contains('note-hidden-by-user') ||
      win.classList.contains('note-hiding')
    )
      return;
    if (matchMedia('(prefers-reduced-motion: reduce)').matches) {
      win.classList.add('note-hidden-by-user');
      return;
    }
    win.classList.add('note-hiding');
    win.noteHideTimer = setTimeout(() => {
      win.classList.add('note-hidden-by-user');
      win.classList.remove('note-hiding');
      persistNoteWindows();
    }, 160);
  });
  persistNoteWindows();
});
const loginBeforeNoteVisibility = login;
login = function () {
  document.querySelectorAll('.note-window').forEach((win) => (win.hidden = true));
  return loginBeforeNoteVisibility();
};

// Change stacking without moving a pressed button in the DOM (which cancels clicks).
function bringNoteToFront(win) {
  focusFloatingWindow(win);
}

function closeNoteWindow(win) {
  if (!win) return;
  clearTimeout(win.noteHideTimer);
  if (matchMedia('(prefers-reduced-motion: reduce)').matches) {
    win.remove();
    persistNoteWindows();
    return;
  }
  win.classList.add('note-closing');
  win.noteHideTimer = setTimeout(() => {
    win.remove();
    persistNoteWindows();
  }, 160);
}

document.addEventListener('click', (e) => {
  const button = e.target.closest('[data-note-choose]');
  if (button && active) {
    noteSelection.set(active.id, button.dataset.noteChoose);
    refreshNoteDock();
  }
  if (!e.target.closest('.note-picker-popover'))
    document.querySelectorAll('.note-picker-popover[open]').forEach((el) => (el.open = false));
});

// Share creation with Send so typing a message during note setup cannot duplicate the chat.

// -----------------------------------------------------------------------------
// Share draft-thread creation with Send
// -----------------------------------------------------------------------------
async function ensureDraftNoteThread() {
  const target = active;
  if (!notesEnabled() || !target?.draft) return;
  if (initialNoteThreads.has(target)) return initialNoteThreads.get(target);
  const owner = state.user.id;
  const task = (async () => {
    try {
      const result = await api('/api/threads', {
        course_id: target.course_id,
        title: 'New conversation',
      });
      await loadNoteIndex(true);
      if (state.user?.id !== owner || active !== target) return;
      const boot = await api('/api/bootstrap');
      if (state.user?.id !== owner || active !== target) return;
      const draft = $('#message')?.value || '',
        scroll = $('#content')?.scrollTop || 0;
      active = { ...target, id: result.id, draft: false };
      state = boot;
      render();
      if ($('#message')) {
        $('#message').value = draft;
        resizeComposerInput();
      }
      if ($('#content')) $('#content').scrollTop = scroll;
    } catch (err) {
      initialNoteThreads.delete(target);
      const dock = $('#note-dock-content');
      if (active === target && dock) dock.textContent = err.message;
      throw err;
    }
  })();
  initialNoteThreads.set(target, task);
  return task;
}
