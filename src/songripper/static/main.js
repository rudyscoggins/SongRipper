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
  syncSelectAll();
});

document.addEventListener('htmx:afterSwap', function (evt) {
  if (evt.target.id === 'alerts') {
    fadeOutAlerts(evt.target);
  }
  if (evt.target.id === 'staging-list') {
    updateApprovalButton();
    syncSelectAll();
  }
});


function updateApprovalButton() {
  const btn = document.getElementById('approve-btn');
  if (!btn) return;
  const hasTracks = document.querySelector('#staging-list tbody tr') !== null;
  btn.disabled = !hasTracks;
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
});
