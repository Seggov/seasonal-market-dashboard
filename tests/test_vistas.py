"""Pruebas de las transformaciones extraidas de la capa de presentacion.

Comprueban que ``src/vistas.py`` reproduce el comportamiento fijado en
``docs/PARIDAD.md`` sin depender de Streamlit.
"""

from __future__ import annotations

from datetime import time

import numpy as np
import pandas as pd
import pytest

from src import vistas
from src.analisis import estadisticas_retornos
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


@pytest.fixture
def utc() -> tuple[escenarios.Escenario, ActivoConfig]:
    escenario = escenarios.escenario_utc_continuo()
    return escenario, _activo(escenario)


def test_agregar_por_hora_conserva_una_vela_por_grupo(utc) -> None:
    """Con velas de una hora, cada grupo horario tiene exactamente una vela."""

    escenario, activo = utc
    horas = vistas.agregar(escenario.datos, "hour", activo, COLUMNA_FECHA)
    assert len(horas) == len(escenario.datos)
    assert set(horas["cantidad_registros"]) == {1}
    assert horas["completo"].all()


def test_agregar_usa_primera_apertura_y_ultimo_cierre(utc) -> None:
    """El retorno de un dia nunca es la suma de los retornos horarios."""

    escenario, activo = utc
    dias = vistas.agregar(escenario.datos, "day", activo, COLUMNA_FECHA)
    primer_dia = escenario.datos.iloc[:24]
    esperado = (
        primer_dia["close"].iloc[-1] / primer_dia["open"].iloc[0] - 1.0
    ) * 100.0
    assert dias["open"].iloc[0] == primer_dia["open"].iloc[0]
    assert dias["close"].iloc[0] == primer_dia["close"].iloc[-1]
    assert dias["return_percent"].iloc[0] == pytest.approx(esperado, abs=1e-12)
    suma_horaria = primer_dia["return_percent"].sum()
    assert dias["return_percent"].iloc[0] != pytest.approx(suma_horaria, abs=1e-6)


def test_agregar_devuelve_siempre_las_mismas_columnas(utc) -> None:
    escenario, activo = utc
    for periodo in ("hour", "day", "week", "month", "year"):
        salida = vistas.agregar(escenario.datos, periodo, activo, COLUMNA_FECHA)
        assert tuple(salida.columns) == vistas.COLUMNAS_AGREGADO


def test_curvas_mensuales_promedian_el_acumulado_desde_la_apertura_del_mes(utc) -> None:
    """A-5: la columna se llama ponderada pero el estadistico es media simple."""

    escenario, activo = utc
    diarios = vistas.datos_diarios(escenario.datos, activo, COLUMNA_FECHA)
    curvas = vistas.curvas_mensuales(diarios)
    assert set(curvas.columns) == {
        "numero_mes",
        "dia_mes",
        "retorno_ponderado",
        "muestras",
    }
    apertura_mes = float(diarios["open"].iloc[0])
    primer_dia = curvas[
        curvas["numero_mes"].eq(3) & curvas["dia_mes"].eq(1)
    ].iloc[0]
    cierre_dia_uno = float(diarios["close"].iloc[0])
    assert primer_dia["retorno_ponderado"] == pytest.approx(
        (cierre_dia_uno / apertura_mes - 1.0) * 100.0, abs=1e-12
    )
    assert int(primer_dia["muestras"]) == 1


def test_curvas_intradia_devuelven_trayectoria_y_retorno_horario(utc) -> None:
    escenario, activo = utc
    trayectoria, retornos = vistas.curvas_intradia_por_dia(
        escenario.datos, activo, COLUMNA_FECHA
    )
    assert set(trayectoria.columns) == {"numero_dia", "hora", "retorno", "muestras"}
    assert set(retornos.columns) == {"numero_dia", "hora", "retorno", "muestras"}
    # La trayectoria de la hora 0 es siempre el retorno de esa primera vela.
    hora_cero = trayectoria[trayectoria["hora"].eq(0)]
    retorno_cero = retornos[retornos["hora"].eq(0)]
    combinado = hora_cero.merge(retorno_cero, on=["numero_dia", "hora"])
    assert combinado["retorno_x"].to_numpy() == pytest.approx(
        combinado["retorno_y"].to_numpy(), abs=1e-12
    )


