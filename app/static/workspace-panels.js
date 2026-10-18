'use strict';

/**
 * Notes and Files share one right-hand pocket. This controller owns only layout,
 * motion and file previews; notes.js still owns note editing and save queues.
 * Keep the card DOM across chat renders so caret, iframe and scroll state survive.
 */
const workspacePanels = (() => {
  const mobile = matchMedia('(max-width: 750px)');
  const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)');
  const icons = {
    notes:
      '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="5" y="3" width="14" height="18" rx="2"/><path d="M9 8h6M9 12h6M9 16h4"/></svg>',
    files:
      '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 7a2 2 0 0 1 2-2h5l2 2h7a2 2 0 0 1 2 2v10H3Z"/></svg>',
  };
  let context = null;
  let owner = null;
  let slot = null;
  let cards = {};
  let current = null;
  let wanted = mobile.matches ? null : 'notes';
  let epoch = 0;
  let running = false;
  let fileTab = 'chat';
  let fileQuery = '';
  let teachingFiles = [];
  let selection = null;
  let previewRequest = 0;
  let courseRequest = 0;
  let lastTrigger = null;

  const contextKey = () =>
    state.user && screen === 'chat' && active ? `${state.user.id}:${active.id}` : null;

  function filesHTML() {
    return `<aside class="pocket-card workspace-files" aria-label="Files panel">
      <header><b>Files</b><button type="button" data-workspace-close="1" aria-label="Minimise files">−</button></header>
      <div class="pocket-paper files-paper">
        <div class="workspace-file-tabs" role="tablist" aria-label="File collection">
          <button type="button" role="tab" data-file-tab="chat" aria-selected="true">Chat files</button>
          <button type="button" role="tab" data-file-tab="course" aria-selected="false">Course files</button>
        </div>
        <label class="workspace-file-search">Find a file<input type="search" data-file-search placeholder="Search files…"></label>
        <div class="workspace-file-list" aria-label="Available files"></div>
        <section class="workspace-file-preview" aria-label="File preview"><p class="muted">Choose a file to preview it here.</p></section>
      </div>
    </aside>`;
  }

  /** Called before the main renderer replaces #app. Floating notes stay in body. */
  function preserve() {
    captureNoteEditors();
    if (slot?.isConnected) slot.remove();
  }

  function mount() {
    const key = contextKey();
    document.querySelectorAll('.header-notes').forEach((el) => el.remove());
    document.querySelectorAll('.note-window').forEach((win) => {
      win.hidden = !key;
    });
    if (owner !== state.user?.id) {
      owner = state.user?.id;
      context = null;
      wanted = mobile.matches ? null : 'notes';
    }
    if (!key) {
      epoch++;
      previewRequest++;
      courseRequest++;
      slot?.remove();
      slot = null;
      cards = {};
      context = null;
      document
        .querySelectorAll('.workspace-bookmarks,.workspace-panel-scrim')
        .forEach((el) => el.remove());
      return;
    }
    const grid = document.querySelector('.workspace-grid');
    if (!grid) return;
    const freshNotes = grid.querySelector('.chat-notes-rail');
    if (key !== context) {
      epoch++;
      previewRequest++;
      courseRequest++;
      context = key;
      selection = null;
      fileTab = 'chat';
      fileQuery = '';
      teachingFiles = [];
      slot = document.createElement('div');
      slot.className = 'workspace-panel-slot';
      const rail =
        freshNotes ||
        document.createRange().createContextualFragment(notesDockHTML()).firstElementChild;
      rail.classList.add('pocket-card');
      rail.setAttribute('aria-label', 'Notes panel');
      // Fold everything below the card header as one sheet.
      const paper = document.createElement('div');
      paper.className = 'pocket-paper';
      while (rail.children.length > 1) paper.append(rail.children[1]);
      rail.append(paper);
      slot.append(rail);
      slot.insertAdjacentHTML('beforeend', filesHTML());
      cards = { notes: rail, files: slot.querySelector('.workspace-files') };
      cards.notes.id = 'workspace-notes';
      cards.files.id = 'workspace-files';
    } else if (freshNotes && freshNotes !== cards.notes) {
      freshNotes.remove();
    }
    grid.classList.remove('with-notes', 'without-notes');
    grid.classList.add('with-workspace-panels');
    grid.append(slot);
    addBookmarks();
    settle();
    refreshNoteDock();
    refreshFiles();
  }

  function addBookmarks() {
    const main = document.querySelector('.main');
    if (!main.querySelector('.workspace-bookmarks')) {
      main.insertAdjacentHTML(
        'beforeend',
        `<nav class="workspace-bookmarks" aria-label="Chat tools">
        ${['notes', 'files'].map((name) => `<button type="button" class="workspace-bookmark" data-workspace-panel="${name}" aria-label="${name === 'notes' ? 'Notes' : 'Files'}" aria-controls="workspace-${name}" aria-expanded="false">${icons[name]}<span class="bookmark-label">${name === 'notes' ? 'Notes' : 'Files'}</span></button>`).join('')}
      </nav><button type="button" class="workspace-panel-scrim" data-workspace-close="1" aria-label="Close chat tools" hidden></button>`,
      );
    }
    measureLabels();
  }

  // A measured text column avoids the gap and label jump caused by fixed widths.
  function measureLabels() {
    document.querySelectorAll('.workspace-bookmark').forEach((button) => {
      const label = button.querySelector('.bookmark-label');
      const range = document.createRange();
      range.selectNodeContents(label);
      button.style.setProperty(
        '--bookmark-label-width',
        `${Math.ceil(range.getBoundingClientRect().width)}px`,
      );
    });
  }

  function panelWidth() {
    if (mobile.matches) return 0;
    const width = document.querySelector('.workspace-grid')?.clientWidth || 800;
    return Math.min(370, Math.max(280, width * 0.43));
  }

  function setSlot(open) {
    if (!slot) return;
    const size = open ? panelWidth() : 0;
    slot.style.width = `${size}px`;
    slot.style.flexBasis = `${size}px`;
  }

  function updateControls() {
    document.querySelectorAll('[data-workspace-panel]').forEach((button) => {
      button.setAttribute('aria-expanded', String(button.dataset.workspacePanel === wanted));
    });
    const overlay = mobile.matches && !!wanted;
    const scrim = document.querySelector('.workspace-panel-scrim');
    if (scrim) scrim.hidden = !overlay;
    // Only the background chat is inert. The bookmarks remain available to switch.
    for (const el of document.querySelectorAll('.conversation,.composer-wrap')) el.inert = overlay;
    document.querySelector('.main')?.classList.toggle('workspace-overlay-open', overlay);
    if (slot) slot.dataset.panel = wanted || 'closed';
  }

  function clearMotion(node) {
    if (!node) return;
    node.getAnimations().forEach((animation) => animation.cancel());
    node.style.removeProperty('transform');
    node.style.removeProperty('opacity');
  }

  /** A re-render or resize commits the latest target, never an old queued card. */
  function settle() {
    epoch++;
    running = false;
    current = wanted;
    for (const [name, card] of Object.entries(cards)) {
      card.hidden = name !== current;
      clearMotion(card);
      clearMotion(card.querySelector('.pocket-paper'));
      card.inert = name !== current;
    }
    slot?.getAnimations().forEach((animation) => animation.cancel());
    setSlot(!!current);
    updateControls();
  }

  async function tween(node, frames, duration) {
    if (!node) return;
    const final = frames[frames.length - 1];
    if (reducedMotion.matches || !node.isConnected) {
      Object.assign(node.style, final);
      return;
    }
    const animation = node.animate(frames, {
      duration,
      easing: 'cubic-bezier(.22,.72,.22,1)',
      fill: 'both',
    });
    try {
      await animation.finished;
      // Keep the folded state before cancelling fill:both. This prevents a flash.
      Object.assign(node.style, final);
      animation.cancel();
    } catch (_) {
      // The main renderer superseded this transition. Its settle() owns the DOM.
    }
  }

  async function resizeSlot(open) {
    const from = slot.getBoundingClientRect().width;
    const to = open ? panelWidth() : 0;
    await tween(
      slot,
      [
        { width: `${from}px`, flexBasis: `${from}px` },
        { width: `${to}px`, flexBasis: `${to}px` },
      ],
      280,
    );
  }

  /** One queue processes the latest target, including rapid Notes/Files/close taps. */
  async function transition() {
    if (running || !slot) return;
    running = true;
    const turn = epoch;
    try {
      while (current !== wanted && turn === epoch) {
        if (current) {
          const card = cards[current];
          const paper = card.querySelector('.pocket-paper');
          card.inert = true;
          await tween(
            paper,
            [
              { transform: 'rotateX(0deg)', opacity: '1' },
              { transform: 'rotateX(-86deg) scaleY(.18)', opacity: '.25' },
            ],
            180,
          );
          if (turn !== epoch) return;
          await Promise.all([
            tween(
              card,
              [
                { transform: 'translateX(0)', opacity: '1' },
                { transform: 'translateX(112%) rotate(2deg) scale(.98)', opacity: '0' },
              ],
              190,
            ),
            !wanted ? resizeSlot(false) : Promise.resolve(),
          ]);
          if (turn !== epoch) return;
          // Hide the parent BEFORE resetting the folded sheet.
          card.hidden = true;
          clearMotion(card);
          clearMotion(paper);
          current = null;
        }
        if (wanted && turn === epoch) {
          const next = wanted;
          const card = cards[next];
          const paper = card.querySelector('.pocket-paper');
          card.style.transform = 'translateX(112%)';
          card.style.opacity = '0';
          paper.style.transform = 'rotateX(-86deg) scaleY(.18)';
          paper.style.opacity = '.25';
          card.hidden = false;
          await Promise.all([
            resizeSlot(true),
            tween(
              card,
              [
                { transform: 'translateX(112%)', opacity: '0' },
                { transform: 'translateX(0)', opacity: '1' },
              ],
              240,
            ),
          ]);
          if (turn !== epoch) return;
          await tween(
            paper,
            [
              { transform: 'rotateX(-86deg) scaleY(.18)', opacity: '.25' },
              { transform: 'rotateX(0deg)', opacity: '1' },
            ],
            210,
          );
          if (turn !== epoch) return;
          clearMotion(card);
          clearMotion(paper);
          card.inert = false;
          current = next;
        }
      }
      if (turn === epoch) {
        setSlot(!!current);
        updateControls();
        if (!current && lastTrigger?.isConnected) lastTrigger.focus({ preventScroll: true });
      }
    } finally {
      if (turn === epoch) running = false;
    }
  }

  function show(name, trigger) {
    if (!contextKey()) return;
    if (!slot?.isConnected) mount();
    const previous = current || wanted;
    lastTrigger =
      trigger || document.querySelector(`[data-workspace-panel="${previous}"]`) || lastTrigger;
    wanted = name;
    updateControls();
    if (name === 'files') refreshFiles();
    transition();
  }

  function allChatFiles() {
    const files = [
      ...(conversationFilesThread === active?.id ? conversationFiles : []),
      ...messages.flatMap((m) => m.meta?.attachments || []),
      ...(pendingImages[active?.id] || []),
    ];
    return [...new Map(files.filter((f) => f.url).map((f) => [f.url, f])).values()];
  }

  function renderFileList() {
    const root = cards.files;
    if (!root) return;
    const list = fileTab === 'course' ? teachingFiles : allChatFiles();
    const visible = list.filter((f) =>
      `${f.name} ${f.course_id || ''}`.toLowerCase().includes(fileQuery.toLowerCase()),
    );
    root
      .querySelectorAll('[data-file-tab]')
      .forEach((button) =>
        button.setAttribute('aria-selected', String(button.dataset.fileTab === fileTab)),
      );
    root.querySelector('.workspace-file-list').innerHTML =
      visible
        .map(
          (f) =>
            `<button type="button" data-workspace-file="${esc(f.id || f.url)}" aria-pressed="${selection?.url === f.url}"><span class="file-kind">${f.mime === 'application/pdf' || /\.pdf$/i.test(f.name) ? 'PDF' : f.document || f.course_id ? 'DOC' : 'IMG'}</span><span>${esc(f.name)}${f.course_id ? `<small>${esc(f.course_id)}</small>` : ''}</span></button>`,
        )
        .join('') ||
      `<p class="muted">${fileQuery ? 'No matching files.' : fileTab === 'course' ? 'No teaching files shared for this subject.' : 'Attach a file to this chat to see it here.'}</p>`;
  }

  async function loadCourseFiles() {
    const request = ++courseRequest;
    const key = context;
    try {
      const data = await materialMarkup(active?.course_id || '');
      if (request !== courseRequest || key !== context) return;
      teachingFiles = data.materials;
      renderFileList();
    } catch (error) {
      if (request === courseRequest && key === context && fileTab === 'course') {
        cards.files.querySelector('.workspace-file-list').textContent = error.message;
      }
    }
  }

  function refreshFiles() {
    if (!cards.files || !context) return;
    renderFileList();
    if (fileTab === 'course') loadCourseFiles();
  }

  function safeFileURL(url) {
    // File previews only use authenticated endpoints belonging to this server.
    return /^\/api\/(?:files\/[a-f0-9]+|attachments\/[a-f0-9]+|course-materials\/[a-f0-9]+\/content)$/.test(
      url || '',
    );
  }

  async function openFile(file, page = 1) {
    if (!safeFileURL(file.url)) throw Error('This file cannot be previewed here.');
    show('files');
    const request = ++previewRequest;
    const key = context;
    selection = { ...file, page };
    renderFileList();
    const preview = cards.files.querySelector('.workspace-file-preview');
    preview.innerHTML = `<div class="workspace-file-heading"><b>${esc(file.name)}</b><a href="${esc(file.url)}" target="_blank" rel="noopener">Open original ↗</a></div><div class="workspace-file-content" role="status">Loading preview…</div>`;
    const content = preview.querySelector('.workspace-file-content');
    try {
      if (file.course_id) {
        const data = await api('/api/course-materials/' + encodeURIComponent(file.id));
        if (request !== previewRequest || key !== context) return;
        selection = { ...data.material, page };
        const pages = [...new Map(data.passages.map((p) => [p.page, p.label])).entries()];
        content.innerHTML = `<label class="workspace-page-control">Location<select aria-label="File page" data-workspace-page>${pages.map(([n, label]) => `<option value="${n}" ${n === page ? 'selected' : ''}>${esc(label)}</option>`).join('')}</select></label><div class="workspace-page-preview"></div>`;
        const picker = content.querySelector('[data-workspace-page]');
        picker.onchange = () => {
          const number = Number(picker.value);
          selection.page = number;
          const target = content.querySelector('.workspace-page-preview');
          if (data.material.mime === 'application/pdf') {
            target.innerHTML = `<iframe title="${esc(file.name)}" src="${esc(file.url)}#page=${number}"></iframe>`;
          } else {
            target.innerHTML = `<pre>${esc(
              data.passages
                .filter((p) => p.page === number)
                .map((p) => p.text)
                .join('\n\n'),
            )}</pre>`;
          }
        };
        picker.onchange();
      } else if (!file.document) {
        content.innerHTML = `<img src="${esc(file.url)}" alt="${esc(file.name)}">`;
      } else if (file.mime === 'application/pdf' || /\.pdf$/i.test(file.name)) {
        content.innerHTML = `<iframe title="${esc(file.name)}" src="${esc(file.url)}?inline=1#page=${page}"></iframe>`;
      } else {
        const data = await api(file.url + '?preview=1');
        if (request !== previewRequest || key !== context) return;
        content.innerHTML = `<p class="muted">Text preview. Long documents may be shortened; open the original for full formatting.</p><pre>${esc(data.text)}</pre>`;
      }
      content.removeAttribute('role');
    } catch (error) {
      if (request === previewRequest && key === context) content.textContent = error.message;
    }
  }

  async function openTeachingFile(id, page = 1) {
    const key = contextKey();
    const data = await api('/api/course-materials/' + encodeURIComponent(id));
    if (!key || key !== contextKey()) return;
    if (!slot?.isConnected) mount();
    fileTab = 'course';
    if (!teachingFiles.some((f) => f.id === id)) teachingFiles.push(data.material);
    await openFile(data.material, page);
  }

  document.addEventListener('click', async (event) => {
    const button = event.target.closest('button');
    if (!button) return;
    try {
      if (button.dataset.workspacePanel) {
        const name = button.dataset.workspacePanel;
        show(wanted === name ? null : name, button);
      } else if (button.dataset.workspaceClose) {
        show(null);
      } else if (button.dataset.fileTab) {
        fileTab = button.dataset.fileTab;
        refreshFiles();
      } else if (button.dataset.workspaceFile) {
        const file = (fileTab === 'course' ? teachingFiles : allChatFiles()).find(
          (f) => (f.id || f.url) === button.dataset.workspaceFile,
        );
        if (file) await openFile(file);
      }
    } catch (error) {
      toast(error.message);
    }
  });
  document.addEventListener('input', (event) => {
    if (!event.target.matches('[data-file-search]')) return;
    fileQuery = event.target.value;
    renderFileList();
  });
  document.addEventListener('keydown', (event) => {
    if (!wanted || document.querySelector('dialog[open]')) return;
    if (event.key === 'Escape') {
      event.preventDefault();
      show(null);
    }
    if (event.key === 'Tab' && mobile.matches) {
      const focusable = [
        ...document.querySelectorAll(
          '.pocket-card:not([hidden]) button,.pocket-card:not([hidden]) input,.pocket-card:not([hidden]) select,.pocket-card:not([hidden]) a,.pocket-card:not([hidden]) [contenteditable],.workspace-bookmark',
        ),
      ].filter((el) => !el.disabled && el.getClientRects().length && !el.closest('[inert]'));
      const first = focusable[0],
        last = focusable[focusable.length - 1];
      if (!first) return;
      if (
        event.shiftKey &&
        (document.activeElement === first || !focusable.includes(document.activeElement))
      ) {
        event.preventDefault();
        last.focus();
      } else if (
        !event.shiftKey &&
        (document.activeElement === last || !focusable.includes(document.activeElement))
      ) {
        event.preventDefault();
        first.focus();
      }
    }
  });
  window.addEventListener('resize', () => {
    if (slot?.isConnected) settle();
  });
  document.fonts.ready.then(measureLabels);
  new MutationObserver(measureLabels).observe(document.body, {
    attributes: true,
    attributeFilter: ['class'],
  });

  return { mount, preserve, show, refreshFiles, openFile, openTeachingFile };
})();

// Keep existing attachment and source-chip actions as entry points into the pocket.
const readTeachingFileBeforePocket = readTeachingFile;
readTeachingFile = async function (id) {
  if (screen === 'chat' && active) return workspacePanels.openTeachingFile(id);
  return readTeachingFileBeforePocket(id);
};
const readTeachingPassageBeforePocket = readTeachingPassage;
readTeachingPassage = async function (id) {
  if (screen !== 'chat' || !active) return readTeachingPassageBeforePocket(id);
  const key = active.id,
    owner = state.user.id;
  const data = await api('/api/course-materials/passages/' + encodeURIComponent(id));
  if (active?.id !== key || state.user?.id !== owner) return;
  return workspacePanels.openTeachingFile(data.material.id, data.passage.page);
};
const renderBeforeWorkspacePanels = render;
render = function () {
  workspacePanels.preserve();
  const result = renderBeforeWorkspacePanels();
  workspacePanels.mount();
  return result;
};
workspacePanels.mount();
