"""Pruebas del contrato JSON estatico."""

from __future__ import annotations

import json
import math

import numpy as np
import pandas as pd
import pytest

from src import exportador, vistas
from src.configuracion import ActivoConfig
from tests import escenarios
from tests.escenarios import COLUMNA_FECHA


def _activo(escenario: escenarios.Escenario, **cambios: object) -> ActivoConfig:
    base = {
        "simbolo": escenario.nombre.upper(),
        "nombre": escenario.descripcion,
        "categoria": "prueba",
        "mercado": "Escenario sintetico",
        "sesion": escenario.sesion,
        "zona_horaria": escenario.zona,
        "temporalidad": escenario.temporalidad,
        "archivo": "sintetico.csv",
        "tipo_timestamp": "instante_utc",
        "formula_retorno": "(close / open - 1) * 100",
    }
    base.update(cambios)
    return ActivoConfig(**base)  # type: ignore[arg-type]


# --------------------------------------------------------------------------
# Saneamiento
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "valor", [float("nan"), float("inf"), float("-inf"), np.nan, pd.NA, pd.NaT, None]
)
def test_limpiar_convierte_todo_lo_no_finito_en_null(valor: object) -> None:
    assert exportador.limpiar(valor) is None


def test_limpiar_convierte_tipos_de_numpy() -> None:
    salida = exportador.limpiar(
        {"a": np.int64(3), "b": np.float64(1.5), "c": np.bool_(True)}
    )
    assert salida == {"a": 3, "b": 1.5, "c": True}
    assert isinstance(salida["a"], int)
    assert isinstance(salida["c"], bool)


def test_volcar_json_es_estricto() -> None:
    texto = exportador.volcar_json({"x": [1.0, float("nan"), float("inf")]})
    assert "NaN" not in texto and "Infinity" not in texto
    assert json.loads(texto) == {"x": [1.0, None, None]}


def test_hash_contenido_es_estable_y_sensible() -> None:
    assert exportador.hash_contenido("a") == exportador.hash_contenido("a")
    assert exportador.hash_contenido("a") != exportador.hash_contenido("b")
    assert len(exportador.hash_contenido("a", 16)) == 16


# --------------------------------------------------------------------------
# Tiempo
# --------------------------------------------------------------------------


@pytest.mark.parametrize("unidad", ["s", "ms", "us", "ns"])
def test_los_epochs_no_dependen_de_la_resolucion_de_pandas(unidad: str) -> None:
    """pandas 2 elige la resolucion al analizar; el resultado no puede cambiar."""

    escenario = escenarios.escenario_utc_continuo()
    marcas = escenario.datos[COLUMNA_FECHA]
    absolutos, locales = exportador.epochs(marcas.dt.as_unit(unidad))
    esperado = [int(marca.timestamp()) for marca in marcas]
    assert absolutos == esperado
    assert locales == esperado  # UTC: el epoch local coincide con el absoluto


def test_el_epoch_local_incorpora_el_desplazamiento() -> None:
    """Nueva York en noviembre: el epoch local va cuatro o cinco horas por detras."""

    escenario = escenarios.escenario_ny_otono()
    absolutos, locales = exportador.epochs(escenario.datos[COLUMNA_FECHA])
    desplazamientos = {local - absoluto for absoluto, local in zip(absolutos, locales)}
    assert desplazamientos == {-14400, -18000}


# --------------------------------------------------------------------------
# Vistas
# --------------------------------------------------------------------------


@pytest.fixture
def entorno() -> tuple[pd.DataFrame, ActivoConfig]:
    escenario = escenarios.escenario_utc_continuo()
    return escenario.datos, _activo(escenario)


def test_calcular_vistas_cubre_las_nueve_vistas(entorno) -> None:
    datos, activo = entorno
    salida = exportador.calcular_vistas(datos, activo, COLUMNA_FECHA)
    assert set(salida) == {
        "resumen", "periodo", "mensual", "semanal", "diaSemana",
        "diaria", "horaria", "matriz", "extremos",
    }


def test_las_vistas_son_json_estricto(entorno) -> None:
    datos, activo = entorno
    texto = exportador.volcar_json(
        exportador.calcular_vistas(datos, activo, COLUMNA_FECHA)
    )
    recargado = json.loads(texto)
    assert recargado["resumen"]["metricas"]["velas"] == len(datos)


def test_vista_resumen_publica_epoch_local_para_el_grafico(entorno) -> None:
    datos, activo = entorno
    salida = exportador.vista_resumen(datos, activo, COLUMNA_FECHA)
    metricas = vistas.metricas_resumen(datos, activo, COLUMNA_FECHA)
    assert salida["metricas"]["ultimo_cierre"] == metricas["ultimo_cierre"]
    assert salida["velas"]["total"] == len(datos)
    assert salida["velas"]["resumido"] is False
    assert len(salida["velas"]["lt"]) == len(datos)
    assert salida["velas"]["lt"][0] == int(datos[COLUMNA_FECHA].iloc[0].timestamp())


def test_vista_resumen_reduce_las_velas_por_encima_del_maximo(entorno) -> None:
    """El grafico nunca recibe mas de MAX_VELAS_GRAFICO puntos."""

    datos, activo = entorno
    salida = exportador.vista_resumen(datos, activo, COLUMNA_FECHA)
    assert salida["velas"]["mostradas"] <= vistas.MAX_VELAS_GRAFICO


