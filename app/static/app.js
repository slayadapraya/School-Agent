'use strict';

/** Application shell, authenticated API calls, chat state and primary navigation.
 * Feature scripts extend these shared functions in the order listed in index.html.
 */
let replyAnimation = null;
// -----------------------------------------------------------------------------
// Reply presentation
// -----------------------------------------------------------------------------
function stopReplyAnimation() {
  if (!replyAnimation) return;
  cancelAnimationFrame(replyAnimation.frame);
  for (const item of replyAnimation.nodes) item.node.textContent = item.text;
  replyAnimation.cleanup?.();
  replyAnimation.element.classList.remove('reply-typing');
  replyAnimation = null;
  if (typeof updateSendControl === 'function') updateSendControl();
}
function animateLatestReply(followOverride) {
  stopReplyAnimation();
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
  const replies = [...document.querySelectorAll('.conversation .message.assistant .message-copy')];
  const element = replies.at(-1);
  if (!element) return;
  const walker = document.createTreeWalker(element, NodeFilter.SHOW_TEXT);
  const nodes = [];
  let node;
  while ((node = walker.nextNode())) {
    if (!node.parentElement.closest('.code-toolbar')) nodes.push({ node, text: node.textContent });
  }
  const length = nodes.reduce((n, item) => n + item.text.length, 0);
  if (!length) return;
  const content = document.getElementById('content');
  let follow = followOverride ?? conversationNearBottom();
  const release = () => {
    follow = false;
  };
  const keys = (e) => {
    if (['ArrowUp', 'ArrowDown', 'PageUp', 'PageDown', 'Home', 'End', ' '].includes(e.key))
      release();
  };
  content?.addEventListener('wheel', release, { passive: true });
  content?.addEventListener('touchstart', release, { passive: true });
  content?.addEventListener('pointerdown', release);
  document.addEventListener('keydown', keys);
  const oldAnchor = content?.style.overflowAnchor;
  if (content) content.style.overflowAnchor = 'none';
  for (const item of nodes) item.node.textContent = '';
  element.classList.add('reply-typing');
  const animation = {
    element,
    nodes,
    frame: null,
    start: performance.now(),
    threadId: active?.id,
    source: messages.at(-1)?.content || '',
    revealed: 0,
  };
  replyAnimation = animation;
  if (typeof updateSendControl === 'function') updateSendControl();
  animation.cleanup = () => {
    content?.removeEventListener('wheel', release);
    content?.removeEventListener('touchstart', release);
    content?.removeEventListener('pointerdown', release);
    document.removeEventListener('keydown', keys);
    if (content) content.style.overflowAnchor = oldAnchor || '';
  };
  const rate = Math.max(65, length / 7);
  const draw = (now) => {
    if (replyAnimation !== animation || !element.isConnected) {
      stopReplyAnimation();
      return;
    }
    // Follow only until the user scrolls, touches, or grabs the scrollbar.
    let available = Math.min(length, Math.floor(((now - animation.start) * rate) / 1000));
    animation.revealed = Math.min(length, Math.floor(((now - animation.start) * rate) / 1000));
    for (const item of nodes) {
      const count = Math.min(item.text.length, available);
      item.node.textContent = item.text.slice(0, count);
      available -= count;
    }
    if (follow && content) scrollChat();
    if (((now - animation.start) * rate) / 1000 >= length) {
      stopReplyAnimation();
      return;
    }
    animation.frame = requestAnimationFrame(draw);
  };
  animation.frame = requestAnimationFrame(draw);
}

