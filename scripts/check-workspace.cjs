/**
 * End-to-end pocket regression checks against a temporary loopback server.
 * npm ci; npx playwright-core install chromium; npm run check:workspace
 * Use CHROMIUM_PATH to select an installed browser. No live account is opened.
 */
const assert = require('node:assert/strict');
const { spawn } = require('node:child_process');
const { mkdir } = require('node:fs/promises');
const path = require('node:path');
const { createInterface } = require('node:readline');
const { chromium } = require('playwright-core');
const root = path.resolve(__dirname, '..');
const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

async function fixture() {
  const process = spawn(processEnv('PYTHON', 'python3'), ['scripts/workspace-fixture.py'], {
    cwd: root,
    stdio: ['ignore', 'pipe', 'inherit'],
  });
  const lines = createInterface({ input: process.stdout });
  const ready = new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(Error('Fixture startup timed out')), 20000);
    lines.once('line', (line) => {
      clearTimeout(timer);
      try {
        resolve(JSON.parse(line));
      } catch (error) {
        reject(error);
      }
    });
    process.once('exit', (code) => {
      clearTimeout(timer);
      reject(Error(`Fixture exited: ${code}`));
    });
  });
  try {
    return { ...(await ready), process };
  } catch (error) {
    process.kill();
    throw error;
  }
}
function processEnv(name, fallback) {
  return process.env[name] || fallback;
}

async function signIn(context, test) {
  const page = await context.newPage();
  await page.goto(test.url);
  await page.getByLabel('Username', { exact: true }).fill('admin');
  await page.getByLabel('Password', { exact: true }).fill(test.password);
  await page.getByRole('button', { name: 'Sign in →', exact: true }).click();
  await page.locator('.shell').waitFor();
  return page;
}
async function settled(page, name) {
  await page.waitForFunction((name) => {
    const card = document.getElementById('workspace-' + name);
    return card && !card.hidden && !card.inert;
  }, name);
}

