/**
 * Envoltorio de Plotly con el aspecto del terminal.
 *
 * Plotly 2.35.2 va vendorizado, sin CDN. Los ejes temporales reciben la hora de
 * pared del mercado, nunca la del navegador.
 */

import { elemento } from './ui.js';

export const COLOR = {
  fondo: '#1e222d',
  borde: '#2a2e39',
  rejilla: '#252a36',
  texto: '#d1d4dc',
  tenue: '#787b86',
  acento: '#2962ff',
  sube: '#26a69a',
  baja: '#ef5350',
};

const CONFIG = { displayModeBar: false, responsive: true, scrollZoom: false, locale: 'es' };

const FUENTE = 'ui-monospace, SFMono-Regular, Menlo, Consolas, monospace';

/** Espera al bundle vendorizado. */
function listo() {
  if (window.Plotly) return Promise.resolve(window.Plotly);
  return new Promise((ok, fallo) => {
    let n = 0;
    const t = setInterval(() => {
      if (window.Plotly) { clearInterval(t); ok(window.Plotly); }
      else if ((n += 1) > 200) { clearInterval(t); fallo(new Error('Plotly no disponible')); }
    }, 50);
  });
}

function reajustar(nodo) {
  if (!nodo?.data || !nodo.isConnected || nodo.clientWidth < 1) return;
  window.Plotly?.Plots.resize(nodo);
}

// El observador cubre los cambios de ancho que no mueven la ventana; el oyente
// de resize cubre el giro del dispositivo sin depender del ciclo de render.
const observador = typeof ResizeObserver === 'undefined' ? null
  : new ResizeObserver((entradas) => { for (const e of entradas) reajustar(e.target); });

let rebote = null;
window.addEventListener('resize', () => {
  clearTimeout(rebote);
  rebote = setTimeout(() => {
    for (const n of document.querySelectorAll('.chart')) reajustar(n);
  }, 120);
});

function base(titulo, ejeY, altura) {
  return {
    title: {
      text: titulo ? titulo.toUpperCase() : '',
      font: { size: 11, color: COLOR.tenue, family: FUENTE },
      x: 0, xanchor: 'left', y: 1, yanchor: 'top', pad: { l: 6, t: 10 },
    },
    paper_bgcolor: COLOR.fondo,
    plot_bgcolor: COLOR.fondo,
    font: { family: FUENTE, color: COLOR.tenue, size: 10 },
    margin: { l: 52, r: 14, t: titulo ? 34 : 12, b: 34 },
    height: altura,
    hovermode: 'x unified',
    showlegend: false,
    xaxis: {
      showgrid: false, linecolor: COLOR.borde, zeroline: false,
      tickfont: { color: COLOR.tenue, size: 10 }, automargin: true,
    },
    yaxis: {
      title: ejeY ? { text: ejeY, font: { color: COLOR.tenue, size: 10 } } : undefined,
      gridcolor: COLOR.rejilla, zerolinecolor: COLOR.borde, zerolinewidth: 1,
      tickfont: { color: COLOR.tenue, size: 10 },
    },
    hoverlabel: {
      bgcolor: '#131722', bordercolor: COLOR.borde,
      font: { color: COLOR.texto, family: FUENTE, size: 11 },
    },
  };
}

/**
 * Crea el contenedor y dibuja en cuanto esta insertado en el documento.
 *
 * El nodo se devuelve antes de que quien lo pide lo inserte, asi que dibujar de
 * inmediato mediria un elemento desconectado y Plotly caeria a su ancho por
 * defecto. Se espera a un macrotask -- para entonces el DOM ya esta montado --
 * y se reajusta una vez mas por si el ancho todavia no era el definitivo.
 */
function lienzo(dibujar, altura) {
  const nodo = elemento('div', { clase: 'chart panel', style: `min-height:${altura}px` });
  listo()
    .then((Plotly) => new Promise((seguir) => { setTimeout(() => seguir(Plotly), 0); }))
    .then((Plotly) => {
      dibujar(Plotly, nodo);
      observador?.observe(nodo);
      setTimeout(() => reajustar(nodo), 0);
    })
    .catch((e) => { nodo.className = 'empty empty--error'; nodo.textContent = e.message; });
  return nodo;
}

/** Barras con color por signo. */
export function barras(x, y, { titulo, ejeY = '%', altura = 300, etiquetas = true } = {}) {
  return lienzo((Plotly, nodo) => {
    const l = base(titulo, ejeY, altura);
    l.bargap = 0.25;
    Plotly.newPlot(nodo, [{
      type: 'bar',
      x,
      y,
      marker: { color: y.map((v) => (Number(v) >= 0 ? COLOR.sube : COLOR.baja)) },
      text: etiquetas ? y.map((v) => (Number.isFinite(v) ? v.toFixed(2) : '')) : undefined,
      textposition: 'outside',
      textfont: { size: 9, color: COLOR.tenue },
      cliponaxis: false,
      hovertemplate: '%{x}  %{y:.2f}%<extra></extra>',
    }], l, CONFIG);
  }, altura);
}

