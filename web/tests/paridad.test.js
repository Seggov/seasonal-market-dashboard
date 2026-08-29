/**
 * Paridad Python <-> JavaScript.
 *
 * Compara las vistas que calcula el navegador contra `defaultViews`, que genera
 * Python durante el build, sobre exactamente las mismas series publicadas.
 * Si `dist/` no existe todavia, las pruebas se saltan con un aviso.
 */

import test from 'node:test';
import assert from 'node:assert/strict';

import { cargarActivo, cargarManifiesto, comparar, simbolos } from './ayudas.js';
import { calcularVistas } from '../assets/analytics/views.js';

const manifiesto = await cargarManifiesto();

if (manifiesto === null) {
  test('paridad Python/JavaScript', { skip: 'Ejecute antes: python tools/build_web.py' }, () => {});
} else {
  test('el manifiesto declara la version del esquema', () => {
    assert.equal(manifiesto.schemaVersion, 1);
    assert.ok(manifiesto.assets.length > 0);
    assert.match(manifiesto.generatedAt, /^\d{4}-\d{2}-\d{2}T/);
    assert.ok(manifiesto.contentHash.length >= 16);
  });

  for (const simbolo of simbolos(manifiesto)) {
    test(`${simbolo}: las diez vistas coinciden con Python`, async (t) => {
      const { informe, contexto, detalle, indices } = await cargarActivo(manifiesto, simbolo);
      const esperado = informe.defaultViews;
      const obtenido = calcularVistas(contexto);

      await t.test('sesion declarada', () => {
        assert.equal(detalle, informe.sesionPorDefecto.detalle);
        assert.equal(indices.length, informe.sesionPorDefecto.velas);
      });

      for (const vista of Object.keys(esperado)) {
        await t.test(vista, () => {
          const diferencias = comparar(obtenido[vista], esperado[vista], `$.${vista}`);
          assert.deepEqual(diferencias.slice(0, 8), [], `${diferencias.length} diferencia(s)`);
        });
      }
    });

    test(`${simbolo}: la calidad publicada es coherente`, async () => {
      const { informe, activo, serie } = await cargarActivo(manifiesto, simbolo);
      assert.equal(serie.n, informe.calidad.velasUtilizadas);
      assert.equal(serie.n, activo.filasValidas);
      assert.equal(
        informe.calidad.filasValidas,
        informe.calidad.filasTotales - informe.calidad.filasInvalidas,
      );
    });
  }
}