const $ = (s) => document.querySelector(s);
const esc = (s) =>
  String(s ?? '').replace(
    /[&<>"']/g,
    (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c],
  );
let state = { courses: [], threads: [], user: null },
  active = null,
  messages = [],
  screen = 'home',
  busy = false;
let studentView = false;
// Admin-only tutor filter switch; it does not change account navigation or role.
let adminTutorFilters = false;
let replyStopRequested = false;
let navOpen = false;
let quickCategory = '';
const expandedSubjects = new Set();
const expandedCategories = new Set();
let stagedImages = [];
let creatingThread = false;
// -----------------------------------------------------------------------------
// Subject navigation and theme selection
// -----------------------------------------------------------------------------
function subjectCategories() {
  return [...new Set(state.courses.map((c) => c.category || c.name))];
}
function selectSubject(code) {
  if (busy) return;
  navOpen = false;
  const c = state.courses.find((c) => c.id === code);
  if (!c) return;
  active = { id: null, draft: true, course_id: code, title: 'New conversation' };
  messages = [];
  stagedImages = [];
  screen = 'chat';
  expandedCategories.add(c.category || c.name);
  expandedSubjects.add(code);
  render();
  $('#message')?.focus();
}
function subjectNavigation() {
  return subjectCategories()
    .map((category) => {
      const cs = state.courses.filter((c) => (c.category || c.name) === category),
        isGeneral = cs[0]?.id === 'GENERAL';
      return `<section class="category-group"><button class="category-toggle" data-category="${esc(category)}" aria-expanded="${expandedCategories.has(category)}"><span>${esc(category)}</span><span>${expandedCategories.has(category) ? '⌄' : '›'}</span></button><div ${expandedCategories.has(category) ? '' : 'hidden'}>${cs
        .map(
          (c) =>
            `<section class="subject-group"><div class="subject-heading"><button class="course-nav ${active?.course_id === c.id ? 'active' : ''}" data-select-course="${esc(c.id)}" aria-current="${active?.course_id === c.id ? 'page' : 'false'}"><span class="subject-dot"></span><span>${isGeneral ? 'General prompts' : esc(c.id)}</span>${c.year_level ? `<small>Year ${c.year_level}</small>` : ''}</button><button class="thread-fold" data-toggle-course="${esc(c.id)}" aria-label="Toggle ${esc(c.id)} threads" aria-expanded="${expandedSubjects.has(c.id)}" aria-controls="threads-${esc(c.id)}">${expandedSubjects.has(c.id) ? '⌄' : '›'}</button></div><div id="threads-${esc(c.id)}" class="subject-threads" ${expandedSubjects.has(c.id) ? '' : 'hidden'}>${state.threads
              .filter((t) => t.course_id === c.id)
              .map(
                (t) =>
                  `<button class="thread-nav ${active?.id === t.id ? 'selected' : ''}" data-thread="${esc(t.id)}">${esc(t.title)}</button>`,
              )
              .join('')}</div></section>`,
        )
        .join('')}</div></section>`;
    })
    .join('');
}
const pendingImages = {};
let uploadBusy = false;
const themes = { cream: 'Cream', navy: 'Navy', studio: 'Research Studio' };
let theme = localStorage.getItem('school-agent-theme') || 'studio';
if (!Object.hasOwn(themes, theme)) theme = 'studio';
function applyTheme(value, persist = true) {
  if (!Object.hasOwn(themes, value)) return;
  theme = value;
  if (persist) localStorage.setItem('school-agent-theme', theme);
  document.body.classList.toggle('dark', theme === 'navy');
  document.body.classList.toggle('theme-studio', theme === 'studio');
  document.body.dataset.theme = theme;
  document.documentElement.style.colorScheme = theme === 'cream' ? 'light' : 'dark';
  document
    .querySelectorAll('[data-theme-choice]')
    .forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.themeChoice === theme)));
  const status = document.querySelector('#appearance-status');
  if (status) status.textContent = themes[theme] + ' selected · saved on this browser.';
  const toggle = document.querySelector('[data-action="theme"]');
  if (toggle) {
    toggle.textContent = theme === 'navy' ? '☀' : theme === 'studio' ? '◐' : '☾';
    toggle.title = 'Theme: ' + themes[theme];
  }
}
applyTheme(theme, false);
const symbols = ['⌘', '∑', '◷', '△', '⌨', '▥'];
// Parse transport failures separately from application errors; never retry a mutation.
// -----------------------------------------------------------------------------
// HTTP requests and sign-in
// -----------------------------------------------------------------------------
async function api(path, data) {
  const options = {
    method: data ? 'POST' : 'GET',
    headers: data ? { 'Content-Type': 'application/json', 'X-School-Agent': '1' } : {},
    body: data ? JSON.stringify(data) : undefined,
  };
  for (let attempt = 0; attempt < (data ? 1 : 2); attempt++) {
    let r, raw, p;
    try {
      r = await fetch(path, options);
      raw = await r.text();
      try {
        p = JSON.parse(raw);
      } catch (err) {
        throw Error(raw.trim() ? 'invalid-json' : 'empty-response');
      }
    } catch (err) {
      const reason = ['invalid-json', 'empty-response'].includes(err.message)
        ? err.message
        : 'connection-failed';
      // Do not record response bodies, submitted text, query strings or credentials.
      if (path != '/api/client-error')
        fetch('/api/client-error', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'X-School-Agent': '1' },
          body: JSON.stringify({
            route: path.split('?')[0].split('/').slice(0, 3).join('/'),
            status: r?.status || 0,
            reason,
          }),
        }).catch(() => {});
      if (!data && attempt === 0) {
        await new Promise((resolve) => setTimeout(resolve, 300));
        continue;
      }
      throw Error(
        r?.status >= 500
          ? `The server is temporarily unavailable (HTTP ${r.status}). Please try again.`
          : 'The connection ended before a complete response arrived. Please try again.',
      );
    }
    if (!r.ok) {
      if (r.status === 401 && path != '/api/login') login();
      throw Error(p?.error || `Request failed (HTTP ${r.status})`);
    }
    return p;
  }
}
function toast(text) {
  $('#toast').textContent = text;
  $('#toast').classList.add('visible');
  setTimeout(() => $('#toast').classList.remove('visible'), 5000);
}
function modal(title, body) {
  $('#modal-content').innerHTML = `<h2>${esc(title)}</h2>${body}`;
  $('#modal').showModal();
}
function course() {
  return state.courses.find((c) => c.id === active?.course_id);
}
function login() {
  if (typeof restoredWorkspaceUser !== 'undefined') restoredWorkspaceUser = null;
  state.user = null;
  $('#app').innerHTML =
    `<main class="login-page"><section class="login-story"><div class="brand"><img class="brand-logo" src="/favicon.svg" alt="" width="48" height="48">School Agent</div><h1>School Agent</h1><p>Local tutoring and course conversations.</p></section><section class="login-form"><form class="login-inner" id="login-form"><h2>Sign in</h2><p class="muted">Sign in with your School Agent username and password.</p><label for="username">Username</label><input id="username" autocomplete="username" required placeholder="Your username"><label for="password">Password</label><input id="password" type="password" autocomplete="current-password" required placeholder="Your password"><button class="primary" type="submit">Sign in <span>→</span></button><div id="login-error" class="error" role="alert"></div><p class="muted">Your administrator manages accounts and access permissions.</p><div class="notice">Conversations are saved. Authorised staff can review assignment records. School Agent is under development. Starter course material still needs staff review.</div></form></section></main>`;
  $('#login-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const b = e.target.querySelector('button');
    b.disabled = true;
    try {
      await api('/api/login', { username: $('#username').value, password: $('#password').value });
      await bootstrap();
    } catch (e) {
      $('#login-error').textContent = e.message;
      b.disabled = false;
    }
  });
}
async function bootstrap() {
  try {
    state = await api('/api/bootstrap');
    render();
    if (typeof restoreWorkspaceLocation === 'function') await restoreWorkspaceLocation();
    if (typeof refreshComposerModelLabel === 'function') refreshComposerModelLabel();
  } catch (e) {
    if (!state.user) login();
    else toast(e.message);
  }
}
// -----------------------------------------------------------------------------
// Sidebar and home screen
// -----------------------------------------------------------------------------
function side() {
  return `<aside class="sidebar" id="site-navigation" aria-label="Chat navigation"><button class="icon sidebar-close" data-action="close-menu" aria-label="Close navigation">✕</button><button class="brand" data-action="home" aria-label="School Agent home"><img class="brand-logo" src="/favicon.svg" alt="" width="48" height="48"><span>School Agent</span></button><div class="institution">${studentView ? 'Student view · preview' : state.user.role === 'admin' ? 'Administrative view' : state.user.role === 'teacher' ? 'Teacher view' : 'Student view'}</div><button class="primary new-thread" data-action="new">New thread <span>＋</span></button><nav><div class="recent-chats-heading"><button class="nav-link recent-home" data-action="home">▤ &nbsp; Recent chats</button><button type="button" data-toggle-recent="1" aria-label="Toggle recent chats" aria-expanded="${!recentChatsHidden()}">${recentChatsHidden() ? '▸' : '▾'}</button></div><div class="sidebar-recent" ${recentChatsHidden() ? 'hidden' : ''}>${recentThreads()
    .slice(0, 3)
    .map(
      (t) =>
        `<button class="sidebar-recent-row ${active?.id === t.id ? 'selected' : ''}" data-thread="${esc(t.id)}"><span>${esc(t.title)}</span><small>${esc(t.course_id)}</small></button>`,
    )
    .join(
      '',
    )}</div>${state.user.role === 'admin' && !studentView && typeof adminPersonalNavigation === 'function' ? adminPersonalNavigation() : '<div class="eyebrow sidebar-subject-label">Subjects</div>' + subjectNavigation()}</nav><div class="side-bottom"><button class="nav-link" data-action="sources">▧ &nbsp; Course library</button>${!studentView && (state.user.role === 'admin' || state.user.role === 'teacher' || state.user.permissions?.review_records || state.user.permissions?.manage_courses) ? '<button class="nav-link" data-action="staff">⊞ &nbsp; Staff studio</button>' : ''}<button class="nav-link" data-action="settings">⚙ &nbsp; Settings</button><div class="profile-area"><div id="profile-popup" class="profile-popup" role="menu" hidden>${state.user.role !== 'student' && (state.user.role !== 'admin' || state.model_selection?.selected === state.model_selection?.main) ? `<button role="menuitem" data-action="student-view">${studentView ? '↩ Return to staff view' : '♙ Student view'}</button>` : ''}<button role="menuitem" data-action="account-settings">⚙ Account settings</button>${(state.user.account_role || state.user.role) === 'admin' ? `<button role="menuitem" data-account-view="${state.user.role === 'teacher' ? 'admin' : 'teacher'}">${state.user.role === 'teacher' ? '↩ Return to admin view' : '♙ Show teacher view'}</button>` : ''}<div class="profile-divider"></div><button role="menuitem" class="logout-item" data-action="logout">↪ Log out</button></div><button class="person profile-trigger" data-action="profile" aria-expanded="false" aria-controls="profile-popup"><span class="avatar">${esc(state.user.name.slice(0, 2).toUpperCase())}</span><span class="profile-name"><b>${esc(state.user.name)}</b><small>${studentView ? 'Student view · preview' : esc(state.user.role) + ' account'}</small></span><span aria-hidden="true">⌃</span></button></div></div></aside>`;
}
function recentThreads() {
  return [...state.threads].sort((a, b) => (b.updated || b.created) - (a.updated || a.created));
}
function quickYears(category) {
  return state.courses
    .filter((c) => (c.category || c.name) === category)
    .map(
      (c) =>
        `<button data-course="${esc(c.id)}"><b>${c.year_level ? 'Year ' + c.year_level : 'Open chat'}</b><small>${esc(c.id)}</small></button>`,
    )
    .join('');
}
function home() {
  if (state.user.role === 'admin' && !studentView && typeof adminPersonalHome === 'function')
    return adminPersonalHome();
  const categories = subjectCategories();
  if (!categories.includes(quickCategory)) quickCategory = categories[0] || '';
  return `<div class="welcome"><section class="recent-chats"><div class="section-label"><h3>Recent chats</h3><small>${state.threads.length} conversations</small></div>${
    state.threads.length
      ? recentThreads()
          .slice(0, 6)
          .map(
            (t) =>
              `<button class="recent-row" data-thread="${esc(t.id)}"><span class="course-symbol">▤</span><span class="recent-copy"><b>${esc(t.title)}</b><small>${esc(t.course_id)} · ${new Date((t.updated || t.created) * 1000).toLocaleDateString()}</small></span><span class="arrow">↗</span></button>`,
          )
          .join('')
      : '<div class="empty">No chats yet. Choose a subject below to start.</div>'
  }</section><section class="mobile-subject-picker"><div class="section-label"><h3>Start a chat</h3></div><label for="quick-subject">Subject</label><select id="quick-subject">${categories.map((c) => `<option ${c === quickCategory ? 'selected' : ''}>${esc(c)}</option>`).join('')}</select><div class="quick-years" id="quick-years">${quickYears(quickCategory)}</div></section><section class="desktop-subjects"><div class="section-label"><h3>Subjects</h3></div><div class="course-grid">${categories
    .map(
      (category, i) =>
        `<article class="course-card"><span class="course-symbol">${symbols[i % symbols.length]}</span><b>${esc(category)}</b><div class="year-choices">${state.courses
          .filter((c) => (c.category || c.name) === category)
          .map(
            (c) =>
              `<button data-course="${esc(c.id)}">${c.year_level ? 'Year ' + c.year_level : 'Open'}<small>${esc(c.id)}</small></button>`,
          )
          .join('')}</div></article>`,
    )
    .join('')}</div></section></div>`;
}
function setMenu(open) {
  navOpen = open;
  $('.shell')?.classList.toggle('menu-open', open);
  const trigger = $('[data-action="menu"]');
  trigger?.setAttribute('aria-expanded', String(open));
  const main = $('.main');
  if (main) main.inert = open && window.matchMedia('(max-width:750px)').matches;
  if (!open && trigger && window.matchMedia('(max-width:750px)').matches) trigger.focus();
  if (open) $('.sidebar-close')?.focus();
}

