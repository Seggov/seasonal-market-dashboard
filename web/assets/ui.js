/**
 * Utilidades de presentacion: formato, tablas y estados.
 *
 * El formato numerico y de fechas es deliberadamente independiente de la
 * configuracion regional del navegador, para reproducir exactamente las
 * cadenas que mostraba la version Streamlit.
 */

import { camposLocales } from './analytics/tz.js';

export const AUSENTE = 'No disponible';

const DIAS_TITULO = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo'];
const MESES_TITULO = [
  'Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio',
  'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre',
];

export { DIAS_TITULO, MESES_TITULO };

/** Inserta separadores de millar cada tres digitos, como `f"{x:,}"`. */
function agruparMillares(entero) {
  return entero.replace(/\B(?=(\d{3})+(?!\d))/g, ',');
}

/** Equivalente de `interfaz._texto_numero`. */
export function textoNumero(valor, decimales = 2, sufijo = '') {
  const numero = Number(valor);
  if (valor === null || valor === undefined || !Number.isFinite(numero)) return AUSENTE;
  const fijo = Math.abs(numero).toFixed(decimales);
  const [entero, fraccion] = fijo.split('.');
  const signo = numero < 0 && Number(fijo) !== 0 ? '-' : '';
  const cuerpo = agruparMillares(entero) + (fraccion ? `.${fraccion}` : '');
  return `${signo}${cuerpo}${sufijo}`;
}

/** Equivalente de `interfaz._texto_entero`. */
export function textoEntero(valor) {
  const numero = Number(valor);
  if (valor === null || valor === undefined || !Number.isFinite(numero)) return AUSENTE;
  const truncado = Math.trunc(numero);
  return (truncado < 0 ? '-' : '') + agruparMillares(String(Math.abs(truncado)));
}

const dos = (valor) => String(valor).padStart(2, '0');

/**
 * Fecha del mercado a partir del epoch local, nunca del reloj del navegador.
 * @param {number} epochLocal segundos
 * @param {string} [abreviatura] huso vigente (EST, JST, UTC…)
 */
export function textoFecha(epochLocal, abreviatura = '') {
  if (epochLocal === null || epochLocal === undefined || !Number.isFinite(epochLocal)) return AUSENTE;
  const { año, mes, dia, hora, minuto } = camposLocales(epochLocal);
  const fecha = `${año}-${dos(mes)}-${dos(dia)}`;
  const sufijo = abreviatura ? ` ${abreviatura}` : '';
  return `${fecha} ${dos(hora)}:${dos(minuto)}${sufijo}`;
}

/** Solo la parte de fecha, sin hora. */
export function textoFechaCorta(epochLocal) {
  if (!Number.isFinite(epochLocal)) return AUSENTE;
  const { año, mes, dia } = camposLocales(epochLocal);
  return `${año}-${dos(mes)}-${dos(dia)}`;
}

/**
 * Convierte un epoch local en la cadena ISO que Plotly interpreta como hora de
 * pared. Al no llevar zona, Plotly la dibuja tal cual, sin desplazarla al huso
 * del navegador.
 */
export function ejeTemporal(epochLocal) {
  const { año, mes, dia, hora, minuto, segundo } = camposLocales(epochLocal);
  return `${año}-${dos(mes)}-${dos(dia)}T${dos(hora)}:${dos(minuto)}:${dos(segundo)}`;
}

/* ------------------------------------------------------------------- DOM */

/** Crea un elemento con atributos e hijos en una sola llamada. */
export function elemento(etiqueta, atributos = {}, hijos = []) {
  const nodo = document.createElement(etiqueta);
  for (const [clave, valor] of Object.entries(atributos)) {
    if (valor === null || valor === undefined || valor === false) continue;
    if (clave === 'clase') nodo.className = valor;
    else if (clave === 'texto') nodo.textContent = valor;
    else if (clave === 'html') nodo.innerHTML = valor;
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

export function vaciar(nodo) {
  while (nodo.firstChild) nodo.removeChild(nodo.firstChild);
  return nodo;
}

/** Bloque de metricas destacadas. */
export function metricas(pares) {
  return elemento('div', { clase: 'metricas' }, pares.map(([etiqueta, valor]) => elemento(
    'div',
    { clase: 'metrica' },
    [
      elemento('span', { clase: 'metrica__etiqueta', texto: etiqueta }),
      elemento('span', { clase: 'metrica__valor', texto: valor }),
    ],
  )));
}

/**
 * Tabla accesible con desplazamiento horizontal propio.
 * @param {string[]} cabeceras
 * @param {Array<Array<{texto: string, clase?: string}|string>>} filas
 */
export function tabla(cabeceras, filas, leyenda = null) {
  if (!filas.length) return estadoVacio('No hay observaciones disponibles para esta vista.');
  const cuerpo = filas.map((fila) => elemento('tr', {}, fila.map((celda) => {
    const contenido = typeof celda === 'object' && celda !== null ? celda : { texto: String(celda) };
    return elemento('td', { clase: contenido.clase ?? null, texto: contenido.texto });
  })));
  return elemento('div', { clase: 'tabla-envoltorio' }, [
    elemento('table', {}, [
      leyenda ? elemento('caption', { texto: leyenda }) : null,
      elemento('thead', {}, [elemento('tr', {}, cabeceras.map(
        (titulo) => elemento('th', { scope: 'col', texto: titulo }),
      ))]),
      elemento('tbody', {}, cuerpo),
    ]),
  ]);
}

/** Colorea una celda numerica segun su signo. */
export function celdaRetorno(valor, decimales = 2) {
  if (valor === null || valor === undefined || !Number.isFinite(valor)) {
    return { texto: AUSENTE, clase: 'ausente' };
  }
  return {
    texto: textoNumero(valor, decimales, '%'),
    clase: valor > 0 ? 'positivo' : (valor < 0 ? 'negativo' : null),
  };
}

export function estadoVacio(mensaje) {
  return elemento('div', { clase: 'estado' }, [elemento('p', { texto: mensaje })]);
}

export function estadoError(mensaje) {
  return elemento('div', { clase: 'estado estado--error', role: 'alert' }, [
    elemento('p', { texto: mensaje }),
  ]);
}

export function estadoCargando(mensaje = 'Calculando…') {
  return elemento('div', { clase: 'estado estado--cargando' }, [
    elemento('span', { clase: 'giro', 'aria-hidden': 'true' }),
    elemento('p', { texto: mensaje }),
  ]);
}

/** Contenedor de una seccion de vista, con titulo opcional. */
export function seccion(titulo, hijos, nota = null) {
  return elemento('section', { clase: 'vista__seccion' }, [
    titulo ? elemento('h3', { clase: 'vista__titulo', texto: titulo }) : null,
    nota ? elemento('p', { clase: 'vista__nota', texto: nota }) : null,
    ...[].concat(hijos),
  ]);
}
