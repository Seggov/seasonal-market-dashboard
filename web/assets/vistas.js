/**
 * Renderizado de las vistas.
 *
 * Cada funcion recibe el informe que genero Python y devuelve DOM. No hay
 * calculo analitico en el navegador: solo se dibuja lo ya calculado.
 */

import { barras, barrasH, linea, mapaCalor, velas } from './graficos.js';
import {
  DIAS, MESES, ejeTemporal, elemento, fechaCorta, fechaHora, kpis, nota, numero,
  porcentaje, rejilla, vacio,
} from './ui.js';

export const VISTAS = [
  { clave: 'resumen', titulo: 'RESUMEN' },
  { clave: 'periodo', titulo: 'ANUAL' },
  { clave: 'mensual', titulo: 'MENSUAL' },
  { clave: 'semanal', titulo: 'SEMANAL' },
  { clave: 'diaSemana', titulo: 'DÍA SEMANA' },
  { clave: 'diaria', titulo: 'DÍA DEL MES' },
  { clave: 'horaria', titulo: 'HORARIO' },
  { clave: 'matriz', titulo: 'MATRIZ' },
  { clave: 'extremos', titulo: 'EXTREMOS' },
];

const bloque = (hijos) => elemento('div', { clase: 'view__body' }, [].concat(hijos));

/**
 * Decimales con los que un mapa de calor resulta legible.
 *
 * Los retornos horarios son centesimas de punto: con dos decimales casi toda la
 * rejilla mostraria `0.00`. Se eligen segun la magnitud real de los datos para
 * que cada celda diga algo.
 */
function decimalesUtiles(matriz) {
  const magnitudes = matriz.flat().filter(Number.isFinite).map(Math.abs);
  if (!magnitudes.length) return 2;
  const maximo = Math.max(...magnitudes);
  if (maximo < 0.02) return 4;
  if (maximo < 0.2) return 3;
  return 2;
}

/** Curvas pequeñas, una por clave, omitiendo las que no tienen forma. */
function curvas(lista, etiquetas, desplazamiento) {
  const tarjetas = etiquetas.map((nombre, indice) => {
    const curva = lista.find((c) => c.clave === indice + desplazamiento);
    if (!curva || curva.retorno.filter(Number.isFinite).length < 2) return null;
    const eje = curva.dia_mes ?? curva.hora;
    return linea(eje, curva.retorno, { titulo: nombre, altura: 150, compacta: true });
  }).filter(Boolean);
  return tarjetas.length ? rejilla(tarjetas, true) : vacio('SIN DATOS SUFICIENTES');
}

/* ------------------------------------------------------------------ vistas */

function resumen({ vistas }) {
  const { metricas, velas: ohlc } = vistas.resumen;
  const serie = { x: ohlc.lt.map(ejeTemporal), o: ohlc.o, h: ohlc.h, l: ohlc.l, c: ohlc.c };
  return bloque([
    kpis([
      ['Último cierre', numero(metricas.ultimo_cierre, 2)],
      ['Mes', porcentaje(metricas.retorno_ultimo_mes), metricas.retorno_ultimo_mes],
      ['Año', porcentaje(metricas.retorno_ultimo_ano), metricas.retorno_ultimo_ano],
      ['Velas +', numero(metricas.positivo_pct, 1, '%')],
      ['Velas −', numero(metricas.negativo_pct, 1, '%')],
      ['Observaciones', numero(metricas.velas, 0)],
    ]),
    ohlc.mostradas ? velas(serie, { titulo: 'Precio', altura: 420 }) : vacio('SIN VELAS'),
  ]);
}

function periodo({ vistas }) {
  const datos = vistas.periodo;
  if (!datos.anual.length) return bloque(vacio('SIN DATOS'));
  const { años, meses } = datos.pivote;
  return bloque([
    barras(datos.anual.map((f) => String(f['año'])), datos.anual.map((f) => f.returnPercent),
      { titulo: 'Retorno por año', altura: 300 }),
    mapaCalor(
      { x: MESES, y: años.map(String), z: meses },
      {
        titulo: 'Retorno por año y mes',
        altura: Math.max(260, 62 + años.length * 24),
        decimales: decimalesUtiles(meses),
      },
    ),
  ]);
}

