/**
 * Agregacion por periodo, equivalente a `analisis.agregar_periodos`.
 *
 * El retorno de un periodo es siempre `(ultimo_close / primer_open - 1) * 100`;
 * nunca se suman retornos. La completitud sigue el criterio conservador
 * documentado en `docs/PARIDAD.md` 3.3.
 */

import { TOLERANCIA } from './stats.js';
import {
  SEGUNDOS_DIA,
  camposLocales,
  diaLocal,
  diasDesdeFecha,
  fechaDesdeDias,
  semanaIsoLocal,
} from './tz.js';

export const PERIODOS = ['hour', 'day', 'week', 'month', 'year'];

/**
 * Clave de agrupacion de cada vela.
 *
 * Para `hour` la clave incorpora el desplazamiento UTC, de modo que las dos
 * apariciones de la hora repetida al terminar el horario de verano quedan
 * separadas (y ordenadas segun la ambiguedad A-1).
 */
function clavesDePeriodo(serie, indices, periodo) {
  const total = indices.length;
  const claves = new Float64Array(total);
  if (periodo === 'hour') {
    const desplazamientos = [...new Set(Array.from(indices, (i) => serie.off[i]))].sort(
      (uno, otro) => uno - otro,
    );
    const orden = new Map(desplazamientos.map((valor, posicion) => [valor, posicion]));
    const factor = desplazamientos.length;
    for (let posicion = 0; posicion < total; posicion += 1) {
      const indice = indices[posicion];
      const { año, mes, dia, hora } = camposLocales(serie.lt[indice]);
      const civil = ((año * 12 + (mes - 1)) * 31 + (dia - 1)) * 24 + hora;
      claves[posicion] = civil * factor + orden.get(serie.off[indice]);
    }
    return claves;
  }
  for (let posicion = 0; posicion < total; posicion += 1) {
    const epochLocal = serie.lt[indices[posicion]];
    if (periodo === 'day') {
      claves[posicion] = diaLocal(epochLocal);
    } else if (periodo === 'week') {
      const { añoIso, semana } = semanaIsoLocal(epochLocal);
      claves[posicion] = añoIso * 100 + semana;
    } else if (periodo === 'month') {
      const { año, mes } = camposLocales(epochLocal);
      claves[posicion] = año * 100 + mes;
    } else {
      claves[posicion] = camposLocales(epochLocal).año;
    }
  }
  return claves;
}

/**
 * Limites calendario locales de un periodo, en instantes absolutos.
 *
 * Replica `analisis._limites_periodo`: los limites se construyen sobre la hora
 * de pared local y luego se convierten, por lo que un dia con cambio de horario
 * mide 23 o 25 horas de tiempo absoluto.
 */
function limitesPeriodo(zona, epochAbsoluto, epochLocal, periodo) {
  if (periodo === 'hour') {
    // `Timestamp.replace(minute=0, ...)` trunca la hora de pared local; el
    // fin exclusivo es una hora absoluta despues.
    const inicioAbsoluto = epochAbsoluto - (epochLocal - Math.floor(epochLocal / 3600) * 3600);
    return [inicioAbsoluto, inicioAbsoluto + 3600];
  }
  const dias = diaLocal(epochLocal);
  const { año, mes, dia } = fechaDesdeDias(dias);
  if (periodo === 'day') {
    return [zona.medianoche(año, mes, dia), zona.medianoche(año, mes, dia + 1)];
  }
  if (periodo === 'week') {
    const { diaSemana } = camposLocales(epochLocal);
    const lunes = fechaDesdeDias(dias - diaSemana);
    return [
      zona.medianoche(lunes.año, lunes.mes, lunes.dia),
      zona.instanteDesdeLocal((diasDesdeFecha(lunes.año, lunes.mes, lunes.dia) + 7) * SEGUNDOS_DIA),
    ];
  }
  if (periodo === 'month') {
    const siguienteMes = mes === 12 ? 1 : mes + 1;
    const siguienteAño = mes === 12 ? año + 1 : año;
    return [zona.medianoche(año, mes, 1), zona.medianoche(siguienteAño, siguienteMes, 1)];
  }
  return [zona.medianoche(año, 1, 1), zona.medianoche(año + 1, 1, 1)];
}

/**
 * Agrega una serie por periodo.
 *
 * @param {import('./series.js').Serie} serie
 * @param {Int32Array|null} indices subconjunto ya filtrado, en orden cronologico
 * @param {string} periodo
 * @param {import('./tz.js').ZonaMercado} zona
 * @param {number} pasoSegundos duracion de la temporalidad base
 */
