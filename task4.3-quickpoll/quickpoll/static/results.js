// Live results over Server-Sent Events. Only textContent and element properties are written (no innerHTML).
(() => {
  const card = document.querySelector('[data-events]');
  const status = document.getElementById('live-status');
  const paused = () => {
    status.textContent = 'Live updates paused - refresh to update';
    status.className = 'live off';
  };

  const copyButton = document.getElementById('copy-link');
  const shareInput = document.getElementById('share-url');
  if (copyButton && shareInput) {
    copyButton.addEventListener('click', async () => {
      shareInput.select();
      try {
        await navigator.clipboard.writeText(shareInput.value);
        copyButton.textContent = 'Copied';
      } catch {
        copyButton.textContent = 'Press Ctrl+C';   // the clipboard API needs HTTPS outside localhost
      }
    });
  }

  if (!card || !('EventSource' in window)) {
    return;
  }
  const source = new EventSource(card.dataset.events);
  source.addEventListener('results', (event) => {
    const data = JSON.parse(event.data);
    document.getElementById('total').textContent = String(data.total);
    for (const option of data.options) {
      const row = card.querySelector(`[data-option="${Number(option.id)}"]`);
      if (!row) continue;
      row.querySelector('meter').value = option.percent;
      row.querySelector('.votes').textContent = `${option.votes} (${option.percent}%)`;
    }
    status.textContent = 'Live';
    status.className = 'live on';
  });
  source.addEventListener('unavailable', () => {
    source.close();
    paused();
  });
  source.onerror = paused;
})();
