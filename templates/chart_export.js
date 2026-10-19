/* Graph-only PNG export — runs after app.js, for every chart in every page. */
(() => {
  'use strict';
  const root = document.getElementById('wrap');
  if (!root) return;

  // Inline the SVG's COMPUTED styles: the on-screen chart relies on app.css
  // classes and CSS custom properties, which aren't available to a saved PNG.
  // Don't copy event handlers or charts' transient hover/focus graphics.
  const SVG_STYLES = [
    'fill', 'fill-opacity', 'fill-rule', 'stroke', 'stroke-width',
    'stroke-opacity', 'stroke-linecap', 'stroke-linejoin', 'stroke-dasharray',
    'stroke-dashoffset', 'opacity', 'font-family', 'font-size', 'font-weight',
    'font-style', 'letter-spacing', 'text-anchor', 'dominant-baseline',
    'visibility', 'paint-order', 'vector-effect', 'shape-rendering',
    'text-rendering'
  ];

  function chartFilename(box) {
    const page = box.closest('.page');
    const heading = box.closest('.card')?.querySelector('.card-head h3')?.textContent ||
      box.closest('section')?.querySelector('h2')?.textContent || 'Chart';
    const selection = box.closest('.card')?.querySelector('select option:checked')?.textContent || '';
    const name = [page?.id, heading, selection]
      .filter(Boolean).join('_').normalize('NFKD')
      .replace(/[^a-zA-Z0-9\u00C0-\uFFFF_-]+/g, '_').replace(/_+/g, '_')
      .replace(/^_|_$/g, '').slice(0, 115);
    return (name || 'SOE_chart') + '.png';
  }

  async function pngFromSVG(svg) {
    const originalViewBox = svg.viewBox && svg.viewBox.baseVal;
    const rect = svg.getBoundingClientRect();
    const width = originalViewBox?.width || parseFloat(svg.getAttribute('width')) || rect.width;
    const height = originalViewBox?.height || parseFloat(svg.getAttribute('height')) || rect.height;
    if (!(width > 0 && height > 0)) throw new Error('Chart has no visible dimensions');
    const scale = Math.min(3, 8192 / Math.max(width, height), 50000000 / (width * height));
    const output = document.createElement('canvas');
    output.width = Math.max(1, Math.round(width * scale));
    output.height = Math.max(1, Math.round(height * scale));
    const clone = svg.cloneNode(true);
    clone.setAttribute('xmlns', 'http://www.w3.org/2000/svg');
    clone.setAttribute('width', String(width));
    clone.setAttribute('height', String(height));
    if (!clone.getAttribute('viewBox')) clone.setAttribute('viewBox', `0 0 ${width} ${height}`);
    const nodes = [svg, ...svg.querySelectorAll('*')];
    const copied = [clone, ...clone.querySelectorAll('*')];
    for (let i = 0; i < nodes.length; i++) {
      const style = window.getComputedStyle(nodes[i]);
      for (const prop of SVG_STYLES) {
        const value = style.getPropertyValue(prop);
        if (value) copied[i].style.setProperty(prop, value);
      }
    }
    // Omit hit areas, which are for tooltips and should not be drawn to PNG.
    clone.querySelectorAll('.hit, .xhair').forEach((node) => node.remove());
    const documentElement = clone.ownerDocument;
    const background = documentElement.createElementNS('http://www.w3.org/2000/svg','rect');
    background.setAttribute('x', '0'); background.setAttribute('y', '0');
    background.setAttribute('width','100%'); background.setAttribute('height','100%');
    background.setAttribute('fill','#ffffff');
    clone.insertBefore(background, clone.firstChild);
    const svgText = new XMLSerializer().serializeToString(clone);
    const svgURL = URL.createObjectURL(new Blob([svgText], { type: 'image/svg+xml;charset=utf-8' }));
    try {
      const image = new Image();
      await new Promise((resolve, reject) => {
        image.onload = resolve;
        image.onerror = () => reject(new Error('Browser could not render the chart image'));
        image.src = svgURL;
      });
      const ctx = output.getContext('2d');
      if (!ctx) throw new Error('Canvas rendering unavailable');
      ctx.fillStyle = '#ffffff'; ctx.fillRect(0, 0, output.width, output.height);
      ctx.drawImage(image, 0, 0, output.width, output.height);
      return await new Promise((resolve, reject) => {
        output.toBlob((b) => b ? resolve(b) : reject(new Error('PNG export failed')), 'image/png');
      });
    } finally { URL.revokeObjectURL(svgURL); }
  }

  async function saveChart(box, button) {
    const svg = box.querySelector(':scope > svg');
    if (!svg) return;
    const name = chartFilename(box);
    button.disabled = true;
    button.setAttribute('aria-busy', 'true');
    try {
      const blob = await pngFromSVG(svg);
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url; a.download = name;
      document.body.appendChild(a); a.click(); a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 30000);
    } catch (err) {
      console.error('SOE chart export:', err);
      const previous = button.title;
      button.title = `PNG export unavailable: ${err.message}`;
      setTimeout(() => { button.title = previous; }, 4500);
    } finally {
      button.disabled = false;
      button.removeAttribute('aria-busy');
    }
  }

  const icon = '<svg xmlns="http://www.w3.org/2000/svg" aria-hidden="true" viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3v12m-4-4 4 4 4-4"/><path d="M4 17v4h16v-4"/></svg>';
  function addButtons() {
    root.querySelectorAll('.chart').forEach((box) => {
      const hasChart = Boolean(box.querySelector(':scope > svg'));
      const existing = box.querySelector(':scope > .chart-save-png');
      if (!hasChart) { if (existing) existing.remove(); return; }
      if (existing) return;
      const button = document.createElement('button');
      button.type = 'button'; button.className = 'chart-save-png';
      button.setAttribute('aria-label', 'Download this chart as PNG');
      button.title = 'Download chart as PNG';
      button.innerHTML = icon;
      button.addEventListener('pointerenter', () => {
        const tip = document.getElementById('tip');
        if (tip) tip.hidden = true;
      });
      button.addEventListener('click', (event) => {
        event.preventDefault(); event.stopPropagation(); saveChart(box, button);
      });
      box.appendChild(button);
    });
  }

  // Charts are re-created on page navigation, year/SOE selection and uploads.
  // Observing their parent retains the button without changing chart renderers.
  let scheduled = false;
  const observer = new MutationObserver(() => {
    if (scheduled) return;
    scheduled = true;
    requestAnimationFrame(() => { scheduled = false; addButtons(); });
  });
  observer.observe(root, { childList: true, subtree: true });
  addButtons();
})();
