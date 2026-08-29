/**
 * Vistas "Matriz día-hora" y "Eventos extremos".
 */

import {
  celdaRetorno, elemento, estadoVacio, seccion, tabla,
  textoFecha, textoNumero,
} from '../ui.js';
import { mapaCalor } from '../graficos.js';

const lienzo = (hijos) => elemento('div', { clase: 'vista__lienzo' }, [].concat(hijos));

const ETIQUETAS_METRICA = {
  mean: 'Promedio',
  median: 'Mediana',
  positive_pct: '% positivos',
  std: 'Desv. estándar',
  count: 'Conteo',
};

/** Campo de formulario compacto para la barra de controles. */
function campo(etiqueta, control) {
  return elemento('label', { clase: 'campo' }, [
    elemento('span', { clase: 'campo__etiqueta', texto: etiqueta }),
    control,
  ]);
}

function seleccion(opciones, valor, alCambiar) {
  const nodo = elemento('select', { clase: 'campo__control' }, opciones.map(
    ([clave, texto]) => elemento('option', { value: clave, texto, selected: clave === valor }),
  ));
  nodo.addEventListener('change', () => alCambiar(nodo.value));
  return nodo;
}

function numero(valor, atributos, alCambiar) {
  const nodo = elemento('input', { type: 'number', clase: 'campo__control', value: valor, ...atributos });
  nodo.addEventListener('change', () => alCambiar(Number(nodo.value)));
  return nodo;
}

/* --------------------------------------------------------- matriz día-hora */

export function vistaMatriz({ vistas, activo, filtros, alCambiarFiltros }) {
  const datos = vistas.matriz;
  const actual = filtros.matriz;
  const cambiar = (parcial) => alCambiarFiltros({ matriz: { ...actual, ...parcial } });

  const casillaIqr = elemento('input', { type: 'checkbox', checked: actual.quitarAtipicos });
  casillaIqr.addEventListener('change', () => cambiar({ quitarAtipicos: casillaIqr.checked }));

  const controles = elemento('div', { clase: 'controles-vista' }, [
    campo('Métrica', seleccion(
      Object.entries(ETIQUETAS_METRICA), actual.metrica, (valor) => cambiar({ metrica: valor }),
    )),
    elemento('label', { clase: 'casilla' }, [
      casillaIqr, elemento('span', { texto: 'Quitar outliers' }),
    ]),
    campo('Factor IQR', numero(actual.factor, {
      min: '0', step: '0.1', disabled: !actual.quitarAtipicos,
    }, (valor) => cambiar({ factor: Number.isFinite(valor) && valor >= 0 ? valor : 1.5 }))),
    campo('Mínimo por celda', numero(actual.minimoObservaciones, {
      min: '1', step: '1',
    }, (valor) => cambiar({ minimoObservaciones: Math.max(1, Math.trunc(valor) || 1) }))),
  ]);

  if (!datos.disponible) {
    return lienzo([estadoVacio('La matriz día-hora solo está disponible para datos intradía.')]);
  }
  const nota = elemento('p', {
    clase: 'vista__nota',
    texto: actual.quitarAtipicos
      ? `Outliers: IQR Q1/Q3 con factor ${actual.factor.toFixed(1)}; `
        + `${textoNumero(datos.eliminados, 0)} retornos horarios excluidos. `
        + 'Los archivos de origen no se modifican.'
      : 'Outliers: filtro IQR desactivado. Los retornos horarios se conservan completos.',
  });

  if (!datos.dias?.length) {
    return lienzo([controles, nota, estadoVacio('No hay observaciones para construir la matriz.')]);
  }

  const esConteo = actual.metrica === 'count';
  const etiqueta = ETIQUETAS_METRICA[actual.metrica];
  const opciones = {
    titulo: `${etiqueta} por día y hora`,
    altura: Math.max(320, 40 + datos.horas.length * 26),
    centro: esConteo ? null : (actual.metrica === 'positive_pct' ? 50 : 0),
    sufijo: esConteo ? '' : '%',
    decimales: esConteo ? 0 : 2,
    ejeX: 'Días (X)',
    ejeY: 'Horas (Y)',
    etiquetaColor: etiqueta,
  };

  const capitalizar = (texto) => texto.charAt(0).toUpperCase() + texto.slice(1);
  const detallePorDia = datos.dias.map((dia, columna) => seccion(
    null,
    mapaCalor({
      x: datos.horas,
      y: [dia],
      z: [datos.valores.map((fila) => fila[columna])],
    }, {
      ...opciones,
      titulo: `${capitalizar(dia)} · ${etiqueta}`,
      altura: 190,
      ejeX: 'Hora',
      ejeY: '',
      mostrarEscala: false,
    }),
  ));

  const filasTabla = datos.horas.map((hora, fila) => [
    hora,
    ...datos.dias.map((_, columna) => {
      const valor = datos.valores[fila][columna];
      if (valor === null) return { texto: '—', clase: 'ausente' };
      return esConteo
        ? { texto: textoNumero(valor, 0) }
        : (actual.metrica === 'positive_pct' || actual.metrica === 'std'
          ? { texto: textoNumero(valor, 2, '%') }
          : celdaRetorno(valor));
    }),
  ]);

  return lienzo([
    controles,
    nota,
    seccion(null, mapaCalor({ x: datos.dias, y: datos.horas, z: datos.valores }, opciones)),
    seccion('Detalle separado por día', detallePorDia),
    seccion(
      'Valores de la matriz',
      tabla(['Hora', ...datos.dias.map(capitalizar)], filasTabla),
      `Se enmascaran las celdas con menos de ${actual.minimoObservaciones} observaciones.`,
    ),
  ]);
}

