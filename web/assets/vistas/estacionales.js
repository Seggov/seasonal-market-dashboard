/**
 * Vistas estacionales: por periodo, mensual, semanal, dia de la semana,
 * diario y horario.
 */

import {
  DIAS_TITULO, MESES_TITULO, celdaRetorno, elemento, estadoVacio,
  seccion, tabla, textoNumero,
} from '../ui.js';
import { barras, linea, mapaCalor } from '../graficos.js';

const lienzo = (hijos) => elemento('div', { clase: 'vista__lienzo' }, [].concat(hijos));

/** Rejilla de curvas pequeñas, una por clave (mes o día). */
function rejillaCurvas(curvas, etiquetas, prefijo, ejeX) {
  const tarjetas = etiquetas.map((nombre, indice) => {
    const clave = prefijo === 'mes' ? indice + 1 : indice;
    const curva = curvas.find((entrada) => entrada.clave === clave);
    // Streamlit omitia una curva con menos de dos puntos.
    if (!curva || curva.retorno.length < 2) {
      return estadoVacio(`${nombre}: información insuficiente.`);
    }
    return linea(curva[ejeX], curva.retorno, { titulo: nombre, altura: 260 });
  });
  return elemento('div', { clase: 'rejilla-graficos' }, tarjetas);
}

/* ------------------------------------------------- análisis por periodo */

export function vistaPeriodo({ vistas }) {
  const datos = vistas.periodo;
  if (!datos.anual.length) {
    return lienzo(estadoVacio('La información disponible no es suficiente para este análisis.'));
  }
  const grafico = barras(
    datos.anual.map((fila) => String(fila['año'])),
    datos.anual.map((fila) => fila.returnPercent),
    { titulo: 'Retorno por año', altura: 400 },
  );

  // El pivote de Streamlit muestra "-" en las celdas sin datos, no la etiqueta
  // larga de ausencia que usan el resto de tablas (contrato de paridad 5.3).
  const celdaPivote = (valor) => (
    Number.isFinite(valor) ? celdaRetorno(valor) : { texto: '-', clase: 'ausente' }
  );
  const { años, meses, retornoAnual } = datos.pivote;
  const filas = años.map((año, indice) => [
    String(año),
    ...meses[indice].map(celdaPivote),
    celdaPivote(retornoAnual[indice]),
  ]);
  return lienzo([
    seccion(null, grafico),
    seccion(
      'Retornos mensuales por año',
      tabla(['Año', ...MESES_TITULO, 'Retorno acumulado del año'], filas),
      'Cada celda es el retorno del mes completo, calculado desde su primera apertura hasta su último cierre.',
    ),
  ]);
}

/* -------------------------------------------------------- análisis mensual */

export function vistaMensual({ vistas }) {
  const datos = vistas.mensual;
  if (!datos.estacional.length) {
    return lienzo(estadoVacio('La información disponible no es suficiente para el análisis mensual.'));
  }
  return lienzo([
    seccion(null, barras(
      datos.estacional.map((fila) => fila.mes),
      datos.estacional.map((fila) => fila.promedio),
      { titulo: 'Retorno promedio histórico por mes', altura: 400 },
    )),
    seccion(
      'Curva histórica ponderada de cada mes',
      rejillaCurvas(datos.curvas, MESES_TITULO, 'mes', 'dia_mes'),
      'Cada curva parte de la primera apertura del mes y promedia el retorno acumulado '
      + 'observado en el mismo día del mes a través de todos los años disponibles.',
    ),
    seccion('Estadísticas por mes', tablaEstadisticas(datos.estacional, 'mes', 'Mes')),
  ]);
}

/** Tabla de estadisticas descriptivas comun a las vistas estacionales. */
function tablaEstadisticas(filas, claveEtiqueta, tituloEtiqueta) {
  return tabla(
    [tituloEtiqueta, 'Promedio', 'Mediana', 'Desv. típica', 'Mejor', 'Peor', '% positivos', 'Observaciones'],
    filas.map((fila) => [
      String(fila[claveEtiqueta]),
      celdaRetorno(fila.promedio),
      celdaRetorno(fila.mediana),
      { texto: textoNumero(fila.std, 2, '%') },
      celdaRetorno(fila.mejor),
      celdaRetorno(fila.peor),
      { texto: textoNumero(fila.positivo_pct, 2, '%') },
      { texto: textoNumero(fila.n, 0) },
    ]),
  );
}

/* -------------------------------------------------------- análisis semanal */

