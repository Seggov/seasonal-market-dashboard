/**
 * Estadistica descriptiva equivalente a `src/analisis.py`.
 *
 * Las sumas usan compensacion de Kahan-Neumaier para acercarse a la suma por
 * pares de NumPy dentro de la tolerancia declarada en `docs/PARIDAD.md` 2.5.
 */

export const TOLERANCIA = 1e-10;

/** Suma compensada de los valores finitos de un iterable. */
export function sumaCompensada(valores) {
  let suma = 0;
  let correccion = 0;
  for (let indice = 0; indice < valores.length; indice += 1) {
    const valor = valores[indice];
    const provisional = suma + valor;
    correccion += Math.abs(suma) >= Math.abs(valor)
      ? (suma - provisional) + valor
      : (valor - provisional) + suma;
    suma = provisional;
  }
  return suma + correccion;
}

/** Filtra los valores finitos conservando el orden original. */
export function soloFinitos(valores) {
  const salida = new Float64Array(valores.length);
  let total = 0;
  for (let indice = 0; indice < valores.length; indice += 1) {
    const valor = valores[indice];
    if (Number.isFinite(valor)) salida[total++] = valor;
  }
  return salida.subarray(0, total);
}

export function media(valores) {
  return valores.length ? sumaCompensada(valores) / valores.length : Number.NaN;
}

/** Mediana sobre una copia ordenada; con n par promedia los dos centrales. */
export function mediana(valores) {
  const n = valores.length;
  if (!n) return Number.NaN;
  const ordenado = Float64Array.from(valores).sort();
  const medio = n >> 1;
  return n % 2 ? ordenado[medio] : (ordenado[medio - 1] + ordenado[medio]) / 2;
}

/** Desviacion estandar muestral (`ddof = 1`); NaN con menos de dos valores. */
export function desviacionMuestral(valores) {
  const n = valores.length;
  if (n < 2) return Number.NaN;
  const promedio = media(valores);
  const desviaciones = new Float64Array(n);
  for (let indice = 0; indice < n; indice += 1) {
    const delta = valores[indice] - promedio;
    desviaciones[indice] = delta * delta;
  }
  return Math.sqrt(sumaCompensada(desviaciones) / (n - 1));
}

/**
 * Cuantil con interpolacion lineal, igual que `numpy.quantile(method="linear")`.
 * @param {ArrayLike<number>} ordenado vector YA ordenado de forma ascendente
 * @param {number} q en [0, 1]
 */
export function cuantilOrdenado(ordenado, q) {
  const n = ordenado.length;
  if (!n) return Number.NaN;
  if (n === 1) return ordenado[0];
  const posicion = (n - 1) * q;
  const inferior = Math.floor(posicion);
  const fraccion = posicion - inferior;
  if (fraccion === 0) return ordenado[inferior];
  return ordenado[inferior] + fraccion * (ordenado[inferior + 1] - ordenado[inferior]);
}

export function cuantil(valores, q) {
  return cuantilOrdenado(Float64Array.from(valores).sort(), q);
}

const VACIO = Object.freeze({
  promedio: null,
  mediana: null,
  maximo: null,
  minimo: null,
  std: null,
  positivo_pct: null,
  negativo_pct: null,
  neutro_pct: null,
  n: 0,
  mejor: null,
  peor: null,
  rango: null,
});

/**
 * Equivalente exacto de `analisis.estadisticas_retornos`.
 *
 * Los valores no finitos se descartan antes de contar `n`, y todo resultado no
 * finito se publica como `null` para respetar el contrato JSON estricto.
 */
export function estadisticasRetornos(valores) {
  const finitos = soloFinitos(valores);
  const n = finitos.length;
  if (!n) return { ...VACIO };

  let maximo = finitos[0];
  let minimo = finitos[0];
  let positivos = 0;
  let negativos = 0;
  let neutros = 0;
  for (let indice = 0; indice < n; indice += 1) {
    const valor = finitos[indice];
    if (valor > maximo) maximo = valor;
    if (valor < minimo) minimo = valor;
    if (valor > TOLERANCIA) positivos += 1;
    else if (valor < -TOLERANCIA) negativos += 1;
    else neutros += 1;
  }
  return {
    promedio: media(finitos),
    mediana: mediana(finitos),
    maximo,
    minimo,
    std: n > 1 ? desviacionMuestral(finitos) : null,
    positivo_pct: (positivos / n) * 100,
    negativo_pct: (negativos / n) * 100,
    neutro_pct: (neutros / n) * 100,
    n,
    mejor: maximo,
    peor: minimo,
    rango: maximo - minimo,
  };
}

/**
 * Filtro IQR equivalente a `analisis.filtrar_iqr` en modo global.
 *
 * Devuelve los indices conservados. Los retornos no finitos se conservan
 * deliberadamente, para no ocultar problemas de calidad ajenos al criterio.
 */
export function indicesTrasIqr(retornos, { activo = false, factor = 1.5 } = {}) {
  const total = retornos.length;
  if (!activo) return { indices: null, eliminados: 0 };
  if (factor < 0) throw new RangeError('El factor IQR no puede ser negativo.');
  const finitos = soloFinitos(retornos);
  if (!finitos.length) return { indices: null, eliminados: 0 };
  const ordenado = Float64Array.from(finitos).sort();
  const q1 = cuantilOrdenado(ordenado, 0.25);
  const q3 = cuantilOrdenado(ordenado, 0.75);
  const rango = q3 - q1;
  const minimo = q1 - factor * rango - TOLERANCIA;
  const maximo = q3 + factor * rango + TOLERANCIA;

  const conservados = new Int32Array(total);
  let cantidad = 0;
  for (let indice = 0; indice < total; indice += 1) {
    const valor = retornos[indice];
    if (!Number.isFinite(valor) || (valor >= minimo && valor <= maximo)) {
      conservados[cantidad++] = indice;
    }
  }
  return { indices: conservados.subarray(0, cantidad), eliminados: total - cantidad };
}

/** Convierte un numero no finito en `null`, como hace el exportador. */
export function limpiar(valor) {
  return Number.isFinite(valor) ? valor : null;
}
