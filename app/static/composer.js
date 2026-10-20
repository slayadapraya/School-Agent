'use strict';

/** The active chat composer: attachment tools, model picker, Send/Stop and input sizing.
 * This replaces the base composer in app.js; keep it after preferences.js.
 */
// One composer layout replaces the older nested row/wrapper combinations.
function toolLock(locked) {
  return `<svg class="tool-lock" viewBox="0 0 20 20" aria-hidden="true"><rect x="4" y="8" width="12" height="9" rx="2"/><path d="${locked ? 'M6 8V5a4 4 0 0 1 8 0v3' : 'M7 8V5a4 4 0 0 1 7-2'}"/></svg>`;
}
// Fixed geometry keeps the send arrow compact regardless of theme typography.
function composerControlIcon(running) {
  return running
    ? '<svg class="composer-action-icon" viewBox="0 0 20 20" aria-hidden="true"><rect x="6" y="6" width="8" height="8" rx="1" fill="currentColor" stroke="none"/></svg>'
    : '<svg class="composer-action-icon" viewBox="0 0 20 20" aria-hidden="true"><path d="M10 15V5M6 9l4-4 4 4"/></svg>';
}
function codeToolAvailable() {
  if (studentView || adminTutorFilters) return false;
  return (
    state.user?.role === 'admin' ||
    !!selectorCache?.models.some((m) => !m.locked && /coder/i.test(m.key))
  );
}
composer = function () {
  const uploads =
    course()?.policy?.upload_images !== false &&
    (state.user.role === 'admin' || state.user.permissions?.upload_images !== false);
  const research =
    course()?.policy?.web_research !== false &&
    (state.user.role === 'admin' || state.user.permissions?.web_research !== false);
  const code = codeToolAvailable(),
    running = busy || !!replyAnimation;
  return `<div class="composer-wrap"><div class="chat-end-control" hidden><button type="button" class="chat-jump-bottom" aria-label="Jump to latest message" title="Jump to latest message"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="m5 8.5 7 7 7-7"/></svg></button></div><form id="chat-form" class="composer modern-composer"><div class="attachment-tray">${stagedImages.map((f, i) => `<span class="attachment-chip">▧ ${esc(f.name)}<button type="button" data-staged-image="${i}" aria-label="Remove ${esc(f.name)}">×</button></span>`).join('')}${(pendingImages[active?.id] || []).map((a) => `<span class="attachment-chip">▧ ${esc(a.name)}<button type="button" data-remove-image="${esc(a.id)}" aria-label="Remove ${esc(a.name)}">×</button></span>`).join('')}</div><input type="file" id="image-upload" accept="image/jpeg,image/png,image/webp,.pdf,.docx,.txt,.md,.csv,.json" multiple hidden><textarea rows="1" aria-label="Ask School Agent" id="message" maxlength="4000" placeholder="Type here…"></textarea><div class="composer-footer"><div class="composer-tool-group">${uploads ? '<button type="button" class="tool" data-action="attach" aria-label="Attach files">＋ File / photo</button>' : ''}${!studentView && (state.user.role === 'admin' || state.user.permissions?.generate_files) ? '<button type="button" class="tool" data-create-file="1">▤ Create file</button>' : ''}${research ? '<button type="button" class="tool" data-action="research">⌕ Research</button>' : ''}<button type="button" class="tool" data-action="sources">▧ Course sources</button><button type="button" class="tool ${code ? 'is-unlocked' : 'is-locked'}" data-code-assist="1" aria-disabled="${!code}" title="${code ? 'Code help' : 'A teacher must grant access to a coding model'}">${toolLock(!code)}Code</button><button type="button" class="tool is-locked" data-image-assist="1" aria-disabled="true" title="No image generation service is connected">${toolLock(true)}Image</button></div><div class="composer-right-controls"><button type="button" data-input-model="1" class="input-model-selector" aria-label="Choose chat model" aria-haspopup="menu" aria-expanded="false">${esc(windowModelLabel || 'Choose model')}${adminTutorFilters ? ' · Student filters' : ''} ▾</button><button type="${running ? 'button' : 'submit'}" class="send composer-send ${running ? 'is-running' : ''}" aria-label="${running ? 'Stop response' : 'Send message'}" ${running ? 'data-stop-response="1"' : ''} ${!running && (uploadBusy || creatingThread) ? 'disabled' : ''}>${composerControlIcon(running)}</button></div></div></form><p class="disclosure">Saved to this conversation · Authorised staff can review</p></div>`;
};
function updateSendControl() {
  const button = document.querySelector('.composer-send');
  if (!button) return;
  const running = busy || !!replyAnimation;
  const hasText = !!document.getElementById('message')?.value.trim();
  button.type = running ? 'button' : 'submit';
  button.setAttribute('aria-label', running ? 'Stop response' : 'Send message');
  button.classList.toggle('is-running', running);
  // Text controls the filled appearance; attachment sending and Stop keep their
  // existing behaviour even when the text field is empty.
  button.classList.toggle('has-text', hasText);
  const iconMode = running ? 'stop' : 'send';
  if (button.dataset.iconMode !== iconMode) {
    button.innerHTML = composerControlIcon(running);
    button.dataset.iconMode = iconMode;
  }
  button.toggleAttribute('data-stop-response', running);
  button.disabled = !running && (uploadBusy || creatingThread);
}
function closeModelPopover() {
  document.querySelectorAll('[id="model-popover"]').forEach((el) => el.remove());
  document.querySelector('[data-input-model]')?.setAttribute('aria-expanded', 'false');
}
chooseInputModel = async function () {
  if (document.getElementById('model-popover')) {
    closeModelPopover();
    return;
  }
  const trigger = document.querySelector('[data-input-model]');
  if (!trigger) return;
  // Mount before requesting models so a second click closes this exact pending picker.
  const preview = studentView,
    owner = state.user?.id;
  const popup = document.createElement('div');
  popup.id = 'model-popover';
  popup.className = 'model-popover';
  popup.setAttribute('role', 'menu');
  popup.setAttribute('aria-label', 'Choose model');
  popup.innerHTML =
    '<div class="model-popover-heading"><span>Model</span><button type="button" data-close-model-picker="1" aria-label="Close model picker">×</button></div><p class="model-popover-label" role="status">Loading models…</p>';
  document.body.append(popup);
  trigger.setAttribute('aria-expanded', 'true');
  const rect = trigger.getBoundingClientRect();
  popup.style.right = Math.max(10, innerWidth - rect.right) + 'px';
  popup.style.bottom = Math.max(10, innerHeight - rect.top + 8) + 'px';
  try {
    const data = await api('/api/models' + (preview ? '?student_preview=1' : ''));
    if (!popup.isConnected || document.getElementById('model-popover') !== popup) return;
    if (!trigger.isConnected || state.user?.id !== owner || studentView !== preview) {
      closeModelPopover();
      return;
    }
    selectorCache = data;
    popup.innerHTML = `<div class="model-popover-heading"><span>Model</span><button type="button" data-close-model-picker="1" aria-label="Close model picker">×</button></div>${data.models.map((m) => `<div class="model-choice-row"><button type="button" role="menuitem" data-pick-input-model="${esc(m.key)}" ${m.locked || (studentView && m.key !== data.main) ? 'disabled' : ''}>${m.locked || (studentView && m.key !== data.main) ? toolLock(true) : ''}<span>${esc(m.name)}</span>${m.key === data.selected ? '<span aria-hidden="true">✓</span>' : ''}</button>${!studentView && state.user.role === 'admin' && m.key === data.main ? `<label class="model-student-toggle"><input type="checkbox" id="picker-student-filters" ${adminTutorFilters ? 'checked' : ''}>Student filters</label>` : ''}</div>`).join('')}`;

    const toggle = popup.querySelector('#picker-student-filters');
    if (toggle)
      toggle.onchange = async (e) => {
        const enabled = e.target.checked;
        try {
          const lastModel = [...messages]
            .reverse()
            .find((m) => m.role === 'assistant' && m.meta?.model)?.meta.model;
          const switchModel =
            enabled && (data.selected !== data.main || (lastModel && lastModel !== data.main));
          const draft = $('#message')?.value || '';
          const scroll = $('#content')?.scrollTop || 0;
          if (switchModel) {
            await api('/api/models/select', { model: data.main });
            state = await api('/api/bootstrap');
          }
          if (enabled)
            windowModelLabel = data.models.find((m) => m.key === data.main)?.name || 'Main tutor';
          adminTutorFilters = enabled;
          closeModelPopover();
          if (switchModel) selectSubject(active?.course_id || 'GENERAL');
          else {
            render();
            if ($('#message')) $('#message').value = draft;
            if ($('#content')) $('#content').scrollTop = scroll;
          }
          toast(
            enabled
              ? switchModel
                ? 'Main tutor selected with student filters.'
                : 'Student filters on for this chat.'
              : 'Student filters off for this chat.',
          );
        } catch (err) {
          toast(err.message);
          e.target.checked = !enabled;
        }
      };
  } catch (err) {
    if (popup.isConnected) {
      const status = document.createElement('p');
      status.className = 'model-popover-label';
      status.setAttribute('role', 'status');
      status.textContent = err.message;
      popup.replaceChildren();
      popup.innerHTML =
        '<div class="model-popover-heading"><span>Model</span><button type="button" data-close-model-picker="1" aria-label="Close model picker">×</button></div>';
      popup.append(status);
    }
  }
};
// Preserve Markdown source when stopping its visible, rendered prefix.
function visibleSourcePrefix(animation) {
  const visible = animation.nodes.map((item) => item.node.textContent).join('');
  const source = animation.source;
  let position = 0;
  for (const character of visible) {
    while (position < source.length) {
      if (source.startsWith('```', position)) {
        const end = source.indexOf('\n', position);
        position = end < 0 ? source.length : end + 1;
        continue;
      }
      if (source.startsWith(character, position)) {
        position += character.length;
        break;
      }
      position++;
    }
  }
  return source.slice(0, position).replace(/[\uD800-\uDBFF]$/, '');
}
async function stopResponse() {
  const animation = replyAnimation;
  if (animation) {
    const draft = $('#message')?.value || '';
    const scroll = $('#content')?.scrollTop || 0;
    const prefix = visibleSourcePrefix(animation);
    cancelAnimationFrame(animation.frame);
    animation.cleanup?.();
    animation.element.classList.remove('reply-typing');
    replyAnimation = null;
    const latest = messages.at(-1);
    if (latest?.role === 'assistant') {
      latest.content = prefix;
      latest.meta = { ...latest.meta, stopped: true };
    }
    render();
    if ($('#message')) $('#message').value = draft;
    if ($('#content')) $('#content').scrollTop = scroll;
    try {
      await api('/api/chat/stop', { thread_id: animation.threadId, visible_text: prefix });
    } catch (err) {
      toast(err.message);
    }
    return;
  }
  if (busy && active?.id) {
    replyStopRequested = true;
    const b = document.querySelector('.composer-send');
    if (b) {
      b.disabled = true;
      b.classList.add('is-stopping');
    }
    try {
      await api('/api/chat/stop', { thread_id: active.id });
    } catch (err) {
      toast(err.message);
      updateSendControl();
    }
  }
}
document.addEventListener(
  'click',
  (e) => {
    const b = e.target.closest('button');
    if (b?.hasAttribute('data-stop-response')) {
      e.preventDefault();
      e.stopImmediatePropagation();
      stopResponse();
      return;
    }
    if (
      document.getElementById('model-popover') &&
      !e.target.closest('#model-popover') &&
      !e.target.closest('[data-input-model]')
    )
      closeModelPopover();
    if (b?.dataset.pickInputModel) {
      const checkbox = document.querySelector('#picker-student-filters');
      if (checkbox) b.dataset.studentFilters = String(checkbox.checked);
      setTimeout(closeModelPopover, 0);
    }
    if (b?.dataset.createFile) {
      const input = $('#message');
      input.value = input.value || 'Create a downloadable file that ';
      input.focus();
      input.dispatchEvent(new Event('input', { bubbles: true }));
    }
    if (b?.dataset.codeAssist) {
      if (!codeToolAvailable())
        toast('Code help is locked. Ask your teacher for access to a coding model.');
      else {
        const input = $('#message');
        input.value = input.value || 'Help me understand and improve this code: ';
        input.focus();
      }
    }
    if (b?.dataset.imageAssist)
      toast('Image generation is not connected. File / photo can upload an existing image.');
  },
  true,
);
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') closeModelPopover();
});

