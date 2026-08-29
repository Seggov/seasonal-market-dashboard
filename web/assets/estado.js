/**
 * Estado de la aplicacion y enrutado por hash.
 *
 * Se usa hash routing (`#/BTCUSDT/matriz?metrica=median`) porque GitHub Pages
 * publica el sitio bajo `/seasonal-market-dashboard/` y no puede reescribir
 * rutas del servidor. Todas las URL de recursos son relativas.
 */

export const VISTAS = [
  { clave: 'resumen', titulo: 'Resumen', grupo: 'Visión general' },
  { clave: 'calidad', titulo: 'Calidad de datos', grupo: 'Visión general' },
  { clave: 'periodo', titulo: 'Análisis por periodo', grupo: 'Periodos' },
  { clave: 'mensual', titulo: 'Análisis mensual', grupo: 'Periodos' },
  { clave: 'semanal', titulo: 'Análisis semanal', grupo: 'Periodos' },
  { clave: 'diaria', titulo: 'Análisis diario', grupo: 'Periodos' },
  { clave: 'diaSemana', titulo: 'Día de la semana', grupo: 'Estacionalidad' },
  { clave: 'horaria', titulo: 'Análisis horario', grupo: 'Estacionalidad' },
  { clave: 'matriz', titulo: 'Matriz día-hora', grupo: 'Estacionalidad' },
  { clave: 'extremos', titulo: 'Eventos extremos', grupo: 'Eventos' },
];

export const GRUPOS = ['Visión general', 'Periodos', 'Estacionalidad', 'Eventos'];

export const CLAVES_VISTA = VISTAS.map((vista) => vista.clave);

const CLAVE_TEMA = 'panel-estacional:tema';

/** Filtros por defecto, equivalentes a los valores iniciales de Streamlit. */
export function filtrosPorDefecto() {
  return {
    sesion: { modo: 'Declarada', dias: null, horas: null, horaInicio: '09:00', horaFin: '17:00' },
    semanal: { quitarAtipicos: false, factor: 1.5 },
    matriz: { metrica: 'mean', quitarAtipicos: false, factor: 1.5, minimoObservaciones: 5 },
    extremos: { periodo: 'Día', n: 5, umbral: null },
  };
}

export const estado = {
  manifiesto: null,
  categoria: null,
  simbolo: null,
  vista: 'resumen',
  activo: null,
  informe: null,
  zona: null,
  filtros: filtrosPorDefecto(),
  vistas: null,
  calculando: false,
};

/* --------------------------------------------------------------- enrutado */

/** Lee la ruta actual del hash: `#/SIMBOLO/vista?clave=valor`. */
export function leerRuta() {
  const bruto = window.location.hash.replace(/^#\/?/, '');
  const [camino, consulta = ''] = bruto.split('?');
  const partes = camino.split('/').filter(Boolean).map(decodeURIComponent);
  return {
    simbolo: partes[0] ?? null,
    vista: partes[1] ?? null,
    parametros: new URLSearchParams(consulta),
  };
}

/** Escribe la ruta sin apilar entradas de historial redundantes. */
export function escribirRuta({ simbolo, vista, parametros = {} }, reemplazar = false) {
  const consulta = new URLSearchParams();
  for (const [clave, valor] of Object.entries(parametros)) {
    if (valor !== null && valor !== undefined && valor !== '') consulta.set(clave, String(valor));
  }
  const texto = consulta.toString();
  const destino = simbolo
    ? `#/${encodeURIComponent(simbolo)}/${encodeURIComponent(vista ?? 'resumen')}${texto ? `?${texto}` : ''}`
    : '#/';
  if (window.location.hash === destino) return;
  if (reemplazar) window.history.replaceState(null, '', destino);
  else window.history.pushState(null, '', destino);
}

/** Serializa los filtros que merece la pena compartir por URL. */
export function parametrosDeFiltros(filtros, vista) {
  const parametros = {};
  if (filtros.sesion.modo !== 'Declarada') parametros.sesion = filtros.sesion.modo;
  if (filtros.sesion.modo === 'Personalizada') {
    parametros.desde = filtros.sesion.horaInicio;
    parametros.hasta = filtros.sesion.horaFin;
  }
  if (vista === 'semanal' && filtros.semanal.quitarAtipicos) parametros.iqr = '1';
  if (vista === 'matriz') {
    if (filtros.matriz.metrica !== 'mean') parametros.metrica = filtros.matriz.metrica;
    if (filtros.matriz.quitarAtipicos) parametros.iqr = String(filtros.matriz.factor);
    if (filtros.matriz.minimoObservaciones !== 5) parametros.min = filtros.matriz.minimoObservaciones;
  }
  if (vista === 'extremos') {
    if (filtros.extremos.periodo !== 'Día') parametros.periodo = filtros.extremos.periodo;
    if (filtros.extremos.umbral !== null) parametros.umbral = filtros.extremos.umbral;
    else if (filtros.extremos.n !== 5) parametros.n = filtros.extremos.n;
  }
  return parametros;
}

/** Aplica sobre los filtros los parametros presentes en la URL. */
export function aplicarParametros(filtros, parametros, vista) {
  const copia = structuredClone(filtros);
  const sesion = parametros.get('sesion');
  if (sesion && ['Declarada', 'Observada', 'Personalizada'].includes(sesion)) {
    copia.sesion.modo = sesion;
  }
  if (parametros.has('desde')) copia.sesion.horaInicio = parametros.get('desde');
  if (parametros.has('hasta')) copia.sesion.horaFin = parametros.get('hasta');
  if (vista === 'semanal') copia.semanal.quitarAtipicos = parametros.get('iqr') === '1';
  if (vista === 'matriz') {
    if (parametros.has('metrica')) copia.matriz.metrica = parametros.get('metrica');
    if (parametros.has('iqr')) {
      copia.matriz.quitarAtipicos = true;
      copia.matriz.factor = Number(parametros.get('iqr')) || 1.5;
    }
    if (parametros.has('min')) copia.matriz.minimoObservaciones = Number(parametros.get('min')) || 5;
  }
  if (vista === 'extremos') {
    if (parametros.has('periodo')) copia.extremos.periodo = parametros.get('periodo');
    if (parametros.has('umbral')) copia.extremos.umbral = Number(parametros.get('umbral'));
    if (parametros.has('n')) copia.extremos.n = Number(parametros.get('n')) || 5;
  }
  return copia;
}

/* ------------------------------------------------------------------- tema */

/** Tema efectivo: el guardado, o la preferencia del sistema. */
export function temaInicial() {
  try {
    const guardado = localStorage.getItem(CLAVE_TEMA);
    if (guardado === 'claro' || guardado === 'oscuro') return guardado;
  } catch {
    // Almacenamiento no disponible (modo privado): se usa la preferencia.
  }
  return window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'oscuro' : 'claro';
}

export function guardarTema(tema) {
  try {
    localStorage.setItem(CLAVE_TEMA, tema);
  } catch {
    // Sin almacenamiento el tema simplemente no persiste entre visitas.
  }
}

/** Vacia lo que la aplicacion haya guardado en este navegador. */
export function limpiarAlmacenamiento() {
  try {
    localStorage.removeItem(CLAVE_TEMA);
    return true;
  } catch {
    return false;
  }
}
