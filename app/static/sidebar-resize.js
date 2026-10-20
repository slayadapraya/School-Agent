'use strict';

/** Desktop navigation: compact icon rail and adjustable expanded width.
 * Remember both choices per account; never rebuild the chat while changing them.
 */
(() => {
  const desktop = matchMedia('(min-width: 751px)');
  let frame = 0;
  let expandedWidth = 270;
  let collapseTimer;
  const storageKey = () => 'school-sidebar-width:' + state.user?.id;
  const compactKey = () => 'school-sidebar-compact:' + state.user?.id;
  const icon = (path) =>
    `<svg class="sidebar-icon" viewBox="0 0 24 24" aria-hidden="true">${path}</svg>`;
  const icons = {
    toggle: icon(
      '<rect x="3" y="4" width="18" height="16" rx="3"/><path d="M9 4v16m6-12-3 4 3 4"/>',
    ),
    chats: icon(
      '<path d="M5 4h14a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H9l-6 3V6a2 2 0 0 1 2-2Z"/><path d="M7 9h10M7 13h7"/>',
    ),
    plus: icon('<path d="M12 5v14M5 12h14"/>'),
    settings: icon(
      '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33 1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09A1.65 1.65 0 0 0 15 4.6a1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82 1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09A1.65 1.65 0 0 0 19.4 15Z"/>',
    ),
  };
  // Reuse the real navigation buttons so their actions and permissions stay the
  // same. Compact mode puts the lower shortcuts in the account pop-out.
  function placeShortcuts(sidebar, compact) {
    const popup = sidebar.querySelector('#profile-popup');
    const profileArea = sidebar.querySelector('.profile-area');
    const shortcuts = popup.querySelector('.profile-shortcuts');
    const footer = popup.querySelector('.profile-footer');
    for (const button of sidebar.querySelectorAll('[data-sidebar-shortcut]')) {
      if (compact && desktop.matches) {
        if (button.dataset.action === 'settings') footer.prepend(button);
        else shortcuts.append(button);
        button.setAttribute('role', 'menuitem');
      } else {
        profileArea.before(button);
        button.removeAttribute('role');
      }
    }
  }
  function syncActive() {
    const sidebar = document.querySelector('.sidebar');
    if (!sidebar) return;
    const settingsOpen =
      document.getElementById('modal')?.open &&
      document.querySelector('#modal-content h2')?.textContent === 'Settings';
    const profileOpen =
      sidebar.querySelector('.profile-trigger')?.getAttribute('aria-expanded') === 'true';
    const drafting = screen === 'chat' && active && messages.length === 0;
    const selected = profileOpen
      ? '.profile-trigger'
      : settingsOpen
        ? '[data-action="settings"]'
        : drafting
          ? '.new-thread'
          : ['home', 'chat'].includes(screen)
            ? '.recent-home'
            : null;
    for (const button of sidebar.querySelectorAll(
      '.recent-home,.new-thread,[data-action="settings"],.profile-trigger',
    )) {
      const current = selected !== null && button.matches(selected);
      button.classList.toggle('rail-active', current);
      if (current) button.setAttribute('aria-current', 'page');
      else button.removeAttribute('aria-current');
    }
  }
  function setCompact(sidebar, compact, save = false) {
    sidebar.closest('.shell').classList.toggle('navigation-compact', compact);
    const toggle = sidebar.querySelector('.sidebar-collapse');
    toggle.setAttribute('aria-expanded', String(!compact));
    toggle.setAttribute('aria-label', compact ? 'Expand sidebar' : 'Collapse sidebar');
    if (!toggle.dataset.hoverHelp) toggle.title = compact ? 'Expand sidebar' : 'Collapse sidebar';
    sidebar.querySelector('.sidebar-resize')?.setAttribute('tabindex', compact ? '-1' : '0');
    placeShortcuts(sidebar, compact);
    closeProfile();
    syncActive();
    if (save) {
      try {
        localStorage.setItem(compactKey(), String(compact));
      } catch (_) {
        /* Navigation works when storage is blocked. */
      }
    }
  }
  function mountCompact(sidebar) {
    if (sidebar.querySelector('.sidebar-collapse')) return;
    const brand = sidebar.querySelector('.brand');
    const heading = document.createElement('div');
    heading.className = 'sidebar-heading';
    brand.before(heading);
    heading.append(brand);
    const toggle = document.createElement('button');
    toggle.type = 'button';
    toggle.className = 'sidebar-collapse';
    toggle.setAttribute('aria-controls', 'site-navigation');
    toggle.innerHTML = icons.toggle;
    heading.append(toggle);
    for (const [selector, image, label] of [
      ['.new-thread', icons.plus, 'New thread'],
      ['.recent-home', icons.chats, 'Chats'],
      ['[data-action="settings"]', icons.settings, 'Settings'],
    ]) {
      const button = sidebar.querySelector(selector);
      button.innerHTML = `${image}<span class="sidebar-button-label">${label}</span>`;
      button.setAttribute('aria-label', label);
      button.title = label;
    }
    sidebar.querySelector('.recent-home').dataset.action = 'chats';
    const profile = sidebar.querySelector('.profile-trigger');
    profile.setAttribute('aria-label', 'Profile');
    profile.title = state.user.name;
    for (const button of sidebar.querySelectorAll('.side-bottom > button')) {
      button.dataset.sidebarShortcut = '1';
      button.addEventListener('click', closeProfile);
    }
    let compact = false;
    try {
      compact = localStorage.getItem(compactKey()) === 'true';
    } catch (_) {
      /* Default expanded. */
    }
    setCompact(sidebar, compact);
    toggle.onclick = () => {
      const shell = sidebar.closest('.shell');
      clearTimeout(collapseTimer);
      const opening = shell.classList.contains('navigation-compact');
      shell.classList.toggle('navigation-opening', opening);
      shell.classList.toggle('navigation-closing', !opening);
      shell.classList.add('navigation-animating');
      setCompact(sidebar, !opening, true);
      collapseTimer = setTimeout(
        () => {
          shell.classList.remove(
            'navigation-animating',
            'navigation-opening',
            'navigation-closing',
          );
        },
        matchMedia('(prefers-reduced-motion: reduce)').matches ? 0 : opening ? 200 : 220,
      );
    };
  }
  const limit = (width) => Math.round(Math.max(220, Math.min(440, innerWidth * 0.4, width)));
  function apply(width, save = false) {
    width = limit(width);
    expandedWidth = width;
    document.documentElement.style.setProperty('--navigation-width', width + 'px');
    const grip = document.querySelector('.sidebar-resize');
    grip?.setAttribute('aria-valuenow', String(width));
    if (save) {
      try {
        localStorage.setItem(storageKey(), String(width));
      } catch (_) {
        /* Storage may be blocked. */
      }
      window.dispatchEvent(new Event('resize'));
    }
  }
  function mount() {
    const sidebar = document.querySelector('.sidebar');
    if (!sidebar || sidebar.querySelector('.sidebar-resize')) return;
    if (screen === 'chat' && active && state.threads.some((t) => t.id === active.id)) {
      try {
        localStorage.setItem('school-last-chat:' + state.user.id, active.id);
      } catch (_) {}
    }
    mountCompact(sidebar);
    let stored;
    try {
      stored = Number(localStorage.getItem(storageKey()));
    } catch (_) {
      /* Use default. */
    }
    apply(stored || 270);
    const grip = document.createElement('div');
    grip.className = 'sidebar-resize';
    grip.tabIndex = 0;
    grip.setAttribute('role', 'separator');
    grip.setAttribute('aria-label', 'Resize navigation');
    grip.setAttribute('aria-orientation', 'vertical');
    grip.setAttribute('aria-valuemin', '220');
    grip.setAttribute('aria-valuemax', '440');
    grip.setAttribute('aria-valuenow', String(limit(stored || 270)));
    sidebar.append(grip);
    if (sidebar.closest('.shell').classList.contains('navigation-compact')) grip.tabIndex = -1;
    grip.addEventListener('pointerdown', (event) => {
      if (
        !desktop.matches ||
        sidebar.closest('.shell').classList.contains('navigation-compact') ||
        event.button !== 0
      )
        return;
      event.preventDefault();
      grip.setPointerCapture(event.pointerId);
      document.body.classList.add('resizing-navigation');
      const origin = event.clientX,
        width = sidebar.getBoundingClientRect().width;
      const move = (next) => {
        cancelAnimationFrame(frame);
        frame = requestAnimationFrame(() => apply(width + next.clientX - origin));
      };
      const finish = () => {
        cancelAnimationFrame(frame);
        document.body.classList.remove('resizing-navigation');
        apply(sidebar.getBoundingClientRect().width, true);
        grip.removeEventListener('pointermove', move);
        grip.removeEventListener('pointerup', finish);
        grip.removeEventListener('pointercancel', finish);
      };
      grip.addEventListener('pointermove', move);
      grip.addEventListener('pointerup', finish);
      grip.addEventListener('pointercancel', finish);
    });
    grip.addEventListener('keydown', (event) => {
      if (!['ArrowLeft', 'ArrowRight', 'Home'].includes(event.key)) return;
      event.preventDefault();
      apply(
        event.key === 'Home'
          ? 270
          : sidebar.getBoundingClientRect().width + (event.key === 'ArrowRight' ? 10 : -10),
        true,
      );
    });
    grip.addEventListener('dblclick', () => apply(270, true));
  }
  const previous = render;
  render = function () {
    const result = previous();
    mount();
    return result;
  };
  window.addEventListener('resize', () => {
    const sidebar = document.querySelector('.sidebar');
    if (sidebar)
      placeShortcuts(sidebar, sidebar.closest('.shell').classList.contains('navigation-compact'));
    if (desktop.matches && document.querySelector('.sidebar')) apply(expandedWidth);
  });
  // Run after the existing navigation/profile handlers without rebuilding DOM.
  document.addEventListener('click', () => queueMicrotask(syncActive));
  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') queueMicrotask(syncActive);
  });
  document.getElementById('modal')?.addEventListener('close', syncActive);
  mount();
})();