// -----------------------------------------------------------------------------
// Chat messages and source links
// -----------------------------------------------------------------------------
function referenceHTML(meta) {
  return `<div class="reference-list"><b>${esc(meta.reference_intro)}</b>${meta.references.map((r) => `<p class="reference-item">${r.parts.map((p) => (p.url && /^https:\/\//i.test(p.url) ? `<a href="${esc(p.url)}" target="_blank" rel="noopener noreferrer">${esc(p.text)}</a>` : p.italic ? `<i>${esc(p.text)}</i>` : esc(p.text))).join('')}</p>`).join('')}</div>`;
}
function agentAvatar(thinking = false) {
  return `<span class="agent-avatar ${thinking ? 'is-thinking' : ''}" aria-hidden="true"><svg viewBox="0 0 36 40" focusable="false"><g class="agent-figure"><path class="agent-shirt" d="M7 36v-3a11 11 0 0 1 22 0v3c-6 2-16 2-22 0Z"/><circle class="agent-head" cx="18" cy="14" r="8"/><g class="agent-eyes"><circle cx="15" cy="14" r="1"/><circle cx="21" cy="14" r="1"/></g></g></svg></span>`;
}
// Escape ordinary text and render fenced code with a local, offline highlighter.
function replyTextHTML(text) {
  const value = String(text ?? '').trim();
  const fence = /```([^\n`]*)\n([\s\S]*?)(?:```|$)/g;
  let html = '',
    offset = 0,
    match;
  const prose = (value) =>
    value
      .split(/\n\s*\n/)
      .filter(Boolean)
      .map(
        (p) =>
          `<p class="reply-paragraph">${esc(p)
            .replace(/\*\*([^*\n]+)\*\*/g, '<strong>$1</strong>')
            .replace(/`([^`\n]+)`/g, '<code class="inline-code">$1</code>')
            .replace(/\n/g, '<br>')}</p>`,
      )
      .join('');
  while ((match = fence.exec(value))) {
    html += prose(value.slice(offset, match.index));
    const language = match[1].trim().split(/\s/)[0].toLowerCase();
    const code = match[2].replace(/\n$/, '');
    let highlighted = esc(code);
    try {
      if (window.hljs) {
        highlighted =
          language && hljs.getLanguage(language)
            ? hljs.highlight(code, { language, ignoreIllegals: true }).value
            : hljs.highlightAuto(code).value;
      }
    } catch (e) {}
    html += `<section class="code-block"><div class="code-toolbar"><span>${esc(language || 'code')}</span><button type="button" data-copy-code="1">Copy code</button></div><pre tabindex="0"><code>${highlighted}</code></pre></section>`;
    offset = fence.lastIndex;
  }
  return html + prose(value.slice(offset));
}
function messageHTML(m) {
  if (m.role === 'user')
    return `<div class="message user">${esc(m.content)}${(m.meta?.attachments || []).map((a) => `<button class="message-image" data-view-file="${esc(a.url)}" data-file-name="${esc(a.name)}" data-document="${a.document ? 1 : 0}">${a.document ? '▤' : `<img src="${esc(a.url)}" alt="${esc(a.name)}">`}<span>${esc(a.name)}</span></button>`).join('')}</div>`;
  const meta = m.meta || {};
  return `<div class="message assistant">${agentAvatar()}<div class="message-body"><div class="message-name">School Agent</div><div class="message-copy">${meta.references ? referenceHTML(meta) : replyTextHTML(meta.route === 'research' ? m.content.split('\n\nSources:\n')[0].trim() : m.content)}</div>${(meta.records || []).map((r) => `<button class="source-chip" data-record="${esc(r.id)}">${esc(r.student)} · ${esc(r.title)} ↗</button>`).join('')}${meta.disclaimer ? `<small class="research-disclaimer">${esc(meta.disclaimer)}</small>` : ''}${(meta.sources || []).map((s) => (/^material-[a-f0-9]{32}$/.test(s.id || '') ? `<button class="source-chip" data-course-passage="${esc(s.id.slice(9))}">[${(meta.sources || []).indexOf(s) + 1}] ${esc(s.title)} · ${esc(s.page_label || s.locator)} ↗</button>` : s.url && /^https:\/\//i.test(s.url) ? `<a class="source-chip" href="${esc(s.url)}" target="_blank" rel="noopener noreferrer">[${(meta.sources || []).indexOf(s) + 1}] ${esc(s.title)} ↗</a>` : `<button class="source-chip" data-source="${esc(s.id)}">▧ ${esc(s.title)} ↗</button>`)).join('')}<small class="route-note">${meta.stopped ? 'Stopped · ' : ''}${meta.image_used ? 'Image read · ' : ''}${meta.route === 'demo' ? 'Demo · sample reply' : meta.route === 'teaching_gap' ? 'Specific teaching material needed' : meta.route === 'concept_guidance' ? 'Concept explanation' : meta.route === 'student_guidance' ? 'Guided tutoring · response checked' : meta.route === 'guidance_unavailable' ? 'Tutoring response unavailable' : meta.route === 'activity_analytics' ? 'Activity analytics · saved records' : meta.route === 'access_denied' ? 'Access restricted' : meta.route === 'research_overview' ? 'Research overview' : meta.route === 'planning' ? 'Planning guidance · no local figures assumed' : meta.route === 'research' ? (meta.references ? 'References · ' + meta.reference_style : 'Live research · source excerpt') : meta.route === 'generation_error' ? 'Response unavailable' : meta.route === 'configured_tutoring' ? 'Learning assistant' : meta.route === 'experimental_checked' ? 'Experimental response · checked, not guaranteed' : meta.route === 'fallback' ? 'General reflection prompt · no generated answer displayed' : meta.route === 'layout' ? 'Blank planning scaffold' : 'Approved course hint'}</small></div></div>`;
}
function chat() {
  const c = course();
  return `<div class="workspace-grid"><section class="conversation" aria-live="polite">${messages.length ? messages.map(messageHTML).join('') : `<div class="empty-start"><span class="course-symbol">✦</span><span class="eyebrow">${c.id === 'GENERAL' ? 'General prompts' : esc(c.id)}</span><h1>New conversation</h1><p>Ask a question or attach a photo of your work.</p><div class="chips"><button data-starter="${esc(c.starter)}">${esc(c.starter)} ↗</button></div><div class="notice">${!studentView && c.policy?.staff_unrestricted ? 'Administrator assistant · your own conversations are unrestricted.' : studentView || c.policy?.student_guidance ? 'Context-aware tutoring: explanations and hints, without completed task answers.' : c.policy?.approved_only ? 'Tutoring uses approved hints. Factual research can retrieve source quotations and article links.' : !c.policy?.approved_only ? 'Ask questions, explore ideas and get clear explanations.' : c.mode === 'strict' ? 'Tutoring uses approved hints.' : 'Experimental mode generates new guidance. It can make mistakes or reveal answers despite review.'}</div></div>`}${busy ? `<div class="loading">${agentAvatar(true)}<span>Thinking through your question…</span></div>` : ''}</section>${typeof notesDockHTML === 'function' ? notesDockHTML() : ''}</div>`;
}
function composer() {
  const canUpload =
    course()?.policy?.upload_images !== false &&
    (state.user.role === 'admin' || state.user.permissions?.upload_images !== false);
  return `<div class="composer-wrap"><form id="chat-form" class="composer"><div class="attachment-tray">${stagedImages.map((f, i) => `<span class="attachment-chip">▧ ${esc(f.name)}<button type="button" data-staged-image="${i}" aria-label="Remove ${esc(f.name)}">×</button></span>`).join('')}${(pendingImages[active?.id] || []).map((a) => `<span class="attachment-chip">▧ ${esc(a.name)}<button type="button" data-remove-image="${esc(a.id)}" aria-label="Remove ${esc(a.name)}">×</button></span>`).join('')}</div><input type="file" id="image-upload" accept="image/jpeg,image/png,image/webp,.pdf,.docx,.txt,.md,.csv,.json" multiple hidden><div class="composer-row">${canUpload ? `<button type="button" class="mobile-photo" data-action="attach" aria-label="Add photo"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M8 6l1.5-2h5L16 6h3a2 2 0 0 1 2 2v11H3V8a2 2 0 0 1 2-2Z"/><circle cx="12" cy="12" r="4"/></svg></button>` : ''}<div class="composer-input"><textarea aria-label="Ask School Agent" id="message" maxlength="4000" placeholder="Type here…" ${!active ? 'disabled' : ''}></textarea><div class="tools desktop-chat-tools">${canUpload ? '<button type="button" class="tool" data-action="attach" aria-label="Attach files">＋ File / photo</button>' : ''}${course()?.policy?.web_research !== false && (state.user.role === 'admin' || state.user.permissions?.web_research !== false) ? '<button type="button" class="tool" data-action="research">⌕ Research</button>' : ''}<button type="button" class="tool" data-action="sources">▧ Course sources</button><button type="button" class="tool" data-action="layout">▤ Blank layout</button>${state.user.role === 'admin' ? '' : '<button type="button" class="tool locked" data-action="locked">♧ Image generation locked</button><button type="button" class="tool locked" data-action="locked">⌘ Code locked</button>'}</div></div><button type="submit" class="send composer-send" aria-label="Send message" ${!active || busy || uploadBusy ? 'disabled' : ''}>↑</button></div></form><p class="disclosure">Saved to this conversation · Authorised staff can review${state.retention_days ? ' · ' + state.retention_days + '-day retention' : ''}</p></div>`;
}

// -----------------------------------------------------------------------------
// Application rendering and chat actions
// -----------------------------------------------------------------------------
function render() {
  stopReplyAnimation();
  const c = course();
  $('#app').innerHTML =
    `<div class="shell ${navOpen ? 'menu-open' : ''}">${side()}<button class="menu-scrim" data-action="close-menu" aria-label="Close navigation backdrop" tabindex="-1"></button><main class="main"><header class="topbar"><button class="icon mobile-menu" data-action="menu" aria-label="Open navigation" aria-expanded="${navOpen}" aria-controls="site-navigation">☰</button><div class="header-title">${active && (state.user.role !== 'admin' || studentView) ? `<div class="breadcrumb">${c.id === 'GENERAL' ? 'General prompts' : `${esc(c.id)} / ${esc(c.name)}`}</div>` : ''}<h2>${screen === 'admin' ? 'Admin menu' : screen === 'staff' ? 'Staff studio' : active ? threadTitleButton() : 'Chats'}</h2></div>${!studentView && state.user.role === 'admin' ? '<button class="header-admin" data-action="admin" aria-label="Open admin panel"><svg viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="3" width="18" height="13" rx="2"/><path d="M8 21h8M12 16v5"/></svg>Admin Controls</button>' : ''}</header>${policyBannerHTML(c)}<div class="content" id="content">${screen === 'admin' ? '<div class="staff" id="admin-body">Loading accounts…</div>' : screen === 'staff' ? '<div class="staff" id="staff-body"><p>Loading staff records…</p></div>' : active ? chat() : home()}</div>${active && screen === 'chat' ? composer() : ''}</main></div>`;
  if ($('.main')) $('.main').inert = navOpen && window.matchMedia('(max-width:750px)').matches;
  if ($('#quick-subject'))
    $('#quick-subject').addEventListener('change', (e) => {
      quickCategory = e.target.value;
      $('#quick-years').innerHTML = quickYears(quickCategory);
    });
  if ($('#chat-form'))
    $('#chat-form').addEventListener('submit', (e) => {
      e.preventDefault();
      send();
    });
  if ($('#image-upload'))
    $('#image-upload').addEventListener('change', (e) => uploadImages(Array.from(e.target.files)));
  if ($('#message'))
    $('#message').addEventListener('input', () => {
      if (typeof resizeComposerInput === 'function') resizeComposerInput();
    });
  if ($('#message'))
    $('#message').addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        send();
      }
    });
  if (screen === 'staff') loadStaff();
  if (screen === 'admin') loadAdmin();
}
async function openThread(id) {
  if (busy) return;
  navOpen = false;
  stagedImages = [];
  const r = await api('/api/threads/' + encodeURIComponent(id));
  active = r.thread;
  expandedSubjects.add(active.course_id);
  const selected = state.courses.find((c) => c.id === active.course_id);
  if (selected) expandedCategories.add(selected.category || selected.name);
  messages = r.messages;
  if (state.user.role === 'admin' && !studentView)
    adminTutorFilters =
      [...messages].reverse().find((m) => m.role === 'assistant')?.meta?.student_preview === true;
  screen = 'chat';
  render();
  scrollChat();
}
async function newThread(code, title) {
  if (busy) return;
  const c = state.courses.find((c) => c.id === code);
  const r = await api('/api/threads', { course_id: code, title: title || c.assignment });
  state = await api('/api/bootstrap');
  await openThread(r.id);
}
async function openCourse(code) {
  selectSubject(code);
}
function conversationNearBottom() {
  const area = $('#content');
  const tail = [...document.querySelectorAll('.conversation .message,.conversation .loading')].at(
    -1,
  );
  return (
    !area ||
    !tail ||
    tail.getBoundingClientRect().bottom <= area.getBoundingClientRect().bottom + 80
  );
}
function scrollChat(anchor = 'end') {
  const area = $('#content');
  if (!area) return;
  const target =
    anchor === 'latest-user'
      ? [...area.querySelectorAll('.conversation .message.user')].at(-1)
      : [...area.querySelectorAll('.conversation .message,.conversation .loading')].at(-1);
  if (!target) return;
  const rect = target.getBoundingClientRect(),
    box = area.getBoundingClientRect();
  const bottom = rect.bottom - box.top + area.scrollTop + (anchor === 'latest-user' ? 80 : 18);
  const top = rect.top - box.top + area.scrollTop - 16;
  area.scrollTop = Math.max(0, bottom - area.clientHeight);
}
// -----------------------------------------------------------------------------
// Message submission and response lifecycle
// -----------------------------------------------------------------------------
async function send(text, action = 'chat') {
  if (busy || creatingThread || uploadBusy) return;
  if (typeof ensureDraftNoteThread === 'function' && active?.draft) {
    try {
      await ensureDraftNoteThread();
    } catch (err) {
      toast(err.message);
      return;
    }
  }
  if (busy || creatingThread) return;
  if (!active) {
    toast('Choose a subject first.');
    return;
  }
  text = text || $('#message')?.value?.trim();
  if (!text && (stagedImages.length || (pendingImages[active.id] || []).length))
    text = 'Help me understand the attached file.';
  if (!text) return;
  if (active.draft) {
    creatingThread = true;
    const sendButton = $('[aria-label="Send message"]');
    if (sendButton) sendButton.disabled = true;
    try {
      const code = active.course_id;
      const created = await api('/api/threads', { course_id: code, title: text.slice(0, 80) });
      active = { ...active, id: created.id, draft: false, title: text.slice(0, 80) };
      state = await api('/api/bootstrap');
      if (stagedImages.length) {
        const files = stagedImages;
        stagedImages = [];
        await uploadImages(files);
      }
    } catch (err) {
      toast(err.message);
      if (sendButton) sendButton.disabled = false;
      return;
    } finally {
      creatingThread = false;
    }
  }
  const threadId = active.id,
    owner = state.user.id;
  const images = [...(pendingImages[threadId] || [])];
  if (!text && images.length) text = 'Help me understand the attached file.';
  if (!text) return;
  try {
    if (typeof flushNoteSaves === 'function') await flushNoteSaves();
  } catch (err) {
    toast(err.message);
    return;
  }
  if (busy || creatingThread || active?.id !== threadId || state.user?.id !== owner) return;
  const draft = text;
  let submitted = false;
  let receivedReply = false;
  replyStopRequested = false;
  busy = true;
  // Attachments belong to this send, not to the next composer draft.
  pendingImages[threadId] = [];
  const sentMessage = { role: 'user', content: text, meta: { attachments: images } };
  messages.push(sentMessage);
  render();
  scrollChat('latest-user');
  requestAnimationFrame(() => {
    if (busy) scrollChat('latest-user');
  });
  try {
    await api('/api/chat', {
      thread_id: threadId,
      message: text,
      action,
      selected_note_id:
        typeof noteSelection !== 'undefined' ? noteSelection.get(active.id) || null : null,
      student_preview: studentView || adminTutorFilters,
      attachments: images.filter((a) => !a.document).map((a) => a.id),
      file_ids: images.filter((a) => a.document).map((a) => a.id),
    });
    submitted = true;
    const r = await api('/api/threads/' + threadId);
    messages = r.messages;
    if (replyStopRequested && messages.at(-1)?.role === 'assistant') {
      await api('/api/chat/stop', { thread_id: active.id, visible_text: '' });
      messages.at(-1).content = '';
      messages.at(-1).meta = { ...messages.at(-1).meta, stopped: true };
    }
    receivedReply = !replyStopRequested && messages.at(-1)?.role === 'assistant';
    const saved = state.threads.find((t) => t.id === active.id);
    if (saved) saved.updated = Date.now() / 1000;
  } catch (e) {
    if (!submitted && state.user?.id === owner) {
      // Rejected/failed sends keep the draft retryable without duplicating attachments.
      pendingImages[threadId] = [
        ...new Map(
          [...images, ...(pendingImages[threadId] || [])].map((file) => [file.id, file]),
        ).values(),
      ];
      const index = messages.indexOf(sentMessage);
      if (index >= 0) messages.splice(index, 1);
    }
    toast(e.message);
  } finally {
    const previous = $('#content');
    const top = previous?.scrollTop || 0;
    const follow = conversationNearBottom();
    busy = false;
    render();
    if ($('#content')) $('#content').scrollTop = top;
    if (receivedReply) animateLatestReply(follow);
    else if (follow) scrollChat();
    if ($('#message')) {
      $('#message').focus({ preventScroll: true });
      if (!submitted) $('#message').value = draft;
      resizeComposerInput();
    }
  }
}
// -----------------------------------------------------------------------------
// Sources, settings and staff views
// -----------------------------------------------------------------------------
function sources(sourceId) {
  const cs = course() ? [course()] : state.courses;
  modal(
    'Approved course library',
    `<p>These are the actual excerpts configured for this workspace. Starter notes are demonstrations, not institution-approved lectures or scholarly research.</p>${cs.flatMap((c) => c.sources.filter((s) => !sourceId || s.id === sourceId).map((s) => `<section class="source-block"><span class="eyebrow">${esc(c.id)}</span><h3>${esc(s.title)}</h3><small>${esc(s.locator)}</small><p>${esc(s.text).replace(/\n/g, '<br>')}</p></section>`)).join('')}`,
  );
}
async function settingsModal() {
  modal(
    'Settings',
    `<div class="source-block"><h3>Appearance</h3><p>Choose a theme. Your conversations and layout stay the same.</p><div class="theme-picker" role="group" aria-label="Theme">${Object.entries(
      themes,
    )
      .map(
        ([key, name]) =>
          `<button type="button" class="theme-option" data-theme-choice="${key}" aria-pressed="${theme === key}"><span class="theme-swatch swatch-${key}" aria-hidden="true"><span></span><span></span><span></span></span><b>${name}</b><small>${key === 'studio' ? 'Charcoal · sage green · editorial type' : key === 'navy' ? 'Dark surfaces · blue accents' : 'Soft cream · green accents'}</small></button>`,
      )
      .join(
        '',
      )}</div><p id="appearance-status" class="muted" role="status">${themes[theme]} selected · saved on this browser.</p></div><div class="source-block"><h3>Privacy & saved records</h3><p>Your messages are stored on this PC. Authorised staff can review records and staff access is logged. ${state.retention_days ? 'Records expire after ' + state.retention_days + ' days.' : 'Automatic expiry is off. Chats and uploaded images remain stored on this PC.'} Research sends a short topic query to Wikipedia and, for article searches, Crossref. The language model runs locally; those services receive the search query. Do not enter sensitive personal information.</p></div><div class="source-block"><h3>Local model connection</h3><p id="model-status">Checking the local backend…</p></div><div class="notice">Under development. Individual logins and course permissions are managed through the admin menu.</div>`,
  );
  try {
    const s = await api('/api/status');
    if ($('#model-status'))
      $('#model-status').textContent =
        `Configured model: ${s.model}. ${s.backend_reachable_and_loaded ? 'LM Studio reports a loaded language model.' : 'A matching loaded model has not been confirmed. Strict mode still offers a reflection prompt when the backend is unavailable.'}`;
  } catch (e) {
    if ($('#model-status')) $('#model-status').textContent = e.message;
  }
}
async function loadStaff() {
  try {
    const p =
      state.user.role === 'admin' || state.user.permissions?.review_records
        ? await api('/api/staff/records')
        : { threads: [] };
    if (!$('#staff-body')) return;
    $('#staff-body').innerHTML =
      `<span class="eyebrow">Institution workspace</span><h1>Support the learning.<br>Keep the boundaries clear.</h1><p class="muted">Review saved assignment records and approve the guidance available in each course.</p><div class="staff-controls">${state.user.role === 'admin' || state.user.permissions?.manage_courses ? '<button class="primary" data-action="edit-courses">Edit course rules & hints</button>' : ''}<button class="secondary" data-action="refresh-records">Refresh records</button></div><div class="notice">Approved-hints mode displays only the teaching material below. Conversational mode generates answers using the class policy. Review teaching material for accuracy and suitability before use. Any source or hint you publish is visible to students.</div><div class="section-label"><h3>Assignment records</h3><small>${p.threads.length} recent records</small></div>${p.threads.length ? p.threads.map((t) => `<button class="record" data-record="${esc(t.id)}"><b>${esc(t.title)}</b><small>${esc(t.student)} · ${esc(t.course_id)} · ${new Date(t.created * 1000).toLocaleString()}</small></button>`).join('') : '<div class="empty">No assignment records yet.</div>'}`;
  } catch (e) {
    toast(e.message);
  }
}
async function editCourses() {
  const p = await api('/api/staff/courses');
  modal(
    'Course rules & approved hints',
    `<p>Changes take effect on the next message. Editing prompts and model settings is also available directly in the project’s <code>config/</code> folder.</p><div class="notice">Only publish content suitable for students. Strict mode displays exact hint text. Experimental mode requires <code>allow_experimental: true</code> in settings.json and <code>mode: experimental</code> for the course. It does not guarantee answer blocking or accuracy.</div><label class="eyebrow" for="course-editor">Course configuration · JSON</label><textarea id="course-editor" spellcheck="false">${esc(JSON.stringify(p.courses, null, 2))}</textarea><div class="chips"><button id="save-courses">Approve & save configuration</button></div><p id="save-status" class="error" role="status"></p>`,
  );
  $('#save-courses').addEventListener('click', async () => {
    try {
      const c = JSON.parse($('#course-editor').value);
      await api('/api/staff/courses', { courses: c });
      state = await api('/api/bootstrap');
      $('#modal').close();
      render();
      toast('Course configuration approved and saved.');
    } catch (e) {
      $('#save-status').textContent = e.message;
    }
  });
}
async function uploadImages(files) {
  if (!active || busy || uploadBusy) return;
  if (active.draft) {
    if (files.length + stagedImages.length > 3) {
      toast('Attach up to three images.');
      return;
    }
    if (
      files.some(
        (f) =>
          !['image/jpeg', 'image/png', 'image/webp'].includes(f.type) || f.size > 6 * 1024 * 1024,
      )
    ) {
      toast('Choose JPEG, PNG or WebP images under 6 MB each.');
      return;
    }
    const draft = $('#message')?.value || '';
    stagedImages.push(...files);
    render();
    if ($('#message')) $('#message').value = draft;
    return;
  }
  const tid = active.id;
  const draft = $('#message')?.value || '';
  if (files.length + (pendingImages[tid]?.length || 0) > 3) {
    toast('Attach up to three images per message.');
    return;
  }
  uploadBusy = true;
  try {
    for (const file of files) {
      if (
        !['image/jpeg', 'image/png', 'image/webp'].includes(file.type) ||
        file.size > 6 * 1024 * 1024
      )
        throw Error('Choose JPEG, PNG or WebP images under 6 MB each.');
      const encoded = await new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(reader.result.split(',')[1]);
        reader.onerror = reject;
        reader.readAsDataURL(file);
      });
      const image = await api('/api/attachments', {
        thread_id: tid,
        name: file.name,
        data: encoded,
      });
      (pendingImages[tid] ||= []).push(image);
    }
    toast('Image attached. Send your question when ready.');
  } catch (e) {
    toast(e.message);
  } finally {
    uploadBusy = false;
    render();
    if ($('#message')) $('#message').value = draft;
  }
}
function threadTitleButton() {
  if (active?.draft) return 'New conversation';
  return `<button class="thread-title-button" data-action="rename" aria-label="Rename thread" title="Click to rename this thread">${esc(active.title)}<span aria-hidden="true">✎</span></button>`;
}
// -----------------------------------------------------------------------------
// Conversation titles and thread creation
// -----------------------------------------------------------------------------
function beginRename() {
  if (!active || active.draft || $('#thread-rename-form')) return;
  const tid = active.id;
  const heading = $('.topbar h2');
  heading.innerHTML = `<form id="thread-rename-form" class="thread-rename-form"><input id="thread-title-input" aria-label="Thread name" maxlength="120" required value="${esc(active.title)}"><button type="submit" class="icon" aria-label="Save thread name">✓</button><button type="button" class="icon" id="cancel-thread-rename" aria-label="Cancel rename">✕</button></form>`;
  const input = $('#thread-title-input');
  input.focus();
  input.select();
  const cancel = () => {
    if (active?.id === tid) heading.innerHTML = threadTitleButton();
  };
  $('#cancel-thread-rename').addEventListener('click', cancel);
  input.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      e.preventDefault();
      cancel();
    }
  });
  $('#thread-rename-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const title = input.value.trim();
    if (!title) {
      input.setCustomValidity('Enter a thread name.');
      input.reportValidity();
      input.addEventListener('input', () => input.setCustomValidity(''), { once: true });
      return;
    }
    const save = e.target.querySelector('[type="submit"]');
    save.disabled = true;
    try {
      const result = await api('/api/threads/' + tid + '/rename', { title });
      const stored = state.threads.find((t) => t.id === tid);
      if (stored) stored.title = result.title;
      if (active?.id === tid) {
        active.title = result.title;
        heading.innerHTML = threadTitleButton();
      }
      document.querySelectorAll('[data-thread]').forEach((el) => {
        if (el.dataset.thread === tid) {
          if (el.classList.contains('thread-nav')) el.textContent = result.title;
          else if (el.querySelector('b')) el.querySelector('b').textContent = result.title;
        }
      });
      toast('Thread renamed.');
    } catch (err) {
      toast(err.message);
      save.disabled = false;
    }
  });
}
function newThreadDialog(code) {
  modal(
    'New conversation',
    `<form id="new-form" class="account-form"><label>Subject<select id="new-course">${state.courses.map((c) => `<option value="${esc(c.id)}" ${c.id === code ? 'selected' : ''}>${esc(c.category || c.name)} · ${c.year_level ? 'Year ' + c.year_level + ' · ' : ''}${esc(c.id)}</option>`).join('')}</select></label><p class="muted">Your first message creates the thread.</p><button class="primary">Open conversation</button></form>`,
  );
  $('#new-form').onsubmit = (e) => {
    e.preventDefault();
    const selected = $('#new-course').value;
    $('#modal').close();
    selectSubject(selected);
  };
}

