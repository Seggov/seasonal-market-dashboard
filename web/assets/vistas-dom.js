/**
 * Registro de renderizadores de vista.
 *
 * Cada renderizador recibe las cargas ya calculadas por el worker y devuelve
 * un fragmento de DOM. No hacen calculos analiticos: solo presentacion.
 */

import { vistaCalidad, vistaResumen } from './vistas/resumen.js';
import {
  vistaDiaSemana, vistaDiaria, vistaHoraria, vistaMensual, vistaPeriodo, vistaSemanal,
} from './vistas/estacionales.js';
import { vistaExtremos, vistaMatriz } from './vistas/matriz.js';

/** @type {Record<string, (contexto: object) => Node>} */
export const RENDERIZADORES = {
  resumen: vistaResumen,
  calidad: vistaCalidad,
  periodo: vistaPeriodo,
  mensual: vistaMensual,
  semanal: vistaSemanal,
  diaSemana: vistaDiaSemana,
  diaria: vistaDiaria,
  horaria: vistaHoraria,
  matriz: vistaMatriz,
  extremos: vistaExtremos,
};
