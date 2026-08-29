/**
 * Envoltorio de Plotly con la identidad visual del panel.
 *
 * Plotly se carga de forma diferida desde `assets/vendor/`, con version fijada
 * (2.35.2) y sin CDN: el sitio funciona sin acceso a terceros.
 *
 * Los ejes temporales reciben cadenas ISO SIN zona, construidas desde el epoch
 * local del mercado, para que Plotly las dibuje tal cual y no las desplace al
 * huso del navegador.
 */

import { elemento, ejeTemporal } from './ui.js';

export const COLORES = {
  azul: '#315b7d',
  verde: '#2f7d69',
  rojo: '#a75151',
  gris: '#73808c',
  arena: '#d5b36a',
};

const CONFIGURACION = {
  displayModeBar: false,
  responsive: true,
  locale: 'es',
  scrollZoom: false,
};

/** Espera a que el bundle vendorizado este disponible. */
export function listo() {
  if (window.Plotly) return Promise.resolve(window.Plotly);
  return new Promise((resolver, rechazar) => {
    let intentos = 0;
    const temporizador = setInterval(() => {
      if (window.Plotly) {
        clearInterval(temporizador);
        resolver(window.Plotly);
      } else if ((intentos += 1) > 200) {
        clearInterval(temporizador);
        rechazar(new Error('No se pudo cargar la biblioteca de gráficos.'));
      }
    }, 50);
  });
}

function paleta() {
  const estilo = getComputedStyle(document.documentElement);
  const leer = (nombre) => estilo.getPropertyValue(nombre).trim();
  return {
    superficie: leer('--superficie') || '#ffffff',
    superficie2: leer('--superficie-2') || '#edf2f5',
    tinta: leer('--tinta') || '#162b3a',
    tintaSuave: leer('--tinta-suave') || '#5e6f7b',
    borde: leer('--borde') || '#d8e0e5',
    rejilla: leer('--rejilla') || '#e7ecef',
    acento: leer('--acento') || '#2f6285',
  };
}

function disposicionBase(titulo, ejeY, altura) {
  const tema = paleta();
  return {
    title: { text: titulo, font: { size: 15, color: tema.tinta }, x: 0, xanchor: 'left' },
    paper_bgcolor: tema.superficie,
    plot_bgcolor: tema.superficie,
    font: { family: 'system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif', color: tema.tintaSuave, size: 12 },
    margin: { l: 52, r: 18, t: 44, b: 44 },
    height: altura,
    hovermode: 'x unified',
    showlegend: false,
    yaxis: {
      title: { text: ejeY, font: { color: tema.tintaSuave } },
      gridcolor: tema.rejilla,
      zerolinecolor: tema.borde,
      tickfont: { color: tema.tintaSuave },
    },
    xaxis: {
      showgrid: false,
      linecolor: tema.borde,
      tickfont: { color: tema.tintaSuave },
      automargin: true,
    },
    hoverlabel: { bgcolor: tema.superficie2, font: { color: tema.tinta }, bordercolor: tema.borde },
  };
}

/** Contenedor de un grafico; el dibujado ocurre cuando Plotly esta listo. */
function lienzo(dibujar, altura) {
  const nodo = elemento('div', { clase: 'grafico', style: `min-height:${altura}px` });
  listo()
    .then((Plotly) => dibujar(Plotly, nodo))
    .catch((error) => {
      nodo.classList.add('estado', 'estado--error');
      nodo.textContent = error.message;
    });
  return nodo;
}

/** Barras verdes/rojas segun el signo. */
export function barras(x, y, { titulo, ejeY = 'Retorno (%)', altura = 380, etiquetas = null } = {}) {
  return lienzo((Plotly, nodo) => {
    const tema = paleta();
    const colores = y.map((valor) => (Number(valor) >= 0 ? COLORES.verde : COLORES.rojo));
    const disposicion = disposicionBase(titulo, ejeY, altura);
    disposicion.bargap = 0.22;
    disposicion.shapes = [{
      type: 'line', xref: 'paper', x0: 0, x1: 1, y0: 0, y1: 0,
      line: { color: tema.borde, width: 1 },
    }];
    Plotly.newPlot(nodo, [{
      type: 'bar',
      x,
      y,
      marker: { color: colores },
      text: etiquetas ?? y.map((valor) => (Number.isFinite(valor) ? `${valor.toFixed(2)}%` : '')),
      textposition: 'outside',
      cliponaxis: false,
      hovertemplate: '%{x}<br>%{y:.2f}%<extra></extra>',
    }], disposicion, CONFIGURACION);
  }, altura);
}

