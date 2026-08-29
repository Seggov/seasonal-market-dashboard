/**
 * Constructores de las nueve cargas de vista.
 *
 * Cada funcion es el espejo exacto de su `exportador.vista_*` en Python, con
 * los mismos nombres de campo, para que las pruebas de paridad puedan comparar
 * las salidas termino a termino.
 */

import { TOLERANCIA, estadisticasRetornos, indicesTrasIqr, limpiar, media } from './stats.js';
import { agregarPeriodos, datosDiarios, filtrarAgregado } from './aggregate.js';
import {
  curvasIntradiaPorDia,
  curvasMensuales,
  curvasPorClave,
  estacionalidadDiaMes,
  estacionalidadDiaSemana,
  estacionalidadHora,
  estacionalidadMes,
  estacionalidadSemanaIso,
  pivoteAnualMensual,
} from './seasonal.js';
import { eventosExtremos, matrizDiaHora } from './matrix.js';
import { camposLocales } from './tz.js';

export const MAX_VELAS_GRAFICO = 3000;

export const PERIODOS_INTERFAZ = {
  'Vela base': null,
  Hora: 'hour',
  'Día': 'day',
  'Semana ISO': 'week',
  Mes: 'month',
  'Año': 'year',
};

/** Contexto compartido por todas las vistas de un activo. */
export function crearContexto(serie, indices, activo, zona) {
  const paso = (activo.baseMinutes ?? 60) * 60;
  const cache = new Map();
  return {
    serie,
    indices,
    activo,
    zona,
    paso,
    agregado(periodo) {
      if (!cache.has(periodo)) {
        cache.set(periodo, agregarPeriodos(serie, indices, periodo, zona, paso));
      }
      return cache.get(periodo);
    },
    diarios() {
      if (!cache.has('__diarios')) {
        cache.set('__diarios', datosDiarios(serie, indices, zona, {
          intradia: activo.intradia, pasoSegundos: paso,
        }));
      }
      return cache.get('__diarios');
    },
  };
}

function limpiarFilas(filas) {
  return filas.map((fila) => {
    const salida = {};
    for (const [clave, valor] of Object.entries(fila)) {
      salida[clave] = typeof valor === 'number' ? limpiar(valor) : valor;
    }
    return salida;
  });
}

/** Reduce velas consecutivas a bloques OHLC, como `vistas.downsample_ohlc`. */
export function downsampleOhlc(serie, indices, maximo = MAX_VELAS_GRAFICO) {
  const total = indices.length;
  if (total <= maximo) {
    return {
      resumido: false,
      total,
      mostradas: total,
      t: Array.from(indices, (i) => serie.t[i]),
      lt: Array.from(indices, (i) => serie.lt[i]),
      o: Array.from(indices, (i) => limpiar(serie.o[i])),
      h: Array.from(indices, (i) => limpiar(serie.h[i])),
      l: Array.from(indices, (i) => limpiar(serie.l[i])),
      c: Array.from(indices, (i) => limpiar(serie.c[i])),
    };
  }
  const tamano = Math.ceil(total / maximo);
  const t = [];
  const lt = [];
  const o = [];
  const h = [];
  const l = [];
  const c = [];
  for (let comienzo = 0; comienzo < total; comienzo += tamano) {
    const fin = Math.min(comienzo + tamano, total);
    let maximoBloque = -Infinity;
    let minimoBloque = Infinity;
    for (let posicion = comienzo; posicion < fin; posicion += 1) {
      const indice = indices[posicion];
      if (serie.h[indice] > maximoBloque) maximoBloque = serie.h[indice];
      if (serie.l[indice] < minimoBloque) minimoBloque = serie.l[indice];
    }
    t.push(serie.t[indices[comienzo]]);
    lt.push(serie.lt[indices[comienzo]]);
    o.push(limpiar(serie.o[indices[comienzo]]));
    h.push(limpiar(maximoBloque));
    l.push(limpiar(minimoBloque));
    c.push(limpiar(serie.c[indices[fin - 1]]));
  }
  return { resumido: true, total, mostradas: t.length, t, lt, o, h, l, c };
}

export function vistaResumen(contexto) {
  const { serie, indices } = contexto;
  const mensual = contexto.agregado('month');
  const anual = contexto.agregado('year');
  const retornos = Array.from(indices, (i) => serie.r[i]);
  const estadisticas = estadisticasRetornos(Float64Array.from(retornos));
  return {
    metricas: {
      ultimo_cierre: indices.length ? limpiar(serie.c[indices[indices.length - 1]]) : null,
      retorno_ultimo_mes: mensual.n ? limpiar(mensual.returnPercent[mensual.n - 1]) : null,
      retorno_ultimo_ano: anual.n ? limpiar(anual.returnPercent[anual.n - 1]) : null,
      positivo_pct: estadisticas.positivo_pct,
      negativo_pct: estadisticas.negativo_pct,
      velas: indices.length,
    },
    velas: downsampleOhlc(serie, indices),
  };
}

export function vistaPeriodo(contexto) {
  const anual = contexto.agregado('year');
  const mensual = contexto.agregado('month');
  if (!anual.n || !mensual.n) {
    return { anual: [], pivote: { años: [], meses: [], retornoAnual: [] } };
  }
  const filas = [];
  for (let i = 0; i < anual.n; i += 1) {
    filas.push({
      'año': camposLocales(anual.inicioLocal[i]).año,
      returnPercent: limpiar(anual.returnPercent[i]),
    });
  }
  return { anual: filas, pivote: pivoteAnualMensual(anual, mensual) };
}

