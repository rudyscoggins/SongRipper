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
});

document.addEventListener('htmx:afterSwap', function (evt) {
  if (evt.target.id === 'alerts') {
    fadeOutAlerts(evt.target);
  }
  if (evt.target.id === 'staging-list') {
    updateApprovalButton();
  }
});

function updateApprovalButton() {
  const btn = document.getElementById('approve-btn');
  if (!btn) return;
  const hasTracks = document.querySelector('#staging-list tbody tr') !== null;
  btn.disabled = !hasTracks;
}
