/**
 * Arranque y orquestacion del panel estatico.
 *
 * Responsabilidades: cargar el manifiesto, pintar el catalogo, gestionar el
 * tema y la navegacion, y delegar todo el calculo en el Web Worker.
 *
 * Todas las URL son relativas al documento, de modo que el sitio funciona
 * igual en la raiz de un servidor local y bajo `/seasonal-market-dashboard/`
 * en GitHub Pages.
 */

import {
  CLAVES_VISTA, GRUPOS, VISTAS, aplicarParametros, escribirRuta, estado,
  filtrosPorDefecto, guardarTema, leerRuta, limpiarAlmacenamiento,
  parametrosDeFiltros, temaInicial,
} from './estado.js';
import {
  AUSENTE, elemento, estadoCargando, estadoError, estadoVacio,
  metricas, tabla, textoEntero, textoFecha, textoNumero, vaciar,
} from './ui.js';
import { repintar } from './graficos.js';
import { ZonaMercado } from './analytics/tz.js';
import { RENDERIZADORES } from './vistas-dom.js';

const $ = (selector) => document.querySelector(selector);

const nodos = {
  aviso: $('#aviso'),
  panel: $('#panel'),
  catalogo: $('#pantalla-catalogo'),
  analisis: $('#pantalla-analisis'),
  botoneraCategorias: $('#botonera-categorias'),
  tituloCategoria: $('#titulo-categoria'),
  tablaCatalogo: $('#tabla-catalogo'),
  selectorCategoria: $('#selector-categoria'),
  selectorActivo: $('#selector-activo'),
  tituloActivo: $('#titulo-activo'),
  metadataActivo: $('#metadata-activo'),
  navegacion: $('#navegacion-vistas'),
  detalleSesion: $('#detalle-sesion'),
  vista: $('#vista'),
  bloqueSesion: $('#bloque-sesion'),
  bloqueDatos: $('#bloque-datos'),
  datosGenerados: $('#datos-generados'),
  pieVersion: $('#pie-version'),
};

const urlBase = (relativo) => new URL(relativo, document.baseURI).href;

/* ------------------------------------------------------------------- tema */

function aplicarTema(tema) {
  document.documentElement.dataset.tema = tema;
  const boton = $('#alternar-tema');
  boton.setAttribute('aria-pressed', String(tema === 'oscuro'));
  $('#icono-tema').textContent = tema === 'oscuro' ? '☀️' : '🌙';
  repintar();
}

/* ----------------------------------------------------------------- avisos */

function mostrarAviso(mensaje, esError = false) {
  if (!mensaje) {
    nodos.aviso.hidden = true;
    return;
  }
  nodos.aviso.textContent = mensaje;
  nodos.aviso.classList.toggle('aviso--error', esError);
  nodos.aviso.hidden = false;
}

/* ----------------------------------------------------------------- worker */

let trabajador = null;
let contadorMensajes = 0;
const pendientes = new Map();

function obtenerTrabajador() {
  if (trabajador) return trabajador;
  trabajador = new Worker(new URL('./worker.js', import.meta.url), { type: 'module' });
  trabajador.addEventListener('message', (evento) => {
    const { id, tipo, carga } = evento.data;
    const pendiente = pendientes.get(id);
    if (!pendiente) return;
    pendientes.delete(id);
    if (tipo === 'error') pendiente.rechazar(new Error(carga.mensaje));
    else pendiente.resolver(carga);
  });
  trabajador.addEventListener('error', (evento) => {
    for (const { rechazar } of pendientes.values()) {
      rechazar(new Error(evento.message || 'El worker de cálculo falló.'));
    }
    pendientes.clear();
  });
  return trabajador;
}

function pedir(tipo, carga) {
  const id = (contadorMensajes += 1);
  return new Promise((resolver, rechazar) => {
    pendientes.set(id, { resolver, rechazar });
    obtenerTrabajador().postMessage({ id, tipo, carga });
  });
}

/* --------------------------------------------------------------- catalogo */

function etiquetaCategoria(clave) {
  return estado.manifiesto.categories?.[clave]
    ?? clave.replace(/_/g, ' ').replace(/\b\w/g, (letra) => letra.toUpperCase());
}

