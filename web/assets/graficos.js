/**
 * Envoltorio de Plotly con el aspecto del terminal.
 *
 * Cada grafico se entrega dentro de una tarjeta con cabecera propia en HTML, no
 * como titulo dibujado dentro del SVG: asi la tipografia es la misma que la del
 * resto de la pagina y el lienzo aprovecha toda su altura.
 *
 * Plotly 2.35.2 va vendorizado, sin CDN. Los ejes temporales reciben la hora de
 * pared del mercado, nunca la del navegador.
 */

import { elemento } from './ui.js';

export const COLOR = {
  fondo: '#1e222d',
  borde: '#2a2e39',
  rejilla: '#242833',
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
  aplicarEtiquetas(nodo);
}

/**
 * Muestra el valor dentro de cada celda solo si la celda es lo bastante ancha.
 *
 * Plotly no recorta ni oculta el texto de un mapa de calor que no cabe: lo
 * superpone. Con muchas columnas en una pantalla estrecha eso es ilegible, asi
 * que la decision se rehace en cada reajuste.
 */
function aplicarEtiquetas(nodo) {
  const cfg = nodo.__etiquetas;
  if (!cfg || !window.Plotly) return;
  const cabe = nodo.clientWidth / cfg.columnas >= cfg.anchoMinimo;
  if (cabe === cfg.visibles) return;
  cfg.visibles = cabe;
  window.Plotly.restyle(nodo, {
    text: [cabe ? cfg.textos : null],
    texttemplate: cabe ? '%{text}' : null,
  }, [0]);
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

/** Guias verticales al pasar el cursor, como en un terminal de mercado. */
function guias(eje) {
  return {
    ...eje,
    showspikes: true,
    spikemode: 'across',
    spikesnap: 'cursor',
    spikethickness: 1,
    spikedash: 'dot',
    spikecolor: '#4a5162',
  };
}

function base(ejeY, altura) {
  return {
    paper_bgcolor: COLOR.fondo,
    plot_bgcolor: COLOR.fondo,
    font: { family: FUENTE, color: COLOR.tenue, size: 10 },
    margin: { l: 50, r: 14, t: 14, b: 30 },
    height: altura,
    hovermode: 'x unified',
    showlegend: false,
    xaxis: guias({
      showgrid: false,
      linecolor: COLOR.borde,
      zeroline: false,
      tickfont: { color: COLOR.tenue, size: 10 },
      automargin: true,
    }),
    yaxis: {
      title: ejeY ? { text: ejeY, font: { color: COLOR.tenue, size: 10 } } : undefined,
      gridcolor: COLOR.rejilla,
      zerolinecolor: '#3d4452',
      zerolinewidth: 1,
      tickfont: { color: COLOR.tenue, size: 10 },
    },
    hoverlabel: {
      bgcolor: '#0f1319',
      bordercolor: '#3d4452',
      font: { color: COLOR.texto, family: FUENTE, size: 11 },
      align: 'left',
    },
    transition: { duration: 0 },
  };
}

/**
 * Espera a que el lienzo tenga un ancho real antes de dibujar.
 *
 * El nodo se devuelve antes de que quien lo pide lo inserte en el documento, y
 * Plotly fija el tamano del SVG en el momento del `newPlot`: medir un elemento
 * todavia desconectado, o con ancho cero, deja el grafico encogido para
 * siempre. Sondear el ancho es fiable en cualquier entorno, a diferencia de
 * `requestAnimationFrame`, que no corre si la pestana no compone fotogramas.
 */
function esperarAncho(nodo, intentos = 60) {
  return new Promise((listo) => {
    let restantes = intentos;
    const mirar = () => {
      if (nodo.isConnected && nodo.clientWidth > 0) listo(true);
      else if ((restantes -= 1) <= 0) listo(false);
      else setTimeout(mirar, 16);
    };
    mirar();
  });
}

/**
 * Marca con un contorno la celda del mapa de calor bajo el cursor.
 *
 * Plotly no resalta la celda apuntada, y en una rejilla de mas de cien celdas
 * cuesta saber cual esta describiendo el tooltip. Con ejes categoricos la
 * coordenada de cada celda es su indice, asi que basta un rectangulo de media
 * celda a cada lado.
 */
function resaltarCelda(Plotly, nodo) {
  const limpiar = () => Plotly.relayout(nodo, { shapes: [] });
  nodo.on('plotly_hover', (evento) => {
    const punto = evento.points?.[0];
    if (!punto || !Array.isArray(punto.pointIndex)) return;
    const [fila, columna] = punto.pointIndex;
    Plotly.relayout(nodo, {
      shapes: [{
        type: 'rect',
        x0: columna - 0.5, x1: columna + 0.5,
        y0: fila - 0.5, y1: fila + 0.5,
        line: { color: '#e9ecf2', width: 1.5 },
        fillcolor: 'rgba(0,0,0,0)',
        layer: 'above',
      }],
    });
  });
  nodo.on('plotly_unhover', limpiar);
  nodo.addEventListener('mouseleave', limpiar);
}

/**
 * Tarjeta con cabecera y lienzo.
 */
function tarjeta(dibujar, altura, titulo, unidad) {
  const lienzo = elemento('div', { clase: 'chart', style: `min-height:${altura}px` });
  const nodo = elemento('figure', { clase: 'card' }, [
    titulo ? elemento('figcaption', { clase: 'card__head' }, [
      elemento('span', { clase: 'card__title', texto: titulo }),
      unidad ? elemento('span', { clase: 'card__unit', texto: unidad }) : null,
    ]) : null,
    lienzo,
  ]);
  listo()
    .then(async (Plotly) => {
      await esperarAncho(lienzo);
      dibujar(Plotly, lienzo);
      observador?.observe(lienzo);
      setTimeout(() => reajustar(lienzo), 0);
    })
    .catch((e) => { nodo.className = 'empty empty--error'; nodo.textContent = e.message; });
  return nodo;
}

/** Barras con color por signo. */
export function barras(x, y, { titulo, unidad = '%', altura = 280, etiquetas = true } = {}) {
  return tarjeta((Plotly, nodo) => {
    const l = base('', altura);
    l.bargap = 0.3;
    Plotly.newPlot(nodo, [{
      type: 'bar',
      x,
      y,
      marker: {
        color: y.map((v) => (Number(v) >= 0 ? COLOR.sube : COLOR.baja)),
        line: { width: 0 },
      },
      text: etiquetas ? y.map((v) => (Number.isFinite(v) ? v.toFixed(2) : '')) : undefined,
      textposition: 'outside',
      textfont: { size: 9, color: COLOR.tenue },
      cliponaxis: false,
      hovertemplate: '%{y:.2f}%<extra></extra>',
    }], l, CONFIG);
  }, altura, titulo, unidad);
}

/** Barras horizontales, para rankings. */
export function barrasH(y, x, { titulo, unidad = '%', altura = 380 } = {}) {
  return tarjeta((Plotly, nodo) => {
    const l = base('', altura);
    l.margin.l = 116;
    l.hovermode = 'closest';
    l.yaxis.autorange = 'reversed';
    l.yaxis.gridcolor = 'rgba(0,0,0,0)';
    l.xaxis = {
      ...l.xaxis,
      showspikes: false,
      showgrid: true,
      gridcolor: COLOR.rejilla,
      zeroline: true,
      zerolinecolor: '#3d4452',
    };
    Plotly.newPlot(nodo, [{
      type: 'bar',
      orientation: 'h',
      x,
      y,
      marker: { color: x.map((v) => (Number(v) >= 0 ? COLOR.sube : COLOR.baja)) },
      text: x.map((v) => (Number.isFinite(v) ? `${v > 0 ? '+' : ''}${v.toFixed(2)}%` : '')),
      textposition: 'outside',
      textfont: { size: 10, color: COLOR.texto },
      cliponaxis: false,
      hovertemplate: '<b>%{y}</b>   %{x:.2f}%<extra></extra>',
    }], l, CONFIG);
  }, altura, titulo, unidad);
}

/** Linea con area y referencia opcional. */
export function linea(x, y, {
  titulo, unidad = '%', altura = 210, referencia = null, compacta = false,
} = {}) {
  return tarjeta((Plotly, nodo) => {
    const l = base('', altura);
    if (compacta) { l.margin.l = 38; l.margin.b = 24; l.margin.t = 10; }
    if (referencia !== null && Number.isFinite(referencia)) {
      l.shapes = [{
        type: 'line', xref: 'paper', x0: 0, x1: 1, y0: referencia, y1: referencia,
        line: { color: '#f2c14e', width: 1, dash: 'dot' },
      }];
    }
    Plotly.newPlot(nodo, [{
      type: 'scatter',
      mode: 'lines',
      x,
      y,
      line: { color: COLOR.acento, width: 1.8, shape: 'spline', smoothing: 0.5 },
      connectgaps: false,
      fill: 'tozeroy',
      fillcolor: 'rgba(41,98,255,.10)',
      hovertemplate: '%{y:.2f}%<extra></extra>',
    }], l, CONFIG);
  }, altura, titulo, unidad);
}

/** Velas OHLC. */
export function velas(datos, { titulo = 'Precio', unidad = '', altura = 400 } = {}) {
  return tarjeta((Plotly, nodo) => {
    const l = base('', altura);
    l.xaxis.type = 'date';
    l.xaxis.rangeslider = { visible: false };
    l.hovermode = 'x';
    l.yaxis.side = 'right';
    l.yaxis.showspikes = true;
    l.yaxis.spikemode = 'across';
    l.yaxis.spikethickness = 1;
    l.yaxis.spikedash = 'dot';
    l.yaxis.spikecolor = '#4a5162';
    l.margin.l = 10;
    l.margin.r = 60;
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
  }, altura, titulo, unidad);
}

/**
 * Mapa de calor divergente.
 * `centro` a `null` produce una escala secuencial.
 */
export function mapaCalor(datos, {
  titulo, unidad = '%', altura = 420, centro = 0, decimales = 2,
  etiquetas = true, escalaVisible = true, tamanoTexto = 10, anchoMinimoCelda = 54,
} = {}) {
  return tarjeta((Plotly, nodo) => {
    const l = base('', altura);
    l.hovermode = 'closest';
    l.margin = { l: 52, r: escalaVisible ? 8 : 14, t: 22, b: 8 };
    l.xaxis = {
      ...l.xaxis,
      showspikes: false,
      side: 'top',
      linecolor: 'rgba(0,0,0,0)',
      tickfont: { color: COLOR.texto, size: 10 },
      ticks: '',
    };
    // Con las categorias del eje X arriba, el eje Y se lee de arriba abajo:
    // la primera fila del array queda en la parte superior.
    l.yaxis = {
      autorange: 'reversed',
      gridcolor: 'rgba(0,0,0,0)',
      linecolor: 'rgba(0,0,0,0)',
      zeroline: false,
      ticks: '',
      tickfont: { color: COLOR.tenue, size: 10 },
    };
    const escala = centro === null
      ? [[0, '#161a23'], [1, COLOR.acento]]
      : [
        [0, '#c0392b'], [0.25, '#7d3038'], [0.5, '#1c2029'],
        [0.75, '#1f6b62'], [1, '#1fae9a'],
      ];

    const textos = etiquetas ? datos.z.map((fila) => fila.map(
      (v) => (Number.isFinite(v) ? `${v > 0 ? '+' : ''}${v.toFixed(decimales)}${unidad}` : ''),
    )) : null;
    const caben = textos !== null
      && nodo.clientWidth / Math.max(1, datos.x.length) >= anchoMinimoCelda;
    if (textos !== null) {
      nodo.__etiquetas = {
        textos, columnas: datos.x.length, anchoMinimo: anchoMinimoCelda, visibles: caben,
      };
    }

    Plotly.newPlot(nodo, [{
      type: 'heatmap',
      x: datos.x,
      y: datos.y,
      z: datos.z,
      text: caben ? textos : undefined,
      texttemplate: caben ? '%{text}' : undefined,
      textfont: { size: tamanoTexto, family: FUENTE, color: '#e9ecf2' },
      colorscale: escala,
      zmid: centro === null ? undefined : centro,
      showscale: escalaVisible,
      colorbar: {
        thickness: 6,
        outlinewidth: 0,
        len: 0.9,
        tickfont: { size: 9, color: COLOR.tenue },
        ticks: '',
      },
      xgap: 2,
      ygap: 2,
      hoverongaps: false,
      hovertemplate:
        `<b>%{x} · %{y}</b><br>%{z:.${decimales}f}${unidad}<extra></extra>`,
    }], l, CONFIG).then(() => resaltarCelda(Plotly, nodo));
  }, altura, titulo, unidad);
}
