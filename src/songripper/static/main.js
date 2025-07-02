console.log('loaded');

function fadeOutAlerts(container) {
  if (container && container.innerHTML.trim() !== '') {
    setTimeout(() => {
      container.innerHTML = '';
    }, 4000);
  }
}

document.addEventListener('DOMContentLoaded', function () {
  const alerts = document.getElementById('alerts');
  fadeOutAlerts(alerts);
  updateApprovalButton();
  document.body.addEventListener('click', fillMultiEditFromCell);
  document.body.addEventListener('click', handleAlbumArtClick);
  syncSelectAll();
});

document.addEventListener('htmx:responseError', function (evt) {
  const alerts = document.getElementById('alerts');
  if (!alerts) return;
  alerts.innerHTML = evt.detail.xhr.responseText;
  alerts.scrollIntoView({behavior: 'smooth'});
  fadeOutAlerts(alerts);
});

document.addEventListener('htmx:afterSwap', function (evt) {
  if (evt.detail && evt.detail.xhr && evt.detail.xhr.status >= 400) {
    evt.target.scrollIntoView({behavior: 'smooth'});
  }
  if (evt.target.id === 'alerts') {
    fadeOutAlerts(evt.target);
  }
  if (evt.target.id === 'staging-list') {
    updateApprovalButton();
    syncSelectAll();
  }
});


function updateApprovalButton() {
  const btnAll = document.getElementById('approve-btn');
  const btnSel = document.getElementById('approve-selected-btn');
  const hasTracks = document.querySelector('#staging-list tbody tr') !== null;
  if (btnAll) btnAll.disabled = !hasTracks;
  if (btnSel) {
    const anyChecked = document.querySelector('#staging-list input[name=track]:checked') !== null;
    btnSel.disabled = !anyChecked;
  }
}

function fillMultiEditFromCell(e) {
  const td = e.target.closest('td[data-field]');
  if (!td) return;
  const field = td.getAttribute('data-field');
  const form = document.getElementById('multi-edit');
  if (!form) return;
  const input = form.querySelector(`input[name="${field}_value"]`);
  const checkbox = form.querySelector(`input[name="${field}_enable"]`);
  if (input) input.value = td.textContent.trim();
  if (checkbox) checkbox.checked = true;
  form.scrollIntoView({behavior: 'smooth'});
  const row = td.closest('tr');
  if (row) {
    const trackBox = row.querySelector('input[name=track]');
    if (trackBox && !trackBox.checked) {
      trackBox.checked = true;
      syncSelectAll();
      updateApprovalButton();
    }
  }
}

function handleAlbumArtClick(e) {
  const img = e.target.closest('.album-art');
  if (!img) return;
  const row = img.closest('tr');
  if (!row) return;
  const form = document.getElementById('multi-edit');
  if (!form) return;
  const section = document.getElementById('online-art');
  if (section) section.hidden = false;
  const lookBtn = form.querySelector('#look-online-btn');
  if (lookBtn) lookBtn.disabled = false;
  const artistField = form.querySelector('#online-art input[name="artist"]');
  const albumField = form.querySelector('#online-art input[name="album"]');
  const fileField = form.querySelector('#online-art input[name="filepath"]');
  if (artistField) artistField.value = row.dataset.artist || '';
  if (albumField) albumField.value = row.dataset.album || '';
  if (fileField) fileField.value = row.dataset.filepath || '';
  const title = form.querySelector('#album-title');
  if (title) title.textContent = row.dataset.album || '';
  const artEnable = form.querySelector('input[name="art_enable"]');
  if (artEnable) artEnable.checked = true;
  form.scrollIntoView({behavior: 'smooth'});
}

function toggleAllTracks(checked) {
  document.querySelectorAll('#staging-list input[name=track]').forEach(cb => {
    cb.checked = checked;
  });
}

function syncSelectAll() {
  const selectAll = document.getElementById('select-all');
  if (!selectAll) return;
  const boxes = document.querySelectorAll('#staging-list input[name=track]');
  selectAll.checked = boxes.length > 0 && Array.from(boxes).every(cb => cb.checked);
}

document.addEventListener('change', function (e) {
  if (e.target.id === 'select-all') {
    toggleAllTracks(e.target.checked);
  } else if (e.target.matches('#staging-list input[name=track]')) {
    syncSelectAll();
  }
  if (e.target.id === 'select-all' || e.target.matches('#staging-list input[name=track]')) {
    updateApprovalButton();
  }
});
