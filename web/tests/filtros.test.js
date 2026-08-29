/**
 * Paridad Python <-> JavaScript con filtros NO predeterminados.
 *
 * `tests/fixtures/paridad-filtros.json` contiene, por activo y configuracion,
 * el numero de velas filtradas, el texto de la sesion y un digesto numerico
 * calculado por Python. Aqui se recalcula lo mismo en JavaScript y se compara.
 */

import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import path from 'node:path';

import { ABS, DIST, RAIZ, cargarManifiesto } from './ayudas.js';
import { unirFragmentos } from '../assets/analytics/series.js';
import { ZonaMercado } from '../assets/analytics/tz.js';
import { aplicarSesion } from '../assets/analytics/sessions.js';
import { calcularVistas, crearContexto } from '../assets/analytics/views.js';

/** Recorrido determinista identico al de `tools/generar_paridad_filtros.py`. */
function digerir(valor, acumulador = null) {
  const acc = acumulador ?? {
    numeros: 0, nulos: 0, textos: 0, booleanos: 0, hojas: 0,
    suma: 0, sumaPonderada: 0, minimo: null, maximo: null, hashTextos: 0,
  };
  if (valor === null || valor === undefined) {
    acc.hojas += 1;
    acc.nulos += 1;
  } else if (typeof valor === 'boolean') {
    acc.hojas += 1;
    acc.booleanos += 1;
    acc.sumaPonderada += (valor ? 1 : 0) * acc.hojas;
  } else if (typeof valor === 'number') {
    if (Number.isFinite(valor)) {
      acc.hojas += 1;
      acc.numeros += 1;
      acc.suma += valor;
      acc.sumaPonderada += valor * acc.hojas;
      acc.minimo = acc.minimo === null ? valor : Math.min(acc.minimo, valor);
      acc.maximo = acc.maximo === null ? valor : Math.max(acc.maximo, valor);
    } else {
      acc.hojas += 1;
      acc.nulos += 1;
    }
  } else if (typeof valor === 'string') {
    acc.hojas += 1;
    acc.textos += 1;
    let codigos = 0;
    for (const caracter of valor) codigos += caracter.codePointAt(0);
    acc.hashTextos = (acc.hashTextos + codigos * acc.hojas) % 2147483647;
  } else if (Array.isArray(valor)) {
    for (const elemento of valor) digerir(elemento, acc);
  } else if (typeof valor === 'object') {
    for (const clave of Object.keys(valor).sort()) {
      digerir(clave, acc);
      digerir(valor[clave], acc);
    }
  }
  return acc;
}

async function cargarFixtura() {
  try {
    const texto = await readFile(
      path.join(RAIZ, 'tests', 'fixtures', 'paridad-filtros.json'), 'utf8',
    );
    return JSON.parse(texto);
  } catch (error) {
    if (error.code === 'ENOENT') return null;
    throw error;
  }
}

/** Carga y decodifica una sola vez las series de cada activo. */
const cache = new Map();
async function serieDe(manifiesto, simbolo) {
  if (cache.has(simbolo)) return cache.get(simbolo);
  const activo = manifiesto.assets.find((entrada) => entrada.symbol === simbolo);
  const base = path.join(DIST, 'data');
  const fragmentos = await Promise.all(
    Object.values(activo.series).map(async (relativo) => JSON.parse(
      await readFile(path.join(base, relativo), 'utf8'),
    )),
  );
  const entrada = { activo, serie: unirFragmentos(fragmentos), zona: new ZonaMercado(activo.tz) };
  cache.set(simbolo, entrada);
  return entrada;
}

const manifiesto = await cargarManifiesto();
const fixtura = await cargarFixtura();

if (manifiesto === null || fixtura === null) {
  test('paridad de filtros', {
    skip: 'Ejecute: python tools/build_web.py && python tools/generar_paridad_filtros.py',
  }, () => {});
} else {
  test('la fixtura declara la misma version de esquema', () => {
    assert.equal(fixtura.schemaVersion, manifiesto.schemaVersion);
    assert.ok(fixtura.casos.length > 0);
  });

  for (const caso of fixtura.casos) {
    test(`${caso.symbol} · ${caso.caso}`, async () => {
      const { activo, serie, zona } = await serieDe(manifiesto, caso.symbol);
      const sesion = caso.filtros.sesion ?? {};
      const { indices, detalle } = aplicarSesion(serie, activo, {
        modo: sesion.modo ?? 'Declarada',
        dias: sesion.dias ?? null,
        horas: sesion.horas ?? null,
        horaInicio: sesion.horaInicio ?? '09:00',
        horaFin: sesion.horaFin ?? '17:00',
      });

      assert.equal(detalle, caso.detalleSesion, 'texto de la sesión');
      assert.equal(indices.length, caso.velasFiltradas, 'velas tras el filtro');
      assert.equal(serie.n, caso.velasTotales, 'velas totales');

      if (caso.digesto === null) {
        assert.equal(indices.length, 0, 'sin vistas solo si no quedan velas');
        return;
      }

      const contexto = crearContexto(serie, indices, activo, zona);
      const vistas = calcularVistas(contexto, {
        semanal: caso.filtros.semanal,
        matriz: caso.filtros.matriz,
        extremos: caso.filtros.extremos,
      });
      const obtenido = digerir(vistas);

      for (const clave of ['hojas', 'numeros', 'nulos', 'textos', 'booleanos', 'hashTextos']) {
        assert.equal(obtenido[clave], caso.digesto[clave], `digesto.${clave}`);
      }
      for (const clave of ['suma', 'sumaPonderada', 'minimo', 'maximo']) {
        const esperado = caso.digesto[clave];
        if (esperado === null) {
          assert.equal(obtenido[clave], null, `digesto.${clave}`);
          continue;
        }
        const diferencia = Math.abs(obtenido[clave] - esperado);
        const escala = Math.max(1, Math.abs(esperado));
        assert.ok(
          diferencia <= Math.max(ABS, escala * 1e-9),
          `digesto.${clave}: ${obtenido[clave]} != ${esperado} (dif ${diferencia})`,
        );
      }
    });
  }
}