export function agregarPeriodos(serie, indices, periodo, zona, pasoSegundos = 3600) {
  if (!PERIODOS.includes(periodo)) throw new RangeError(`Periodo no valido: ${periodo}`);
  const seleccion = indices ?? Int32Array.from({ length: serie.n }, (_, i) => i);
  const total = seleccion.length;
  const salida = {
    n: 0,
    inicio: new Float64Array(0),
    inicioLocal: new Float64Array(0),
    fin: new Float64Array(0),
    finLocal: new Float64Array(0),
    open: new Float64Array(0),
    close: new Float64Array(0),
    returnPercent: new Float64Array(0),
    cantidadRegistros: new Int32Array(0),
    completo: new Uint8Array(0),
  };
  if (!total) return salida;

  const claves = clavesDePeriodo(serie, seleccion, periodo);

  // Se agrupa por clave real (no por tramos contiguos) para reproducir
  // `groupby`, y despues se ordena por clave ascendente.
  const grupos = new Map();
  for (let posicion = 0; posicion < total; posicion += 1) {
    const clave = claves[posicion];
    let grupo = grupos.get(clave);
    if (grupo === undefined) {
      grupo = { clave, primero: posicion, ultimo: posicion, cantidad: 0, continuo: true, unicos: new Set() };
      grupos.set(clave, grupo);
    } else {
      grupo.ultimo = posicion;
    }
    // Traduccion literal de `cambio_grupo | fecha.diff().eq(paso)`: la primera
    // fila de cada cambio de clave se considera continua por definicion.
    const cambioDeClave = posicion === 0 || claves[posicion] !== claves[posicion - 1];
    if (!cambioDeClave
      && serie.t[seleccion[posicion]] - serie.t[seleccion[posicion - 1]] !== pasoSegundos) {
      grupo.continuo = false;
    }
    grupo.cantidad += 1;
    grupo.unicos.add(serie.t[seleccion[posicion]]);
  }

  const ordenados = [...grupos.values()].sort((uno, otro) => uno.clave - otro.clave);
  const cantidad = ordenados.length;
  salida.n = cantidad;
  salida.inicio = new Float64Array(cantidad);
  salida.inicioLocal = new Float64Array(cantidad);
  salida.fin = new Float64Array(cantidad);
  salida.finLocal = new Float64Array(cantidad);
  salida.open = new Float64Array(cantidad);
  salida.close = new Float64Array(cantidad);
  salida.returnPercent = new Float64Array(cantidad);
  salida.cantidadRegistros = new Int32Array(cantidad);
  salida.completo = new Uint8Array(cantidad);

  for (let posicion = 0; posicion < cantidad; posicion += 1) {
    const grupo = ordenados[posicion];
    const primero = seleccion[grupo.primero];
    const ultimo = seleccion[grupo.ultimo];
    salida.inicio[posicion] = serie.t[primero];
    salida.inicioLocal[posicion] = serie.lt[primero];
    salida.fin[posicion] = serie.t[ultimo];
    salida.finLocal[posicion] = serie.lt[ultimo];
    salida.open[posicion] = serie.o[primero];
    salida.close[posicion] = serie.c[ultimo];
    salida.cantidadRegistros[posicion] = grupo.cantidad;
    const apertura = serie.o[primero];
    salida.returnPercent[posicion] = Math.abs(apertura) > TOLERANCIA
      ? (serie.c[ultimo] / apertura - 1) * 100
      : Number.NaN;

    const estructuraValida = grupo.unicos.size === grupo.cantidad && grupo.continuo;
    if (!estructuraValida) {
      salida.completo[posicion] = 0;
      continue;
    }
    const [inicioEsperado, finExclusivo] = limitesPeriodo(
      zona, serie.t[primero], serie.lt[primero], periodo,
    );
    const esperados = (finExclusivo - inicioEsperado) / pasoSegundos;
    salida.completo[posicion] = (
      serie.t[primero] === inicioEsperado
      && serie.t[ultimo] === finExclusivo - pasoSegundos
      && grupo.cantidad === esperados
    ) ? 1 : 0;
  }
  return salida;
}

/**
 * Convierte una serie base en "velas diarias" listas para estacionalidad.
 * Con datos intradia agrega por dia; con datos ya diarios conserva cada vela.
 */
export function datosDiarios(serie, indices, zona, { intradia = true, pasoSegundos = 3600 } = {}) {
  if (intradia) return agregarPeriodos(serie, indices, 'day', zona, pasoSegundos);
  const seleccion = indices ?? Int32Array.from({ length: serie.n }, (_, i) => i);
  const total = seleccion.length;
  const salida = {
    n: total,
    inicio: new Float64Array(total),
    inicioLocal: new Float64Array(total),
    fin: new Float64Array(total),
    finLocal: new Float64Array(total),
    open: new Float64Array(total),
    close: new Float64Array(total),
    returnPercent: new Float64Array(total),
    cantidadRegistros: new Int32Array(total).fill(1),
    completo: new Uint8Array(total).fill(1),
  };
  for (let posicion = 0; posicion < total; posicion += 1) {
    const indice = seleccion[posicion];
    salida.inicio[posicion] = serie.t[indice];
    salida.inicioLocal[posicion] = serie.lt[indice];
    salida.fin[posicion] = serie.t[indice];
    salida.finLocal[posicion] = serie.lt[indice];
    salida.open[posicion] = serie.o[indice];
    salida.close[posicion] = serie.c[indice];
    salida.returnPercent[posicion] = serie.r[indice];
  }
  return salida;
}

/** Reduce un agregado a los indices indicados, conservando el orden. */
export function filtrarAgregado(agregado, indices) {
  if (indices === null) return agregado;
  const total = indices.length;
  const salida = { n: total };
  for (const clave of ['inicio', 'inicioLocal', 'fin', 'finLocal', 'open', 'close', 'returnPercent']) {
    const columna = new Float64Array(total);
    for (let posicion = 0; posicion < total; posicion += 1) columna[posicion] = agregado[clave][indices[posicion]];
    salida[clave] = columna;
  }
  const conteos = new Int32Array(total);
  const completos = new Uint8Array(total);
  for (let posicion = 0; posicion < total; posicion += 1) {
    conteos[posicion] = agregado.cantidadRegistros[indices[posicion]];
    completos[posicion] = agregado.completo[indices[posicion]];
  }
  salida.cantidadRegistros = conteos;
  salida.completo = completos;
  return salida;
}