function categorias() {
  return [...new Set(estado.manifiesto.assets.map((activo) => activo.categoria))]
    .sort((uno, otro) => uno.localeCompare(otro, 'es'));
}

function activosDe(categoria) {
  return estado.manifiesto.assets.filter((activo) => activo.categoria === categoria);
}

function porcentajeCobertura(cobertura) {
  if (!cobertura?.disponible) return AUSENTE;
  return textoNumero(cobertura.porcentaje, 2, '%');
}

function pintarCatalogo() {
  const lista = categorias();
  if (!lista.includes(estado.categoria)) [estado.categoria] = lista;

  vaciar(nodos.botoneraCategorias);
  for (const categoria of lista) {
    const cantidad = activosDe(categoria).length;
    nodos.botoneraCategorias.append(elemento('button', {
      type: 'button',
      clase: `boton${categoria === estado.categoria ? ' activo' : ''}`,
      'aria-pressed': String(categoria === estado.categoria),
      texto: `${etiquetaCategoria(categoria)} · ${cantidad}`,
      onClick: () => {
        estado.categoria = categoria;
        pintarCatalogo();
        sincronizarSelectores();
      },
    }));
  }

  nodos.tituloCategoria.textContent = etiquetaCategoria(estado.categoria);
  const filas = activosDe(estado.categoria).map((activo) => [
    activo.symbol,
    activo.nombre,
    activo.mercado,
    activo.sesion,
    activo.zonaHoraria,
    activo.temporalidad,
    activo.primeraFecha ? activo.primeraFecha.slice(0, 10) : AUSENTE,
    activo.ultimaFecha ? activo.ultimaFecha.slice(0, 10) : AUSENTE,
    textoEntero(activo.filasValidas),
    textoNumero(activo.porcentajeValido, 2, '%'),
    porcentajeCobertura(activo.cobertura),
  ]);
  vaciar(nodos.tablaCatalogo).append(tabla(
    ['Símbolo', 'Activo', 'Mercado', 'Sesión', 'Zona horaria', 'Temporalidad',
      'Desde', 'Hasta', 'Velas válidas', '% válidas', 'Cobertura'],
    filas,
    'Catálogo precalculado durante la construcción del sitio.',
  ));
}

function sincronizarSelectores() {
  const lista = categorias();
  vaciar(nodos.selectorCategoria).append(...lista.map((categoria) => elemento('option', {
    value: categoria, texto: etiquetaCategoria(categoria),
    selected: categoria === estado.categoria,
  })));
  const disponibles = activosDe(estado.categoria);
  const elegido = disponibles.some((activo) => activo.symbol === estado.simbolo)
    ? estado.simbolo
    : disponibles[0]?.symbol;
  vaciar(nodos.selectorActivo).append(...disponibles.map((activo) => elemento('option', {
    value: activo.symbol, texto: `${activo.symbol} · ${activo.nombre}`,
    selected: activo.symbol === elegido,
  })));
}

/* --------------------------------------------------------------- análisis */

function pintarNavegacion() {
  vaciar(nodos.navegacion);
  for (const grupo of GRUPOS) {
    const vistasGrupo = VISTAS.filter((vista) => vista.grupo === grupo);
    nodos.navegacion.append(elemento('div', { clase: 'navegacion__grupo' }, [
      elemento('span', { clase: 'navegacion__etiqueta', texto: grupo }),
      ...vistasGrupo.map((vista) => elemento('button', {
        type: 'button',
        clase: `boton${vista.clave === estado.vista ? ' activo' : ''}`,
        'aria-pressed': String(vista.clave === estado.vista),
        texto: vista.titulo,
        onClick: () => irA(estado.simbolo, vista.clave),
      })),
    ]));
  }
}