export function vistaMensual(contexto) {
  const mensual = contexto.agregado('month');
  if (!mensual.n) return { estacional: [], curvas: [] };
  return {
    estacional: limpiarFilas(estacionalidadMes(mensual)),
    curvas: curvasPorClave(
      curvasMensuales(contexto.diarios()), 'numero_mes', 'dia_mes', 'retorno_ponderado',
    ),
  };
}

export function vistaSemanal(contexto, { quitarAtipicos = false, factor = 1.5 } = {}) {
  const semanal = contexto.agregado('week');
  const { indices, eliminados } = indicesTrasIqr(semanal.returnPercent, {
    activo: quitarAtipicos, factor,
  });
  const filtrado = filtrarAgregado(semanal, indices);
  if (!filtrado.n) return { estacional: [], promedioGeneral: null, eliminados };
  const finitos = Float64Array.from(filtrado.returnPercent);
  return {
    estacional: limpiarFilas(estacionalidadSemanaIso(filtrado)),
    promedioGeneral: limpiar(media(finitos)),
    eliminados,
  };
}

export function vistaDiaSemana(contexto) {
  const diarios = contexto.diarios();
  const salida = { estacional: limpiarFilas(estacionalidadDiaSemana(diarios)), trayectorias: [] };
  if (contexto.activo.intradia) {
    const { trayectorias } = curvasIntradiaPorDia(
      contexto.serie, contexto.indices, contexto.zona, contexto.paso,
    );
    salida.trayectorias = curvasPorClave(trayectorias, 'numero_dia', 'hora');
  }
  return salida;
}

export function vistaDiaria(contexto) {
  const estacional = estacionalidadDiaMes(contexto.diarios());
  if (!estacional.length) return { estacional: [], promedio: null };
  const promedios = Float64Array.from(
    estacional.map((fila) => (Number.isFinite(fila.promedio) ? fila.promedio : Number.NaN)),
  );
  return { estacional: limpiarFilas(estacional), promedio: limpiar(media(promedios)) };
}

export function vistaHoraria(contexto) {
  if (!contexto.activo.intradia) return { disponible: false, estacional: [], curvas: [] };
  const horas = contexto.agregado('hour');
  if (!horas.n) return { disponible: true, estacional: [], curvas: [] };
  const { retornosHora } = curvasIntradiaPorDia(
    contexto.serie, contexto.indices, contexto.zona, contexto.paso,
  );
  return {
    disponible: true,
    estacional: limpiarFilas(estacionalidadHora(horas)),
    curvas: curvasPorClave(retornosHora, 'numero_dia', 'hora'),
  };
}

export function vistaMatriz(contexto, {
  metrica = 'mean', quitarAtipicos = false, factor = 1.5, minimoObservaciones = 5,
} = {}) {
  if (!contexto.activo.intradia) return { disponible: false };
  const horas = contexto.agregado('hour');
  if (!horas.n) {
    return { disponible: true, dias: [], horas: [], valores: [], conteos: [], eliminados: 0 };
  }
  const { indices, eliminados } = indicesTrasIqr(horas.returnPercent, {
    activo: quitarAtipicos, factor,
  });
  const matriz = matrizDiaHora(filtrarAgregado(horas, indices), metrica, { minimoObservaciones });
  return { disponible: true, ...matriz, eliminados };
}

export function vistaExtremos(contexto, { periodo = 'Día', n = 5, umbral = null } = {}) {
  const clave = PERIODOS_INTERFAZ[periodo];
  let agregado;
  if (clave === null) {
    const { serie, indices } = contexto;
    const total = indices.length;
    agregado = {
      n: total,
      inicio: Float64Array.from(indices, (i) => serie.t[i]),
      inicioLocal: Float64Array.from(indices, (i) => serie.lt[i]),
      fin: Float64Array.from(indices, (i) => serie.t[i]),
      finLocal: Float64Array.from(indices, (i) => serie.lt[i]),
      open: Float64Array.from(indices, (i) => serie.o[i]),
      close: Float64Array.from(indices, (i) => serie.c[i]),
      returnPercent: Float64Array.from(indices, (i) => serie.r[i]),
      cantidadRegistros: new Int32Array(total).fill(1),
      completo: new Uint8Array(total).fill(1),
    };
  } else {
    agregado = contexto.agregado(clave);
  }
  return {
    periodo,
    n,
    umbral,
    filas: limpiarFilas(eventosExtremos(agregado, { n, umbral })),
  };
}

/** Calcula las nueve vistas con una configuracion concreta de filtros. */
export function calcularVistas(contexto, filtros = {}) {
  return {
    resumen: vistaResumen(contexto),
    periodo: vistaPeriodo(contexto),
    mensual: vistaMensual(contexto),
    semanal: vistaSemanal(contexto, filtros.semanal),
    diaSemana: vistaDiaSemana(contexto),
    diaria: vistaDiaria(contexto),
    horaria: vistaHoraria(contexto),
    matriz: vistaMatriz(contexto, filtros.matriz),
    extremos: vistaExtremos(contexto, filtros.extremos),
  };
}

export { TOLERANCIA };
