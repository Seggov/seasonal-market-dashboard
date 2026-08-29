/** Utilidades compartidas por las pruebas de Node. */

import { readFile, readdir } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

import { unirFragmentos } from '../assets/analytics/series.js';
import { ZonaMercado } from '../assets/analytics/tz.js';
import { aplicarSesion } from '../assets/analytics/sessions.js';
import { crearContexto } from '../assets/analytics/views.js';

export const RAIZ = path.resolve(fileURLToPath(new URL('../..', import.meta.url)));
export const DIST = process.env.DIST_DIR
  ? path.resolve(process.env.DIST_DIR)
  : path.join(RAIZ, 'dist');

/** Tolerancias declaradas en `docs/PARIDAD.md` 2.5. */
export const ABS = 1e-9;
export const REL = 1e-12;

async function leerJson(ruta) {
  return JSON.parse(await readFile(ruta, 'utf8'));
}

/** Carga el manifiesto publicado, o `null` si aun no se ha construido. */
export async function cargarManifiesto() {
  try {
    return await leerJson(path.join(DIST, 'data', 'manifest.json'));
  } catch (error) {
    if (error.code === 'ENOENT') return null;
    throw error;
  }
}

/** Carga informe, series y contexto por defecto de un activo publicado. */
export async function cargarActivo(manifiesto, simbolo) {
  const activo = manifiesto.assets.find((entrada) => entrada.symbol === simbolo);
  if (!activo) throw new Error(`Activo ausente en el manifiesto: ${simbolo}`);
  const base = path.join(DIST, 'data');
  const informe = await leerJson(path.join(base, activo.report));
  const fragmentos = await Promise.all(
    Object.values(activo.series).map((relativo) => leerJson(path.join(base, relativo))),
  );
  const serie = unirFragmentos(fragmentos);
  const zona = new ZonaMercado(activo.tz);
  const { indices, detalle } = aplicarSesion(serie, activo, { modo: 'Declarada' });
  return {
    activo,
    informe,
    serie,
    zona,
    indices,
    detalle,
    contexto: crearContexto(serie, indices, activo, zona),
  };
}

/** Lista los simbolos publicados. */
export function simbolos(manifiesto) {
  return manifiesto.assets.map((entrada) => entrada.symbol);
}

/** Comprueba que dos numeros coinciden dentro de la tolerancia documentada. */
export function cercanos(obtenido, esperado, ruta) {
  if (esperado === null || esperado === undefined) {
    if (obtenido === null || obtenido === undefined) return null;
    return `${ruta}: se esperaba null y se obtuvo ${obtenido}`;
  }
  if (obtenido === null || obtenido === undefined) {
    return `${ruta}: se esperaba ${esperado} y se obtuvo null`;
  }
  const diferencia = Math.abs(obtenido - esperado);
  if (diferencia <= ABS) return null;
  const relativa = diferencia / Math.max(Math.abs(esperado), Number.MIN_VALUE);
  if (relativa <= REL) return null;
  return `${ruta}: ${obtenido} != ${esperado} (dif ${diferencia.toExponential(3)})`;
}

/**
 * Compara dos estructuras recursivamente y devuelve la lista de diferencias.
 * Los numeros usan la tolerancia de paridad; el resto exige igualdad estricta.
 */
export function comparar(obtenido, esperado, ruta = '$', diferencias = []) {
  if (typeof esperado === 'number' || typeof obtenido === 'number'
    || (esperado === null && typeof obtenido !== 'object')) {
    const problema = cercanos(obtenido, esperado, ruta);
    if (problema) diferencias.push(problema);
    return diferencias;
  }
  if (Array.isArray(esperado)) {
    if (!Array.isArray(obtenido)) {
      diferencias.push(`${ruta}: se esperaba un array`);
      return diferencias;
    }
    if (obtenido.length !== esperado.length) {
      diferencias.push(`${ruta}: longitud ${obtenido.length} != ${esperado.length}`);
      return diferencias;
    }
    for (let indice = 0; indice < esperado.length; indice += 1) {
      comparar(obtenido[indice], esperado[indice], `${ruta}[${indice}]`, diferencias);
    }
    return diferencias;
  }
  if (esperado === null || esperado === undefined) {
    if (obtenido !== null && obtenido !== undefined) {
      diferencias.push(`${ruta}: se esperaba null y se obtuvo ${JSON.stringify(obtenido)}`);
    }
    return diferencias;
  }
  if (typeof esperado === 'object') {
    if (typeof obtenido !== 'object' || obtenido === null) {
      diferencias.push(`${ruta}: se esperaba un objeto`);
      return diferencias;
    }
    for (const clave of Object.keys(esperado)) {
      comparar(obtenido[clave], esperado[clave], `${ruta}.${clave}`, diferencias);
    }
    return diferencias;
  }
  if (obtenido !== esperado) {
    diferencias.push(`${ruta}: ${JSON.stringify(obtenido)} != ${JSON.stringify(esperado)}`);
  }
  return diferencias;
}

/** Enumera todos los archivos de un directorio, recursivamente. */
export async function archivos(directorio) {
  const entradas = await readdir(directorio, { withFileTypes: true });
  const salida = [];
  for (const entrada of entradas) {
    const completo = path.join(directorio, entrada.name);
    if (entrada.isDirectory()) salida.push(...await archivos(completo));
    else salida.push(completo);
  }
  return salida;
}