def test_downsample_respeta_el_maximo_y_agrega_ohlc(utc) -> None:
    escenario, activo = utc
    resumido, aplicado = vistas.downsample_ohlc(
        escenario.datos, COLUMNA_FECHA, maximo=20
    )
    assert aplicado is True
    assert len(resumido) <= 20
    tamano = int(np.ceil(len(escenario.datos) / 20))
    bloque = escenario.datos.iloc[:tamano]
    assert resumido["open"].iloc[0] == bloque["open"].iloc[0]
    assert resumido["close"].iloc[0] == bloque["close"].iloc[-1]
    assert resumido["high"].iloc[0] == bloque["high"].max()
    assert resumido["low"].iloc[0] == bloque["low"].min()


def test_downsample_no_toca_series_pequenas(utc) -> None:
    escenario, activo = utc
    resumido, aplicado = vistas.downsample_ohlc(
        escenario.datos, COLUMNA_FECHA, maximo=100_000
    )
    assert aplicado is False
    assert resumido is escenario.datos


def test_metricas_resumen_usan_el_ultimo_periodo(utc) -> None:
    escenario, activo = utc
    metricas = vistas.metricas_resumen(escenario.datos, activo, COLUMNA_FECHA)
    mensual = vistas.agregar(escenario.datos, "month", activo, COLUMNA_FECHA)
    estadisticas = estadisticas_retornos(escenario.datos)
    assert metricas["ultimo_cierre"] == float(escenario.datos["close"].iloc[-1])
    assert metricas["retorno_ultimo_mes"] == pytest.approx(
        float(mensual["return_percent"].iloc[-1]), abs=1e-12
    )
    assert metricas["positivo_pct"] == pytest.approx(estadisticas["positivo_pct"])
    assert metricas["velas"] == len(escenario.datos)


def test_metricas_resumen_con_serie_vacia(utc) -> None:
    _, activo = utc
    vacio = pd.DataFrame(
        columns=[COLUMNA_FECHA, "open", "high", "low", "close", "return_percent"]
    )
    metricas = vistas.metricas_resumen(vacio, activo, COLUMNA_FECHA)
    assert metricas["velas"] == 0
    assert np.isnan(metricas["ultimo_cierre"])


def test_pivote_anual_cubre_todos_los_anos_y_los_doce_meses() -> None:
    escenario = escenarios.escenario_tokio_semana_iso()
    activo = _activo(escenario)
    anual = vistas.agregar(escenario.datos, "year", activo, COLUMNA_FECHA)
    mensual = vistas.agregar(escenario.datos, "month", activo, COLUMNA_FECHA)
    tabla = vistas.pivote_anual_mensual(anual, mensual)
    assert list(tabla["año"]) == [2020, 2021]
    assert list(tabla.columns) == ["año", *range(1, 13), "retorno_anual"]
    # Solo diciembre de 2020 y enero de 2021 tienen datos.
    fila_2020 = tabla[tabla["año"].eq(2020)].iloc[0]
    assert np.isfinite(fila_2020[12])
    assert pd.isna(fila_2020[6])


def test_pivote_anual_vacio_devuelve_columnas_estables(utc) -> None:
    vacio = pd.DataFrame(columns=vistas.COLUMNAS_AGREGADO)
    tabla = vistas.pivote_anual_mensual(vacio, vacio)
    assert tabla.empty
    assert list(tabla.columns) == ["año", *range(1, 13), "retorno_anual"]


def test_matriz_enmascara_las_celdas_por_debajo_del_minimo(utc) -> None:
    escenario, activo = utc
    horas = vistas.agregar(escenario.datos, "hour", activo, COLUMNA_FECHA)
    matriz, conteos, eliminados = vistas.matriz_con_minimo(
        horas, "mean", minimo_observaciones=100
    )
    assert eliminados == 0
    assert matriz.isna().all().all()
    sin_mascara, _, _ = vistas.matriz_con_minimo(horas, "mean", minimo_observaciones=1)
    assert sin_mascara.notna().any().any()
    assert (conteos.fillna(0) >= 0).all().all()


def test_matriz_con_iqr_excluye_retornos(utc) -> None:
    escenario, activo = utc
    horas = vistas.agregar(escenario.datos, "hour", activo, COLUMNA_FECHA)
    _, _, eliminados = vistas.matriz_con_minimo(
        horas, "mean", quitar_atipicos=True, factor=0.1, minimo_observaciones=1
    )
    assert eliminados > 0