export function vistaSemanal({ vistas, filtros, alCambiarFiltros }) {
  const datos = vistas.semanal;
  const casilla = elemento('input', {
    type: 'checkbox', id: 'iqr-semanal', checked: filtros.semanal.quitarAtipicos,
  });
  casilla.addEventListener('change', () => alCambiarFiltros({
    semanal: { ...filtros.semanal, quitarAtipicos: casilla.checked },
  }));
  const controles = elemento('div', { clase: 'controles-vista' }, [
    elemento('label', { clase: 'casilla' }, [casilla, elemento('span', { texto: 'Excluir outliers semanales' })]),
    elemento('span', {
      clase: 'vista__nota',
      texto: filtros.semanal.quitarAtipicos
        ? `Método IQR Q1/Q3: ${textoNumero(datos.eliminados, 0)} semanas excluidas del cálculo.`
        : 'Filtro IQR desactivado: se conservan todas las semanas.',
    }),
  ]);

  if (!datos.estacional.length) {
    return lienzo([controles, estadoVacio('La información disponible no es suficiente para el análisis semanal.')]);
  }
  const etiquetas = datos.estacional.map((fila) => String(fila.semana_iso));
  const promedios = datos.estacional.map((fila) => fila.promedio);
  return lienzo([
    controles,
    seccion(null, barras(etiquetas, promedios, {
      titulo: 'Retorno histórico ponderado por semana ISO', altura: 400,
    })),
    seccion(null, linea(etiquetas, promedios, {
      titulo: 'Curva semanal comparada con el promedio general',
      altura: 420,
      promedio: datos.promedioGeneral,
    })),
    seccion('Estadísticas por semana ISO', tablaEstadisticas(datos.estacional, 'semana_iso', 'Semana ISO')),
  ]);
}

/* --------------------------------------------------------- día de la semana */

export function vistaDiaSemana({ vistas, activo }) {
  const datos = vistas.diaSemana;
  if (!datos.estacional.length) {
    return lienzo(estadoVacio('La información disponible no es suficiente para esta vista.'));
  }
  const bloques = [
    seccion(null, barras(
      datos.estacional.map((fila) => fila.dia_semana),
      datos.estacional.map((fila) => fila.promedio),
      { titulo: 'Retorno promedio por día de la semana', altura: 400 },
    )),
  ];
  if (!activo.intradia) {
    bloques.push(estadoVacio(
      'Los datos diarios permiten comparar el retorno de cada día, pero no contienen '
      + 'horas suficientes para construir las siete curvas intradía.',
    ));
  } else {
    bloques.push(seccion(
      'Trayectoria histórica ponderada por día',
      rejillaCurvas(datos.trayectorias, DIAS_TITULO, 'dia', 'hora'),
      'Retorno acumulado medio respecto a la primera apertura de cada día local.',
    ));
  }
  bloques.push(seccion('Estadísticas por día', tablaEstadisticas(datos.estacional, 'dia_semana', 'Día')));
  return lienzo(bloques);
}

/* --------------------------------------------------------- análisis diario */

export function vistaDiaria({ vistas }) {
  const datos = vistas.diaria;
  if (!datos.estacional.length) {
    return lienzo(estadoVacio('La información disponible no es suficiente para el análisis diario.'));
  }
  const etiquetas = datos.estacional.map((fila) => String(fila.dia_mes));
  const promedios = datos.estacional.map((fila) => fila.promedio);
  const porDia = new Map(datos.estacional.map((fila) => [fila.dia_mes, fila.promedio]));
  const dias = Array.from({ length: 31 }, (_, indice) => indice + 1);
  return lienzo([
    seccion(null, barras(etiquetas, promedios, {
      titulo: 'Retorno promedio por día del mes', altura: 400,
    })),
    seccion(null, linea(etiquetas, promedios, {
      titulo: 'Curva de retorno por día del mes', altura: 400, promedio: datos.promedio,
    })),
    seccion(null, mapaCalor({
      x: dias.map(String),
      y: ['Retorno'],
      z: [dias.map((dia) => porDia.get(dia) ?? null)],
    }, {
      titulo: 'Mapa de calor por día del mes', altura: 220, ejeX: 'Día del mes',
      etiquetaColor: 'Retorno (%)',
    })),
    seccion('Estadísticas por día del mes', tablaEstadisticas(datos.estacional, 'dia_mes', 'Día del mes')),
  ]);
}

/* -------------------------------------------------------- análisis horario */

export function vistaHoraria({ vistas, activo }) {
  const datos = vistas.horaria;
  if (!datos.disponible) {
    return lienzo(estadoVacio(
      `La temporalidad ${activo.temporalidad} es diaria o superior y no conserva `
      + 'horas observables. El análisis horario no está disponible.',
    ));
  }
  if (!datos.estacional.length) {
    return lienzo(estadoVacio('La información disponible no es suficiente para el análisis horario.'));
  }
  return lienzo([
    seccion(null, barras(
      datos.estacional.map((fila) => `${String(fila.hora).padStart(2, '0')}:00`),
      datos.estacional.map((fila) => fila.promedio),
      { titulo: 'Retorno promedio por hora', altura: 400 },
    )),
    seccion(
      'Comportamiento horario por día de la semana',
      rejillaCurvas(datos.curvas, DIAS_TITULO, 'dia', 'hora'),
      'Retorno medio de cada hora, sin acumular.',
    ),
    seccion('Estadísticas por hora', tablaEstadisticas(datos.estacional, 'hora', 'Hora')),
  ]);
}
