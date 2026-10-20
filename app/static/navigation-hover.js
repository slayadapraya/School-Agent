'use strict';

/** Delayed help for compact navigation. The Chats fly-out lists only the
 * signed-in account's bootstrap threads and uses the normal thread action.
 */
(() => {
  let panel, trigger, openTimer, closeTimer;
  function dismiss() {
    clearTimeout(openTimer);
    clearTimeout(closeTimer);
    trigger?.removeAttribute('aria-describedby');
    panel?.remove();
    panel = trigger = null;
  }
  function scheduleClose() {
    clearTimeout(openTimer);
    clearTimeout(closeTimer);
    closeTimer = setTimeout(dismiss, 180);
  }
  function open(button, chats) {
    dismiss();
    if (
      !button.isConnected ||
      !button.closest('.navigation-compact') ||
      !matchMedia('(min-width: 751px)').matches
    )
      return;
    trigger = button;
    panel = document.createElement('section');
    panel.id = 'navigation-hover-help';
    panel.className = chats
      ? 'navigation-hover-card navigation-chat-flyout'
      : 'navigation-hover-card navigation-tooltip';
    panel.setAttribute('role', chats ? 'region' : 'tooltip');
    if (chats) {
      panel.setAttribute('aria-label', 'Recent conversations');
      panel.innerHTML = `<header><strong>Chats</strong><button type="button" data-action="new" aria-label="New thread">＋</button></header><div class="navigation-flyout-threads">${
        recentThreads()
          .slice(0, 20)
          .map(
            (t) =>
              `<button type="button" data-thread="${esc(t.id)}" class="${active?.id === t.id ? 'selected' : ''}"><span>${esc(t.title)}</span><small>${esc(t.course_id)}</small></button>`,
          )
          .join('') || '<p>No conversations yet.</p>'
      }</div><button type="button" data-action="home" class="navigation-all-chats">View all chats</button>`;
      panel.addEventListener('pointerenter', () => clearTimeout(closeTimer));
      panel.addEventListener('pointerleave', scheduleClose);
      panel.addEventListener('focusin', () => clearTimeout(closeTimer));
      panel.addEventListener('focusout', (event) => {
        if (!panel?.contains(event.relatedTarget)) scheduleClose();
      });
    } else {
      panel.textContent = button.getAttribute('aria-label') || button.textContent.trim();
      button.setAttribute('aria-describedby', panel.id);
    }
    document.body.append(panel);
    const box = button.getBoundingClientRect();
    const rail = button.closest('.sidebar').getBoundingClientRect();
    panel.style.left = `${rail.right + 8}px`;
    panel.style.top = `${Math.max(8, Math.min(box.top, innerHeight - panel.offsetHeight - 8))}px`;
  }
  function mount() {
    dismiss();
    for (const button of document.querySelectorAll(
      '.sidebar .brand,.sidebar-collapse,.sidebar .new-thread,.sidebar .recent-home,.sidebar .profile-trigger',
    )) {
      if (button.dataset.hoverHelp) continue;
      button.dataset.hoverHelp = '1';
      button.removeAttribute('title');
      const schedule = () => {
        dismiss();
        if (!button.closest('.navigation-compact')) return;
        const chats = button.classList.contains('recent-home');
        openTimer = setTimeout(() => open(button, chats), chats ? 150 : 200);
      };
      button.addEventListener('pointerenter', schedule);
      button.addEventListener('pointerleave', scheduleClose);
      button.addEventListener('focus', schedule);
      button.addEventListener('blur', (event) => {
        if (!panel?.contains(event.relatedTarget)) scheduleClose();
      });
    }
  }
  const before = render;
  render = function () {
    const result = before();
    mount();
    return result;
  };
  document.addEventListener('click', dismiss);
  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') dismiss();
  });
  window.addEventListener('resize', dismiss);
  mount();
})();