let adminData = null;
async function loadAdmin() {
  try {
    adminData = await api('/api/admin/users');
    if (!$('#admin-body')) return;
    $('#admin-body').innerHTML =
      `<span class="eyebrow">Under development · Administration</span><div class="admin-heading"><div><h1>People & permissions.</h1><p class="muted">Manage individual logins, course access and staff responsibilities.</p></div><button class="primary" data-action="create-account">＋ Create account</button></div><div class="account-list">${adminData.users.map((u) => `<button class="account-row" data-user-id="${u.id}"><span class="avatar">${esc(u.name.slice(0, 2).toUpperCase())}</span><span class="account-name"><b>${esc(u.name)}</b><small>@${esc(u.username)}</small></span><span class="badge">${esc(u.role)}</span><span class="account-state ${u.enabled ? '' : 'disabled'}">${u.enabled ? 'Active' : 'Disabled'}</span><span>Manage ↗</span></button>`).join('')}</div><p class="muted">Passwords are stored as salted hashes and cannot be viewed. Set a new password to reset access. Disabling an account, resetting its password or changing permissions signs that user out.</p>`;
  } catch (e) {
    toast(e.message);
  }
}
async function accountForm(id) {
  if (!adminData) adminData = await api('/api/admin/users');
  const u = adminData.users.find((u) => u.id === id);
  const perms = u?.permissions || {
    courses: ['GENERAL'],
    review_records: false,
    manage_courses: false,
  };
  modal(
    u ? 'Manage ' + u.name : 'Create an account',
    `<form id="account-form" class="account-form"><div class="form-grid"><label>Display name<input id="account-name" required maxlength="120" value="${esc(u?.name || '')}" autocomplete="off"></label><label>Username<input id="account-username" required maxlength="64" pattern="[a-zA-Z0-9_.-]+" value="${esc(u?.username || '')}" autocomplete="off"></label><label>Role<select id="account-role">${['student', 'teacher', 'admin'].map((r) => `<option value="${r}" ${u?.role === r ? 'selected' : ''}>${r === 'admin' ? 'Administrator' : r === 'teacher' ? 'Teacher' : 'Student'}</option>`).join('')}</select></label><label>${u ? 'Reset password' : 'Initial password'}<input id="account-password" type="password" maxlength="256" ${u ? '' : 'required'} autocomplete="new-password" placeholder="${u ? 'Leave blank to keep current password' : 'Set a password'}"></label></div><label class="check-row"><input type="checkbox" id="account-enabled" ${!u || u.enabled ? 'checked' : ''}> Account enabled</label><fieldset><legend>Course access</legend><div class="course-checks">${adminData.courses.map((c) => `<label class="check-row"><input type="checkbox" name="account-course" value="${esc(c.id)}" ${perms.courses.includes(c.id) ? 'checked' : ''}>${esc(c.id)} · ${esc(c.name)}</label>`).join('')}</div></fieldset><fieldset><legend>Student tools</legend><label class="check-row"><input type="checkbox" id="account-images" ${perms.upload_images !== false ? 'checked' : ''}> Upload photos and paper images</label><label class="check-row"><input type="checkbox" id="account-research" ${perms.web_research !== false ? 'checked' : ''}> Research public sources online</label></fieldset><fieldset><legend>Staff permissions</legend><label class="check-row"><input type="checkbox" id="account-review" ${perms.review_records ? 'checked' : ''}> Review records for assigned courses</label><label class="check-row"><input type="checkbox" id="account-edit" ${perms.manage_courses ? 'checked' : ''}> Edit rules, sources and hints for assigned courses</label><small>Student accounts have no staff permissions. Administrators have full access.</small></fieldset><p id="account-error" class="error" role="alert"></p><div class="staff-controls"><button class="primary" type="submit">${u ? 'Save changes' : 'Create account'}</button>${u ? `<button class="secondary" type="button" data-account-history="${u.id}">View account history</button>` : ''}${u ? '<button class="secondary" type="button" id="revoke-sessions">Sign out all sessions</button>' : ''}</div></form>`,
  );
  const accountForm = $('#account-form');
  const policySection = document.createElement('fieldset');
  policySection.dataset.editorSection = 'policies';
  policySection.innerHTML =
    '<legend>Individual tutoring policies</legend><p class="muted">Override inherited class settings for this person. Upload and research permissions in Tools remain upper limits. Student answer restrictions and response review remain enforced.</p><div id="account-policy-fields"></div>';
  accountForm.insertBefore(policySection, $('#account-error'));
  const showAccountPolicies = () => {
    const current = policySection.querySelector('select')
      ? readPolicy(accountForm, 'account-policy')
      : perms.tutoring_policy || {};
    const role = $('#account-role').value;
    $('#account-policy-fields').innerHTML = policyFields(
      current,
      'account-policy',
      role === 'student',
    );
    policySection.disabled = role === 'admin';
  };
  showAccountPolicies();
  $('#account-role').addEventListener('change', showAccountPolicies);
  accountForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const role = $('#account-role').value;
    const payload = {
      action: u ? 'update' : 'create',
      id: u?.id,
      name: $('#account-name').value,
      username: $('#account-username').value,
      role,
      enabled: $('#account-enabled').checked,
      password: $('#account-password').value,
      permissions: {
        ...perms,
        tutoring_policy: readPolicy(accountForm, 'account-policy'),
        web_research: $('#account-research').checked,
        upload_images: $('#account-images').checked,
        courses: Array.from(document.querySelectorAll('[name="account-course"]:checked')).map(
          (el) => el.value,
        ),
        review_records: role !== 'student' && $('#account-review').checked,
        manage_courses: role !== 'student' && $('#account-edit').checked,
      },
    };
    const submit = e.target.querySelector('[type="submit"]');
    submit.disabled = true;
    try {
      await api('/api/admin/users', payload);
      await bootstrap();
      await loadAdmin();
      $('#modal').close();
      toast(u ? 'Account updated.' : 'Account created.');
    } catch (err) {
      if ($('#account-error')) $('#account-error').textContent = err.message;
    } finally {
      submit.disabled = false;
    }
  });
  if ($('#revoke-sessions'))
    $('#revoke-sessions').addEventListener('click', async () => {
      try {
        await api('/api/admin/users', { action: 'revoke_sessions', id: u.id });
        $('#modal').close();
        if (u.id === state.user.id) {
          login();
        } else toast('All sessions signed out.');
      } catch (e) {
        $('#account-error').textContent = e.message;
      }
    });
}
document.addEventListener('click', async (e) => {
  const b = e.target.closest('button');
  if (!b) return;
  try {
    if (b.dataset.stagedImage !== undefined) {
      stagedImages.splice(Number(b.dataset.stagedImage), 1);
      const draft = $('#message')?.value || '';
      render();
      if ($('#message')) $('#message').value = draft;
      return;
    }
    if (b.dataset.category) {
      const key = b.dataset.category;
      if (expandedCategories.has(key)) expandedCategories.delete(key);
      else expandedCategories.add(key);
      const draft = $('#message')?.value || '';
      render();
      if ($('#message')) $('#message').value = draft;
      return;
    }
    if (b.dataset.selectCourse) {
      selectSubject(b.dataset.selectCourse);
      return;
    }
    if (typeof adminAction === 'function' && (await adminAction(b))) return;
    if (b.dataset.themeChoice) {
      applyTheme(b.dataset.themeChoice);
      return;
    }
    if (b.dataset.toggleCourse) {
      const id = b.dataset.toggleCourse;
      const open = !expandedSubjects.has(id);
      if (open) expandedSubjects.add(id);
      else expandedSubjects.delete(id);
      b.setAttribute('aria-expanded', String(open));
      b.textContent = open ? '⌄' : '›';
      document.getElementById('threads-' + id).hidden = !open;
      return;
    }
    if (b.dataset.removeImage) {
      pendingImages[active.id] = (pendingImages[active.id] || []).filter(
        (a) => a.id !== b.dataset.removeImage,
      );
      const draft = $('#message')?.value;
      render();
      if ($('#message')) $('#message').value = draft || '';
      return;
    }
    if (b.dataset.userId) return await accountForm(Number(b.dataset.userId));
    if (b.dataset.thread) return await openThread(b.dataset.thread);
    if (b.dataset.course) return await openCourse(b.dataset.course);
    if (b.dataset.starter) return await send(b.dataset.starter);
    if (b.dataset.source) return sources(b.dataset.source);
    if (b.dataset.record) {
      const p = await api('/api/staff/record/' + b.dataset.record);
      modal(
        p.thread.title,
        `<p class="muted">${esc(p.thread.student)} · ${esc(p.thread.course_id)} · Staff review access logged</p>${p.messages.map(messageHTML).join('')}`,
      );
      return;
    }
    switch (b.dataset.action) {
      case 'profile': {
        const popup = $('#profile-popup');
        popup.hidden = !popup.hidden;
        b.setAttribute('aria-expanded', String(!popup.hidden));
        break;
      }
      case 'student-view':
        if (busy) break;
        studentView = !studentView;
        active = null;
        screen = 'home';
        render();
        break;
      case 'account-settings':
        accountSettings();
        break;
      case 'home':
        if (busy) break;
        navOpen = false;
        active = null;
        screen = 'home';
        render();
        break;
      case 'theme': {
        const options = Object.keys(themes);
        applyTheme(options[(options.indexOf(theme) + 1) % options.length]);
        break;
      }
      case 'menu':
        setMenu(!navOpen);
        break;
      case 'close-menu':
        setMenu(false);
        break;
      case 'new':
        if (busy) break;
        if (state.user.role === 'admin' && !studentView) {
          selectSubject('GENERAL');
          break;
        }
        if (active) selectSubject(active.course_id);
        else newThreadDialog();
        break;
      case 'rename':
        beginRename();
        break;
      case 'attach':
        if (!active) toast('Open or create a thread first.');
        else if (!busy && !uploadBusy) $('#image-upload').click();
        break;
      case 'sources':
        sources();
        break;
      case 'research':
        await send(undefined, 'research');
        break;
      case 'layout':
        await send('Help me plan a blank structure.', 'layout');
        break;
      case 'locked':
        modal(
          'This tool is locked',
          `<p>Code and image generation are not enabled for this course. The model has no code execution, shell, email or image tools.</p><p>Future course-specific generation permissions must be granted by staff and kept in the same reviewable assignment record.</p>`,
        );
        break;
      case 'rules':
        modal(
          'The rules for this workspace',
          `<p>${esc(course()?.rules || 'Learning support only. Select a subject to see its course-specific rules.')}</p><div class="notice">${course()?.policy?.approved_only ? 'This class uses approved hints and fixed planning prompts.' : 'The assistant answers questions and explains concepts using your conversation. Generated information can be wrong. Explicit research can retrieve sources; references default to APA 7.'}</div><p>Saved records can be reviewed by authorised staff. This software cannot enforce an institution’s policy on external AI services or determine grades.</p>`,
        );
        break;
      case 'settings':
        await settingsModal();
        break;
      case 'logout':
        if (busy) break;
        await api('/api/logout', {});
        active = null;
        messages = [];
        login();
        break;
      case 'admin':
        if (busy) break;
        navOpen = false;
        screen = 'admin';
        active = null;
        render();
        break;
      case 'staff':
        if (busy) break;
        navOpen = false;
        screen = 'staff';
        active = null;
        render();
        break;
      case 'create-account':
        await accountForm();
        break;
      case 'edit-courses':
        await editCourses();
        break;
      case 'refresh-records':
        await loadStaff();
        break;
    }
  } catch (e) {
    toast(e.message);
  }
});
bootstrap();

