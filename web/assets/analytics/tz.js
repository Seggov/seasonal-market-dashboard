/**
 * Calendario del mercado sin usar jamas la zona horaria del navegador.
 *
 * Todo campo de calendario se deriva del *epoch local* que publica el
 * generador Python (`epoch_utc + desplazamiento`). Las conversiones de hora
 * local a instante absoluto usan la tabla de transiciones del manifiesto, de
 * modo que un dia con cambio de horario dura correctamente 23 o 25 horas.
 *
 * No se construye ningun objeto `Date`: la aritmetica civil es exacta y
 * evita depender de la configuracion regional de quien mira la pagina.
 */

export const SEGUNDOS_DIA = 86400;

/** 1970-01-01 fue jueves; pandas numera los dias con lunes = 0. */
const DESPLAZAMIENTO_DIA_SEMANA = 3;

/**
 * Convierte un numero de dias desde la epoca en fecha civil proleptica.
 * Algoritmo de Howard Hinnant, exacto para todo el rango util.
 * @param {number} dias
 * @returns {{ año: number, mes: number, dia: number }}
 */
export function fechaDesdeDias(dias) {
  const z = dias + 719468;
  const era = Math.floor(z / 146097);
  const diaDeEra = z - era * 146097;
  const añoDeEra = Math.floor(
    (diaDeEra - Math.floor(diaDeEra / 1460) + Math.floor(diaDeEra / 36524) - Math.floor(diaDeEra / 146096)) / 365,
  );
  const año = añoDeEra + era * 400;
  const diaDeAño = diaDeEra - (365 * añoDeEra + Math.floor(añoDeEra / 4) - Math.floor(añoDeEra / 100));
  const mp = Math.floor((5 * diaDeAño + 2) / 153);
  const dia = diaDeAño - Math.floor((153 * mp + 2) / 5) + 1;
  const mes = mp < 10 ? mp + 3 : mp - 9;
  return { año: mes <= 2 ? año + 1 : año, mes, dia };
}

/**
 * Inversa de {@link fechaDesdeDias}.
 * @param {number} año @param {number} mes @param {number} dia
 * @returns {number} dias desde 1970-01-01
 */
export function diasDesdeFecha(año, mes, dia) {
  const a = mes <= 2 ? año - 1 : año;
  const era = Math.floor(a / 400);
  const añoDeEra = a - era * 400;
  const diaDeAño = Math.floor((153 * (mes > 2 ? mes - 3 : mes + 9) + 2) / 5) + dia - 1;
  const diaDeEra = añoDeEra * 365 + Math.floor(añoDeEra / 4) - Math.floor(añoDeEra / 100) + diaDeAño;
  return era * 146097 + diaDeEra - 719468;
}

/** Dia local (numero de dias desde la epoca) de un epoch local en segundos. */
export function diaLocal(epochLocal) {
  return Math.floor(epochLocal / SEGUNDOS_DIA);
}

/** Segundo dentro del dia local. */
export function segundoDelDia(epochLocal) {
  return epochLocal - diaLocal(epochLocal) * SEGUNDOS_DIA;
}

/** Dia de la semana con lunes = 0, igual que `pandas.Series.dt.dayofweek`. */
export function diaSemanaDesdeDias(dias) {
  return (((dias % 7) + 7) % 7 + DESPLAZAMIENTO_DIA_SEMANA) % 7;
}

/** Campos de calendario completos de un epoch local. */
export function camposLocales(epochLocal) {
  const dias = diaLocal(epochLocal);
  const { año, mes, dia } = fechaDesdeDias(dias);
  const resto = epochLocal - dias * SEGUNDOS_DIA;
  return {
    año,
    mes,
    dia,
    hora: Math.floor(resto / 3600),
    minuto: Math.floor((resto % 3600) / 60),
    segundo: resto % 60,
    diaSemana: diaSemanaDesdeDias(dias),
    dias,
  };
}

/**
 * Semana ISO 8601 de una fecha civil.
 * @returns {{ añoIso: number, semana: number }}
 */
export function semanaIsoDeFecha(año, mes, dia) {
  const dias = diasDesdeFecha(año, mes, dia);
  const diaSemana = diaSemanaDesdeDias(dias);
  // El jueves de esta semana decide a que año ISO pertenece.
  const jueves = dias - diaSemana + 3;
  const { año: añoIso } = fechaDesdeDias(jueves);
  const primerJueves = diasDesdeFecha(añoIso, 1, 4);
  const inicioSemana1 = primerJueves - diaSemanaDesdeDias(primerJueves);
  return { añoIso, semana: Math.floor((jueves - 3 - inicioSemana1) / 7) + 1 };
}

/** Semana ISO directamente desde un epoch local. */
export function semanaIsoLocal(epochLocal) {
  const { año, mes, dia } = fechaDesdeDias(diaLocal(epochLocal));
  return semanaIsoDeFecha(año, mes, dia);
}

/**
 * Zona horaria de un mercado, reconstruida desde el manifiesto.
 *
 * `transiciones` es una lista `[instanteUTC, desplazamiento]` ordenada.
 */
export class ZonaMercado {
  /** @param {{name: string, initialOffset: number, transitions: number[][]}} datos */
  constructor(datos) {
    this.nombre = datos?.name ?? 'UTC';
    this.desplazamientoInicial = datos?.initialOffset ?? 0;
    const transiciones = datos?.transitions ?? [];
    this.instantes = Float64Array.from(transiciones.map(([instante]) => instante));
    this.desplazamientos = Int32Array.from(transiciones.map(([, offset]) => offset));
  }

  /** Desplazamiento UTC vigente en un instante absoluto. */
  desplazamientoEn(epochUtc) {
    let bajo = 0;
    let alto = this.instantes.length;
    while (bajo < alto) {
      const medio = (bajo + alto) >> 1;
      if (this.instantes[medio] <= epochUtc) bajo = medio + 1;
      else alto = medio;
    }
    return bajo === 0 ? this.desplazamientoInicial : this.desplazamientos[bajo - 1];
  }

  /**
   * Convierte una hora de pared local en instante absoluto.
   *
   * Se prueban los desplazamientos candidatos vigentes alrededor del momento y
   * se devuelve el primero coherente, que es lo que hace pandas al construir
   * un `Timestamp` con zona para las medianoches de estos mercados. Si la hora
   * no existe (adelanto de horario) se devuelve el instante posterior a la
   * transicion, igual que hace `DateOffset` al recolocar la hora de pared.
   */
  instanteDesdeLocal(epochPared) {
    const candidatos = new Set([
      this.desplazamientoEn(epochPared - this.desplazamientoInicial),
      this.desplazamientoEn(epochPared),
      this.desplazamientoEn(epochPared - 86400),
      this.desplazamientoEn(epochPared + 86400),
    ]);
    for (const desplazamiento of candidatos) {
      const absoluto = epochPared - desplazamiento;
      if (this.desplazamientoEn(absoluto) === desplazamiento) return absoluto;
    }
    // Hora local inexistente: se usa el desplazamiento posterior al salto.
    const posterior = this.desplazamientoEn(epochPared);
    return epochPared - posterior;
  }

  /** Instante absoluto de la medianoche local de una fecha civil. */
  medianoche(año, mes, dia) {
    return this.instanteDesdeLocal(diasDesdeFecha(año, mes, dia) * SEGUNDOS_DIA);
  }
}

export const ZONA_UTC = new ZonaMercado({ name: 'UTC', initialOffset: 0, transitions: [] });
