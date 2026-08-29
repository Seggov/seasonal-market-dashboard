/**
 * Matriz dia-hora y eventos extremos, equivalentes a `analisis.py`.
 */

import { TOLERANCIA, desviacionMuestral, media, mediana } from './stats.js';
import { camposLocales } from './tz.js';
import { DIAS_SEMANA_ES } from './seasonal.js';

export const METRICAS = ['mean', 'median', 'positive_pct', 'std', 'count'];

function calcularMetrica(valores, metrica) {
  if (metrica === 'count') return valores.length;
  if (!valores.length) return Number.NaN;
  if (metrica === 'mean') return media(valores);
  if (metrica === 'median') return mediana(valores);
  if (metrica === 'std') return valores.length > 1 ? desviacionMuestral(valores) : Number.NaN;
  let positivos = 0;
  for (let i = 0; i < valores.length; i += 1) if (valores[i] > TOLERANCIA) positivos += 1;
  return (positivos / valores.length) * 100;
}

/**
 * Construye la matriz con dias en X y horas en Y.
 *
 * Solo se incluyen los dias y horas observados, en orden ascendente, igual que
 * `analisis.matriz_dia_hora` sin ejes explicitos. Las celdas cuyo conteo no
 * alcance `minimoObservaciones` se enmascaran a `null`.
 */
export function matrizDiaHora(agregado, metrica, { minimoObservaciones = 5 } = {}) {
  if (!METRICAS.includes(metrica)) throw new RangeError(`Metrica no valida: ${metrica}`);
  const celdas = new Map();
  const diasVistos = new Set();
  const horasVistas = new Set();
  for (let i = 0; i < agregado.n; i += 1) {
    const retorno = agregado.returnPercent[i];
    if (!Number.isFinite(retorno)) continue;
    const { diaSemana, hora } = camposLocales(agregado.inicioLocal[i]);
    diasVistos.add(diaSemana);
    horasVistas.add(hora);
    const clave = diaSemana * 100 + hora;
    if (!celdas.has(clave)) celdas.set(clave, []);
    celdas.get(clave).push(retorno);
  }
  const dias = [...diasVistos].sort((uno, otro) => uno - otro);
  const horas = [...horasVistas].sort((uno, otro) => uno - otro);
  const valores = [];
  const conteos = [];
  for (const hora of horas) {
    const filaValores = [];
    const filaConteos = [];
    for (const dia of dias) {
      const lista = celdas.get(dia * 100 + hora);
      if (lista === undefined) {
        filaValores.push(null);
        filaConteos.push(null);
        continue;
      }
      const datos = Float64Array.from(lista);
      const conteo = datos.length;
      const valor = calcularMetrica(datos, metrica);
      filaConteos.push(conteo);
      filaValores.push(
        conteo < minimoObservaciones || !Number.isFinite(valor) ? null : valor,
      );
    }
    valores.push(filaValores);
    conteos.push(filaConteos);
  }
  return {
    metrica,
    dias: dias.map((dia) => DIAS_SEMANA_ES[dia]),
    horas: horas.map((hora) => `${String(hora).padStart(2, '0')}:00`),
    valores,
    conteos,
    minimoObservaciones,
  };
}

/**
 * Mejores y peores periodos historicos.
 *
 * Sin umbral se toman hasta `n` positivos y `n` negativos. El orden final es
 * por retorno CON SIGNO descendente y, a igualdad, fecha ascendente
 * (ambiguedad A-6: no es orden por magnitud absoluta, pese al docstring).
 */
export function eventosExtremos(agregado, { n = 5, umbral = null } = {}) {
  if (n < 0) throw new RangeError('n no puede ser negativo.');
  if (umbral !== null && umbral < 0) throw new RangeError('El umbral no puede ser negativo.');

  const candidatos = [];
  for (let i = 0; i < agregado.n; i += 1) {
    const retorno = agregado.returnPercent[i];
    if (!Number.isFinite(retorno)) continue;
    candidatos.push(i);
  }

  let seleccion;
  if (umbral === null) {
    const positivos = candidatos.filter((i) => agregado.returnPercent[i] > TOLERANCIA);
    const negativos = candidatos.filter((i) => agregado.returnPercent[i] < -TOLERANCIA);
    // `nlargest`/`nsmallest` conservan la primera aparicion en los empates.
    positivos.sort((uno, otro) => (agregado.returnPercent[otro] - agregado.returnPercent[uno]) || (uno - otro));
    negativos.sort((uno, otro) => (agregado.returnPercent[uno] - agregado.returnPercent[otro]) || (uno - otro));
    seleccion = [...positivos.slice(0, n), ...negativos.slice(0, n)];
  } else {
    seleccion = candidatos.filter(
      (i) => Math.abs(agregado.returnPercent[i]) >= umbral - TOLERANCIA,
    );
  }

  seleccion.sort((uno, otro) => (
    (agregado.returnPercent[otro] - agregado.returnPercent[uno])
    || (agregado.inicio[uno] - agregado.inicio[otro])
  ));

  return seleccion.map((i) => {
    const retorno = agregado.returnPercent[i];
    let tipo = 'neutro';
    if (retorno > TOLERANCIA) tipo = 'positivo';
    else if (retorno < -TOLERANCIA) tipo = 'negativo';
    return {
      inicio: agregado.inicio[i],
      inicioLocal: agregado.inicioLocal[i],
      fin: agregado.fin[i],
      finLocal: agregado.finLocal[i],
      open: agregado.open[i],
      close: agregado.close[i],
      return_percent: retorno,
      cantidad_registros: agregado.cantidadRegistros[i],
      completo: Boolean(agregado.completo[i]),
      tipo_extremo: tipo,
    };
  });
}