// -----------------------------------------------------------------------------
// Profile menu and account settings
// -----------------------------------------------------------------------------
function closeProfile() {
  const p = $('#profile-popup');
  if (p) p.hidden = true;
  const b = $('[data-action="profile"]');
  if (b) b.setAttribute('aria-expanded', 'false');
}
document.addEventListener('click', (e) => {
  if (!e.target.closest('.profile-area')) closeProfile();
});
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') closeProfile();
});
function accountSettings() {
  closeProfile();
  modal(
    'Account settings',
    `<form id="self-account" class="account-form"><p class="muted">@${esc(state.user.username)} · ${esc(state.user.role)}</p><label>Display name<input name="name" required maxlength="120" value="${esc(state.user.name)}"></label><label>Current password<input name="current_password" type="password" autocomplete="current-password"></label><label>New password<input name="password" type="password" maxlength="256" autocomplete="new-password" placeholder="Leave blank to keep current password"></label><p class="muted">Use at least 12 characters for public sign-in. Changing your password signs out all your sessions.</p><p class="error" id="self-error"></p><button class="primary">Save account</button></form>`,
  );
  $('#self-account').onsubmit = async (e) => {
    e.preventDefault();
    try {
      const value = await api('/api/account', Object.fromEntries(new FormData(e.target)));
      $('#modal').close();
      if (value.sign_in_again) login();
      else await bootstrap();
    } catch (err) {
      $('#self-error').textContent = err.message;
    }
  };
}

