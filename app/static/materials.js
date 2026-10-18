'use strict';

/** Class and subject teaching-file library, publishing and passage navigation.
 * Chat previews delegate to the shared pocket; standalone library readers use a dialog.
 */
let materialLibrary = null,
  materialRequest = 0;
function materialRecords(data) {
  return (
    data.materials
      .map(
        (m) =>
          `<article class="teaching-file ${m.archived ? 'is-archived' : ''}"><div><b>${esc(m.name)}</b><small>${esc(m.course_id)} · ${m.page_count} ${m.unit_kind.toLowerCase()}${m.page_count === 1 ? '' : 's'} · ${m.class_id ? 'Class file' : 'Subject-wide'}${m.archived ? ' · Archived' : ''}</small></div><div class="material-actions"><button class="secondary" data-read-material="${esc(m.id)}">Read excerpts</button><a class="secondary" href="${esc(m.url)}" target="_blank" rel="noopener">Open file ↗</a>${m.can_manage ? `<button class="secondary" data-archive-material="${esc(m.id)}" data-archived="${m.archived ? '0' : '1'}">${m.archived ? 'Restore' : 'Archive'}</button>` : ''}</div></article>`,
      )
      .join('') || '<p class="muted">No teaching files have been shared for this selection.</p>'
  );
}
function materialUploadForm(data, code) {
  if (!data.can_upload) return '';
  return `<details class="material-upload"><summary>＋ Share a teaching file</summary><form id="material-upload-form" class="account-form"><div class="material-form-row"><label>Subject<select name="course_id" required>${data.courses.map((c) => `<option value="${esc(c.id)}" ${c.id === code ? 'selected' : ''}>${esc(c.id)} · ${esc(c.name)}</option>`).join('')}</select></label><label>Share with<select name="class_id" required></select></label></div><label>File<input type="file" name="file" accept=".pdf,.docx,.pptx,.txt,.md" required></label><p class="muted">PDF, PowerPoint, Word or text · up to 6 MB. Text-based PDFs retain page numbers; slides retain slide numbers. Word and text use section numbers.</p><button class="primary">Share file</button><p id="material-upload-status" role="status"></p></form></details>`;
}
async function materialMarkup(code = '') {
  const query = code ? '?course=' + encodeURIComponent(code) : '';
  return api('/api/course-materials' + query);
}
async function fillMaterialLibrary(root, code = '', asModal = false) {
  const request = ++materialRequest,
    owner = state.user?.id;
  const data = await materialMarkup(code);
  if (request !== materialRequest || state.user?.id !== owner || !root.isConnected) return;
  materialLibrary = { root, code, asModal };
  const courses = state.courses || [];
  root.innerHTML = `<p class="muted">Shared teaching files for your subjects and classes. Ask a question in that subject’s chat to use relevant passages.</p><label class="material-filter">Subject<select id="material-subject-filter"><option value="">All subjects</option>${courses.map((c) => `<option value="${esc(c.id)}" ${c.id === code ? 'selected' : ''}>${esc(c.id)} · ${esc(c.name)}</option>`).join('')}</select></label>${materialUploadForm(data, code)}<div id="teaching-file-list">${materialRecords(data)}</div>`;
  root.querySelector('#material-subject-filter').onchange = (e) =>
    fillMaterialLibrary(root, e.target.value, asModal).catch((err) => toast(err.message));
  const form = root.querySelector('#material-upload-form');
  if (!form) return;
  const classes = () => {
    const selected = form.elements.course_id.value;
    form.elements.class_id.innerHTML =
      (state.user.role === 'admin'
        ? '<option value="">All students enrolled in this subject</option>'
        : '') +
      data.groups
        .filter((g) => g.courses.includes(selected))
        .map((g) => `<option value="${g.id}">${esc(g.name)}</option>`)
        .join('');
    form.elements.class_id.required = state.user.role !== 'admin';
  };
  classes();
  form.elements.course_id.onchange = classes;
  form.onsubmit = async (e) => {
    e.preventDefault();
    const file = form.elements.file.files[0],
      button = form.querySelector('button'),
      status = root.querySelector('#material-upload-status');
    if (!file) return;
    if (file.size > 6 * 1024 * 1024) {
      status.textContent = 'Choose a file at most 6 MB.';
      return;
    }
    button.disabled = true;
    status.textContent = 'Reading and indexing the file…';
    try {
      const body = await new Promise((resolve, reject) => {
        const r = new FileReader();
        r.onload = () => resolve(r.result.split(',')[1]);
        r.onerror = reject;
        r.readAsDataURL(file);
      });
      const result = await api('/api/course-materials', {
        course_id: form.elements.course_id.value,
        class_id: form.elements.class_id.value ? Number(form.elements.class_id.value) : null,
        name: file.name,
        data: body,
      });
      toast(
        `Shared ${result.page_count} ${result.unit_kind.toLowerCase()}${result.page_count === 1 ? '' : 's'}.`,
      );
      await fillMaterialLibrary(root, form.elements.course_id.value, asModal);
    } catch (err) {
      status.textContent = err.message;
    } finally {
      button.disabled = false;
    }
  };
}
const sourcesBeforeTeachingFiles = sources;
sources = async function (sourceId) {
  if (sourceId) return sourcesBeforeTeachingFiles(sourceId);
  modal('Course library', '<div id="material-library-root">Loading teaching files…</div>');
  $('#modal').classList.add('course-library-dialog');
  try {
    await fillMaterialLibrary($('#material-library-root'), course()?.id || '', true);
  } catch (err) {
    $('#material-library-root').textContent = err.message;
  }
};
$('#modal').addEventListener('close', () => $('#modal').classList.remove('course-library-dialog'));
async function renderMaterialsWorkspace(root) {
  root.innerHTML = '<h1>Teaching files</h1><div id="material-library-root">Loading…</div>';
  await fillMaterialLibrary(root.querySelector('#material-library-root'));
}
async function readTeachingFile(id) {
  const data = await api('/api/course-materials/' + encodeURIComponent(id));
  const pages = [...new Map(data.passages.map((p) => [p.page, p.label])).entries()];
  modal(
    data.material.name,
    `<div class="material-reader-bar"><label>Location<select id="material-page">${pages.map(([n, label]) => `<option value="${n}">${esc(label)}</option>`).join('')}</select></label><a id="material-original" class="secondary" target="_blank" rel="noopener">Open original file ↗</a></div><p class="muted">${esc(data.material.course_id)}${data.material.archived ? ' · Archived from tutoring; kept for saved references' : ''}</p><div id="material-page-text" class="material-passage"></div>`,
  );
  $('#modal').classList.add('course-library-dialog');
  const show = () => {
    const page = Number($('#material-page').value);
    $('#material-page-text').textContent = data.passages
      .filter((p) => p.page === page)
      .map((p) => p.text)
      .join('\n\n');
    $('#material-original').href =
      data.material.url + (data.material.mime === 'application/pdf' ? '#page=' + page : '');
  };
  $('#material-page').onchange = show;
  show();
}
async function readTeachingPassage(id) {
  const data = await api('/api/course-materials/passages/' + encodeURIComponent(id));
  modal(
    data.material.name,
    `<p class="muted">${esc(data.material.course_id)} · ${esc(data.passage.label)}</p><div class="material-passage">${esc(data.passage.text)}</div><a class="secondary" href="${esc(data.material.url + (data.material.mime === 'application/pdf' ? '#page=' + data.passage.page : ''))}" target="_blank" rel="noopener">Open original file ↗</a>`,
  );
  $('#modal').classList.add('course-library-dialog');
}
document.addEventListener('click', async (e) => {
  const b = e.target.closest('button');
  if (!b) return;
  try {
    if (b.dataset.readMaterial) await readTeachingFile(b.dataset.readMaterial);
    else if (b.dataset.coursePassage) await readTeachingPassage(b.dataset.coursePassage);
    else if (b.dataset.archiveMaterial) {
      await api('/api/course-materials/' + b.dataset.archiveMaterial, {
        archived: b.dataset.archived === '1',
      });
      if (materialLibrary?.root.isConnected)
        await fillMaterialLibrary(
          materialLibrary.root,
          materialLibrary.code,
          materialLibrary.asModal,
        );
    }
  } catch (err) {
    toast(err.message);
  }
});
