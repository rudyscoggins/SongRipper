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
});

document.addEventListener('htmx:afterSwap', function (evt) {
  if (evt.target.id === 'alerts') {
    fadeOutAlerts(evt.target);
  }
});