/** Barras horizontales, para rankings. */
export function barrasH(y, x, { titulo, altura = 380 } = {}) {
  return lienzo((Plotly, nodo) => {
    const l = base(titulo, '', altura);
    l.margin.l = 120;
    l.hovermode = 'closest';
    l.yaxis.autorange = 'reversed';
    l.yaxis.gridcolor = 'rgba(0,0,0,0)';
    l.xaxis.gridcolor = COLOR.rejilla;
    l.xaxis.showgrid = true;
    l.xaxis.zeroline = true;
    l.xaxis.zerolinecolor = COLOR.borde;
    Plotly.newPlot(nodo, [{
      type: 'bar',
      orientation: 'h',
      x,
      y,
      marker: { color: x.map((v) => (Number(v) >= 0 ? COLOR.sube : COLOR.baja)) },
      text: x.map((v) => (Number.isFinite(v) ? `${v > 0 ? '+' : ''}${v.toFixed(2)}%` : '')),
      textposition: 'outside',
      textfont: { size: 9, color: COLOR.tenue },
      cliponaxis: false,
      hovertemplate: '%{y}  %{x:.2f}%<extra></extra>',
    }], l, CONFIG);
  }, altura);
}

/** Linea con marcadores y referencia opcional. */
export function linea(x, y, { titulo, ejeY = '%', altura = 230, referencia = null } = {}) {
  return lienzo((Plotly, nodo) => {
    const l = base(titulo, ejeY, altura);
    if (referencia !== null && Number.isFinite(referencia)) {
      l.shapes = [{
        type: 'line', xref: 'paper', x0: 0, x1: 1, y0: referencia, y1: referencia,
        line: { color: COLOR.acento, width: 1, dash: 'dot' },
      }];
    }
    Plotly.newPlot(nodo, [{
      type: 'scatter',
      mode: 'lines',
      x,
      y,
      line: { color: COLOR.acento, width: 1.6, shape: 'spline', smoothing: 0.4 },
      connectgaps: false,
      fill: 'tozeroy',
      fillcolor: 'rgba(41,98,255,.08)',
      hovertemplate: '%{x}  %{y:.2f}%<extra></extra>',
    }], l, CONFIG);
  }, altura);
}

/** Velas OHLC. */
export function velas(datos, { titulo = 'Precio', altura = 400 } = {}) {
  return lienzo((Plotly, nodo) => {
    const l = base(titulo, '', altura);
    l.xaxis.type = 'date';
    l.xaxis.rangeslider = { visible: false };
    l.hovermode = 'x';
    l.yaxis.side = 'right';
    l.margin.l = 14;
    l.margin.r = 58;
    Plotly.newPlot(nodo, [{
      type: 'candlestick',
      x: datos.x,
      open: datos.o,
      high: datos.h,
      low: datos.l,
      close: datos.c,
      increasing: { line: { color: COLOR.sube, width: 1 }, fillcolor: COLOR.sube },
      decreasing: { line: { color: COLOR.baja, width: 1 }, fillcolor: COLOR.baja },
    }], l, CONFIG);
  }, altura);
}

/**
 * Mapa de calor divergente.
 * `centro` a `null` produce una escala secuencial.
 */
export function mapaCalor(datos, {
  titulo, altura = 420, centro = 0, sufijo = '%', decimales = 2,
  etiquetas = true, escalaVisible = true, ejeY = '',
} = {}) {
  return lienzo((Plotly, nodo) => {
    const l = base(titulo, ejeY, altura);
    l.hovermode = 'closest';
    l.xaxis.side = 'top';
    // Con las categorias del eje X arriba, el eje Y se lee de arriba abajo:
    // la primera fila del array queda en la parte superior.
    l.yaxis.autorange = 'reversed';
    l.yaxis.gridcolor = 'rgba(0,0,0,0)';
    const escala = centro === null
      ? [[0, '#131722'], [1, COLOR.acento]]
      : [[0, COLOR.baja], [0.5, '#1b1f2b'], [1, COLOR.sube]];
    Plotly.newPlot(nodo, [{
      type: 'heatmap',
      x: datos.x,
      y: datos.y,
      z: datos.z,
      text: etiquetas ? datos.z.map((f) => f.map(
        (v) => (Number.isFinite(v) ? v.toFixed(decimales) : ''),
      )) : undefined,
      texttemplate: etiquetas ? '%{text}' : undefined,
      textfont: { size: 9, family: FUENTE },
      colorscale: escala,
      zmid: centro === null ? undefined : centro,
      showscale: escalaVisible,
      colorbar: { thickness: 8, outlinewidth: 0, tickfont: { size: 9, color: COLOR.tenue } },
      xgap: 1,
      ygap: 1,
      hoverongaps: false,
      hovertemplate: `%{y} · %{x}  %{z:.${decimales}f}${sufijo}<extra></extra>`,
    }], l, CONFIG);
  }, altura);
}
