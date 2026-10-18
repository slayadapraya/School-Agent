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
