'use strict';

/** Generated file editor. Keep only one body in memory; lists contain metadata.
 * The Files pocket preserves its DOM while Notes is selected and during renders.
 * Requests are scoped to the current account/thread so stale replies cannot leak.
 */
const artifactEditor = (() => {
  let current = null;
  let files = [];
  let listKey = null;
  let loading = null;
  let request = 0;
  let dirty = false;
  let saving = false;
  const key = () =>
    state.user && active && screen === 'chat' ? `${state.user.id}:${active.id}` : null;

  function reset() {
    request++;
    current = null;
    files = [];
    listKey = null;
    loading = null;
    dirty = false;
    saving = false;
    releaseEditor();
    releaseEditor = () => {};
  }

  async function list(force = false) {
    const context = key();
    if (!context || active.draft) return [];
    if (listKey === context && !force) return files;
    if (loading?.key === context && !force) return loading.promise;
    const promise = api('/api/artifacts?thread_id=' + encodeURIComponent(active.id))
      .then((data) => {
        if (context !== key()) return [];
        files = data.files;
        listKey = context;
        return files;
      })
      .finally(() => {
        if (loading?.promise === promise) loading = null;
      });
    loading = { key: context, promise };
    return promise;
  }

  // Shared, local SVGs keep toolbars consistent without another icon dependency.
  const icon = (name) =>
    `<svg viewBox="0 0 24 24" aria-hidden="true">${
      {
        code: '<path d="m8 6-6 6 6 6m8-12 6 6-6 6M14 3l-4 18"/>',
        preview:
          '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M3 9h18M7 6.5h.01M10 6.5h.01"/>',
        reload: '<path d="M20 7v5h-5M4 17v-5h5M6 7a7 7 0 0 1 12-2l2 3M4 16l2 3a7 7 0 0 0 12-2"/>',
        save: '<path d="M4 3h13l4 4v14H3V3Z"/><path d="M7 3v6h10V3M7 21v-8h10v8"/>',
        download: '<path d="M12 3v12m-5-5 5 5 5-5M4 16v5h16v-5"/>',
        run: '<path d="m8 4 12 8-12 8Z"/>',
        files: '<path d="M3 7a2 2 0 0 1 2-2h5l2 2h7a2 2 0 0 1 2 2v10H3Z"/>',
        output: '<rect x="2" y="4" width="20" height="16" rx="2"/><path d="m6 8 4 4-4 4m7 0h5"/>',
      }[name] || ''
    }</svg>`;
  let releaseEditor = () => {};

  async function open(id, reload = false) {
    if (
      !reload &&
      current?.id === id &&
      current.context === key() &&
      document.querySelector('.artifact-source')
    ) {
      workspacePanels.show('files');
      workspacePanels.generatedTab(current);
      return;
    }
    if (dirty && !confirm('Discard the unsaved changes to this file?')) return;
    const context = key(),
      turn = ++request;
    const data = await api('/api/artifacts/' + encodeURIComponent(id));
    if (turn !== request || context !== key()) return;
    releaseEditor();
    workspacePanels.show('files');
    workspacePanels.setEditorWide(false);
    workspacePanels.generatedTab(data.file);
    current = { ...data.file, context };
    const file = current;
    dirty = false;
    const preview = document.querySelector('.workspace-files .workspace-file-preview');
    if (!preview) return;
    const supportsPreview = ['html', 'css', 'svg'].includes(file.language);
    preview.classList.add('generated-preview');
    preview.innerHTML = `<div class="workspace-file-heading artifact-heading"><b>${icon('code')}<span>${esc(file.name)}</span></b><a class="artifact-download-icon" href="${esc(file.url)}" download aria-label="Download" title="Download">${icon('download')}</a></div>
      <div class="artifact-actions">
        <button type="button" data-artifact-browse aria-expanded="false">${icon('files')}<span>Browse files</span></button>
        <button type="button" data-artifact-reload>${icon('reload')}<span>Reload saved</span></button>
        <button type="button" data-artifact-save ${data.can_edit ? '' : 'disabled'}>${icon('save')}<span>Save changes</span></button>
        ${['python', 'py', 'js', 'javascript'].includes(file.language) ? `<button type="button" data-artifact-run ${data.can_edit && data.can_run && data.runner_enabled ? '' : 'disabled'} title="${data.runner_enabled ? 'Run in a restricted container' : 'Container execution is not enabled on this server'}">${icon('run')}<span>Run</span></button>` : ''}
      </div>
      <div class="artifact-view-tabs" role="tablist" aria-label="File view">
        <button type="button" role="tab" data-artifact-code aria-selected="true">${icon('code')}<span>Code</span></button>
        ${supportsPreview ? `<button type="button" role="tab" data-artifact-preview aria-selected="false">${icon('preview')}<span>Preview</span></button>` : ''}
        <button type="button" role="tab" data-artifact-output aria-selected="false" hidden>${icon('output')}<span>Output</span></button>
      </div>
      <small class="artifact-status" role="status">${esc(file.language)} · ${Math.ceil(file.size / 1024)} KiB · Saved${['python', 'py', 'js', 'javascript'].includes(file.language) && !data.runner_enabled ? ' · Execution unavailable' : ''}</small>
      <div class="artifact-code-editor" role="tabpanel" aria-label="Code editor">
        <pre class="artifact-highlight" aria-hidden="true"><code></code></pre>
        <textarea class="artifact-source" aria-label="File contents" wrap="off" spellcheck="false" autocapitalize="off" autocomplete="off" ${data.can_edit ? '' : 'readonly'}>${esc(file.content)}</textarea>
      </div>
      <section class="artifact-result" hidden role="tabpanel" aria-label="Website preview"></section>
      <section class="artifact-console" hidden role="tabpanel" aria-label="Code output"></section>`;
    const editor = preview.querySelector('.artifact-source');
    const highlight = preview.querySelector('.artifact-highlight');
    const code = highlight.querySelector('code');
    const status = preview.querySelector('.artifact-status');
    const codePane = preview.querySelector('.artifact-code-editor');
    const result = preview.querySelector('.artifact-result');
    const output = preview.querySelector('.artifact-console');
    let mode = 'code',
      highlightTimer = null;

    // Reuse the bundled highlighter. One debounced, selected file is highlighted;
    // no editor workers, background polling or automatic language detection.
    function highlightCode() {
      clearTimeout(highlightTimer);
      if (file !== current || mode !== 'code') return;
      const source = editor.value + '\n';
      try {
        const language = window.hljs?.getLanguage(file.language) ? file.language : null;
        code.innerHTML = language
          ? hljs.highlight(source, { language, ignoreIllegals: true }).value
          : esc(source);
      } catch (_) {
        code.textContent = source;
      }
      syncScroll();
    }
    function syncScroll() {
      // Match the textarea's scrollport, excluding native scrollbars, so colours
      // and the caret still line up at the end of long lines and files.
      highlight.style.width = `${editor.clientWidth}px`;
      highlight.style.height = `${editor.clientHeight}px`;
      highlight.scrollTop = editor.scrollTop;
      highlight.scrollLeft = editor.scrollLeft;
    }
    const editorResize = new ResizeObserver(syncScroll);
    editorResize.observe(editor);
    releaseEditor = () => {
      clearTimeout(highlightTimer);
      editorResize.disconnect();
    };
    highlightCode();
    editor.addEventListener('scroll', syncScroll, { passive: true });
    editor.addEventListener('input', () => {
      dirty = editor.value !== file.content;
      status.textContent = dirty ? 'Unsaved changes' : 'Saved';
      // Immediate plain text keeps new characters visible while colours catch up.
      code.textContent = editor.value + '\n';
      syncScroll();
      clearTimeout(highlightTimer);
      highlightTimer = setTimeout(highlightCode, 140);
    });

    function view(next) {
      if (next === 'preview' && dirty) return toast('Save changes before previewing.');
      mode = next;
      codePane.hidden = next !== 'code';
      result.hidden = next !== 'preview';
      output.hidden = next !== 'output';
      for (const button of preview.querySelectorAll('.artifact-view-tabs button')) {
        button.setAttribute('aria-selected', String(button.hasAttribute(`data-artifact-${next}`)));
      }
      if (next === 'preview') {
        workspacePanels.openPreview();
        if (!result.querySelector('iframe'))
          result.innerHTML = `<div class="artifact-browser-bar">${icon('preview')}<span>${esc(file.name)}</span><small>Sandboxed preview · JavaScript enabled</small></div><iframe title="Generated file preview" sandbox="allow-scripts" referrerpolicy="no-referrer" src="/api/artifacts/${file.id}/preview?v=${file.version}"></iframe>`;
      } else if (next === 'code') highlightCode();
    }
    preview.querySelector('[data-artifact-code]').onclick = () => view('code');
    const previewButton = preview.querySelector('[data-artifact-preview]');
    if (previewButton) previewButton.onclick = () => view('preview');
    preview.querySelector('[data-artifact-output]').onclick = () => view('output');
    preview.querySelector('[data-artifact-browse]').onclick = (event) => {
      const shown = preview.closest('.workspace-files').classList.toggle('artifact-browser-open');
      event.currentTarget.setAttribute('aria-expanded', String(shown));
    };
    preview.querySelector('[data-artifact-reload]').onclick = () =>
      open(file.id, true).catch((error) => toast(error.message));
    preview.querySelector('[data-artifact-save]').onclick = async (event) => {
      if (saving || !dirty) return;
      const content = editor.value,
        button = event.currentTarget;
      saving = true;
      button.disabled = true;
      try {
        const saved = await api('/api/artifacts/' + file.id, { content, version: file.version });
        file.version = saved.version;
        file.content = content;
        if (file === current) {
          dirty = editor.value !== content;
          status.textContent = dirty ? 'New changes have not been saved yet' : 'Saved';
          result.replaceChildren();
          listKey = null;
        }
      } catch (error) {
        status.textContent = error.message;
      } finally {
        saving = false;
        button.disabled = false;
      }
    };
    const runButton = preview.querySelector('[data-artifact-run]');
    if (runButton)
      runButton.onclick = async () => {
        if (dirty) return toast('Save changes before running.');
        runButton.disabled = true;
        preview.querySelector('[data-artifact-output]').hidden = false;
        view('output');
        output.textContent = 'Running in a restricted container…';
        try {
          const run = await api('/api/artifacts/' + file.id + '/run', {});
          if (current !== file || context !== key()) return;
          output.innerHTML = `<small>${run.timed_out ? 'Time limit reached' : 'Exit code: ' + run.exit_code}${run.truncated ? ' · Output shortened' : ''}</small><pre>${esc(run.output || '(No output)')}</pre>`;
        } catch (error) {
          if (current === file) output.textContent = error.message;
        } finally {
          runButton.disabled = false;
        }
      };
  }

  document.addEventListener('click', (event) => {
    const button = event.target.closest('[data-generated-file]');
    if (button) open(button.dataset.generatedFile).catch((error) => toast(error.message));
  });
  window.addEventListener('beforeunload', (event) => {
    if (!dirty) return;
    event.preventDefault();
    event.returnValue = '';
  });
  // Preserve a dirty editor during normal renders; warn before navigating away.
  const renderBeforeArtifacts = render;
  render = function () {
    if (current && current.context !== key()) {
      if (dirty) toast('Unsaved file changes were discarded when leaving the chat.');
      reset();
    }
    return renderBeforeArtifacts();
  };
  function leaveFile() {
    if (dirty && !confirm('Discard the unsaved changes to this file?')) return false;
    current = null;
    dirty = false;
    releaseEditor();
    releaseEditor = () => {};
    request++;
    return true;
  }
  document.addEventListener(
    'click',
    (event) => {
      const button = event.target.closest('button');
      if (!dirty || !button) return;
      if (
        button.dataset.thread ||
        button.dataset.course ||
        ['home', 'new', 'logout', 'staff'].includes(button.dataset.action)
      ) {
        if (!leaveFile()) {
          event.preventDefault();
          event.stopImmediatePropagation();
        }
      }
    },
    true,
  );
  return { list, open, reset, leaveFile };
})();
