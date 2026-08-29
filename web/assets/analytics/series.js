/**
 * Decodifica los fragmentos `series-<año>.json` del contrato JSON.
 *
 * El resultado es una serie en arrays tipados. Todas las vistas trabajan sobre
 * *indices* de esta serie para no copiar cientos de miles de velas en cada
 * cambio de filtro.
 */

import { TOLERANCIA } from './stats.js';

/** @typedef {{
 *   n: number,
 *   t: Float64Array,   // instante absoluto en segundos
 *   lt: Float64Array,  // epoch local (t + desplazamiento)
 *   off: Int32Array,   // desplazamiento UTC en segundos
 *   o: Float64Array, h: Float64Array, l: Float64Array, c: Float64Array,
 *   r: Float64Array,   // retorno por vela en puntos porcentuales
 * }} Serie */

function expandirPrecios(valores, escala, total) {
  const salida = new Float64Array(total);
  if (escala === null || escala === undefined) {
    for (let indice = 0; indice < total; indice += 1) {
      const valor = valores[indice];
      salida[indice] = valor === null ? Number.NaN : valor;
    }
    return salida;
  }
  let acumulado = 0;
  for (let indice = 0; indice < total; indice += 1) {
    acumulado += valores[indice];
    // La division de un entero exacto por una potencia de diez esta
    // correctamente redondeada: reproduce el doble original bit a bit.
    salida[indice] = acumulado / escala;
  }
  return salida;
}

function expandirDesplazamientos(tramos, total) {
  const salida = new Int32Array(total);
  for (let posicion = 0; posicion < tramos.length; posicion += 1) {
    const [inicio, desplazamiento] = tramos[posicion];
    const fin = posicion + 1 < tramos.length ? tramos[posicion + 1][0] : total;
    salida.fill(desplazamiento, inicio, fin);
  }
  return salida;
}

/**
 * Decodifica un fragmento anual.
 * @param {object} fragmento
 * @returns {Serie}
 */
export function decodificarFragmento(fragmento) {
  const total = fragmento.count;
  const t = new Float64Array(total);
  if (total > 0) {
    t[0] = fragmento.t0;
    const deltas = fragmento.dt;
    for (let indice = 1; indice < total; indice += 1) t[indice] = t[indice - 1] + deltas[indice - 1];
  }
  const off = expandirDesplazamientos(fragmento.off ?? [], total);
  const lt = new Float64Array(total);
  for (let indice = 0; indice < total; indice += 1) lt[indice] = t[indice] + off[indice];

  const escala = fragmento.scale ?? null;
  const o = expandirPrecios(fragmento.o, escala, total);
  const h = expandirPrecios(fragmento.h, escala, total);
  const l = expandirPrecios(fragmento.l, escala, total);
  const c = expandirPrecios(fragmento.c, escala, total);
  const r = new Float64Array(total);
  for (let indice = 0; indice < total; indice += 1) {
    const apertura = o[indice];
    r[indice] = Math.abs(apertura) > TOLERANCIA ? (c[indice] / apertura - 1) * 100 : Number.NaN;
  }
  return { n: total, t, lt, off, o, h, l, c, r };
}

/** Une varios fragmentos anuales en una unica serie cronologica. */
export function unirFragmentos(fragmentos) {
  const ordenados = [...fragmentos].sort((uno, otro) => uno.year - otro.year);
  const series = ordenados.map(decodificarFragmento);
  const total = series.reduce((suma, serie) => suma + serie.n, 0);
  const salida = {
    n: total,
    t: new Float64Array(total),
    lt: new Float64Array(total),
    off: new Int32Array(total),
    o: new Float64Array(total),
    h: new Float64Array(total),
    l: new Float64Array(total),
    c: new Float64Array(total),
    r: new Float64Array(total),
  };
  let desplazamiento = 0;
  for (const serie of series) {
    for (const clave of ['t', 'lt', 'off', 'o', 'h', 'l', 'c', 'r']) {
      salida[clave].set(serie[clave], desplazamiento);
    }
    desplazamiento += serie.n;
  }
  return salida;
}

/** Todos los indices de una serie, en orden cronologico. */
export function todosLosIndices(serie) {
  const indices = new Int32Array(serie.n);
  for (let indice = 0; indice < serie.n; indice += 1) indices[indice] = indice;
  return indices;
}

/** Extrae una columna de la serie siguiendo un vector de indices. */
export function tomar(columna, indices) {
  if (indices === null) return columna;
  const salida = new Float64Array(indices.length);
  for (let posicion = 0; posicion < indices.length; posicion += 1) {
    salida[posicion] = columna[indices[posicion]];
  }
  return salida;
}
