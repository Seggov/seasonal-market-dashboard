/**
 * Arranque del panel.
 *
 * Lee el manifiesto y el informe del instrumento seleccionado y dibuja la vista
 * pedida. No hay calculo analitico ni controles de analisis: los numeros son el
 * resultado que Python escribio en el JSON.
 *
 * Las URL son relativas al documento, asi que el sitio funciona igual en la
 * raiz de un servidor local y bajo /seasonal-market-dashboard/ en Pages.
 */

import { RENDER, VISTAS } from './vistas.js';
import { cargando, elemento, error, isoCorta, numero } from './ui.js';

const $ = (sel) => document.querySelector(sel);
const nodos = {
  simbolos: $('#symbols'),
  meta: $('#meta'),
  vistas: $('#views'),
  vista: $('#view'),
  pie: $('#foot'),
};

const url = (rel) => new URL(rel, document.baseURI).href;

const estado = { manifiesto: null, simbolo: null, vista: 'resumen', informe: null };
const informes = new Map();

/* --------------------------------------------------------------- enrutado */

function leerRuta() {
  const bruto = window.location.hash.replace(/^#\/?/, '');
  const [simbolo, vista] = bruto.split('/').filter(Boolean).map(decodeURIComponent);
  return { simbolo: simbolo ?? null, vista: vista ?? null };
}

function escribirRuta(simbolo, vista, reemplazar = false) {
  const destino = `#/${encodeURIComponent(simbolo)}/${encodeURIComponent(vista)}`;
  if (window.location.hash === destino) return;
  if (reemplazar) window.history.replaceState(null, '', destino);
  else window.history.pushState(null, '', destino);
}

/* ------------------------------------------------------------------ chrome */

function pintarSimbolos() {
  nodos.simbolos.replaceChildren(...estado.manifiesto.assets.map((activo) => elemento('button', {
    type: 'button',
    'aria-current': String(activo.symbol === estado.simbolo),
    title: activo.nombre,
    texto: activo.symbol,
    onClick: () => ir(activo.symbol, estado.vista),
  })));
  const activo = nodos.simbolos.querySelector('[aria-current="true"]');
  activo?.scrollIntoView({ block: 'nearest', inline: 'nearest' });
}

function pintarVistas() {
  nodos.vistas.replaceChildren(...VISTAS.map((vista) => elemento('button', {
    type: 'button',
    'aria-current': String(vista.clave === estado.vista),
    texto: vista.titulo,
    onClick: () => ir(estado.simbolo, vista.clave),
  })));
}

function pintarMeta() {
  const activo = estado.manifiesto.assets.find((a) => a.symbol === estado.simbolo);
  const dato = (clave, valor) => elemento('span', { clase: 'meta__dato' }, [
    `${clave} `, elemento('b', { texto: valor }),
  ]);
  nodos.meta.replaceChildren(
    elemento('span', { clase: 'meta__simbolo', texto: activo.symbol }),
    elemento('span', { clase: 'meta__nombre', texto: activo.nombre }),
    dato('MERCADO', activo.mercado),
    dato('TF', activo.temporalidad),
    dato('TZ', activo.zonaHoraria),
    dato('RANGO', `${isoCorta(activo.primeraFecha)} → ${isoCorta(activo.ultimaFecha)}`),
    dato('N', numero(activo.filasValidas, 0)),
  );
}

/* ------------------------------------------------------------------ datos */

async function informeDe(simbolo) {
  if (informes.has(simbolo)) return informes.get(simbolo);
  const activo = estado.manifiesto.assets.find((a) => a.symbol === simbolo);
  if (!activo) throw new Error(`Instrumento no publicado: ${simbolo}`);
  const respuesta = await fetch(url(`data/${activo.report}`));
  if (!respuesta.ok) throw new Error(`No se pudo leer el informe (HTTP ${respuesta.status})`);
  const informe = await respuesta.json();
  informes.set(simbolo, informe);
  return informe;
}

/* ---------------------------------------------------------------- pintado */

async function render() {
  pintarSimbolos();
  pintarVistas();
  nodos.vista.replaceChildren(cargando());
  let informe;
  try {
    informe = await informeDe(estado.simbolo);
  } catch (e) {
    nodos.vista.replaceChildren(error(e.message));
    return;
  }
  estado.informe = informe;
  pintarMeta();
  const dibujar = RENDER[estado.vista];
  const activo = estado.manifiesto.assets.find((a) => a.symbol === estado.simbolo);
  try {
    nodos.vista.replaceChildren(dibujar({ vistas: informe.vistas, informe, activo }));
  } catch (e) {
    nodos.vista.replaceChildren(error(`No se pudo dibujar la vista: ${e.message}`));
  }
}

function ir(simbolo, vista) {
  escribirRuta(simbolo, vista);
  atender();
}

async function atender() {
  const ruta = leerRuta();
  const simbolos = estado.manifiesto.assets.map((a) => a.symbol);
  estado.simbolo = simbolos.includes(ruta.simbolo) ? ruta.simbolo : simbolos[0];
  estado.vista = RENDER[ruta.vista] ? ruta.vista : 'resumen';
  escribirRuta(estado.simbolo, estado.vista, true);
  await render();
}

/* -------------------------------------------------------------- arranque */

async function arrancar() {
  try {
    const respuesta = await fetch(url('data/manifest.json'), { cache: 'no-cache' });
    if (!respuesta.ok) throw new Error(`HTTP ${respuesta.status}`);
    estado.manifiesto = await respuesta.json();
  } catch (e) {
    nodos.vista.replaceChildren(error(
      `No se pudo cargar el índice de datos (${e.message}). `
      + 'Genere el sitio con "python tools/build_web.py" y sírvalo por HTTP.',
    ));
    return;
  }
  const generado = (estado.manifiesto.generatedAt ?? '').replace('T', ' ').replace('+00:00', ' UTC');
  nodos.pie.textContent = `${numero(estado.manifiesto.sourceRowCount, 0)} observaciones · `
    + `generado ${generado} · esquema v${estado.manifiesto.schemaVersion}`;
  window.addEventListener('hashchange', atender);
  await atender();
}

arrancar();
