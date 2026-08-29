/**
 * Estacionalidad y curvas historicas, equivalentes a `analisis.py` y a las
 * transformaciones de `src/vistas.py`.
 */

import { TOLERANCIA, estadisticasRetornos, media } from './stats.js';
import { agregarPeriodos } from './aggregate.js';
import { camposLocales, diaLocal, semanaIsoLocal } from './tz.js';

export const MESES_ES = [
  'enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio',
  'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre',
];

export const DIAS_SEMANA_ES = [
  'lunes', 'martes', 'miercoles', 'jueves', 'viernes', 'sabado', 'domingo',
];

/**
 * Agrupa retornos por una clave entera y devuelve una fila de estadisticas por
 * grupo, ordenada por la clave ascendente (como `groupby(sort=True)`).
 */
function estadisticasAgrupadas(claves, retornos, nombreClave) {
  const grupos = new Map();
  for (let posicion = 0; posicion < claves.length; posicion += 1) {
    const clave = claves[posicion];
    if (!Number.isFinite(clave)) continue;
    let lista = grupos.get(clave);
    if (lista === undefined) {
      lista = [];
      grupos.set(clave, lista);
    }
    lista.push(retornos[posicion]);
  }
  return [...grupos.keys()]
    .sort((uno, otro) => uno - otro)
    .map((clave) => ({
      [nombreClave]: clave,
      ...estadisticasRetornos(Float64Array.from(grupos.get(clave))),
    }));
}

/** Estacionalidad por mes calendario, con nombre en español. */
export function estacionalidadMes(agregado) {
  const claves = new Float64Array(agregado.n);
  for (let i = 0; i < agregado.n; i += 1) claves[i] = camposLocales(agregado.inicioLocal[i]).mes;
  return estadisticasAgrupadas(claves, agregado.returnPercent, 'numero_mes').map((fila) => ({
    numero_mes: fila.numero_mes,
    mes: MESES_ES[fila.numero_mes - 1],
    ...fila,
  }));
}

/** Estacionalidad por numero de semana ISO (1 a 53). */
export function estacionalidadSemanaIso(agregado) {
  const claves = new Float64Array(agregado.n);
  for (let i = 0; i < agregado.n; i += 1) claves[i] = semanaIsoLocal(agregado.inicioLocal[i]).semana;
  return estadisticasAgrupadas(claves, agregado.returnPercent, 'semana_iso');
}

/** Estacionalidad por dia de la semana, lunes = 0. */
export function estacionalidadDiaSemana(agregado) {
  const claves = new Float64Array(agregado.n);
  for (let i = 0; i < agregado.n; i += 1) claves[i] = camposLocales(agregado.inicioLocal[i]).diaSemana;
  return estadisticasAgrupadas(claves, agregado.returnPercent, 'numero_dia').map((fila) => ({
    numero_dia: fila.numero_dia,
    dia_semana: DIAS_SEMANA_ES[fila.numero_dia],
    ...fila,
  }));
}

/** Estacionalidad por dia calendario del mes (1 a 31). */
export function estacionalidadDiaMes(agregado) {
  const claves = new Float64Array(agregado.n);
  for (let i = 0; i < agregado.n; i += 1) claves[i] = camposLocales(agregado.inicioLocal[i]).dia;
  return estadisticasAgrupadas(claves, agregado.returnPercent, 'dia_mes');
}

/** Estacionalidad por hora observada (0 a 23). */
export function estacionalidadHora(agregado) {
  const claves = new Float64Array(agregado.n);
  for (let i = 0; i < agregado.n; i += 1) claves[i] = camposLocales(agregado.inicioLocal[i]).hora;
  return estadisticasAgrupadas(claves, agregado.returnPercent, 'hora');
}

/**
 * Media por par de claves enteras, con el numero de muestras.
 * Reproduce `groupby([a, b]).agg(mean, count)` sobre valores finitos.
 */
function mediaPorPar(clavesA, clavesB, valores) {
  const grupos = new Map();
  for (let posicion = 0; posicion < valores.length; posicion += 1) {
    const clave = clavesA[posicion] * 1000 + clavesB[posicion];
    let lista = grupos.get(clave);
    if (lista === undefined) {
      lista = { a: clavesA[posicion], b: clavesB[posicion], valores: [] };
      grupos.set(clave, lista);
    }
    lista.valores.push(valores[posicion]);
  }
  return [...grupos.values()]
    .sort((uno, otro) => (uno.a - otro.a) || (uno.b - otro.b))
    .map(({ a, b, valores: lista }) => {
      const finitos = Float64Array.from(lista.filter(Number.isFinite));
      return { a, b, retorno: finitos.length ? media(finitos) : Number.NaN, muestras: finitos.length };
    });
}

/**
 * Curvas mensuales: media del retorno acumulado diario respecto a la primera
 * apertura de cada mes historico (ambiguedad A-5: media simple, no ponderada).
 */
