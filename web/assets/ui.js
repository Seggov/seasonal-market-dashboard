/**
 * Utilidades de presentacion.
 *
 * El formato numerico y de fechas es independiente de la configuracion
 * regional y de la zona horaria del navegador: las marcas llegan como epoch
 * local del mercado y se convierten con aritmetica civil exacta.
 */

const SEGUNDOS_DIA = 86400;

export const MESES = ['ENE', 'FEB', 'MAR', 'ABR', 'MAY', 'JUN',
  'JUL', 'AGO', 'SEP', 'OCT', 'NOV', 'DIC'];

export const DIAS = ['LUN', 'MAR', 'MIE', 'JUE', 'VIE', 'SAB', 'DOM'];

/** Fecha civil proleptica desde el numero de dias (algoritmo de Hinnant). */
export function fechaDesdeDias(dias) {
  const z = dias + 719468;
  const era = Math.floor(z / 146097);
  const diaDeEra = z - era * 146097;
  const añoDeEra = Math.floor(
    (diaDeEra - Math.floor(diaDeEra / 1460) + Math.floor(diaDeEra / 36524)
      - Math.floor(diaDeEra / 146096)) / 365,
  );
  const año = añoDeEra + era * 400;
  const diaDeAño = diaDeEra - (365 * añoDeEra + Math.floor(añoDeEra / 4)
    - Math.floor(añoDeEra / 100));
  const mp = Math.floor((5 * diaDeAño + 2) / 153);
  const dia = diaDeAño - Math.floor((153 * mp + 2) / 5) + 1;
  const mes = mp < 10 ? mp + 3 : mp - 9;
  return { año: mes <= 2 ? año + 1 : año, mes, dia };
}

/** Campos de calendario del mercado a partir de su epoch local. */
export function camposLocales(epochLocal) {
  const dias = Math.floor(epochLocal / SEGUNDOS_DIA);
  const { año, mes, dia } = fechaDesdeDias(dias);
  const resto = epochLocal - dias * SEGUNDOS_DIA;
  return {
    año, mes, dia,
    hora: Math.floor(resto / 3600),
    minuto: Math.floor((resto % 3600) / 60),
  };
}

const dos = (valor) => String(valor).padStart(2, '0');

/** `2025-04-09` en hora del mercado. */
export function fechaCorta(epochLocal) {
  if (!Number.isFinite(epochLocal)) return '';
  const { año, mes, dia } = camposLocales(epochLocal);
  return `${año}-${dos(mes)}-${dos(dia)}`;
}

/** `2025-04-09 09:30` en hora del mercado. */
export function fechaHora(epochLocal) {
  if (!Number.isFinite(epochLocal)) return '';
  const { hora, minuto } = camposLocales(epochLocal);
  return `${fechaCorta(epochLocal)} ${dos(hora)}:${dos(minuto)}`;
}

/**
 * Cadena ISO SIN zona a partir del epoch local del mercado.
 * Plotly la dibuja como hora de pared y no la desplaza al huso del navegador.
 */
export function ejeTemporal(epochLocal) {
  const { año, mes, dia, hora, minuto } = camposLocales(epochLocal);
  return `${año}-${dos(mes)}-${dos(dia)}T${dos(hora)}:${dos(minuto)}:00`;
}

/** Recorta una marca ISO a `YYYY-MM-DD`. */
export function isoCorta(texto) {
  return typeof texto === 'string' ? texto.slice(0, 10) : '';
}

function millares(entero) {
  return entero.replace(/\B(?=(\d{3})+(?!\d))/g, ',');
}

/** Numero con separador de millar y decimales fijos. */
export function numero(valor, decimales = 2, sufijo = '') {
  if (valor === null || valor === undefined || !Number.isFinite(Number(valor))) return '—';
  const n = Number(valor);
  const fijo = Math.abs(n).toFixed(decimales);
  const [ent, dec] = fijo.split('.');
  const signo = n < 0 && Number(fijo) !== 0 ? '-' : '';
  return `${signo}${millares(ent)}${dec ? `.${dec}` : ''}${sufijo}`;
}

/** Porcentaje con signo explicito, como en un ticker. */
export function porcentaje(valor, decimales = 2) {
  if (valor === null || valor === undefined || !Number.isFinite(Number(valor))) return '—';
  const n = Number(valor);
  return `${n > 0 ? '+' : ''}${numero(n, decimales)}%`;
}

/** Crea un elemento con atributos e hijos. */
export function elemento(etiqueta, atributos = {}, hijos = []) {
  const nodo = document.createElement(etiqueta);
  for (const [clave, valor] of Object.entries(atributos)) {
    if (valor === null || valor === undefined || valor === false) continue;
    if (clave === 'clase') nodo.className = valor;
    else if (clave === 'texto') nodo.textContent = valor;
    else if (clave.startsWith('on') && typeof valor === 'function') {
      nodo.addEventListener(clave.slice(2).toLowerCase(), valor);
    } else if (valor === true) nodo.setAttribute(clave, '');
    else nodo.setAttribute(clave, String(valor));
  }
  for (const hijo of [].concat(hijos)) {
    if (hijo === null || hijo === undefined) continue;
    nodo.append(hijo instanceof Node ? hijo : document.createTextNode(String(hijo)));
  }
  return nodo;
}

/** Tira de indicadores destacados. */
export function kpis(pares) {
  return elemento('div', { clase: 'kpis' }, pares.map(([clave, valor, signo]) => elemento(
    'div', { clase: 'kpi' }, [
      elemento('span', { clase: 'kpi__k', texto: clave }),
      elemento('span', {
        clase: `kpi__v${signo === undefined || signo === null || !Number.isFinite(signo)
          ? '' : (signo > 0 ? ' up' : (signo < 0 ? ' down' : ''))}`,
        texto: valor,
      }),
    ],
  )));
}

export const vacio = (texto) => elemento('div', { clase: 'empty', texto });
export const error = (texto) => elemento('div', { clase: 'empty empty--error', role: 'alert', texto });
export const cargando = (texto = 'CARGANDO') => elemento('div', { clase: 'loading', texto });

/** Nota breve bajo un grafico. */
export const nota = (texto) => elemento('p', { clase: 'hint', texto });

/** Rejilla de graficos. */
export const rejilla = (hijos, compacta = false) => elemento(
  'div', { clase: compacta ? 'grid grid--3' : 'grid' }, hijos,
);