@pytest.mark.parametrize(
    ("sesion", "espera_filtro"),
    [
        ("24/7", False),
        ("24/5", True),
        ("Dukascopy 24/5 extendida", False),
        ("NYSE regular observada", False),
    ],
)
def test_sesion_declarada_solo_reconoce_las_etiquetas_exactas(
    sesion: str, espera_filtro: bool
) -> None:
    """Ambiguedad A-3: la comparacion es de igualdad exacta."""

    escenario = escenarios.escenario_utc_continuo()
    activo = _activo(escenario, sesion=sesion)
    filtrado, detalle = vistas.aplicar_sesion(
        escenario.datos, activo, COLUMNA_FECHA, modo="Declarada"
    )
    if espera_filtro:
        assert set(filtrado[COLUMNA_FECHA].dt.dayofweek) <= {0, 1, 2, 3, 4}
        assert len(filtrado) < len(escenario.datos)
        assert "lunes a viernes" in detalle
    else:
        assert len(filtrado) == len(escenario.datos)


def test_sesion_observada_filtra_dias_y_horas(utc) -> None:
    escenario, _ = utc
    activo = _activo(escenario, sesion="Dukascopy 24/5 extendida")
    filtrado, detalle = vistas.aplicar_sesion(
        escenario.datos,
        activo,
        COLUMNA_FECHA,
        modo="Observada",
        dias=[0, 1],
        horas=[9, 10, 11],
    )
    assert set(filtrado[COLUMNA_FECHA].dt.dayofweek) == {0, 1}
    assert set(filtrado[COLUMNA_FECHA].dt.hour) == {9, 10, 11}
    assert "Sesión observada" in detalle


def test_sesion_personalizada_acepta_texto_y_objetos_time(utc) -> None:
    escenario, _ = utc
    activo = _activo(escenario, sesion="Dukascopy 24/5 extendida")
    desde_texto, _ = vistas.aplicar_sesion(
        escenario.datos, activo, COLUMNA_FECHA, modo="Personalizada",
        hora_inicio="09:00", hora_fin="17:00",
    )
    desde_objeto, detalle = vistas.aplicar_sesion(
        escenario.datos, activo, COLUMNA_FECHA, modo="Personalizada",
        hora_inicio=time(9, 0), hora_fin=time(17, 0),
    )
    pd.testing.assert_frame_equal(desde_texto, desde_objeto)
    assert "[09:00, 17:00)" in detalle


def test_sesion_rechaza_un_modo_desconocido(utc) -> None:
    escenario, _ = utc
    activo = _activo(escenario, sesion="Dukascopy 24/5 extendida")
    with pytest.raises(ValueError, match="Modo de sesión no reconocido"):
        vistas.aplicar_sesion(escenario.datos, activo, COLUMNA_FECHA, modo="Otro")


def test_dias_y_horas_observados(utc) -> None:
    escenario, _ = utc
    dias, horas = vistas.dias_y_horas_observados(escenario.datos, COLUMNA_FECHA)
    assert dias == [0, 1, 2, 3, 4, 5, 6]
    assert horas == list(range(24))


def test_opciones_y_periodo_seleccionado(utc) -> None:
    escenario, activo = utc
    assert vistas.opciones_periodo(activo) == [
        "Vela base", "Hora", "Día", "Semana ISO", "Mes", "Año",
    ]
    base, columna = vistas.periodo_seleccionado(
        "Vela base", escenario.datos, activo, COLUMNA_FECHA
    )
    assert columna == COLUMNA_FECHA
    assert len(base) == len(escenario.datos)
    assert base["completo"].all()
    semanas, columna = vistas.periodo_seleccionado(
        "Semana ISO", escenario.datos, activo, COLUMNA_FECHA
    )
    assert columna == "inicio"
    assert len(semanas) < len(escenario.datos)


def test_datos_diarios_con_temporalidad_diaria(utc) -> None:
    """Una serie ya diaria se conserva vela a vela, sin reagregar."""

    escenario, _ = utc
    activo = _activo(escenario, temporalidad="1d")
    diarios = vistas.datos_diarios(escenario.datos, activo, COLUMNA_FECHA)
    assert len(diarios) == len(escenario.datos)
    assert diarios["completo"].all()
    assert set(diarios["cantidad_registros"]) == {1}
