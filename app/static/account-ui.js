'use strict';

/** Account-owned pictures are saved independently of the password/name form.
 * The server validates and re-encodes uploads to a small metadata-free image.
 */
const accountSettingsBeforePicture = accountSettings;
accountSettings = function () {
  accountSettingsBeforePicture();
  const form = document.getElementById('self-account');
  const owner = state.user.id;
  const icons = ['', '🌱', '🌻', '🐱', '🦉', '🚀', '⭐'];
  form.insertAdjacentHTML(
    'afterbegin',
    `<section class="account-picture"><div data-account-picture-preview>${accountAvatarHTML()}</div><div><h3>Profile picture</h3><label class="secondary picture-upload">Upload picture<input type="file" accept="image/jpeg,image/png,image/webp" hidden data-avatar-upload></label><p class="muted">JPEG, PNG or WebP · up to 2 MB</p><div class="avatar-choices" role="group" aria-label="Profile icons">${icons.map((icon) => `<button type="button" data-avatar-icon="${esc(icon)}" aria-label="${icon ? 'Use ' + icon + ' icon' : 'Use initials'}">${icon || 'Initials'}</button>`).join('')}</div><small data-avatar-status role="status">Pictures and icons save immediately.</small></div></section>`,
  );
  const status = form.querySelector('[data-avatar-status]');
  let saving = false;
  async function save(value) {
    if (saving) return;
    saving = true;
    status.textContent = 'Saving profile picture…';
    try {
      const avatar = await api('/api/preferences/avatar', value);
      if (state.user?.id !== owner || !form.isConnected) return;
      state.avatar = avatar;
      refreshAccountIdentity();
      form.querySelector('[data-account-picture-preview]').innerHTML = accountAvatarHTML();
      status.textContent = 'Profile picture saved';
    } catch (err) {
      status.textContent = err.message;
    } finally {
      saving = false;
    }
  }
  for (const button of form.querySelectorAll('[data-avatar-icon]'))
    button.onclick = () => save({ icon: button.dataset.avatarIcon });
  form.querySelector('[data-avatar-upload]').onchange = async (event) => {
    const file = event.target.files[0];
    if (!file) return;
    if (file.size > 2 * 1024 * 1024) {
      status.textContent = 'Choose a picture under 2 MB';
      return;
    }
    try {
      const image = await new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(reader.result);
        reader.onerror = reject;
        reader.readAsDataURL(file);
      });
      await save({ image });
    } catch (_) {
      status.textContent = 'Could not read that picture';
    }
    event.target.value = '';
  };
};