(async () => {
  const test = await fixture();
  let browser;
  try {
    browser = await chromium.launch({
      headless: true,
      ...(process.env.CHROMIUM_PATH ? { executablePath: process.env.CHROMIUM_PATH } : {}),
      args: ['--no-sandbox', '--disable-dev-shm-usage'],
    });
    const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
    const page = await signIn(context, test);
    const errors = [];
    page.on('pageerror', (error) => errors.push(error.message));
    await page.getByRole('button', { name: 'New thread ＋', exact: true }).click();
    await page.waitForSelector('#note-dock-content .note-editor');
    const input = page.getByRole('textbox', { name: 'Ask School Agent', exact: true });
    const send = page.locator('.composer-send');
    assert.equal(await send.evaluate((el) => el.classList.contains('has-text')), false);
    await input.fill('Composer draft survives');
    assert.equal(await send.evaluate((el) => el.classList.contains('has-text')), true);
    await page.locator('#note-dock-content .note-title').fill('Wave notes');
    assert.equal(
      await page.locator('.note-picker-popover summary [data-note-title]').innerText(),
      'Wave notes',
    );
    const note = page.locator('#note-dock-content .note-body');
    await note.fill('Waves note: frequency is measured in hertz.');
    const noteID = await note.evaluate((el) => el.closest('[data-note-editor]').dataset.noteEditor);
    const noteNode = await note.elementHandle();
    const initialWidth = await page
      .locator('.conversation')
      .evaluate((el) => el.getBoundingClientRect().width);
    await page.getByRole('button', { name: 'Files', exact: true }).click();
    await settled(page, 'files');
    await page.getByRole('button', { name: 'Notes', exact: true }).click();
    await settled(page, 'notes');
    assert.equal(await noteNode.evaluate((el) => el.isConnected), true);
    assert.match(await note.innerText(), /frequency/);
    assert.equal(await input.inputValue(), 'Composer draft survives');
    await page.getByRole('button', { name: 'Minimise notes', exact: true }).click();
    await page.waitForFunction(
      () => document.querySelector('.workspace-panel-slot').getBoundingClientRect().width === 0,
    );
    const fullWidth = await page
      .locator('.conversation')
      .evaluate((el) => el.getBoundingClientRect().width);
    assert(fullWidth > initialWidth + 250);
    await page.getByRole('button', { name: 'Files', exact: true }).click();
    await settled(page, 'files');
    await page.locator('#image-upload').setInputFiles({
      name: 'study.txt',
      mimeType: 'text/plain',
      buffer: Buffer.from('Temporary file about waves and frequency.'),
    });
    await page.waitForSelector('.workspace-file-content pre');
    const preview = page.locator('.workspace-file-content pre');
    assert.match(await preview.innerText(), /waves and frequency/);
    const previewNode = await preview.elementHandle();
    for (const name of ['Notes', 'Files', 'Notes', 'Files']) {
      await page.getByRole('button', { name, exact: true }).click();
      await delay(65);
    }
    await settled(page, 'files');
    await delay(800);
    assert.equal(await page.locator('#workspace-notes').isVisible(), false);
    assert.equal(await previewNode.evaluate((el) => el.isConnected), true);
    const saved = await page.evaluate(
      async (id) => (await fetch('/api/notes/' + id)).json(),
      noteID,
    );
    assert.match(saved.note.body, /frequency is measured in hertz/);
    // Publishing fixtures and opening a subject exercises the real file-list APIs.
    await page.evaluate(() => newThread('MATH101', 'Course file preview'));
    if (
      (await page
        .getByRole('button', { name: 'Files', exact: true })
        .getAttribute('aria-expanded')) !== 'true'
    )
      await page.getByRole('button', { name: 'Files', exact: true }).click();
    await settled(page, 'files');
    await page.getByRole('tab', { name: 'Course files', exact: true }).click();
    await page.locator('[data-workspace-file]').filter({ hasText: 'Waves lecture.pdf' }).click();
    await page.getByLabel('File page', { exact: true }).selectOption('2');
    await page.waitForSelector('.workspace-page-preview iframe');
    const frame = page.locator('.workspace-page-preview iframe');
    assert.match(await frame.getAttribute('src'), /#page=2$/);
    const frameNode = await frame.elementHandle();
    await page.getByRole('button', { name: 'Notes', exact: true }).click();
    await settled(page, 'notes');
    await page.getByRole('button', { name: 'Files', exact: true }).click();
    await settled(page, 'files');
    assert.equal(await page.getByLabel('File page', { exact: true }).inputValue(), '2');
    assert.equal(await frameNode.evaluate((el) => el.isConnected), true);
    const pdf = await page.request.get(
      new URL((await frame.getAttribute('src')).split('#')[0], test.url).href,
    );
    assert.equal(pdf.status(), 200);
    assert.match(pdf.headers()['content-security-policy'], /frame-ancestors 'self'/);
    // A normal theme change must retain the selected source and its page.
    await page.evaluate(() => applyTheme('dark', false));
    assert.equal(await page.getByLabel('File page', { exact: true }).inputValue(), '2');
    await page.evaluate(() => applyTheme('studio', false));
    const shotDir = process.env.WORKSPACE_SCREENSHOTS;
    if (shotDir) {
      await mkdir(shotDir, { recursive: true });
      await page.screenshot({ path: path.join(shotDir, 'workspace-files.png') });
    }

    // Account tabs must retain their form controls and save a person's policies atomically.
    await page.getByRole('button', { name: 'Open admin panel', exact: true }).click();
    await page.locator('.account-row').filter({ hasText: 'Test second student' }).click();
    await page.getByRole('tab', { name: 'Policies', exact: true }).click();
    await page.locator('[name=account-policy-overviews]').selectOption('on');
    await page.getByRole('tab', { name: 'Tools', exact: true }).click();
    await page.locator('#account-images').uncheck();
    await page.getByRole('tab', { name: 'Policies', exact: true }).click();
    assert.equal(await page.locator('[name=account-policy-overviews]').inputValue(), 'on');
    await page.getByRole('button', { name: 'Save changes', exact: true }).click();
    await page.waitForFunction(() => !document.querySelector('#modal').open);
    await page.locator('[data-admin-tab=people]').click();
    await page.locator('.account-row').filter({ hasText: 'Test second student' }).click();
    await page.getByRole('tab', { name: 'Policies', exact: true }).click();
    assert.equal(await page.locator('[name=account-policy-overviews]').inputValue(), 'on');
    await page.getByRole('tab', { name: 'Tools', exact: true }).click();
    assert.equal(await page.locator('#account-images').isChecked(), false);
    await page.locator('#modal .close').click();
    await page.locator('[data-admin-tab=policies]').click();
    const secondID = await page.evaluate(
      () => management.users.find((u) => u.username === 'second').id,
    );
    await page.locator('#policy-person [name=user]').selectOption(String(secondID));
    for (const setting of ['off', 'on', 'inherit']) {
      await page.locator('[name=policy-overviews]').selectOption(setting);
      const oldForm = await page.locator('#policy-person').elementHandle();
      await page.getByRole('button', { name: 'Save individual overrides', exact: true }).click();
      await page.waitForFunction((form) => !form.isConnected, oldForm);
      await page.waitForFunction(
        ({ id, setting }) => {
          const f = document.querySelector('#policy-person');
          return f?.elements.user.value === id && f.elements['policy-overviews'].value === setting;
        },
        { id: String(secondID), setting },
      );
    }
    const unchanged = await page.evaluate(async () =>
      (await api('/api/admin/management')).users.find((u) => u.username === 'student'),
    );
    assert.equal(unchanged.permissions.tutoring_policy?.overviews, undefined);
    // A synthetic terminal exercises focus ordering without opening an operating-system shell.
    await page.evaluate(() => {
      const el = document.createElement('section');
      el.id = 'stack-test-terminal';
      el.className = 'terminal-window';
      el.style.cssText = 'left:1000px;top:600px;width:300px;height:180px';
      el.innerHTML =
        '<header class="terminal-window-bar">Focus test terminal</header><input aria-label="Focus test input">';
      document.body.append(el);
      makeTerminalDraggable(el);
    });
    const topWindow = () =>
      page.evaluate(
        () =>
          [...document.querySelectorAll('.terminal-window,.note-window')].sort(
            (a, b) => Number(b.style.zIndex) - Number(a.style.zIndex),
          )[0].id,
      );
    assert.equal(await topWindow(), 'stack-test-terminal');
    await page.locator('#admin-window .terminal-window-bar b').click();
    assert.equal(await topWindow(), 'admin-window');
    await page.getByLabel('Focus test input', { exact: true }).focus();
    assert.equal(await topWindow(), 'stack-test-terminal');
    await page.getByRole('button', { name: 'Open admin panel', exact: true }).click();
    assert.equal(await topWindow(), 'admin-window');
    await page.getByRole('button', { name: 'Close admin panel', exact: true }).click();
    await page.evaluate(() => document.querySelector('#stack-test-terminal').remove());

    // Exercise the actual note Pop out control and its minimise/restore/close lifecycle.
    await page.getByRole('button', { name: 'Notes', exact: true }).click();
    await settled(page, 'notes');
    await page.locator('#note-dock-content [data-note-pop]').click();
    await page.locator('.note-window').waitFor();
    const floatingNote = page.locator('.note-window').first();
    await floatingNote.locator('.note-body').fill('Edited in the pop-out');
    assert.equal(
      await page.locator('#note-dock-content .note-body').innerText(),
      'Edited in the pop-out',
    );
    await floatingNote.getByRole('button', { name: 'Minimise note', exact: true }).click();
    assert(await floatingNote.evaluate((el) => el.classList.contains('is-minimised')));
    await floatingNote.getByRole('button', { name: 'Expand note', exact: true }).click();
    assert(!(await floatingNote.evaluate((el) => el.classList.contains('is-minimised'))));
    await page.getByRole('button', { name: 'Open admin panel', exact: true }).click();
    assert.equal(await topWindow(), 'admin-window');
    await floatingNote.evaluate((el) => {
      el.id = 'stack-test-note';
      el.style.left = '5px';
      el.style.top = '650px';
    });
    await floatingNote.locator('.note-origin').click({ position: { x: 3, y: 3 } });
    assert.equal(await topWindow(), 'stack-test-note');
    await floatingNote.getByRole('button', { name: 'Close note', exact: true }).click();
    await floatingNote.waitFor({ state: 'detached' });
    await page.getByRole('button', { name: 'Close admin panel', exact: true }).click();

    // Clear attached files at dispatch, preserve the sent copy and restore on rejection.
    await page.evaluate(() => newThread('GENERAL', 'Attachment send check'));
    const image = await page.evaluate(() => {
      const c = document.createElement('canvas');
      c.width = c.height = 32;
      c.getContext('2d').fillRect(0, 0, 32, 32);
      return c.toDataURL('image/png').split(',')[1];
    });
    await page.locator('#image-upload').setInputFiles({
      name: 'sample.png',
      mimeType: 'image/png',
      buffer: Buffer.from(image, 'base64'),
    });
    await page.waitForSelector('.attachment-chip');
    await page.locator('#message').fill('Explain this picture');
    const sent = [];
    let unblock;
    const gate = new Promise((resolve) => (unblock = resolve));
    await page.route('**/api/chat', async (route) => {
      sent.push(route.request().postDataJSON());
      await gate;
      await route.continue();
    });
    await page.getByRole('button', { name: 'Send message', exact: true }).click();
    await page.waitForFunction(() => busy);
    assert.equal(await page.locator('.attachment-tray .attachment-chip').count(), 0);
    assert.equal(await page.locator('.message.user .message-image').count(), 1);
    unblock();
    await page.waitForFunction(() => !busy);
    assert.equal(await page.locator('.attachment-tray .attachment-chip').count(), 0);
    await delay(1100); // Respect the application's one-second per-thread message limit.
    await page.locator('#message').fill('Another question');
    await page.getByRole('button', { name: 'Send message', exact: true }).click();
    await page.waitForFunction(() => !busy);
    assert.equal(sent[0].attachments.length, 1);
    assert.deepEqual(sent[1].attachments, []);
    await page.unroute('**/api/chat');
    await page.locator('#image-upload').setInputFiles({
      name: 'retry.png',
      mimeType: 'image/png',
      buffer: Buffer.from(image, 'base64'),
    });
    await page.waitForSelector('.attachment-chip');
    await page.locator('#message').fill('Keep this failed draft');
    await page.route('**/api/chat', (route) =>
      route.fulfill({
        status: 503,
        contentType: 'application/json',
        body: JSON.stringify({ error: 'Synthetic rejected request' }),
      }),
    );
    await page.getByRole('button', { name: 'Send message', exact: true }).click();
    await page.waitForFunction(
      () => !busy && document.querySelector('#message').value === 'Keep this failed draft',
    );
    assert.equal(await page.locator('.attachment-tray .attachment-chip').count(), 1);
    await page.unroute('**/api/chat');

    const phone = await browser.newContext({
      viewport: { width: 390, height: 844 },
      isMobile: true,
      hasTouch: true,
      reducedMotion: 'reduce',
    });
    const mobile = await signIn(phone, test);
    mobile.on('pageerror', (error) => errors.push(error.message));
    await mobile.evaluate(() => newThread('GENERAL', 'Phone pocket check'));
    await mobile.getByRole('button', { name: 'Notes', exact: true }).tap();
    await settled(mobile, 'notes');
    const mobileNote = mobile.locator('#note-dock-content .note-body');
    await mobileNote.fill('Typed on a phone');
    // The backdrop must be behind the editor, not a dim layer blocking it.
    const hit = await mobileNote.evaluate((el) => {
      const r = el.getBoundingClientRect();
      return el.contains(document.elementFromPoint(r.x + 10, r.y + 10));
    });
    assert(hit);
    assert(await mobile.locator('.conversation').evaluate((el) => el.inert));
    await mobile.getByRole('button', { name: 'Minimise notes', exact: true }).tap();
    await mobile.waitForFunction(() => document.querySelector('#workspace-notes').hidden);
    assert(!(await mobile.locator('.conversation').evaluate((el) => el.inert)));
    await mobile.getByRole('button', { name: 'Notes', exact: true }).tap();
    await settled(mobile, 'notes');
    await mobile.locator('.workspace-panel-scrim').tap({ position: { x: 3, y: 400 } });
    await mobile.waitForFunction(() => document.querySelector('#workspace-notes').hidden);
    await mobile.getByRole('button', { name: 'Files', exact: true }).tap();
    await settled(mobile, 'files');
    await mobile.keyboard.press('Escape');
    await mobile.waitForFunction(() => document.querySelector('#workspace-files').hidden);
    await mobile.getByRole('button', { name: 'Notes', exact: true }).tap();
    await settled(mobile, 'notes');
    assert.equal(await mobileNote.innerText(), 'Typed on a phone');
    assert(!(await mobile.evaluate(() => document.documentElement.scrollWidth > innerWidth)));
    if (shotDir)
      await mobile.screenshot({ path: path.join(shotDir, 'workspace-notes-mobile.png') });
    assert.deepEqual(errors, []);
    console.log(
      JSON.stringify(
        {
          individualPoliciesSaved: true,
          floatingWindowFocus: true,
          attachmentSendAndRetry: true,
          notesSaved: true,
          composerDraftPreserved: true,
          persistentEditors: true,
          rapidSwitching: true,
          chatWidths: { initialWidth, fullWidth },
          filePagePreserved: true,
          pdfAuthorized: true,
          mobileTapTargets: true,
          backdropAndEscape: true,
          reducedMotion: true,
          errors,
        },
        null,
        2,
      ),
    );
  } finally {
    await browser?.close();
    test.process.kill('SIGTERM');
  }
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
