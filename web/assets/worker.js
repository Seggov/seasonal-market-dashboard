/**
 * Web Worker de calculo.
 *
 * Descarga las series del activo seleccionado, las decodifica una sola vez y
 * recalcula las nueve vistas cada vez que cambia un filtro. Todo el trabajo
 * pesado ocurre fuera del hilo principal, de modo que la interfaz nunca se
 * bloquea aunque el activo tenga 140 000 velas.
 */

import { unirFragmentos } from './analytics/series.js';
import { ZonaMercado } from './analytics/tz.js';
import { aplicarSesion, diasYHorasObservados } from './analytics/sessions.js';
import { calcularVistas, crearContexto } from './analytics/views.js';

/** @type {Map<string, {activo: object, serie: object, zona: ZonaMercado, observado: object}>} */
const cargados = new Map();

async function descargarJson(url) {
  const respuesta = await fetch(url);
  if (!respuesta.ok) {
    throw new Error(`No se pudo descargar ${url}: HTTP ${respuesta.status}`);
  }
  return respuesta.json();
}

async function cargar({ activo, urls }) {
  if (cargados.has(activo.symbol)) return cargados.get(activo.symbol);
  const fragmentos = await Promise.all(urls.map(descargarJson));
  const serie = unirFragmentos(fragmentos);
  const zona = new ZonaMercado(activo.tz);
  const entrada = { activo, serie, zona, observado: diasYHorasObservados(serie) };
  cargados.set(activo.symbol, entrada);
  return entrada;
}

function calcular(entrada, filtros) {
  const { serie, activo, zona } = entrada;
  const { indices, detalle } = aplicarSesion(serie, activo, filtros.sesion);
  const contexto = crearContexto(serie, indices, activo, zona);
  return {
    detalleSesion: detalle,
    velasFiltradas: indices.length,
    velasTotales: serie.n,
    vistas: indices.length ? calcularVistas(contexto, filtros) : null,
  };
}

self.addEventListener('message', async (evento) => {
  const { id, tipo, carga } = evento.data;
  const comienzo = performance.now();
  try {
    if (tipo === 'cargar') {
      const entrada = await cargar(carga);
      self.postMessage({
        id,
        tipo: 'cargado',
        carga: {
          simbolo: entrada.activo.symbol,
          velas: entrada.serie.n,
          observado: entrada.observado,
          ms: performance.now() - comienzo,
        },
      });
      return;
    }
    if (tipo === 'calcular') {
      const entrada = cargados.get(carga.simbolo) ?? await cargar(carga);
      const resultado = calcular(entrada, carga.filtros);
      self.postMessage({
        id,
        tipo: 'vistas',
        carga: {
          simbolo: entrada.activo.symbol,
          filtros: carga.filtros,
          ...resultado,
          ms: performance.now() - comienzo,
        },
      });
      return;
    }
    if (tipo === 'olvidar') {
      cargados.delete(carga.simbolo);
      self.postMessage({ id, tipo: 'olvidado', carga: { simbolo: carga.simbolo } });
      return;
    }
    throw new Error(`Mensaje no reconocido: ${tipo}`);
  } catch (error) {
    self.postMessage({
      id,
      tipo: 'error',
      carga: { mensaje: error?.message ?? String(error) },
    });
  }
});