document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape' && navOpen) setMenu(false);
});
window.matchMedia('(max-width:750px)').addEventListener('change', (e) => {
  if (!e.matches) setMenu(false);
});

function policyBannerHTML(c) {
  if (state.demo)
    return '<div class="policy"><span>Demo workspace · synthetic data and sample replies · host terminal disabled</span></div>';
  if (!state.user) return '';
  try {
    if (localStorage.getItem('school-notice-dismissed-' + state.user.id) === '1') return '';
  } catch (e) {}
  const notice =
    state.user.role === 'admin' && !studentView
      ? 'Administrator assistant · unrestricted personal conversations.'
      : !studentView && c?.policy && !c.policy.block_answers
        ? 'Administrator-configured tutoring · completed answers permitted.'
        : c?.mode === 'experimental'
          ? 'Experimental tutoring: may make mistakes or reveal answers.'
          : 'Learning support: concepts and hints, without final answers or answer confirmation.';
  return `<div class="policy"><span>${esc(notice)}</span><button data-action="rules">Course rules ↗</button><button type="button" class="policy-dismiss" data-dismiss-policy="1" aria-label="Dismiss notice permanently">×</button></div>`;
}
document.addEventListener('click', (e) => {
  if (!e.target.closest('[data-dismiss-policy]')) return;
  try {
    localStorage.setItem('school-notice-dismissed-' + state.user.id, '1');
  } catch (err) {}
  document.querySelector('.policy')?.remove();
});

function recentChatsHidden() {
  try {
    return localStorage.getItem('school-recent-hidden-' + state.user.id) === 'true';
  } catch (e) {
    return false;
  }
}
