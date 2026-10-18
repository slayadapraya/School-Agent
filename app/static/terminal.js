'use strict';

/** Authenticated host-terminal UI with xterm rendering, PTY input and window controls.
 * The server binds every terminal session to the administrator session that opened it.
 */
let hostTerminal = null;
const renderAdminBeforeTerminal = renderAdminPanel;
renderAdminPanel = async function () {
  if (adminTab !== 'terminal') return renderAdminBeforeTerminal();
  if (state.user?.role !== 'admin' || studentView) return;
  if (hostTerminal) {
    $('#admin-panel').innerHTML =
      `<div class="admin-heading"><h1>SSH / Terminal</h1></div><p>Your terminal is connected in its floating window.</p><button class="primary" data-terminal-restore="1">Show terminal</button>`;
    return;
  }
  $('#admin-panel').innerHTML =
    `<div class="admin-heading"><h1>SSH / Terminal</h1><span class="badge">Administrator only</span></div><p class="muted">Interactive terminal on the computer hosting School Agent. Commands run as the server’s operating-system account.</p><form id="terminal-unlock" class="account-form terminal-unlock"><label>Current account password<input type="password" name="password" autocomplete="current-password" required maxlength="256"></label><button class="primary">Connect to host</button><p class="error" id="terminal-error" role="status"></p></form><section id="host-console" hidden><div class="terminal-toolbar"><span id="terminal-host"></span><button data-terminal-disconnect="1">Disconnect</button></div><div id="terminal-scroll" role="region" aria-label="Scrollable host terminal"><div id="terminal-screen" aria-label="Host terminal"></div></div><p class="muted" id="terminal-status">Connected · disconnects after 5 minutes without input.</p></section>`;
  $('#terminal-unlock').onsubmit = async (e) => {
    e.preventDefault();
    const f = e.target,
      button = f.querySelector('button');
    button.disabled = true;
    try {
      const result = await api('/api/admin/terminal', {
        action: 'open',
        password: f.elements.password.value,
      });
      f.elements.password.value = '';
      if (
        !$('#terminal-screen') ||
        adminTab !== 'terminal' ||
        (!document.getElementById('admin-window') && screen !== 'admin')
      ) {
        await api('/api/admin/terminal', { action: 'close', id: result.id });
        return;
      }
      f.hidden = true;
      $('#host-console').hidden = false;
      $('#terminal-host').textContent = result.user + '@' + result.host;
      const windowEl = document.createElement('section');
      windowEl.className = 'terminal-window';
      windowEl.setAttribute('aria-label', 'Floating host terminal');
      windowEl.innerHTML = `<header class="terminal-window-bar"><span class="terminal-window-title">Host terminal</span><div><button data-terminal-minimise="1" aria-label="Minimise terminal" title="Minimise">−</button><button data-terminal-restore="1" aria-label="Restore terminal" title="Restore"><svg viewBox="0 0 16 16" aria-hidden="true"><rect x="3" y="3" width="10" height="10" rx="1"/></svg></button><button data-terminal-disconnect="1" aria-label="Close terminal" title="Close and disconnect">✕</button></div></header>`;
      windowEl.append($('#host-console'));
      document.body.append(windowEl);
      makeTerminalDraggable(windowEl);
      const terminal = new Terminal({
        cursorBlink: false,
        cursorStyle: 'block',
        cursorInactiveStyle: 'outline',
        fontSize: 16,
        fontFamily: 'ui-monospace, SFMono-Regular, Consolas, monospace',
        scrollback: 3000,
        theme: {
          background: '#101e19',
          foreground: '#e3eedb',
          cursor: '#c4f8a4',
          cursorAccent: '#101e19',
          selectionBackground: '#4d705b',
          black: '#101e19',
          red: '#ed9292',
          green: '#9edcaa',
          yellow: '#e9ce8c',
          blue: '#9abde9',
          magenta: '#d6a5df',
          cyan: '#90d8cf',
          white: '#d5e2d0',
          brightBlack: '#6d8f7c',
          brightRed: '#ffaaaa',
          brightGreen: '#b3f0ac',
          brightYellow: '#ffe2a6',
          brightBlue: '#bdd5ff',
          brightMagenta: '#ecc0f1',
          brightCyan: '#adf1e9',
          brightWhite: '#f4faed',
        },
      });
      const fit = new FitAddon.FitAddon();
      terminal.loadAddon(fit);
      terminal.open($('#terminal-screen'));
      fit.fit();
      const connection = { id: result.id, terminal, fit, windowEl, closed: false };
      hostTerminal = connection;
      const socket = new WebSocket(
        (location.protocol === 'https:' ? 'wss:' : 'ws:') +
          '//' +
          location.host +
          '/api/admin/terminal-stream?id=' +
          encodeURIComponent(result.id),
      );
      socket.binaryType = 'arraybuffer';
      connection.socket = socket;
      const resize = () => {
        if (!connection.closed) {
          const box = document.getElementById('terminal-screen');
          if (!box || connection.windowEl.classList.contains('minimised')) return;
          const usableHeight = box.clientHeight - 24;
          const cell = terminal.element
            ?.querySelector('.xterm-char-measure-element')
            ?.getBoundingClientRect();
          fit.fit();
          if (cell?.height > 0) {
            const rows = Math.max(5, Math.floor(usableHeight / cell.height) - 1);
            if (terminal.rows > rows) terminal.resize(terminal.cols, rows);
          }
          if (
            socket.readyState === WebSocket.OPEN &&
            (connection.cols !== terminal.cols || connection.rows !== terminal.rows)
          ) {
            connection.cols = terminal.cols;
            connection.rows = terminal.rows;
            socket.send(JSON.stringify({ cols: terminal.cols, rows: terminal.rows }));
          }
        }
      };
      terminal.onData((text) => sendTerminalInput(connection, text));
      socket.onopen = () => {
        resize();
        terminal.focus();
        $('#terminal-status').textContent =
          'Live connection · Swipe sideways for wide output on small screens. · 5-minute idle timeout.';
      };
      socket.onmessage = (event) => {
        if (!connection.closed && event.data instanceof ArrayBuffer)
          terminal.write(new Uint8Array(event.data));
      };
      socket.onerror = () =>
        finishTerminal(
          connection,
          'Could not establish the live terminal connection. Please reconnect.',
          true,
        );
      socket.onclose = () =>
        finishTerminal(connection, 'Terminal disconnected. Connect again to start a shell.', false);
      connection.resize = new ResizeObserver(resize);
      connection.resize.observe($('#terminal-screen'));
      terminal.focus();
    } catch (err) {
      if ($('#terminal-error')) $('#terminal-error').textContent = err.message;
    } finally {
      button.disabled = false;
    }
  };
};
function sendTerminalInput(c, text) {
  if (!c.closed && c.socket?.readyState === WebSocket.OPEN && text.length <= 8192)
    c.socket.send(JSON.stringify({ input: text }));
}
async function finishTerminal(c, message, notify) {
  if (c.closed) return;
  await disconnectTerminal(notify);
  if ($('#terminal-status')) $('#terminal-status').textContent = message;
  if ((screen === 'admin' || document.getElementById('admin-window')) && adminTab === 'terminal') {
    await renderAdminPanel();
    if ($('#terminal-error')) $('#terminal-error').textContent = message;
  }
}
async function disconnectTerminal(notify = true) {
  const c = hostTerminal;
  if (!c) return;
  hostTerminal = null;
  c.closed = true;
  c.resize?.disconnect();
  c.socket?.close();
  c.terminal.dispose();
  c.windowEl?.remove();
  if (notify) {
    try {
      await api('/api/admin/terminal', { action: 'close', id: c.id });
    } catch (e) {}
  }
}
document.addEventListener('click', async (e) => {
  const b = e.target.closest('button');
  if (!b) return;
  if (b.dataset.terminalDisconnect) {
    await disconnectTerminal();
    if ((screen === 'admin' || document.getElementById('admin-window')) && adminTab === 'terminal')
      await renderAdminPanel();
  }
  if (b.dataset.terminalMinimise && hostTerminal) {
    hostTerminal.windowEl.classList.add('minimised');
  }
  if (b.dataset.terminalRestore && hostTerminal) {
    hostTerminal.windowEl.classList.remove('minimised');
    hostTerminal.terminal.focus();
  }
  if (b.dataset.action === 'logout' || b.dataset.action === 'student-view')
    await disconnectTerminal();
  if (b.dataset.terminalKey && hostTerminal) {
    const keys = { 'ctrl-c': '\x03', tab: '\t', up: '\x1b[A', down: '\x1b[B', escape: '\x1b' };
    sendTerminalInput(hostTerminal, keys[b.dataset.terminalKey] || '');
    hostTerminal.terminal.focus();
  }
});
// Site navigation preserves the floating shell. Logout and browser navigation close it.
new MutationObserver(() => {
  if (hostTerminal && !document.getElementById('terminal-screen')) disconnectTerminal();
}).observe(document.getElementById('app'), { childList: true, subtree: true });
window.addEventListener('pagehide', () => {
  if (hostTerminal)
    fetch('/api/admin/terminal', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-School-Agent': '1' },
      body: JSON.stringify({ action: 'close', id: hostTerminal.id }),
      keepalive: true,
    });
});

function makeTerminalDraggable(el) {
  const bar = el.querySelector('.terminal-window-bar');
  bar.addEventListener('pointerdown', (e) => {
    if (e.target.closest('button') || e.button !== 0) return;
    const rect = el.getBoundingClientRect();
    const dx = e.clientX - rect.left,
      dy = e.clientY - rect.top;
    bar.setPointerCapture(e.pointerId);
    el.style.right = 'auto';
    el.style.bottom = 'auto';
    const move = (ev) => {
      el.style.left =
        Math.max(0, Math.min(Math.max(0, innerWidth - el.offsetWidth), ev.clientX - dx)) + 'px';
      el.style.top = Math.max(0, Math.min(Math.max(0, innerHeight - 44), ev.clientY - dy)) + 'px';
    };
    const stop = () => {
      bar.removeEventListener('pointermove', move);
      bar.removeEventListener('pointerup', stop);
      bar.removeEventListener('pointercancel', stop);
    };
    bar.addEventListener('pointermove', move);
    bar.addEventListener('pointerup', stop);
    bar.addEventListener('pointercancel', stop);
  });
}