function mensual({ vistas }) {
  const datos = vistas.mensual;
  if (!datos.estacional.length) return bloque(vacio('SIN DATOS'));
  return bloque([
    barras(datos.estacional.map((f) => MESES[f.numero_mes - 1]),
      datos.estacional.map((f) => f.promedio),
      { titulo: 'Retorno medio por mes', altura: 300 }),
    curvas(datos.curvas, MESES, 1),
    nota('Cada curva promedia el retorno acumulado desde la primera apertura del mes, por día del mes y a través de todos los años.'),
  ]);
}

function semanal({ vistas }) {
  const datos = vistas.semanal;
  if (!datos.estacional.length) return bloque(vacio('SIN DATOS'));
  const x = datos.estacional.map((f) => String(f.semana_iso));
  const y = datos.estacional.map((f) => f.promedio);
  return bloque([
    barras(x, y, { titulo: 'Retorno medio por semana ISO', altura: 320, etiquetas: false }),
    linea(x, y, { titulo: 'Curva semanal frente al promedio general', altura: 260, referencia: datos.promedioGeneral }),
  ]);
}

function diaSemana({ vistas }) {
  const datos = vistas.diaSemana;
  if (!datos.estacional.length) return bloque(vacio('SIN DATOS'));
  const hijos = [
    barras(datos.estacional.map((f) => DIAS[f.numero_dia]),
      datos.estacional.map((f) => f.promedio),
      { titulo: 'Retorno medio por día de la semana', altura: 300 }),
  ];
  if (datos.trayectorias.length) {
    hijos.push(curvas(datos.trayectorias, DIAS, 0));
    hijos.push(nota('Retorno acumulado medio respecto a la primera apertura de cada día.'));
  }
  return bloque(hijos);
}

function diaria({ vistas }) {
  const datos = vistas.diaria;
  if (!datos.estacional.length) return bloque(vacio('SIN DATOS'));
  const porDia = new Map(datos.estacional.map((f) => [f.dia_mes, f.promedio]));
  const dias = Array.from({ length: 31 }, (_, i) => i + 1);
  return bloque([
    barras(datos.estacional.map((f) => String(f.dia_mes)),
      datos.estacional.map((f) => f.promedio),
      { titulo: 'Retorno medio por día del mes', altura: 300, etiquetas: false }),
    mapaCalor(
      { x: dias.map(String), y: [''], z: [dias.map((d) => porDia.get(d) ?? null)] },
      {
        titulo: 'Mapa por día del mes',
        altura: 118,
        escalaVisible: false,
        tamanoTexto: 9,
      },
    ),
  ]);
}

function horaria({ vistas }) {
  const datos = vistas.horaria;
  if (!datos.disponible) return bloque(vacio('SIN DATOS INTRADÍA'));
  if (!datos.estacional.length) return bloque(vacio('SIN DATOS'));
  return bloque([
    barras(datos.estacional.map((f) => `${String(f.hora).padStart(2, '0')}`),
      datos.estacional.map((f) => f.promedio),
      { titulo: 'Retorno medio por hora', altura: 300, etiquetas: false }),
    curvas(datos.curvas, DIAS, 0),
  ]);
}

function matriz({ vistas }) {
  const datos = vistas.matriz;
  if (!datos.disponible || !datos.dias?.length) return bloque(vacio('SIN DATOS INTRADÍA'));
  return bloque([
    mapaCalor(
      { x: datos.dias.map((d) => d.slice(0, 3).toUpperCase()), y: datos.horas, z: datos.valores },
      {
        titulo: 'Retorno medio por día y hora',
        altura: Math.max(340, 74 + datos.horas.length * 26),
        decimales: decimalesUtiles(datos.valores),
        tamanoTexto: 9,
      },
    ),
    nota(`Celdas con menos de ${datos.minimoObservaciones} observaciones quedan vacías.`),
  ]);
}

function extremos({ vistas }) {
  const datos = vistas.extremos;
  if (!datos.filas.length) return bloque(vacio('SIN EVENTOS'));
  const etiqueta = (fila) => (
    fila.cantidad_registros > 1 ? fechaCorta(fila.inicioLocal) : fechaHora(fila.inicioLocal)
  );
  return bloque([
    barrasH(datos.filas.map(etiqueta), datos.filas.map((f) => f.return_percent),
      { titulo: `Mejores y peores · ${datos.periodo.toLowerCase()}`, altura: Math.max(280, 40 + datos.filas.length * 30) }),
  ]);
}

/** @type {Record<string, (informe: object) => Node>} */
export const RENDER = {
  resumen, periodo, mensual, semanal, diaSemana, diaria, horaria, matriz, extremos,
};