function pintarCabeceraActivo() {
  const activo = estado.activo;
  nodos.tituloActivo.textContent = `${activo.symbol} · ${activo.nombre}`;
  const calidad = estado.informe.calidad;
  nodos.metadataActivo.replaceChildren(
    elemento('b', { texto: etiquetaCategoria(activo.categoria) }),
    document.createTextNode(` · ${activo.mercado} · Sesión declarada: ${activo.sesion} · ${activo.temporalidad}`),
    elemento('br'),
    document.createTextNode(
      `Zona: ${activo.zonaHoraria} · Timestamp: ${activo.tipoTimestamp} · `
      + `Periodo observado: ${calidad.fechaInicial?.slice(0, 16).replace('T', ' ') ?? AUSENTE}`
      + ` a ${calidad.fechaFinal?.slice(0, 16).replace('T', ' ') ?? AUSENTE}`,
    ),
  );
}

/** Descarga manifiesto, informe y series, y deja el activo listo para calcular. */
async function prepararActivo(simbolo) {
  const activo = estado.manifiesto.assets.find((entrada) => entrada.symbol === simbolo);
  if (!activo) throw new Error(`El activo ${simbolo} no está publicado.`);
  if (estado.activo?.symbol !== simbolo) {
    const respuesta = await fetch(urlBase(`data/${activo.report}`));
    if (!respuesta.ok) throw new Error(`No se pudo descargar el informe de ${simbolo}.`);
    estado.informe = await respuesta.json();
    estado.activo = activo;
    // La zona del mercado se reconstruye tambien en el hilo principal para
    // poder formatear fechas sin consultar la zona horaria del navegador.
    estado.zona = new ZonaMercado(activo.tz);
    await pedir('cargar', {
      activo,
      urls: Object.values(activo.series).map((relativo) => urlBase(`data/${relativo}`)),
    });
  }
  return activo;
}

let calculoEnCurso = 0;

async function recalcular() {
  const turno = (calculoEnCurso += 1);
  nodos.vista.replaceChildren(estadoCargando());
  try {
    const resultado = await pedir('calcular', {
      simbolo: estado.activo.symbol,
      activo: estado.activo,
      urls: Object.values(estado.activo.series).map((relativo) => urlBase(`data/${relativo}`)),
      filtros: estado.filtros,
    });
    if (turno !== calculoEnCurso) return;
    estado.vistas = resultado.vistas;
    nodos.detalleSesion.textContent = resultado.velasFiltradas === resultado.velasTotales
      ? resultado.detalleSesion
      : `${resultado.detalleSesion} ${textoEntero(resultado.velasFiltradas)} de `
        + `${textoEntero(resultado.velasTotales)} velas.`;
    pintarVista();
  } catch (error) {
    if (turno !== calculoEnCurso) return;
    nodos.vista.replaceChildren(estadoError(`No se pudo calcular esta sección: ${error.message}`));
  }
}

function pintarVista() {
  pintarNavegacion();
  const renderizador = RENDERIZADORES[estado.vista];
  if (!renderizador) {
    nodos.vista.replaceChildren(estadoVacio('Esta vista aún no está disponible.'));
    return;
  }
  if (estado.vista !== 'calidad' && estado.vistas === null) {
    nodos.vista.replaceChildren(
      estadoVacio('Los filtros actuales no dejan observaciones para analizar.'),
    );
    return;
  }
  try {
    nodos.vista.replaceChildren(renderizador({
      vistas: estado.vistas,
      informe: estado.informe,
      activo: estado.activo,
      zona: estado.zona,
      filtros: estado.filtros,
      alCambiarFiltros: actualizarFiltros,
    }));
  } catch (error) {
    nodos.vista.replaceChildren(estadoError(`No se pudo dibujar esta sección: ${error.message}`));
  }
}

/** Aplica un cambio de filtros: actualiza URL y recalcula o solo repinta. */
function actualizarFiltros(cambios, { recalcularTodo = true } = {}) {
  estado.filtros = { ...estado.filtros, ...cambios };
  escribirRuta({
    simbolo: estado.simbolo,
    vista: estado.vista,
    parametros: parametrosDeFiltros(estado.filtros, estado.vista),
  }, true);
  if (recalcularTodo) recalcular();
  else pintarVista();
}

/* ------------------------------------------------------------- navegación */

function irA(simbolo, vista) {
  escribirRuta({
    simbolo,
    vista,
    parametros: simbolo ? parametrosDeFiltros(estado.filtros, vista) : {},
  });
  atenderRuta();
}

