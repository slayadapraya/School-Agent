/**
 * Generated artifacts and resizable navigation checks against a temporary loopback server.
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

// Exercise the scroll affordance with DOM-only synthetic content: no chat writes.
async function checkChatJump(page, screenshot = false) {
  const code = page.locator('.conversation .code-block pre code').first();
  const original = await code.innerHTML();
  try {
    await code.evaluate((el) => {
      el.textContent = Array.from({ length: 200 }, (_, i) => `// Scroll test line ${i}`).join('\n');
    });
    await page.locator('#content').evaluate((el) => {
      el.scrollTop = 0;
    });
    const jump = page.getByRole('button', { name: 'Jump to latest message', exact: true });
    await jump.waitFor({ state: 'visible' });
    const geometry = await jump.evaluate((el) => {
      const rect = el.getBoundingClientRect();
      const wrap = el.closest('.composer-wrap').getBoundingClientRect();
      const form = document.getElementById('chat-form').getBoundingClientRect();
      const icon = el.querySelector('svg').getBoundingClientRect();
      return {
        inside: rect.left >= wrap.left && rect.right <= wrap.right,
        centre: Math.abs(rect.left + rect.width / 2 - form.left - form.width / 2),
        iconCentre: Math.max(
          Math.abs(icon.left + icon.width / 2 - rect.left - rect.width / 2),
          Math.abs(icon.top + icon.height / 2 - rect.top - rect.height / 2),
        ),
        above: rect.bottom <= wrap.top + 1,
        fade: getComputedStyle(el.parentElement).backgroundImage,
      };
    });
    assert.equal(geometry.inside, true);
    assert.equal(
      await page
        .locator('#content')
        .evaluate((el) => el.classList.contains('chat-away-from-bottom')),
      true,
    );
    assert(geometry.centre <= 1, JSON.stringify(geometry));
    assert(geometry.iconCentre <= 1, JSON.stringify(geometry));
    assert.equal(geometry.above, true);
    assert.match(geometry.fade, /linear-gradient/);
    if (screenshot)
      await page.screenshot({
        path: path.join(root, '.local-test-artifacts/chat-jump-bottom.png'),
      });
    await jump.click();
    await page.waitForFunction(() => {
      const area = document.getElementById('content');
      return (
        area.scrollHeight - area.clientHeight - area.scrollTop <= 2 &&
        document.querySelector('.chat-end-control').hidden
      );
    });
    assert.equal(
      await page
        .locator('#content')
        .evaluate((el) => el.classList.contains('chat-away-from-bottom')),
      false,
    );
  } finally {
    await code.evaluate((el, html) => {
      el.innerHTML = html;
    }, original);
  }
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
    // A second account's thread must never appear in the admin's own home/nav.
    const student = await browser.newContext();
    await student.request.post(test.url + '/api/login', {
      headers: { 'X-School-Agent': '1' },
      data: { username: 'student', password: test.password },
    });
    const studentThreadResponse = await student.request.post(test.url + '/api/threads', {
      headers: { 'X-School-Agent': '1' },
      data: { course_id: 'GENERAL', title: 'Private student chat fixture' },
    });
    const studentThread = await studentThreadResponse.json();
    const studentNoteResponse = await student.request.post(test.url + '/api/notes', {
      headers: { 'X-School-Agent': '1' },
      data: { thread_id: studentThread.id },
    });
    const studentNote = (await studentNoteResponse.json()).note;
    await student.request.post(test.url + '/api/notes/' + studentNote.id, {
      headers: { 'X-School-Agent': '1' },
      data: {
        version: studentNote.version,
        title: 'Synthetic review note',
        body: 'A student note for read-only review.',
      },
    });
    await student.close();
    const page = await signIn(context, test);
    assert.equal(await page.locator('.sidebar .course-nav,.sidebar .category-toggle').count(), 0);
    assert.equal(
      await page
        .locator('.sidebar')
        .getByText('Private student chat fixture', { exact: true })
        .count(),
      0,
    );
    await context.request.post(test.url + '/api/threads', {
      headers: { 'X-School-Agent': '1' },
      data: { course_id: 'GENERAL', title: 'My own admin chat fixture' },
    });
    await page.reload();
    await page.locator('.sidebar .personal-category').first().waitFor();
    assert.equal(await page.locator('.sidebar .course-nav,.sidebar .category-toggle').count(), 0);
    assert(
      (await page
        .locator('.sidebar')
        .getByRole('button', { name: 'My own admin chat fixture', exact: true })
        .count()) > 0,
    );
    assert.equal(await page.getByText('Private student chat fixture', { exact: true }).count(), 0);
    assert(
      (await page
        .locator('.sidebar-recent-row')
        .first()
        .evaluate((el) => parseFloat(getComputedStyle(el).fontSize))) >= 17,
    );
    const errors = [];
    page.on('pageerror', (error) => errors.push(error.message));
    await page.getByRole('button', { name: 'New thread', exact: true }).click();
    await page.getByRole('button', { name: 'Create file', exact: false }).click();
    assert.match(await page.locator('#message').inputValue(), /downloadable/);
    await page.locator('#message').fill('artifact-test: Create an HTML file and a Python file.');
    await page.locator('.composer-send').click();
    await page.locator('.artifact-source').waitFor({ state: 'visible' });
    await settled(page, 'files');
    assert.match(await page.locator('.artifact-source').inputValue(), /Artifact preview/);
    const fileDownload = page
      .locator('.artifact-heading')
      .getByRole('link', { name: 'Download', exact: true });
    assert.equal((await fileDownload.textContent()).trim(), '');
    assert.equal(await fileDownload.getAttribute('title'), 'Download');
    assert.equal(await fileDownload.locator('svg').count(), 1);

    // Quick code tools stay inside their original block and export that source.
    await page.evaluate(() => {
      stopReplyAnimation();
      busy = true;
      render();
    });
    assert.equal(await page.locator('.thinking-dots i').count(), 3);
    const dotDelays = await page
      .locator('.thinking-dots i')
      .evaluateAll((els) => els.map((el) => getComputedStyle(el).animationDelay));
    assert.equal(new Set(dotDelays).size, 3);
    await page.evaluate(() => {
      busy = false;
      render();
      animateLatestReply(false);
    });
    await page.locator('.reply-caret').waitFor();
    assert.equal(
      await page.locator('.reply-caret').evaluate((el) => !!el.closest('pre,.reply-paragraph')),
      true,
    );
    await page.evaluate(() => stopReplyAnimation());
    // Step the real reveal callback without wall-clock timing: later toolbars,
    // empty code cards and metadata must stay hidden until their source is reached.
    const sequence = await page.evaluate(() => {
      const nativeRAF = window.requestAnimationFrame;
      let paint,
        finished = 0;
      window.requestAnimationFrame = (callback) => {
        paint = callback;
        return 0;
      };
      try {
        animateLatestReply(false, () => finished++);
        const animation = replyAnimation;
        const root = animation.element;
        const codes = [...root.querySelectorAll('.code-block')];
        const shown = (node) => getComputedStyle(node).display !== 'none';
        const snapshot = () => ({
          codes: codes.map(shown),
          footer: shown(codes[0].querySelector('.code-footer')),
          metadata: shown(root.parentElement.querySelector('[data-generated-file]')),
        });
        const initial = snapshot();
        const length = animation.nodes.reduce((n, item) => n + item.text.length, 0);
        const rate = Math.max(65, length / 7);
        let firstCode = 0;
        for (const item of animation.nodes) {
          if (codes[0].contains(item.node)) break;
          firstCode += item.text.length;
        }
        paint(animation.start + ((firstCode + 3) / rate) * 1000);
        const duringFirstCode = snapshot();
        paint(animation.start + ((length + 1) / rate) * 1000);
        const complete = snapshot();
        return {
          initial,
          duringFirstCode,
          complete,
          finished,
          pending: root.parentElement.querySelectorAll('[data-reply-pending]').length,
        };
      } finally {
        window.requestAnimationFrame = nativeRAF;
        stopReplyAnimation();
      }
    });
    assert(sequence.initial.codes.every((value) => !value));
    assert.equal(sequence.initial.metadata, false);
    assert.equal(sequence.duringFirstCode.codes[0], true);
    assert(sequence.duringFirstCode.codes.slice(1).every((value) => !value));
    assert.equal(sequence.duringFirstCode.footer, false);
    assert.equal(sequence.duringFirstCode.metadata, false);
    assert(sequence.complete.codes.every(Boolean));
    assert.equal(sequence.complete.metadata, true);
    assert.equal(sequence.finished, 1);
    assert.equal(sequence.pending, 0);
    const block = page.locator('.code-block').first();
    await block.getByRole('button', { name: 'Copy', exact: true }).waitFor();
    const copyLabel = block.locator('[data-copy-code] .code-action-label');
    assert.equal(await copyLabel.evaluate((el) => el.getBoundingClientRect().width), 0);
    await block.getByRole('button', { name: 'Copy', exact: true }).hover();
    await page.waitForTimeout(220);
    assert((await copyLabel.evaluate((el) => el.getBoundingClientRect().width)) > 20);
    // A long code block keeps its toolbar pinned within the chat scrollport.
    const stickyGeometry = await block.evaluate((el) => {
      const content = document.getElementById('content');
      const code = el.querySelector('pre code');
      const original = code.innerHTML;
      const oldScroll = content.scrollTop;
      code.textContent = Array.from(
        { length: 120 },
        (_, index) => `// Long code line ${index}`,
      ).join('\n');
      content.scrollTop +=
        el.getBoundingClientRect().top - content.getBoundingClientRect().top + 250;
      const result = {
        toolbar: el.querySelector('.code-toolbar').getBoundingClientRect().top,
        scrollport: content.getBoundingClientRect().top,
      };
      code.innerHTML = original;
      content.scrollTop = oldScroll;
      return result;
    });
    assert(
      Math.abs(stickyGeometry.toolbar - stickyGeometry.scrollport) <= 1,
      JSON.stringify(stickyGeometry),
    );
    const downloadEvent = page.waitForEvent('download');
    await block.getByRole('button', { name: 'Download', exact: true }).click();
    const inlineDownload = await downloadEvent;
    assert.match(inlineDownload.suggestedFilename(), /\.html$/);
    // Long replies expose the jump: opening used to shrink the source to 420px
    // while moving the focused footer below the new iframe.
    const originalInlineSource = await block.locator('pre code').innerHTML();
    await block.locator('pre code').evaluate((el) => {
      el.append('\n' + Array.from({ length: 120 }, (_, i) => `<!-- Line ${i} -->`).join('\n'));
    });
    const inlinePreviewButton = block.getByRole('button', { name: 'Preview', exact: true });
    await inlinePreviewButton.scrollIntoViewIfNeeded();
    const chatTopBeforePreview = await page.locator('#content').evaluate((el) => el.scrollTop);
    const sourceHeightBeforePreview = (await block.locator('pre').boundingBox()).height;
    await inlinePreviewButton.click();
    await block.locator('.inline-code-preview').waitFor();
    assert.equal(await block.locator('pre').isVisible(), true);
    assert.equal(await block.locator('iframe').getAttribute('sandbox'), 'allow-scripts');
    const inlineFrame = block.frameLocator('iframe');
    await inlineFrame.getByText('Artifact preview', { exact: true }).waitFor();
    assert.equal(
      await page.locator('#content').evaluate((el) => el.scrollTop),
      chatTopBeforePreview,
      'Opening a chat code preview must not scroll the conversation',
    );
    assert.equal(
      (await block.locator('pre').boundingBox()).height,
      sourceHeightBeforePreview,
      'Opening a preview must not collapse the source code above it',
    );
    const closeInlineButton = block.getByRole('button', { name: 'Hide preview', exact: true });
    const closeInlineBox = await closeInlineButton.boundingBox();
    await page.mouse.click(
      closeInlineBox.x + closeInlineBox.width / 2,
      closeInlineBox.y + closeInlineBox.height / 2,
    );
    assert.equal(await block.locator('.inline-code-preview').count(), 0);
    assert.equal(
      await page.locator('#content').evaluate((el) => el.scrollTop),
      chatTopBeforePreview,
      'Closing a chat code preview must keep the same reading position',
    );
    await block.getByRole('button', { name: 'Preview', exact: true }).click();
    await inlineFrame.getByText('Artifact preview', { exact: true }).waitFor();
    await block.locator('pre code').evaluate((el, html) => {
      el.innerHTML = html;
    }, originalInlineSource);
    assert.equal(await inlineFrame.locator('body').getAttribute('data-executed'), 'yes');
    assert.equal(await inlineFrame.locator('body').getAttribute('data-isolated'), 'yes');
    assert.equal(await page.locator('body').getAttribute('data-preview-escaped'), null);
    await inlineFrame.getByRole('button', { name: 'Show details', exact: true }).click();
    assert.equal(await inlineFrame.getByText('Another section', { exact: true }).isVisible(), true);

    assert.equal(
      await inlineFrame.locator('h1').evaluate((el) => getComputedStyle(el).color),
      'rgb(25, 120, 80)',
    );
    assert.equal(await page.locator('#workspace-files').isVisible(), true);
    assert(
      (await block.locator('pre').boundingBox()).y <
        (await block.locator('iframe').boundingBox()).y,
    );
    await page.screenshot({
      path: path.join(root, '.local-test-artifacts/inline-code-preview.png'),
    });
    await block.getByRole('button', { name: 'Pop out preview', exact: true }).click();
    // The floating panel follows the same window focus, resize and drag rules.
    await page.locator('.code-preview-window').waitFor();
    await page
      .frameLocator('.code-preview-window iframe')
      .getByText('Artifact preview', { exact: true })
      .waitFor();
    await page.getByRole('button', { name: 'Minimise website preview', exact: true }).click();
    assert.equal(await page.locator('.code-preview-window iframe').isVisible(), false);
    await page.getByRole('button', { name: 'Restore website preview', exact: true }).click();
    const floatingBefore = await page.locator('.code-preview-window').boundingBox();
    await page.locator('.code-preview-window .terminal-window-bar > span').hover();
    await page.mouse.down();
    await page.mouse.move(floatingBefore.x + 130, floatingBefore.y + 70, { steps: 5 });
    await page.mouse.up();
    const floatingAfter = await page.locator('.code-preview-window').boundingBox();
    assert(
      Math.abs(floatingAfter.x - floatingBefore.x) > 10 ||
        Math.abs(floatingAfter.y - floatingBefore.y) > 10,
    );
    await page.getByRole('button', { name: 'Close website preview', exact: true }).click();
    assert.equal(await page.locator('.code-preview-window').count(), 0);
    await block.getByRole('button', { name: 'Preview', exact: true }).click();
    await block.getByRole('button', { name: 'Hide preview', exact: true }).click();
    assert.equal(await block.locator('iframe').count(), 0);
    assert.equal(await block.locator('pre').isVisible(), true);

    await page.locator('.artifact-highlight .hljs-tag').first().waitFor();
    assert((await page.locator('.artifact-highlight span').count()) > 0);
    assert.equal(await page.locator('.artifact-highlight').getAttribute('aria-hidden'), 'true');
    assert.equal(
      await page.locator('.artifact-source').evaluate((el) => getComputedStyle(el).caretColor),
      await page.locator('.artifact-code-editor').evaluate((el) => getComputedStyle(el).color),
    );

    const source = page.locator('.artifact-source');
    const originalSource = await source.inputValue();
    await source.fill(
      Array.from({ length: 100 }, (_, i) => `<p>${i} ${'wide line '.repeat(30)}</p>`).join('\n'),
    );
    await source.press('Control+End');
    await page.waitForFunction(() => {
      const editor = document.querySelector('.artifact-source');
      const colours = document.querySelector('.artifact-highlight');
      return (
        editor.scrollTop > 0 &&
        Math.abs(editor.scrollTop - colours.scrollTop) < 1 &&
        Math.abs(editor.scrollLeft - colours.scrollLeft) < 1
      );
    });
    await source.fill(originalSource);
    await source.fill((await source.inputValue()) + '\n<h2>Edited and saved</h2>');
    await page.getByRole('button', { name: 'Save changes', exact: true }).click();
    await page.waitForFunction(
      () => document.querySelector('.artifact-status').textContent === 'Saved',
    );
    // A stale editor must recover through Reload saved after a version conflict.
    const artifactID = await page
      .getByRole('link', { name: 'Download', exact: true })
      .getAttribute('href');
    const endpoint = test.url + artifactID.replace('/download', '');
    const latest = await (await context.request.get(endpoint)).json();
    await context.request.post(endpoint, {
      headers: { 'X-School-Agent': '1' },
      data: {
        content: latest.file.content + '\n<!-- other window -->',
        version: latest.file.version,
      },
    });
    await source.fill((await source.inputValue()) + '\n<!-- stale change -->');
    await page.getByRole('button', { name: 'Save changes', exact: true }).click();
    await page.waitForFunction(() =>
      document.querySelector('.artifact-status').textContent.includes('another window'),
    );
    page.once('dialog', (dialog) => dialog.accept());
    await page.getByRole('button', { name: 'Reload saved', exact: true }).click();
    await page.waitForFunction(() =>
      document.querySelector('.artifact-source').value.includes('other window'),
    );
    assert.doesNotMatch(await source.inputValue(), /stale change/);
    await page.getByRole('tab', { name: 'Preview', exact: true }).click();
    await page
      .frameLocator('iframe[title="Generated file preview"]')
      .getByRole('heading', { name: 'Edited and saved' })
      .waitFor();
    assert.equal(
      await page
        .frameLocator('iframe[title="Generated file preview"]')
        .locator('body')
        .getAttribute('data-executed'),
      'yes',
    );
    assert.equal(
      await page.locator('iframe[title="Generated file preview"]').getAttribute('sandbox'),
      'allow-scripts',
    );
    const savedPreview = page.frameLocator('iframe[title="Generated file preview"]');
    assert.equal(
      await savedPreview.locator('h1').evaluate((el) => getComputedStyle(el).color),
      'rgb(25, 120, 80)',
    );
    await page.waitForFunction(
      () => document.querySelector('.workspace-panel-slot').getAnimations().length === 0,
    );
    await savedPreview.getByRole('button', { name: 'Show details', exact: true }).click();
    try {
      await savedPreview
        .getByText('Another section', { exact: true })
        .waitFor({ state: 'visible', timeout: 5000 });
    } catch (error) {
      console.error(await savedPreview.locator('body').evaluate((el) => el.innerHTML), errors);
      throw error;
    }

    await page.getByRole('tab', { name: 'Chat files', exact: true }).waitFor({ state: 'visible' });
    await page.getByRole('tab', { name: 'Generated', exact: true }).waitFor({ state: 'visible' });
    await page
      .getByRole('tab', { name: 'Course files', exact: true })
      .waitFor({ state: 'visible' });
    await delay(400);
    await page.getByRole('tab', { name: 'Course files', exact: true }).click();
    assert.equal(
      await page
        .getByRole('tab', { name: 'Course files', exact: true })
        .getAttribute('aria-selected'),
      'true',
    );
    await page.locator('.workspace-file-search').waitFor({ state: 'visible' });
    await page.getByRole('tab', { name: 'Generated', exact: true }).click();
    await page.locator('.workspace-file-list [data-workspace-file]').first().waitFor();
    await page.getByRole('button', { name: 'Browse files', exact: true }).click();
    await page.locator('.workspace-file-search').waitFor({ state: 'hidden' });
    const fileGrip = page.getByRole('separator', { name: 'Resize file panel' });
    const initialPanelWidth = await page
      .locator('.workspace-files')
      .evaluate((el) => el.getBoundingClientRect().width);
    const fileGripBox = await fileGrip.boundingBox();
    await page.mouse.move(fileGripBox.x + 5, fileGripBox.y + 220);
    await page.mouse.down();
    await page.mouse.move(fileGripBox.x + 125, fileGripBox.y + 220, { steps: 8 });
    await page.mouse.up();
    const draggedWidth = await page
      .locator('.workspace-files')
      .evaluate((el) => el.getBoundingClientRect().width);
    assert(Math.abs(draggedWidth - initialPanelWidth + 120) < 3);
    await fileGrip.focus();
    await page.keyboard.press('ArrowLeft');
    const savedFileWidth = await page
      .locator('.workspace-files')
      .evaluate((el) => el.getBoundingClientRect().width);
    assert.equal(savedFileWidth, draggedWidth + 10);
    const frameHandle = await page
      .locator('iframe[title="Generated file preview"]')
      .elementHandle();
    await page.getByRole('button', { name: 'Notes', exact: true }).click();
    await settled(page, 'notes');
    const noteHeight = await page
      .locator('#workspace-notes')
      .evaluate((el) => el.getBoundingClientRect().height);
    assert(noteHeight <= 680 && noteHeight > 350, String(noteHeight));
    const tabTop = await page
      .getByRole('button', { name: 'Notes', exact: true })
      .evaluate((el) => el.getBoundingClientRect().top);
    const noteTop = await page
      .locator('#workspace-notes')
      .evaluate((el) => el.getBoundingClientRect().top);
    assert(Math.abs(tabTop - noteTop) <= 1);
    assert.equal(
      await page
        .getByRole('button', { name: 'Files', exact: true })
        .evaluate((el) => getComputedStyle(el).borderLeftWidth),
      '1px',
    );
    assert.equal(await page.locator('#workspace-notes > header [data-workspace-close]').count(), 1);
    assert.equal(
      await page.locator('#workspace-notes .note-rail-controls [data-workspace-close]').count(),
      0,
    );

    await mkdir(path.join(root, '.local-test-artifacts'), { recursive: true });
    await page.screenshot({
      path: path.join(root, '.local-test-artifacts', 'compact-notes-joined-tabs.png'),
    });
    await page.getByRole('button', { name: 'Files', exact: true }).click();
    assert.equal(
      await page.locator('.main').evaluate((el) => el.classList.contains('workspace-in-motion')),
      true,
    );
    assert.equal(
      await page
        .getByRole('button', { name: 'Files', exact: true })
        .evaluate((el) => getComputedStyle(el).borderRightWidth),
      '1px',
    );
    await settled(page, 'files');
    assert.equal(
      await page
        .locator('#workspace-files')
        .evaluate((el) => getComputedStyle(el).borderTopLeftRadius),
      '0px',
    );
    assert.equal(
      await page.locator('.main').evaluate((el) => el.classList.contains('workspace-in-motion')),
      false,
    );
    assert.equal(await frameHandle.evaluate((el) => el.isConnected), true);
    assert.equal(
      await page.locator('.workspace-files').evaluate((el) => el.getBoundingClientRect().width),
      savedFileWidth,
    );
    await delay(400);
    const geometry = await page.evaluate(() => {
      const pane = document.querySelector('.workspace-files').getBoundingClientRect();
      const main = document.querySelector('.main').getBoundingClientRect();
      const chat = document.querySelector('.conversation').getBoundingClientRect();
      const composer = document.querySelector('.composer').getBoundingClientRect();
      const frame = document
        .querySelector('iframe[title="Generated file preview"]')
        .getBoundingClientRect();
      return {
        rightGap: main.right - pane.right,
        paneWidth: pane.width,
        frameWidth: frame.width,
        frameHeight: frame.height,
        leftDifference: Math.abs(chat.left + 28 - composer.left),
        rightDifference: Math.abs(chat.right - 28 - composer.right),
      };
    });
    assert(geometry.rightGap <= 10, JSON.stringify(geometry));
    assert(geometry.frameWidth > 500, JSON.stringify(geometry));
    assert(geometry.frameHeight > 400, JSON.stringify(geometry));
    assert(geometry.leftDifference < 2 && geometry.rightDifference < 2, JSON.stringify(geometry));
    await page.waitForFunction(() => !document.querySelector('.reply-typing'));
    await mkdir(path.join(root, '.local-test-artifacts'), { recursive: true });
    await page.screenshot({
      path: path.join(root, '.local-test-artifacts', 'generated-preview-desktop.png'),
    });
    const downloadURL = await page
      .getByRole('link', { name: 'Download', exact: true })
      .getAttribute('href');
    const downloaded = await context.request.get(test.url + downloadURL);
    assert.match(await downloaded.text(), /Edited and saved/);
    assert.match(downloaded.headers()['content-disposition'], /attachment/);
    await page.getByRole('tab', { name: 'Code', exact: true }).click();
    await delay(400);
    await source.fill((await source.inputValue()) + '\n<!-- draft -->');
    const editorNode = await source.elementHandle();
    await page.getByRole('button', { name: 'Notes', exact: true }).click();
    await settled(page, 'notes');
    await page.getByRole('button', { name: 'Files', exact: true }).click();
    await settled(page, 'files');
    assert.equal(await editorNode.evaluate((el) => el.isConnected), true);
    assert.match(await source.inputValue(), /draft/);
    await page.getByRole('button', { name: 'Save changes', exact: true }).click();
    await page.waitForFunction(
      () => document.querySelector('.artifact-status').textContent === 'Saved',
    );
    assert.equal(await page.locator('[data-artifact-expand]').count(), 0);
    await page.waitForFunction(
      () => document.querySelector('.workspace-panel-slot').getBoundingClientRect().width > 450,
    );
    await delay(400);
    await page.getByRole('button', { name: 'Minimise files', exact: true }).click();
    await delay(600);
    const sidebar = page.locator('.sidebar');
    const oldWidth = await sidebar.evaluate((el) => el.getBoundingClientRect().width);
    const expandedMainWidth = await page.locator('.main').evaluate((el) => el.clientWidth);
    await page.getByRole('button', { name: 'Collapse sidebar', exact: true }).click();
    const closingRail = await sidebar.evaluate((el) => ({
      opacity: getComputedStyle(el.querySelector('nav')).opacity,
      chatWidth: el.querySelector('.recent-home').getBoundingClientRect().width,
    }));
    assert.equal(closingRail.opacity, '0', 'Do not flash compact controls during collapse');
    assert.equal(closingRail.chatWidth, 36, 'Active chat background must never stretch');
    await delay(420);
    assert.equal(await sidebar.evaluate((el) => el.getBoundingClientRect().width), 56);
    assert(
      (await page.locator('.main').evaluate((el) => el.clientWidth)) > expandedMainWidth + 100,
    );
    assert.equal(
      await page.getByRole('separator', { name: 'Resize navigation' }).isVisible(),
      false,
    );
    const railPlus = sidebar.getByRole('button', { name: 'New thread', exact: true });
    const railGeometry = await railPlus.evaluate((el) => {
      const plus = el.getBoundingClientRect();
      const logo = document.querySelector('.sidebar .brand-logo').getBoundingClientRect();
      const toggle = document.querySelector('.sidebar-collapse').getBoundingClientRect();
      return {
        plus: plus.width,
        logo: logo.width,
        iconAlignment: Math.abs(logo.left + logo.width / 2 - plus.left - plus.width / 2),
        gap: plus.top - toggle.bottom,
        border: getComputedStyle(el).borderTopWidth,
      };
    });
    assert.equal(railGeometry.plus, 36);
    assert.equal(railGeometry.logo, 20);
    assert(railGeometry.iconAlignment < 1, 'Logo must align with the rail icons');
    assert.equal(railGeometry.border, '0px');
    assert(railGeometry.gap >= 0 && railGeometry.gap <= 6);
    await page.mouse.move(700, 100);
    assert.equal(
      await railPlus.evaluate((el) => getComputedStyle(el).backgroundColor),
      'rgba(0, 0, 0, 0)',
    );
    await railPlus.hover();
    await delay(180);
    assert.notEqual(
      await railPlus.evaluate((el) => getComputedStyle(el).backgroundColor),
      'rgba(0, 0, 0, 0)',
    );
    await sidebar.getByRole('button', { name: 'Profile', exact: true }).click();
    assert.equal(await page.locator('#profile-popup').isVisible(), true);
    const profileSpacing = await sidebar.evaluate((el) => {
      const photo = el.querySelector('.profile-trigger .avatar').getBoundingClientRect();
      const divider = el.querySelector('.side-bottom').getBoundingClientRect();
      return {
        above: photo.top - divider.top - 1,
        below: el.getBoundingClientRect().bottom - photo.bottom,
        cardBackground: getComputedStyle(el.querySelector('.profile-account-card')).backgroundColor,
        dividerWidth: getComputedStyle(el.querySelector('.profile-account-card')).borderBottomWidth,
      };
    });
    assert(
      Math.abs(profileSpacing.above - profileSpacing.below) <= 1,
      JSON.stringify(profileSpacing),
    );
    assert.equal(profileSpacing.cardBackground, 'rgba(0, 0, 0, 0)');
    assert.equal(profileSpacing.dividerWidth, '1px');
    assert.equal(await sidebar.locator('.profile-trigger').getAttribute('aria-current'), 'page');
    assert.equal(await sidebar.locator('.side-bottom > [data-action="settings"]').count(), 0);
    assert.equal(
      await page
        .locator('#profile-popup')
        .getByRole('menuitem', { name: /Course library/ })
        .isVisible(),
      true,
    );
    await page
      .locator('#profile-popup')
      .getByRole('menuitem', { name: 'Settings', exact: true })
      .click();
    assert.equal(
      await sidebar.locator('[data-action="settings"]').getAttribute('aria-current'),
      'page',
    );
    await page.getByRole('button', { name: 'Close dialog', exact: true }).click();
    await sidebar.getByRole('button', { name: 'Profile', exact: true }).click();
    assert.equal(
      await page
        .locator('#profile-popup [data-action="student-view"],#profile-popup [data-account-view]')
        .count(),
      0,
    );
    const menuSettings = page.locator('#profile-popup .profile-footer [data-action="settings"]');
    assert.equal(await menuSettings.isVisible(), true);
    assert.equal(await menuSettings.locator('.sidebar-button-label').isVisible(), true);
    await page.screenshot({ path: path.join(root, '.local-test-artifacts/profile-menu.png') });
    const accountScroll = await page.evaluate(() => {
      const spacer = document.createElement('div');
      spacer.dataset.avatarScrollSpacer = '1';
      spacer.style.height = '1400px';
      document.querySelector('.conversation').append(spacer);
      const area = document.getElementById('content');
      area.scrollTop = 280;
      window.accountScrollNode = area;
      document.getElementById('message').value = 'Keep my unsent draft';
      return area.scrollTop;
    });
    assert(accountScroll > 0);
    await page.getByRole('menuitem', { name: 'Account settings', exact: true }).click();
    await page.getByRole('button', { name: 'Use 🌱 icon', exact: true }).click();
    await page.getByText('Profile picture saved', { exact: true }).waitFor();
    assert.equal(await page.locator('.profile-trigger .avatar').textContent(), '🌱');
    const avatarPNG = await page.evaluate(() => {
      const canvas = document.createElement('canvas');
      canvas.width = canvas.height = 64;
      const drawing = canvas.getContext('2d');
      drawing.fillStyle = '#547c61';
      drawing.fillRect(0, 0, 64, 64);
      return canvas.toDataURL('image/png').split(',')[1];
    });
    await page.locator('[data-avatar-upload]').setInputFiles({
      name: 'profile.png',
      mimeType: 'image/png',
      buffer: Buffer.from(avatarPNG, 'base64'),
    });
    await page.locator('.profile-trigger .avatar img').waitFor();
    assert.equal(
      await page.locator('.profile-trigger .avatar img').evaluate((el) => el.naturalWidth),
      128,
    );
    assert.equal(await page.locator('#content').evaluate((el) => el.scrollTop), accountScroll);
    await page.locator('#self-account [name="name"]').fill('Updated test administrator');
    await page.getByRole('button', { name: 'Save account', exact: true }).click();
    await page
      .locator('.profile-name b')
      .filter({ hasText: 'Updated test administrator' })
      .waitFor({ state: 'attached' });
    assert.equal(
      await page.evaluate(() => document.getElementById('content') === window.accountScrollNode),
      true,
    );
    assert.equal(await page.locator('#content').evaluate((el) => el.scrollTop), accountScroll);
    assert.equal(await page.locator('#message').inputValue(), 'Keep my unsent draft');
    await page.evaluate(() => {
      document.querySelector('[data-avatar-scroll-spacer]').remove();
      document.getElementById('message').value = '';
    });
    const resumeId = await page.evaluate(() => active.id);
    await sidebar.getByRole('button', { name: 'School Agent home', exact: true }).click();
    await page.locator('.home-summary-card').waitFor();
    await page.locator('.sidebar').getByRole('button', { name: 'Chats', exact: true }).click();
    await page.waitForFunction((id) => active?.id === id && screen === 'chat', resumeId);
    await page.locator('.sidebar .brand').hover();
    await page.getByRole('tooltip').filter({ hasText: 'School Agent home' }).waitFor();
    await page.locator('.sidebar .recent-home').hover();
    const flyout = page.getByRole('region', { name: 'Recent conversations', exact: true });
    await flyout.waitFor();
    assert.equal(
      await flyout.getByText('Private student chat fixture', { exact: true }).count(),
      0,
    );
    await flyout.locator('[data-thread="' + resumeId + '"]').click();
    await page.waitForFunction((id) => active?.id === id && screen === 'chat', resumeId);
    await page.locator('.sidebar').getByRole('button', { name: 'Profile', exact: true }).click();
    await page.getByRole('menuitem', { name: /Staff studio/ }).click();
    await page
      .getByLabel('Review student', { exact: true })
      .selectOption({ label: 'Test student · @student' });
    await page.locator('[data-workspace-review-chat="' + studentThread.id + '"]').click();
    await page
      .locator('.student-review-detail h2')
      .filter({ hasText: 'Private student chat fixture' })
      .waitFor();
    await page.locator('[data-workspace-review-note="' + studentNote.id + '"]').click();
    await page.getByText('A student note for read-only review.', { exact: true }).waitFor();
    await page.screenshot({
      path: path.join(root, '.local-test-artifacts/student-readonly-workspace.png'),
    });
    assert.equal(
      await page
        .locator(
          '.student-review-detail textarea,.student-review-detail [contenteditable],.composer-send',
        )
        .count(),
      0,
    );
    assert.equal(await page.evaluate(() => state.user.username), 'admin');
    const deniedStudentWrite = await context.request.post(test.url + '/api/chat', {
      headers: { 'X-School-Agent': '1' },
      data: { thread_id: studentThread.id, message: 'Must not be sent as another account' },
    });
    assert.equal(deniedStudentWrite.status(), 404);
    await page.locator('.sidebar').getByRole('button', { name: 'Chats', exact: true }).click();
    await page.waitForFunction((id) => active?.id === id && screen === 'chat', resumeId);
    await page.reload();
    await page.getByRole('button', { name: 'Expand sidebar', exact: true }).waitFor();
    assert.equal(
      await page.locator('.sidebar').evaluate((el) => el.getBoundingClientRect().width),
      56,
    );
    await page.screenshot({ path: path.join(root, '.local-test-artifacts/sidebar-collapsed.png') });
    await page.getByRole('button', { name: 'Expand sidebar', exact: true }).focus();
    await page.keyboard.press('Enter');
    assert.equal(
      await page.locator('.sidebar nav').evaluate((el) => getComputedStyle(el).opacity),
      '0',
    );
    await page.waitForFunction(
      () => getComputedStyle(document.querySelector('.sidebar nav')).opacity === '1',
    );
    assert.equal(await sidebar.locator('.side-bottom > [data-action="settings"]').count(), 1);
    assert.equal(
      await page.locator('.sidebar').evaluate((el) => el.getBoundingClientRect().width),
      oldWidth,
    );
    const grip = page.getByRole('separator', { name: 'Resize navigation' });
    const box = await grip.boundingBox();
    await page.mouse.move(box.x + box.width / 2, box.y + 200);
    await page.mouse.down();
    await page.mouse.move(box.x + box.width / 2 + 80, box.y + 200, { steps: 10 });
    await delay(100);
    await page.mouse.up();
    const newWidth = await sidebar.evaluate((el) => el.getBoundingClientRect().width);
    assert(newWidth > oldWidth + 60);
    await page.reload();
    await page.locator('.shell').waitFor();
    assert.equal(
      await page.locator('.sidebar').evaluate((el) => el.getBoundingClientRect().width),
      newWidth,
    );
    await page.getByRole('separator', { name: 'Resize navigation' }).focus();
    await page.keyboard.press('ArrowLeft');
    assert.equal(
      await page.locator('.sidebar').evaluate((el) => el.getBoundingClientRect().width),
      newWidth - 10,
    );
    await page
      .getByRole('button', { name: /demo.html/, exact: false })
      .first()
      .click();
    await page.locator('.artifact-source').waitFor({ state: 'visible' });
    assert.match(await page.locator('.artifact-source').inputValue(), /draft/);
    await page.getByRole('tab', { name: 'Preview', exact: true }).click();
    await delay(400);
    assert.equal(
      await page.locator('.workspace-files').evaluate((el) => el.getBoundingClientRect().width),
      savedFileWidth,
    );
    await page.getByRole('tab', { name: 'Code', exact: true }).click();
    await page
      .getByRole('button', { name: /hello.py/, exact: false })
      .first()
      .click();
    await page.waitForFunction(() =>
      document.querySelector('.artifact-source')?.value.includes('Hello from a file'),
    );
    assert.match(await page.locator('.artifact-source').inputValue(), /Hello from a file/);
    assert.equal(await page.locator('[data-artifact-run]').isDisabled(), true);
    await mkdir(path.join(root, '.local-test-artifacts'), { recursive: true });
    await page.screenshot({
      path: path.join(root, '.local-test-artifacts', 'generated-code-desktop.png'),
    });
    // A fresh browser-tab session starts Preview at its large default, rather
    // than inheriting the resized width from a previous session.
    const activeThreadID = await page
      .locator('.sidebar-recent-row.selected')
      .getAttribute('data-thread');
    const fresh = await context.newPage();
    await fresh.goto(test.url);
    await fresh.locator('.sidebar').waitFor();
    await fresh.locator(`.sidebar [data-thread="${activeThreadID}"]`).first().click();
    await fresh
      .getByRole('button', { name: /demo.html/, exact: false })
      .first()
      .click();
    await fresh.locator('.artifact-source').waitFor({ state: 'visible' });
    await fresh.getByRole('tab', { name: 'Preview', exact: true }).click();
    await delay(400);
    const freshSize = await fresh.evaluate(() => {
      const main = document.querySelector('.main').clientWidth;
      return {
        expected: Math.round(Math.min(1200, main * 0.66, main - 350)),
        actual: document.querySelector('.workspace-files').getBoundingClientRect().width,
      };
    });
    assert(Math.abs(freshSize.actual - freshSize.expected) <= 1, JSON.stringify(freshSize));
    assert.equal(await fresh.locator('[data-artifact-expand]').count(), 0);
    await fresh.close();
    await page.locator('[data-action="settings"]').click();
    await page.getByLabel('Chat text', { exact: true }).fill('23');
    await page.getByLabel('Page text', { exact: true }).fill('120');
    await page.getByText('Saved for your account', { exact: true }).waitFor();
    await page.waitForFunction(
      () =>
        document.querySelector('[data-text-size-status]').textContent === 'Saved for your account',
    );
    const sizes = await page.evaluate(() => ({
      user: getComputedStyle(document.querySelector('.message.user')).fontSize,
      reply: getComputedStyle(document.querySelector('.message-copy')).fontSize,
    }));
    assert.equal(sizes.user, '23px');
    assert.equal(sizes.reply, '23px');
    const appearance = await (
      await context.request.get(test.url + '/api/preferences/appearance')
    ).json();
    assert.deepEqual(appearance, { ui_scale: 120, chat_size: 23 });
    await page.getByRole('button', { name: 'Reset text sizes', exact: true }).click();
    await page.waitForFunction(
      () =>
        document.querySelector('[data-text-size-status]').textContent === 'Saved for your account',
    );
    await page.evaluate(() => document.getElementById('modal').close());
    await checkChatJump(page, true);
    await page.setViewportSize({ width: 390, height: 844 });
    assert.equal(
      await page.getByRole('separator', { name: 'Resize navigation' }).isVisible(),
      false,
    );
    assert(
      await page
        .locator('.workspace-files')
        .evaluate((el) => el.getBoundingClientRect().width <= innerWidth),
    );
    await page.locator('.workspace-files [data-workspace-close]').click();
    await delay(600);
    await checkChatJump(page);
    await mkdir(path.join(root, '.local-test-artifacts'), { recursive: true });
    await page.screenshot({
      path: path.join(root, '.local-test-artifacts', 'generated-files-mobile.png'),
    });
    await page.locator('#message').fill('activity-test: How do waves carry energy?');
    await page.locator('.composer-send').click();
    await page
      .locator('[data-activity-current]')
      .filter({ hasText: 'Writing a response' })
      .waitFor();
    await page.locator('[data-activity-steps] li').first().waitFor();
    assert(
      (await page.locator('[data-activity-steps]').textContent()).includes('Reading your question'),
    );
    await page.locator('[data-activity-live]').filter({ hasText: 'updates received' }).waitFor();
    // Follow live growth while at the end; moving upward must release that follow.
    assert(
      await page
        .locator('#content')
        .evaluate((el) => el.scrollHeight - el.scrollTop - el.clientHeight < 85),
    );
    await page.locator('#content').hover();
    await page.mouse.wheel(0, -500);
    await page.waitForTimeout(100);
    const readingTop = await page.locator('#content').evaluate((el) => el.scrollTop);
    await page.waitForTimeout(550);
    assert(
      Math.abs((await page.locator('#content').evaluate((el) => el.scrollTop)) - readingTop) <= 2,
    );
    await page.locator('.reply-activity').waitFor({ state: 'hidden' });
    assert.deepEqual(errors, []);
    console.log(
      'PASS: generated files, save/reload/download, sandbox preview, Notes switching, editor expansion, desktop resize/persistence/keyboard and mobile layout.',
    );
    await context.close();
  } finally {
    await browser?.close();
    test.process.kill('SIGTERM');
  }
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