/** Serie de linea con marcadores y linea de promedio opcional. */
export function linea(x, y, { titulo, ejeY = 'Retorno (%)', altura = 330, promedio = null, ejeFechas = false } = {}) {
  return lienzo((Plotly, nodo) => {
    const tema = paleta();
    const disposicion = disposicionBase(titulo, ejeY, altura);
    if (ejeFechas) disposicion.xaxis.type = 'date';
    disposicion.shapes = [{
      type: 'line', xref: 'paper', x0: 0, x1: 1, y0: 0, y1: 0,
      line: { color: tema.borde, width: 1 },
    }];
    if (promedio !== null && Number.isFinite(promedio)) {
      disposicion.shapes.push({
        type: 'line', xref: 'paper', x0: 0, x1: 1, y0: promedio, y1: promedio,
        line: { color: COLORES.arena, width: 1.5, dash: 'dash' },
      });
      disposicion.annotations = [{
        xref: 'paper', x: 0, y: promedio, xanchor: 'left', yanchor: 'bottom',
        text: `Promedio ${promedio.toFixed(2)}%`, showarrow: false,
        font: { size: 11, color: COLORES.arena },
      }];
    }
    Plotly.newPlot(nodo, [{
      type: 'scatter',
      mode: 'lines+markers',
      x,
      y,
      line: { color: tema.acento, width: 2 },
      marker: { size: 4 },
      connectgaps: false,
      hovertemplate: '%{x}<br>%{y:.2f}%<extra></extra>',
    }], disposicion, CONFIGURACION);
  }, altura);
}

/** Grafico de velas OHLC. */
export function velas(datos, { titulo = 'Evolución del precio', altura = 430 } = {}) {
  return lienzo((Plotly, nodo) => {
    const disposicion = disposicionBase(titulo, 'Precio', altura);
    disposicion.xaxis.type = 'date';
    disposicion.xaxis.rangeslider = { visible: false };
    disposicion.hovermode = 'x';
    Plotly.newPlot(nodo, [{
      type: 'candlestick',
      x: datos.lt.map(ejeTemporal),
      open: datos.o,
      high: datos.h,
      low: datos.l,
      close: datos.c,
      increasing: { line: { color: COLORES.verde }, fillcolor: COLORES.verde },
      decreasing: { line: { color: COLORES.rojo }, fillcolor: COLORES.rojo },
      name: 'OHLC',
    }], disposicion, CONFIGURACION);
  }, altura);
}

/**
 * Mapa de calor divergente (o secuencial para conteos).
 * @param {{x: string[], y: string[], z: (number|null)[][]}} datos
 */
export function mapaCalor(datos, {
  titulo, altura = 620, centro = 0, sufijo = '%', decimales = 2,
  ejeX = '', ejeY = '', etiquetaColor = '', mostrarEscala = true,
} = {}) {
  return lienzo((Plotly, nodo) => {
    const tema = paleta();
    const escala = centro === null
      ? [[0, tema.superficie2], [1, tema.acento]]
      : [[0, COLORES.rojo], [0.5, tema.superficie2], [1, COLORES.verde]];
    const disposicion = disposicionBase(titulo, ejeY, altura);
    disposicion.xaxis.title = { text: ejeX, font: { color: tema.tintaSuave } };
    disposicion.hovermode = 'closest';
    const textos = datos.z.map((fila) => fila.map(
      (valor) => (Number.isFinite(valor) ? `${valor.toFixed(decimales)}${sufijo}` : ''),
    ));
    Plotly.newPlot(nodo, [{
      type: 'heatmap',
      x: datos.x,
      y: datos.y,
      z: datos.z,
      text: textos,
      texttemplate: '%{text}',
      textfont: { size: 10 },
      colorscale: escala,
      zmid: centro === null ? undefined : centro,
      showscale: mostrarEscala,
      colorbar: { title: { text: etiquetaColor, side: 'right' }, thickness: 12 },
      hoverongaps: false,
      hovertemplate: `%{x}<br>%{y}<br>%{z:.${decimales}f}${sufijo}<extra></extra>`,
    }], disposicion, CONFIGURACION);
  }, altura);
}

/** Redibuja todos los graficos visibles tras un cambio de tema. */
export function repintar() {
  if (!window.Plotly) return;
  for (const nodo of document.querySelectorAll('.grafico')) {
    if (!nodo.data) continue;
    const tema = paleta();
    window.Plotly.relayout(nodo, {
      paper_bgcolor: tema.superficie,
      plot_bgcolor: tema.superficie,
      'title.font.color': tema.tinta,
      'font.color': tema.tintaSuave,
      'xaxis.linecolor': tema.borde,
      'xaxis.tickfont.color': tema.tintaSuave,
      'yaxis.gridcolor': tema.rejilla,
      'yaxis.zerolinecolor': tema.borde,
      'yaxis.tickfont.color': tema.tintaSuave,
      'hoverlabel.bgcolor': tema.superficie2,
      'hoverlabel.font.color': tema.tinta,
      'hoverlabel.bordercolor': tema.borde,
    });
  }
}
