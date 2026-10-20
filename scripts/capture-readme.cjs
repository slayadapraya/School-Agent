/** Public documentation screenshots, always from a disposable synthetic demo. */
const { spawn } = require('node:child_process');
const { mkdtemp, mkdir, rm } = require('node:fs/promises');
const { tmpdir } = require('node:os');
const path = require('node:path');
const { createInterface } = require('node:readline');
const { chromium } = require('playwright-core');
const assert = require('node:assert/strict');
const root = path.resolve(__dirname, '..');
(async () => {
  const temporary = await mkdtemp(path.join(tmpdir(), 'school-readme-'));
  const output = path.join(root, 'docs/screenshots');
  await mkdir(output, { recursive: true });
  const server = spawn(
    'python3',
    ['-u', '-c', 'from app.demo import run; import sys; run(0,sys.argv[1])', temporary],
    { cwd: root, stdio: ['ignore', 'pipe', 'inherit'] },
  );
  let browser;
  try {
    const url = await new Promise((resolve, reject) => {
      const lines = createInterface({ input: server.stdout });
      const timer = setTimeout(() => reject(Error('Demo startup timed out')), 20000);
      lines.on('line', (line) => {
        const match = line.match(/http:\/\/127\.0\.0\.1:\d+/);
        if (match) {
          clearTimeout(timer);
          resolve(match[0]);
        }
      });
      server.once('exit', () => reject(Error('Demo exited')));
    });
    browser = await chromium.launch({
      headless: true,
      executablePath: process.env.CHROMIUM_PATH || undefined,
      args: ['--no-sandbox', '--disable-dev-shm-usage'],
    });
    async function login(user, password) {
      const context = await browser.newContext({
        viewport: { width: 1440, height: 960 },
        // Capture at half resolution while preserving the desktop layout.
        deviceScaleFactor: 0.5,
        reducedMotion: 'reduce',
      });
      const page = await context.newPage();
      await page.route('**/api/admin/system', (route) =>
        route.fulfill({
          json: {
            timestamp: 1792400400,
            cpu: { utilization: 12, temperature: 48 },
            ram: { used: 8 * 1073741824, total: 32 * 1073741824 },
            gpu: {
              utilization: 24,
              temperature: 52,
              vram_used: 5 * 1073741824,
              vram_total: 16 * 1073741824,
              power_watts: 65,
            },
            note: 'Synthetic demonstration readings',
          },
        }),
      );
      await page.goto(url);
      await page.getByLabel('Username', { exact: true }).fill(user);
      await page.getByLabel('Password', { exact: true }).fill(password);
      await page.getByRole('button', { name: 'Sign in →', exact: true }).click();
      await page.locator('.shell').waitFor();
      await page.evaluate(() => document.fonts.ready);
      return page;
    }
    const admin = await login('demo.admin', 'DemoAdmin-2026!');
    await admin.screenshot({ path: path.join(output, 'home.png') });
    await admin.getByRole('button', { name: 'Open admin panel', exact: true }).click();
    await admin.locator('.account-row').first().waitFor();
    await admin.screenshot({ path: path.join(output, 'admin-people.png') });
    await admin.locator('[data-admin-tab="classes"]').click();
    await admin.getByRole('heading', { name: 'Classes & groups', exact: true }).waitFor();
    await admin.screenshot({ path: path.join(output, 'admin-classes.png') });
    await admin.getByRole('button', { name: 'Close admin panel', exact: true }).click();
    await admin.locator('[data-action="settings"]').click();
    await admin.locator('.text-size-settings').waitFor();
    await admin.screenshot({ path: path.join(output, 'appearance-settings.png') });
    const student = await login('demo.student1', 'DemoStudent1-2026!');
    await student.evaluate(async () => {
      const data = await (await fetch('/api/bootstrap')).json();
      await openThread(
        data.threads.find((t) => t.title === 'Understanding frequency and period').id,
      );
    });
    await student.locator('.message.assistant').waitFor();
    if (
      (await student
        .getByRole('button', { name: 'Notes', exact: true })
        .getAttribute('aria-expanded')) !== 'true'
    )
      await student.getByRole('button', { name: 'Notes', exact: true }).click();
    await student.waitForFunction(() => !document.getElementById('workspace-notes').inert);
    await student.locator('#note-dock-content .note-title').fill('Frequency and period');
    await student
      .locator('#note-dock-content .note-body')
      .fill(
        'Frequency: cycles per second (Hz).\nPeriod: seconds per cycle.\nNext: compare two waves on the same time axis.',
      );
    await student.waitForFunction(
      () =>
        document.querySelector('#note-dock-content [data-note-status]')?.textContent === 'Saved',
    );
    const composerRow = await student.evaluate(() => {
      const tool = document.querySelector('.composer-tool-group .tool').getBoundingClientRect();
      const model = document.querySelector('.input-model-selector').getBoundingClientRect();
      const send = document.querySelector('.composer-send').getBoundingClientRect();
      return {
        tool: tool.top + tool.height / 2,
        model: model.top + model.height / 2,
        send: send.top + send.height / 2,
      };
    });
    assert(
      Math.abs(composerRow.tool - composerRow.model) < 2,
      'Demo model selector wrapped below the tools',
    );
    assert(
      Math.abs(composerRow.tool - composerRow.send) < 2,
      'Demo send button wrapped below the tools',
    );
    await student.screenshot({ path: path.join(output, 'chat-notes.png') });
    await student.getByRole('button', { name: 'Files', exact: true }).click();
    await student.waitForFunction(() => !document.getElementById('workspace-files').inert);
    await student.getByRole('tab', { name: 'Course files', exact: true }).click();
    await student.locator('[data-workspace-file]').first().click();
    await student.locator('.workspace-file-content').waitFor();
    await student.screenshot({ path: path.join(output, 'course-files.png') });
    console.log('Saved six demo-only screenshots to docs/screenshots');
  } finally {
    await browser?.close();
    server.kill('SIGTERM');
    await new Promise((resolve) => server.once('exit', resolve));
    await rm(temporary, { recursive: true, force: true });
  }
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
