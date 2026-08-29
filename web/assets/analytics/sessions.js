/**
 * Filtros de sesion, equivalentes a `analisis.filtrar_sesion_*` y a la
 * resolucion de modos de `vistas.aplicar_sesion`.
 *
 * Reproduce la ambiguedad A-3: la comparacion de la etiqueta declarada es de
 * igualdad exacta contra `"24/7"` y `"24/5"`, asi que `"Dukascopy 24/5
 * extendida"` no filtra nada.
 */

import { camposLocales, segundoDelDia } from './tz.js';

export const MODOS = ['Declarada', 'Observada', 'Personalizada'];

/** Convierte `"09:30"` o un numero de horas en segundos desde medianoche. */
export function segundosDeHora(valor) {
  if (typeof valor === 'number') {
    if (!Number.isInteger(valor) || valor < 0 || valor > 23) {
      throw new RangeError('La hora entera debe estar entre 0 y 23.');
    }
    return valor * 3600;
  }
  const partes = String(valor).split(':');
  const horas = Number(partes[0]);
  const minutos = Number(partes[1] ?? 0);
  const segundos = Number(partes[2] ?? 0);
  if (![horas, minutos, segundos].every(Number.isFinite)) {
    throw new RangeError(`Hora no valida: ${valor}`);
  }
  return horas * 3600 + minutos * 60 + segundos;
}

function seleccionCompleta(serie) {
  return Int32Array.from({ length: serie.n }, (_, indice) => indice);
}

/** Filtra por dias de semana y horas discretas presentes en los datos. */
export function filtrarSesionObservada(serie, { dias = null, horas = null } = {}) {
  if (dias === null && horas === null) return seleccionCompleta(serie);
  const diasPermitidos = dias === null ? null : new Set(dias.map(Number));
  const horasPermitidas = horas === null ? null : new Set(horas.map(Number));
  const salida = new Int32Array(serie.n);
  let cantidad = 0;
  for (let indice = 0; indice < serie.n; indice += 1) {
    const { diaSemana, hora } = camposLocales(serie.lt[indice]);
    if (diasPermitidos !== null && !diasPermitidos.has(diaSemana)) continue;
    if (horasPermitidas !== null && !horasPermitidas.has(hora)) continue;
    salida[cantidad++] = indice;
  }
  return salida.subarray(0, cantidad);
}

/**
 * Filtra un intervalo `[inicio, fin)` que puede cruzar medianoche.
 * `inicio === fin` significa 24 horas (ambiguedad A-11).
 */
export function filtrarSesionPersonalizada(serie, horaInicio, horaFin, { dias = null, incluirFin = false } = {}) {
  const inicio = segundosDeHora(horaInicio);
  const fin = segundosDeHora(horaFin);
  const diasPermitidos = dias === null ? null : new Set(dias.map(Number));
  const salida = new Int32Array(serie.n);
  let cantidad = 0;
  for (let indice = 0; indice < serie.n; indice += 1) {
    const epochLocal = serie.lt[indice];
    const segundo = segundoDelDia(epochLocal);
    let dentro;
    if (inicio === fin) {
      dentro = true;
    } else {
      const antesDelFin = incluirFin ? segundo <= fin : segundo < fin;
      dentro = inicio < fin ? (segundo >= inicio && antesDelFin) : (segundo >= inicio || antesDelFin);
    }
    if (!dentro) continue;
    if (diasPermitidos !== null && !diasPermitidos.has(camposLocales(epochLocal).diaSemana)) continue;
    salida[cantidad++] = indice;
  }
  return salida.subarray(0, cantidad);
}

/**
 * Resuelve el modo de sesion elegido y devuelve los indices conservados.
 *
 * @param {import('./series.js').Serie} serie
 * @param {{sesion: string, zonaHoraria: string, intradia: boolean}} activo
 * @param {{modo?: string, dias?: number[]|null, horas?: number[]|null,
 *          horaInicio?: string, horaFin?: string}} opciones
 * @returns {{ indices: Int32Array, detalle: string }}
 */
export function aplicarSesion(serie, activo, opciones = {}) {
  const {
    modo = 'Declarada', dias = null, horas = null,
    horaInicio = '09:00', horaFin = '17:00',
  } = opciones;
  const etiqueta = (activo.sesion ?? '').trim().toLowerCase();

  if (etiqueta === '24/7') {
    return {
      indices: seleccionCompleta(serie),
      detalle: `Sesión declarada ${activo.sesion}; sin filtro adicional.`,
    };
  }
  if (!activo.intradia) {
    return {
      indices: seleccionCompleta(serie),
      detalle: modo === 'Declarada'
        ? `Sesión declarada ${activo.sesion}; sin filtro horario.`
        : `${modo}: no aplicable a datos diarios; serie completa.`,
    };
  }
  if (modo === 'Declarada') {
    if (etiqueta === '24/5') {
      return {
        indices: filtrarSesionObservada(serie, { dias: [0, 1, 2, 3, 4] }),
        detalle: 'Sesión declarada 24/5: lunes a viernes; sin inventar horas.',
      };
    }
    return {
      indices: seleccionCompleta(serie),
      detalle: `Sesión declarada ${activo.sesion}; calendario exacto no disponible.`,
    };
  }
  if (modo === 'Observada') {
    return {
      indices: filtrarSesionObservada(serie, { dias, horas }),
      detalle: 'Sesión observada: solo días y horas presentes en el archivo.',
    };
  }
  if (modo !== 'Personalizada') throw new RangeError(`Modo de sesión no reconocido: ${modo}`);
  return {
    indices: filtrarSesionPersonalizada(serie, horaInicio, horaFin, { dias }),
    detalle: `Sesión personalizada [${horaInicio}, ${horaFin}); zona ${activo.zonaHoraria}.`,
  };
}

/** Enumera los dias de semana y horas presentes en la serie. */
export function diasYHorasObservados(serie) {
  const dias = new Set();
  const horas = new Set();
  for (let indice = 0; indice < serie.n; indice += 1) {
    const { diaSemana, hora } = camposLocales(serie.lt[indice]);
    dias.add(diaSemana);
    horas.add(hora);
  }
  return {
    dias: [...dias].sort((uno, otro) => uno - otro),
    horas: [...horas].sort((uno, otro) => uno - otro),
  };
}
