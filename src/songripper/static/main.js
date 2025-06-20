console.log('loaded');

document.addEventListener('DOMContentLoaded', function () {
  const params = new URLSearchParams(window.location.search);
  const msg = params.get('msg');
  if (msg) {
    alert(msg.replace(/\+/g, ' '));
  }
});
