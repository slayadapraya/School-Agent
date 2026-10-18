'use strict';

/** Shared stacking for the admin panel, terminal and floating notes.
 * Update z-index in place: moving nodes would reset terminal/editor focus.
 * Native modal dialogs stay in the browser's top layer above these windows.
 */
function focusFloatingWindow(windowEl) {
  if (!windowEl?.isConnected) return;
  const windows = [...document.querySelectorAll('.terminal-window,.note-window')];
  const others = windows
    .filter((el) => el !== windowEl)
    .sort((a, b) => Number(getComputedStyle(a).zIndex) - Number(getComputedStyle(b).zIndex));
  [...others, windowEl].forEach((el, index) => {
    el.style.zIndex = String(500 + index);
    el.classList.toggle('is-focused-window', el === windowEl);
  });
}
for (const eventName of ['pointerdown', 'focusin']) {
  document.addEventListener(
    eventName,
    (event) => {
      const windowEl = event.target.closest?.('.terminal-window,.note-window');
      if (windowEl) focusFloatingWindow(windowEl);
    },
    true,
  );
}
