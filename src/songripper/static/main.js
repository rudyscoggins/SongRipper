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
  attachSelectAllHandler();
});

document.addEventListener('htmx:afterSwap', function (evt) {
  if (evt.target.id === 'alerts') {
    fadeOutAlerts(evt.target);
  }
  if (evt.target.id === 'staging-list') {
    updateApprovalButton();
    attachSelectAllHandler();
  }
});

if (!window.htmx) {
  // Minimal fallback so inline editing works when the CDN script fails to load
  document.addEventListener('DOMContentLoaded', function () {
    document.body.addEventListener('click', function (e) {
      const td = e.target.closest('td[hx-get][hx-trigger="click"]');
      if (!td) return;
      fetch(td.getAttribute('hx-get'))
        .then(r => r.text())
        .then(html => {
          td.outerHTML = html;
        });
    });

    document.body.addEventListener('keydown', function (e) {
      if (e.key !== 'Enter') return;
      const input = e.target;
      if (!(input instanceof HTMLInputElement)) return;
      const form = input.form;
      if (!form || !form.hasAttribute('hx-put')) return;
      e.preventDefault();
      const data = new FormData(form);
      fetch(form.getAttribute('hx-put'), {
        method: 'PUT',
        body: data
      })
        .then(r => r.text())
        .then(html => {
          const td = form.closest('td');
          if (td) td.outerHTML = html;
        });
    });
  });
}

function updateApprovalButton() {
  const btn = document.getElementById('approve-btn');
  if (!btn) return;
  const hasTracks = document.querySelector('#staging-list tbody tr') !== null;
  btn.disabled = !hasTracks;
}

function attachSelectAllHandler() {
  const selectAll = document.getElementById('select-all');
  if (!selectAll) return;
  selectAll.addEventListener('change', function () {
    document
      .querySelectorAll('#staging-list input[name="track"]')
      .forEach(cb => {
        cb.checked = selectAll.checked;
      });
  });
}
