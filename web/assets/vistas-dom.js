/**
 * Renderizadores de cada vista.
 *
 * Cada funcion recibe las cargas ya calculadas por el worker y devuelve un
 * fragmento de DOM. No hacen calculos: solo presentacion.
 */

import { elemento, estadoVacio } from './ui.js';

/** @type {Record<string, (contexto: object) => Node>} */
export const RENDERIZADORES = {};

/** Registra el renderizador de una vista. */
export function registrar(clave, renderizador) {
  RENDERIZADORES[clave] = renderizador;
}

/** Envoltorio comun: agrupa las secciones de una vista. */
export function contenedor(hijos) {
  return elemento('div', { clase: 'vista__lienzo' }, [].concat(hijos));
}

export { estadoVacio };