export function curvasMensuales(diarios) {
  if (!diarios.n) return [];
  const meses = new Float64Array(diarios.n);
  const dias = new Float64Array(diarios.n);
  const acumulados = new Float64Array(diarios.n);
  const aperturaPorMes = new Map();
  for (let i = 0; i < diarios.n; i += 1) {
    const { año, mes, dia } = camposLocales(diarios.inicioLocal[i]);
    meses[i] = mes;
    dias[i] = dia;
    const clave = año * 100 + mes;
    if (!aperturaPorMes.has(clave)) aperturaPorMes.set(clave, diarios.open[i]);
    const apertura = aperturaPorMes.get(clave);
    acumulados[i] = Math.abs(apertura) > TOLERANCIA
      ? (diarios.close[i] / apertura - 1) * 100
      : Number.NaN;
  }
  return mediaPorPar(meses, dias, acumulados).map(({ a, b, retorno, muestras }) => ({
    numero_mes: a, dia_mes: b, retorno_ponderado: retorno, muestras,
  }));
}

/**
 * Trayectoria intradia acumulada y retorno horario medio, por dia de la semana.
 * @returns {{ trayectorias: object[], retornosHora: object[] }}
 */
export function curvasIntradiaPorDia(serie, indices, zona, pasoSegundos = 3600) {
  const horas = agregarPeriodos(serie, indices, 'hour', zona, pasoSegundos);
  if (!horas.n) return { trayectorias: [], retornosHora: [] };

  const diasSemana = new Float64Array(horas.n);
  const horasDelDia = new Float64Array(horas.n);
  const acumulados = new Float64Array(horas.n);
  const aperturaPorDia = new Map();
  for (let i = 0; i < horas.n; i += 1) {
    const { diaSemana, hora } = camposLocales(horas.inicioLocal[i]);
    diasSemana[i] = diaSemana;
    horasDelDia[i] = hora;
    const clave = diaLocal(horas.inicioLocal[i]);
    if (!aperturaPorDia.has(clave)) aperturaPorDia.set(clave, horas.open[i]);
    const apertura = aperturaPorDia.get(clave);
    acumulados[i] = Math.abs(apertura) > TOLERANCIA
      ? (horas.close[i] / apertura - 1) * 100
      : Number.NaN;
  }
  const formatear = (filas) => filas.map(({ a, b, retorno, muestras }) => ({
    numero_dia: a, hora: b, retorno, muestras,
  }));
  return {
    trayectorias: formatear(mediaPorPar(diasSemana, horasDelDia, acumulados)),
    retornosHora: formatear(mediaPorPar(diasSemana, horasDelDia, horas.returnPercent)),
  };
}

/** Agrupa una tabla larga en una curva por cada valor de `clave`. */
export function curvasPorClave(filas, clave, eje, columnaValor = 'retorno') {
  const grupos = new Map();
  for (const fila of filas) {
    const grupo = fila[clave];
    if (!grupos.has(grupo)) grupos.set(grupo, []);
    grupos.get(grupo).push(fila);
  }
  return [...grupos.keys()].sort((uno, otro) => uno - otro).map((grupo) => {
    const ordenado = grupos.get(grupo).sort((uno, otro) => uno[eje] - otro[eje]);
    return {
      clave: grupo,
      [eje]: ordenado.map((fila) => fila[eje]),
      retorno: ordenado.map((fila) => (
        Number.isFinite(fila[columnaValor]) ? fila[columnaValor] : null
      )),
      muestras: ordenado.map((fila) => fila.muestras),
    };
  });
}

/** Pivote año x mes con la columna de retorno anual. */
export function pivoteAnualMensual(anual, mensual) {
  if (!anual.n || !mensual.n) return { años: [], meses: [], retornoAnual: [] };
  const porAño = new Map();
  let minimo = Infinity;
  let maximo = -Infinity;
  for (let i = 0; i < mensual.n; i += 1) {
    const { año, mes } = camposLocales(mensual.inicioLocal[i]);
    if (!porAño.has(año)) porAño.set(año, new Array(12).fill(null));
    const valor = mensual.returnPercent[i];
    porAño.get(año)[mes - 1] = Number.isFinite(valor) ? valor : null;
    if (año < minimo) minimo = año;
    if (año > maximo) maximo = año;
  }
  const retornoPorAño = new Map();
  for (let i = 0; i < anual.n; i += 1) {
    retornoPorAño.set(camposLocales(anual.inicioLocal[i]).año, anual.returnPercent[i]);
  }
  const años = [];
  const meses = [];
  const retornoAnual = [];
  for (let año = minimo; año <= maximo; año += 1) {
    años.push(año);
    meses.push(porAño.get(año) ?? new Array(12).fill(null));
    const valor = retornoPorAño.get(año);
    retornoAnual.push(Number.isFinite(valor) ? valor : null);
  }
  return { años, meses, retornoAnual };
}