function mostrarPantalla(cual) {
  nodos.catalogo.hidden = cual !== 'catalogo';
  nodos.analisis.hidden = cual !== 'analisis';
  nodos.bloqueSesion.hidden = cual !== 'analisis';
  nodos.bloqueDatos.hidden = cual !== 'analisis';
}

async function atenderRuta() {
  const ruta = leerRuta();
  if (!ruta.simbolo) {
    estado.simbolo = null;
    estado.activo = null;
    mostrarPantalla('catalogo');
    pintarCatalogo();
    sincronizarSelectores();
    return;
  }
  const vista = CLAVES_VISTA.includes(ruta.vista) ? ruta.vista : 'resumen';
  const cambiaActivo = estado.simbolo !== ruta.simbolo;
  estado.simbolo = ruta.simbolo;
  estado.vista = vista;
  if (cambiaActivo) estado.filtros = filtrosPorDefecto();
  estado.filtros = aplicarParametros(estado.filtros, ruta.parametros, vista);

  mostrarPantalla('analisis');
  nodos.vista.replaceChildren(estadoCargando('Preparando el activo…'));
  pintarNavegacion();
  try {
    await prepararActivo(ruta.simbolo);
  } catch (error) {
    nodos.vista.replaceChildren(estadoError(error.message));
    return;
  }
  estado.categoria = estado.activo.categoria;
  sincronizarSelectores();
  pintarCabeceraActivo();
  construirControlesSesion();
  if (cambiaActivo || estado.vistas === null) await recalcular();
  else pintarVista();
}

/* ------------------------------------------------- controles de la sesión */

function construirControlesSesion() {
  const activo = estado.activo;
  const declarada = (activo.sesion ?? '').trim().toLowerCase();
  const soloDeclarada = declarada === '24/7' || !activo.intradia;
  const ayuda = $('#sesion-ayuda');

  for (const radio of document.querySelectorAll('input[name="sesion-modo"]')) {
    radio.checked = radio.value === estado.filtros.sesion.modo;
    radio.disabled = soloDeclarada;
  }
  if (soloDeclarada) {
    ayuda.textContent = declarada === '24/7'
      ? 'La sesión declarada 24/7 abarca la serie completa; no hay filtro que aplicar.'
      : 'La temporalidad no conserva horas observables, así que se mantiene toda la serie.';
  } else if (estado.filtros.sesion.modo === 'Declarada' && declarada !== '24/5') {
    ayuda.textContent = 'No hay un calendario exacto para esta etiqueta de sesión. '
      + 'Se conservan todas las observaciones y no se presuponen horarios ni festivos.';
  } else {
    ayuda.textContent = 'La sesión declarada es la opción predeterminada.';
  }

  const observado = estado.informe.observado;
  const modo = estado.filtros.sesion.modo;
  const esObservada = modo === 'Observada' && !soloDeclarada;
  const esPersonalizada = modo === 'Personalizada' && !soloDeclarada;

  $('#sesion-dias').hidden = !(esObservada || esPersonalizada);
  $('#sesion-horas').hidden = !esObservada;
  $('#sesion-personalizada').hidden = !esPersonalizada;

  const diasElegidos = estado.filtros.sesion.dias ?? observado.dias;
  const horasElegidas = estado.filtros.sesion.horas ?? observado.horas;
  const nombresDias = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo'];

  const casillas = (contenedor, valores, elegidos, etiquetar, alCambiar) => {
    vaciar(contenedor).append(...valores.map((valor) => {
      const entrada = elemento('input', {
        type: 'checkbox', value: String(valor), checked: elegidos.includes(valor),
      });
      entrada.addEventListener('change', () => {
        const marcados = [...contenedor.querySelectorAll('input:checked')]
          .map((casilla) => Number(casilla.value));
        alCambiar(marcados);
      });
      return elemento('label', { clase: 'casilla' }, [entrada, elemento('span', { texto: etiquetar(valor) })]);
    }));
  };

  casillas($('#casillas-dias'), observado.dias, diasElegidos,
    (dia) => nombresDias[dia],
    (marcados) => actualizarFiltros({
      sesion: { ...estado.filtros.sesion, dias: marcados },
    }));
  casillas($('#casillas-horas'), observado.horas, horasElegidas,
    (hora) => `${String(hora).padStart(2, '0')}:00`,
    (marcados) => actualizarFiltros({
      sesion: { ...estado.filtros.sesion, horas: marcados },
    }));

  $('#sesion-inicio').value = estado.filtros.sesion.horaInicio;
  $('#sesion-fin').value = estado.filtros.sesion.horaFin;
}

