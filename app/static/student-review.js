'use strict';

/** Read-only student workspace. Keep the staff identity/session throughout;
 * existing roster-scoped GET endpoints authorise and audit each opened record.
 * This view never mounts the student's composer, note editor or write controls.
 */
async function renderStudentWorkspaces(panel) {
  panel.innerHTML = '<p role="status">Loading student workspaces…</p>';
  try {
    const [records, savedNotes] = await Promise.all([
      api('/api/staff/records'),
      api('/api/staff/notes'),
    ]);
    if (!panel.isConnected || staffTab !== 'students') return;
    panel.innerHTML = `<h1>Student workspaces</h1><p class="muted">Read only · ${state.user.role === 'admin' ? 'Student accounts' : 'Students in your assigned classes'} · Record access is logged. You stay signed in as yourself.</p><label>Student<select aria-label="Review student" class="review-student">${staffRoster.students.map((u) => `<option value="${u.id}">${esc(u.name)} · @${esc(u.username)}</option>`).join('')}</select></label><div class="student-review-layout"><nav class="student-review-list" aria-label="Student chats and notes"></nav><section class="student-review-detail" aria-label="Read-only student content"></section></div>`;
    const select = panel.querySelector('.review-student');
    const list = panel.querySelector('.student-review-list');
    const detail = panel.querySelector('.student-review-detail');
    let request = 0;
    function chooseStudent() {
      request++;
      const uid = Number(select.value);
      const threads = records.threads.filter((t) => t.user_id === uid);
      const notes = savedNotes.notes.filter((n) => n.user_id === uid);
      list.innerHTML = `<h3>Chats</h3>${threads.map((t) => `<button type="button" data-workspace-review-chat="${esc(t.id)}">${esc(t.title)}<small>${esc(t.course_id)}</small></button>`).join('') || '<p>No accessible chats</p>'}<h3>Notes</h3>${notes.map((n) => `<button type="button" data-workspace-review-note="${esc(n.id)}">${esc(n.title)}<small>${esc(n.chat_title)}</small></button>`).join('') || '<p>No accessible notes</p>'}`;
      detail.innerHTML = '<p>Select a chat or note to view it.</p>';
    }
    select.onchange = chooseStudent;
    chooseStudent();
    list.onclick = async (event) => {
      const button = event.target.closest(
        '[data-workspace-review-chat],[data-workspace-review-note]',
      );
      if (!button) return;
      const turn = ++request;
      detail.innerHTML = '<p role="status">Opening read-only record…</p>';
      try {
        if (button.dataset.workspaceReviewChat) {
          const result = await api(
            '/api/staff/record/' + encodeURIComponent(button.dataset.workspaceReviewChat),
          );
          if (turn !== request || !detail.isConnected) return;
          detail.innerHTML = `<h2>${esc(result.thread.title)}</h2><p class="muted">${esc(result.thread.course_id)} · Read only</p>${result.messages.map((m) => `<article class="student-review-message"><strong>${m.role === 'user' ? esc(result.thread.student) : 'School Agent'}</strong><div>${replyTextHTML(m.content)}</div></article>`).join('') || '<p>No messages in this conversation.</p>'}`;
        } else {
          const result = await api(
            '/api/staff/notes/' + encodeURIComponent(button.dataset.workspaceReviewNote),
          );
          if (turn !== request || !detail.isConnected) return;
          const n = result.note;
          detail.innerHTML = `<h2>${esc(n.title)}</h2><p class="muted">${esc(n.chat_title)} · Read only</p><article class="student-review-note">${safeNoteHTML(n.body_html) || esc(n.body).replace(/\n/g, '<br>') || 'Empty note'}</article>`;
          detail.querySelector('.student-review-note').style.backgroundColor = n.colour;
        }
      } catch (err) {
        if (turn === request && detail.isConnected) detail.textContent = err.message;
      }
    };
  } catch (err) {
    if (panel.isConnected) panel.textContent = err.message;
  }
}