def test_vista_periodo_publica_pivote_de_doce_meses(entorno) -> None:
    datos, activo = entorno
    salida = exportador.vista_periodo(datos, activo, COLUMNA_FECHA)
    assert salida["pivote"]["años"] == [2021]
    assert len(salida["pivote"]["meses"][0]) == 12
    assert salida["pivote"]["meses"][0][2] is not None  # marzo
    assert salida["pivote"]["meses"][0][0] is None  # enero sin datos


def test_las_vistas_estacionales_solo_publican_lo_que_dibujan(entorno) -> None:
    """Cada fila lleva la clave, el promedio y el tamaño de muestra."""

    datos, activo = entorno
    mensual = exportador.vista_mensual(datos, activo, COLUMNA_FECHA)
    assert set(mensual["estacional"][0]) == {"numero_mes", "promedio", "n"}
    horaria = exportador.vista_horaria(datos, activo, COLUMNA_FECHA)
    assert set(horaria["estacional"][0]) == {"hora", "promedio", "n"}
    semanal = exportador.vista_semanal(datos, activo, COLUMNA_FECHA)
    assert set(semanal["estacional"][0]) == {"semana_iso", "promedio", "n"}
    assert math.isfinite(semanal["promedioGeneral"])


def test_las_curvas_llevan_eje_y_retorno(entorno) -> None:
    datos, activo = entorno
    curvas = exportador.vista_mensual(datos, activo, COLUMNA_FECHA)["curvas"]
    assert curvas
    assert set(curvas[0]) == {"clave", "dia_mes", "retorno"}
    assert len(curvas[0]["dia_mes"]) == len(curvas[0]["retorno"])


def test_vista_matriz_enmascara_por_minimo(entorno) -> None:
    datos, activo = entorno
    salida = exportador.vista_matriz(datos, activo, COLUMNA_FECHA)
    assert salida["disponible"] is True
    assert salida["minimoObservaciones"] == exportador.MINIMO_MATRIZ
    assert len(salida["valores"]) == len(salida["horas"])
    assert all(len(fila) == len(salida["dias"]) for fila in salida["valores"])


def test_vista_matriz_y_horaria_no_disponibles_sin_intradia(entorno) -> None:
    datos, _ = entorno
    diario = _activo(escenarios.escenario_utc_continuo(), temporalidad="1d")
    assert exportador.vista_matriz(datos, diario, COLUMNA_FECHA) == {"disponible": False}
    assert exportador.vista_horaria(datos, diario, COLUMNA_FECHA)["disponible"] is False


def test_vista_extremos_respeta_el_orden_documentado(entorno) -> None:
    """Ambiguedad A-6: orden por retorno con signo, no por magnitud."""

    datos, activo = entorno
    salida = exportador.vista_extremos(datos, activo, COLUMNA_FECHA)
    retornos = [fila["return_percent"] for fila in salida["filas"]]
    assert retornos == sorted(retornos, reverse=True)
    assert len(salida["filas"]) <= 2 * exportador.N_EXTREMOS
    assert set(salida["filas"][0]) == {
        "inicioLocal", "return_percent", "cantidad_registros",
    }


# --------------------------------------------------------------------------
# Informe y manifiesto
# --------------------------------------------------------------------------


def _resultado(datos: pd.DataFrame):
    from src.datos import ResultadoValidacion

    return ResultadoValidacion(
        datos_originales=datos,
        datos_validos=datos,
        invalidos=pd.DataFrame(columns=["motivo_invalidez"]),
        resumen={
            "filas_totales": len(datos),
            "filas_validas": len(datos),
            "filas_invalidas": 0,
            "porcentaje_valido": 100.0,
            "positivas": 1,
            "negativas": 1,
            "neutras": 0,
            "tolerancia_neutra": 1e-10,
            "cobertura": {"disponible": False, "razon": "prueba"},
        },
        advertencias=[],
    )


def test_el_informe_no_publica_rutas_absolutas_ni_series() -> None:
    escenario = escenarios.escenario_utc_continuo()
    activo = _activo(escenario)
    informe = exportador.construir_informe(activo, escenario.datos, COLUMNA_FECHA)
    texto = exportador.volcar_json(informe)

    assert "C:\\\\" not in texto and "/home/" not in texto
    assert informe["schemaVersion"] == exportador.SCHEMA_VERSION
    # El informe es autosuficiente: identidad y vistas, nada mas.
    assert set(informe) == {"schemaVersion", "processingVersion", "symbol", "vistas"}


def test_la_entrada_del_manifiesto_describe_el_activo() -> None:
    escenario = escenarios.escenario_utc_continuo()
    activo = _activo(escenario)
    entrada = exportador.entrada_manifiesto(
        activo, _resultado(escenario.datos), escenario.datos, COLUMNA_FECHA
    )
    assert entrada["symbol"] == activo.simbolo
    assert entrada["intradia"] is True
    assert entrada["baseMinutes"] == 60
    assert entrada["filasValidas"] == len(escenario.datos)
    assert entrada["primeraFecha"].startswith("2021-03-01")
    # Nunca se publica la ruta del CSV de origen.
    assert "archivo" not in entrada