// A fast bootstrap can finish before the final deferred script is loaded.
if (state.user && active && screen === 'chat') {
  const draft = $('#message')?.value || '';
  const top = $('#content')?.scrollTop || 0;
  render();
  if ($('#message')) $('#message').value = draft;
  if ($('#content')) $('#content').scrollTop = top;
}

// Match content height on desktop and mobile; stop growing at 180px.
function resizeComposerInput() {
  const input = document.getElementById('message');
  if (!input) return;
  input.style.height = '34px';
  const height = Math.max(34, Math.min(180, input.scrollHeight));
  input.style.height = height + 'px';
  input.style.overflowY = input.scrollHeight > 180 ? 'auto' : 'hidden';
  updateSendControl();
}
window.addEventListener('resize', resizeComposerInput);
const renderBeforeInputSizing = render;
render = function () {
  const result = renderBeforeInputSizing();
  watchChatEnd();
  requestAnimationFrame(resizeComposerInput);
  return result;
};
requestAnimationFrame(resizeComposerInput);

document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape' && document.getElementById('model-popover')) {
    e.preventDefault();
    closeModelPopover();
    document.querySelector('[data-input-model]')?.focus({ preventScroll: true });
  }
});
document.addEventListener(
  'click',
  (e) => {
    if (e.target.closest('[data-close-model-picker]')) {
      e.preventDefault();
      closeModelPopover();
    }
  },
  true,
);