/* ------------------------------------------------------------- cableado */

function cablear() {
  $('#alternar-tema').addEventListener('click', () => {
    const nuevo = document.documentElement.dataset.tema === 'oscuro' ? 'claro' : 'oscuro';
    aplicarTema(nuevo);
    guardarTema(nuevo);
  });

  $('#alternar-panel').addEventListener('click', (evento) => {
    const abierto = nodos.panel.dataset.abierto === 'true';
    nodos.panel.dataset.abierto = String(!abierto);
    evento.currentTarget.setAttribute('aria-expanded', String(!abierto));
  });

  nodos.selectorCategoria.addEventListener('change', (evento) => {
    estado.categoria = evento.target.value;
    pintarCatalogo();
    sincronizarSelectores();
  });

  $('#boton-analizar').addEventListener('click', () => {
    const simbolo = nodos.selectorActivo.value;
    if (simbolo) {
      nodos.panel.dataset.abierto = 'false';
      irA(simbolo, estado.vista ?? 'resumen');
    }
  });

  $('#boton-catalogo').addEventListener('click', () => {
    nodos.panel.dataset.abierto = 'false';
    irA(null, null);
  });

  $('#boton-recargar').addEventListener('click', () => {
    mostrarAviso('Recargando la versión publicada…');
    window.location.reload();
  });

  $('#boton-limpiar').addEventListener('click', () => {
    const hecho = limpiarAlmacenamiento();
    mostrarAviso(hecho
      ? 'Caché local vaciada. No se han descargado datos de mercado.'
      : 'Este navegador no permite almacenamiento local; no había nada que limpiar.');
  });

  for (const radio of document.querySelectorAll('input[name="sesion-modo"]')) {
    radio.addEventListener('change', (evento) => {
      actualizarFiltros({
        sesion: { ...estado.filtros.sesion, modo: evento.target.value, dias: null, horas: null },
      });
      construirControlesSesion();
    });
  }

  for (const campo of ['#sesion-inicio', '#sesion-fin']) {
    $(campo).addEventListener('change', () => {
      actualizarFiltros({
        sesion: {
          ...estado.filtros.sesion,
          horaInicio: $('#sesion-inicio').value || '09:00',
          horaFin: $('#sesion-fin').value || '17:00',
        },
      });
    });
  }

  window.addEventListener('hashchange', atenderRuta);
  window.matchMedia?.('(prefers-color-scheme: dark)').addEventListener?.('change', () => {
    if (!document.documentElement.dataset.temaFijado) aplicarTema(temaInicial());
  });
}

/* -------------------------------------------------------------- arranque */

async function arrancar() {
  aplicarTema(temaInicial());
  cablear();
  try {
    const respuesta = await fetch(urlBase('data/manifest.json'), { cache: 'no-cache' });
    if (!respuesta.ok) throw new Error(`HTTP ${respuesta.status}`);
    estado.manifiesto = await respuesta.json();
  } catch (error) {
    nodos.catalogo.replaceChildren(estadoError(
      'No se pudo cargar el catálogo de datos publicados. '
      + `Genere el sitio con "python tools/build_web.py" y sírvalo por HTTP. (${error.message})`,
    ));
    return;
  }
  const generado = estado.manifiesto.generatedAt?.replace('T', ' ').replace('Z', ' UTC');
  nodos.datosGenerados.textContent = `Datos generados el ${generado ?? AUSENTE}.`;
  nodos.pieVersion.textContent = `esquema v${estado.manifiesto.schemaVersion} · `
    + `procesamiento ${estado.manifiesto.processingVersion} · ${estado.manifiesto.contentHash} · `
    + `${textoEntero(estado.manifiesto.sourceRowCount)} observaciones`;
  await atenderRuta();
}

arrancar();

export { estado, metricas, tabla, textoFecha };
