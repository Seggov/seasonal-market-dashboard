/** Vistas "Resumen" y "Calidad de datos". */

import { AUSENTE, elemento, estadoVacio, metricas, seccion, textoEntero, textoNumero } from '../ui.js';
import { velas } from '../graficos.js';

/** Formatea la marca ISO con desplazamiento que publica el informe. */
function fechaDeInforme(iso) {
  if (!iso) return AUSENTE;
  const coincidencia = /^(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2})(?::\d{2})?(Z|[+-]\d{2}:\d{2})?$/.exec(iso);
  if (!coincidencia) return iso;
  const [, fecha, hora, desplazamiento] = coincidencia;
  const sufijo = !desplazamiento || desplazamiento === 'Z' ? ' UTC' : ` UTC${desplazamiento}`;
  return `${fecha} ${hora}${sufijo}`;
}

export function vistaResumen({ vistas }) {
  const { metricas: valores, velas: datos } = vistas.resumen;
  const partes = [
    metricas([
      ['Último cierre', textoNumero(valores.ultimo_cierre, 4)],
      ['Retorno del último mes', textoNumero(valores.retorno_ultimo_mes, 2, '%')],
      ['Retorno del último año', textoNumero(valores.retorno_ultimo_ano, 2, '%')],
      ['Velas positivas', textoNumero(valores.positivo_pct, 2, '%')],
      ['Velas negativas', textoNumero(valores.negativo_pct, 2, '%')],
    ]),
  ];

  if (!datos.mostradas) {
    partes.push(estadoVacio('No hay velas que dibujar con los filtros actuales.'));
  } else {
    partes.push(seccion(
      null,
      velas(datos),
      datos.resumido
        ? `El gráfico resume ${textoEntero(datos.total)} velas en ${textoEntero(datos.mostradas)} `
          + 'bloques OHLC para acelerar la visualización. Las estadísticas usan todas las observaciones.'
        : null,
    ));
  }
  return elemento('div', { clase: 'vista__lienzo' }, partes);
}

export function vistaCalidad({ informe }) {
  const calidad = informe.calidad;
  const bloques = [
    metricas([
      ['Filas totales del archivo', textoEntero(calidad.filasTotales)],
      ['Fecha inicial', fechaDeInforme(calidad.fechaInicial)],
      ['Fecha final', fechaDeInforme(calidad.fechaFinal)],
      ['Filas válidas', textoEntero(calidad.filasValidas)],
      ['Velas utilizadas en los análisis', textoEntero(calidad.velasUtilizadas)],
      ['Filas eliminadas en la validación', textoEntero(calidad.filasInvalidas)],
    ]),
  ];

  const motivos = Object.entries(calidad.motivosInvalidez ?? {});
  if (motivos.length) {
    bloques.push(seccion('Motivos de exclusión', elemento('ul', { clase: 'lista' }, motivos.map(
      ([motivo, cantidad]) => elemento('li', { texto: `${motivo} — ${textoEntero(cantidad)} fila(s)` }),
    ))));
  }

  const cobertura = calidad.cobertura ?? {};
  bloques.push(seccion(
    'Cobertura del calendario',
    elemento('p', {
      clase: 'vista__nota',
      texto: cobertura.disponible
        ? `${textoNumero(cobertura.porcentaje, 2, '%')} de los ${textoEntero(cobertura.esperados)} `
          + `intervalos esperados; faltan ${textoEntero(cobertura.faltantes)}.`
        : (cobertura.razon ?? 'Cobertura no disponible para esta sesión.'),
    }),
  ));

  if (calidad.advertencias?.length) {
    bloques.push(seccion('Advertencias de la validación', elemento(
      'ul', { clase: 'lista' },
      calidad.advertencias.map((aviso) => elemento('li', { texto: aviso })),
    )));
  }
  return elemento('div', { clase: 'vista__lienzo' }, bloques);
}