// A single passive scroll listener and size observer keep this affordance in sync
// with replies, panel resizing and the keyboard, without polling or stealing scroll.
let chatEndFrame = null;
const chatEndObserver = new ResizeObserver(scheduleChatEndUpdate);
function scheduleChatEndUpdate() {
  if (chatEndFrame !== null) return;
  chatEndFrame = requestAnimationFrame(() => {
    chatEndFrame = null;
    const area = document.getElementById('content');
    const control = document.querySelector('.chat-end-control');
    if (!control || !area) return;
    const composer = document.getElementById('chat-form');
    if (composer) {
      const box = composer.getBoundingClientRect();
      const parent = control.parentElement.getBoundingClientRect();
      control.style.setProperty(
        '--chat-jump-center',
        `${box.left + box.width / 2 - parent.left}px`,
      );
    }

    const away =
      !!area.querySelector('.conversation .message') &&
      area.scrollHeight - area.clientHeight - area.scrollTop > 80;
    control.hidden = !away;
    area.classList.toggle('chat-away-from-bottom', away);
  });
}
function watchChatEnd() {
  chatEndObserver.disconnect();
  const area = document.getElementById('content');
  const conversation = area?.querySelector('.conversation');
  if (area && conversation) {
    chatEndObserver.observe(area);
    chatEndObserver.observe(conversation);
  }
  scheduleChatEndUpdate();
}
document.addEventListener(
  'scroll',
  (event) => {
    if (event.target.id === 'content') scheduleChatEndUpdate();
  },
  { capture: true, passive: true },
);
document.addEventListener('click', (event) => {
  if (!event.target.closest('.chat-jump-bottom')) return;
  const area = document.getElementById('content');
  area?.scrollTo({
    top: area.scrollHeight,
    behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth',
  });
});
watchChatEnd();