/* ---------------------------------------------------------- eventos extremos */

export function vistaExtremos({ vistas, informe, filtros, alCambiarFiltros, activo, zona }) {
  const datos = vistas.extremos;
  const actual = filtros.extremos;
  const cambiar = (parcial) => alCambiarFiltros({ extremos: { ...actual, ...parcial } });
  const usaUmbral = actual.umbral !== null && actual.umbral !== undefined;

  const casillaUmbral = elemento('input', { type: 'checkbox', checked: usaUmbral });
  casillaUmbral.addEventListener('change', () => cambiar({
    umbral: casillaUmbral.checked ? 2.0 : null,
  }));

  const controles = elemento('div', { clase: 'controles-vista' }, [
    campo('Periodo', seleccion(
      (informe.opcionesPeriodo ?? ['Día']).map((valor) => [valor, valor]),
      actual.periodo,
      (valor) => cambiar({ periodo: valor }),
    )),
    elemento('label', { clase: 'casilla' }, [
      casillaUmbral, elemento('span', { texto: 'Usar umbral absoluto' }),
    ]),
    usaUmbral
      ? campo('Umbral (%)', numero(actual.umbral, { min: '0', step: '0.1' },
        (valor) => cambiar({ umbral: Number.isFinite(valor) && valor >= 0 ? valor : 0 })))
      : campo('Mejores y peores', numero(actual.n, { min: '1', max: '100', step: '1' },
        (valor) => cambiar({ n: Math.min(100, Math.max(1, Math.trunc(valor) || 5)) }))),
  ]);

  if (!datos.filas.length) {
    return lienzo([
      controles,
      estadoVacio('Ningún periodo cumple el criterio seleccionado.'),
    ]);
  }

  const abreviatura = (epochAbsoluto) => zona?.abreviaturaEn(epochAbsoluto) ?? '';
  const filas = datos.filas.map((fila) => [
    textoFecha(fila.inicioLocal, abreviatura(fila.inicio)),
    textoFecha(fila.finLocal, abreviatura(fila.fin)),
    { texto: textoNumero(fila.open, 4) },
    { texto: textoNumero(fila.close, 4) },
    celdaRetorno(fila.return_percent),
    { texto: textoNumero(fila.cantidad_registros, 0) },
    { texto: fila.completo ? 'Sí' : 'No', clase: fila.completo ? null : 'ausente' },
    { texto: fila.tipo_extremo, clase: fila.tipo_extremo === 'positivo' ? 'positivo' : (fila.tipo_extremo === 'negativo' ? 'negativo' : null) },
  ]);

  return lienzo([
    controles,
    seccion(
      null,
      tabla(
        ['Fecha inicial', 'Fecha final', 'Apertura', 'Cierre', 'Retorno (%)', 'Conteo', 'Completo', 'Tipo'],
        filas,
      ),
      `Zona horaria del mercado: ${activo.zonaHoraria}. Orden: retorno con signo `
      + 'descendente y, a igualdad, fecha ascendente.',
    ),
  ]);
}