// Reserve the scrollbar's geometry, but reveal its thumb only during deliberate
// scrolling or while the reader is above the latest messages.
let chatScrollbarTimer;
function revealChatScrollbar(event) {
  const area = document.getElementById('content');
  if (!area?.querySelector('.conversation')) return;
  if (event.type === 'keydown') {
    if (
      !['PageUp', 'PageDown', 'Home', 'End', 'ArrowUp', 'ArrowDown'].includes(event.key) ||
      event.target.closest('textarea,input,[contenteditable="true"]')
    )
      return;
  } else if (!area.contains(event.target)) return;
  area.classList.add('chat-is-scrolling');
  clearTimeout(chatScrollbarTimer);
  chatScrollbarTimer = setTimeout(() => area.classList.remove('chat-is-scrolling'), 900);
}
for (const type of ['wheel', 'touchmove', 'pointerdown'])
  document.addEventListener(type, revealChatScrollbar, { capture: true, passive: true });
document.addEventListener('keydown', revealChatScrollbar);

// Poll only during this send. Fixed public phase summaries come from real server
// milestones, never from raw model reasoning, prompts, logs or an extra model call.
let replyActivitySession = null;
function stopReplyActivity() {
  if (!replyActivitySession) return;
  clearTimeout(replyActivitySession.timer);
  replyActivitySession.controller?.abort();
  replyActivitySession.cleanup?.();
  replyActivitySession = null;
}
function startReplyActivity(threadId, owner) {
  stopReplyActivity();
  const area = document.getElementById('content');
  const session = { threadId, owner, timer: null, controller: null, follow: true };
  const oldAnchor = area?.style.overflowAnchor;
  if (area) area.style.overflowAnchor = 'none';
  const readPosition = () => {
    if (area && area.scrollHeight - area.clientHeight - area.scrollTop <= 4) session.follow = true;
  };
  const userScroll = (event) => {
    if (event.type === 'keydown') {
      if (
        event.target.closest('input,textarea,[contenteditable="true"]') ||
        !['ArrowUp', 'ArrowDown', 'PageUp', 'PageDown', 'Home', 'End'].includes(event.key)
      )
        return;
    }
    session.follow = false;
    // Browser scrolling happens after wheel/touch/key dispatch.
    requestAnimationFrame(readPosition);
  };
  for (const type of ['wheel', 'touchmove', 'pointerdown'])
    area?.addEventListener(type, userScroll, { passive: true });
  area?.addEventListener('scroll', readPosition, { passive: true });
  document.addEventListener('keydown', userScroll);
  session.cleanup = () => {
    for (const type of ['wheel', 'touchmove', 'pointerdown'])
      area?.removeEventListener(type, userScroll);
    area?.removeEventListener('scroll', readPosition);
    document.removeEventListener('keydown', userScroll);
    if (area) area.style.overflowAnchor = oldAnchor || '';
  };
  replyActivitySession = session;
  const poll = async () => {
    if (
      replyActivitySession !== session ||
      !busy ||
      active?.id !== threadId ||
      state.user?.id !== owner
    )
      return;
    session.controller = new AbortController();
    try {
      const response = await fetch('/api/chat/activity?thread_id=' + encodeURIComponent(threadId), {
        signal: session.controller.signal,
      });
      if (!response.ok) return;
      const data = await response.json();
      if (replyActivitySession !== session || !busy || active?.id !== threadId) return;
      const root = document.querySelector('.reply-activity');
      const steps = data.steps || [];
      const current = steps.at(-1);
      if (root && current) {
        const previousTop = area?.scrollTop || 0;
        root.querySelector('[data-activity-current]').textContent = current.label;
        root.querySelector('[data-activity-detail]').textContent = current.detail;
        const list = root.querySelector('[data-activity-steps]');
        const previous = steps.slice(0, -1);
        const signature = previous.map((step) => step.phase).join(',');
        if (list.dataset.signature !== signature) {
          list.innerHTML = previous.map((step) => `<li>${esc(step.label)}</li>`).join('');
          list.dataset.signature = signature;
        }
        list.hidden = previous.length === 0;
        const live = root.querySelector('[data-activity-live]');
        const seconds = Math.floor((data.elapsed_ms || 0) / 1000);
        const updates = data.stream_updates || 0;
        live.textContent = `${seconds}s · ${data.model_active ? (data.request_updates ? 'Receiving model output' : 'Waiting for model output') : 'Processing request'}${updates ? ` · ${updates} updates received` : ''}`;
        if (session.follow) scrollChat();
        else if (area) area.scrollTop = previousTop;
      }
    } catch (error) {
      /* Reply delivery remains independent of progress updates. */
    } finally {
      if (replyActivitySession === session && busy) session.timer = setTimeout(poll, 500);
    }
  };
  session.timer = setTimeout(poll, 200);
}
