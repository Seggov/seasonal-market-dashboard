"""Pruebas de agregacion y estadistica sobre velas pequenas."""

import pandas as pd
import pytest

from src.analisis import (
    agregar_periodos,
    dia_semana,
    estacionalidad_mes,
    filtrar_iqr,
    hora,
    matriz_dia_hora,
)


def _velas_desordenadas(fechas: list[str], temporalidad: str) -> pd.DataFrame:
    """Crea tres velas cuyo orden de entrada no es cronologico."""

    marcas = pd.to_datetime(fechas)
    cronologicas = pd.DataFrame(
        {
            "timestamp": marcas,
            "timeframe": temporalidad,
            "open": [100.0, 110.0, 120.0],
            "high": [106.0, 116.0, 131.0],
            "low": [99.0, 109.0, 119.0],
            "close": [105.0, 115.0, 130.0],
        }
    )
    return cronologicas.iloc[[2, 0, 1]].reset_index(drop=True)


@pytest.mark.parametrize(
    ("periodo", "temporalidad", "fechas"),
    [
        ("hour", "15m", ["2024-01-02 10:00", "2024-01-02 10:15", "2024-01-02 10:30"]),
        ("day", "1h", ["2024-01-02 09:00", "2024-01-02 10:00", "2024-01-02 11:00"]),
        ("week", "1d", ["2024-01-01", "2024-01-03", "2024-01-05"]),
        ("month", "1d", ["2024-01-01", "2024-01-15", "2024-01-31"]),
        ("year", "1d", ["2024-01-01", "2024-06-15", "2024-12-31"]),
    ],
)
def test_retorno_de_periodo_usa_primera_open_y_ultima_close(
    periodo: str, temporalidad: str, fechas: list[str]
) -> None:
    """Calcula cada escala con extremos cronologicos, no con orden de entrada."""

    resultado = agregar_periodos(
        _velas_desordenadas(fechas, temporalidad), periodo
    )

    assert len(resultado) == 1
    assert resultado.loc[0, "open"] == 100.0
    assert resultado.loc[0, "close"] == 130.0
    assert resultado.loc[0, "return_percent"] == pytest.approx(30.0)


def test_estacionalidad_por_mes_y_dia_de_semana() -> None:
    """Agrupa retornos con etiquetas espanolas y orden calendario."""

    datos = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(
                ["2024-01-01", "2024-01-02", "2024-02-05"]
            ),
            "return_percent": [10.0, -10.0, 20.0],
        }
    )

    por_mes = estacionalidad_mes(datos)
    por_dia = dia_semana(datos)

    assert por_mes["mes"].tolist() == ["enero", "febrero"]
    assert por_mes["promedio"].tolist() == pytest.approx([0.0, 20.0])
    assert por_dia["dia_semana"].tolist() == ["lunes", "martes"]
    assert por_dia["promedio"].tolist() == pytest.approx([15.0, -10.0])


def test_filtro_iqr_apagado_y_encendido() -> None:
    """El filtro conserva todo apagado y elimina el extremo encendido."""

    datos = pd.DataFrame({"return_percent": [0.0, 1.0, 2.0, 3.0, 100.0]})

    sin_filtro, eliminados_apagado = filtrar_iqr(datos, activo=False)
    con_filtro, eliminados_encendido = filtrar_iqr(datos, activo=True)

    pd.testing.assert_frame_equal(sin_filtro, datos)
    assert eliminados_apagado == 0
    assert con_filtro["return_percent"].tolist() == [0.0, 1.0, 2.0, 3.0]
    assert eliminados_encendido == 1


def test_analisis_horario_rechaza_temporalidad_diaria() -> None:
    """No interpreta una fecha diaria como observacion de medianoche."""

    datos = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(["2024-01-01"]),
            "timeframe": ["1d"],
            "return_percent": [1.0],
        }
    )

    with pytest.raises(ValueError, match="requiere datos intradia"):
        hora(datos)


def test_matriz_tiene_horas_en_filas_y_dias_en_columnas() -> None:
    """Orienta y etiqueta la matriz dia-hora segun el contrato publico."""

    datos = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(
                ["2024-01-01 09:00", "2024-01-01 10:00", "2024-01-02 09:00"]
            ),
            "timeframe": ["1h", "1h", "1h"],
            "return_percent": [1.0, 3.0, 5.0],
        }
    )

    matriz = matriz_dia_hora(datos)

    assert matriz.index.tolist() == ["09:00", "10:00"]
    assert matriz.columns.tolist() == ["lunes", "martes"]
    assert matriz.index.name == "hora"
    assert matriz.columns.name == "dia_semana"
    assert matriz.loc["09:00", "lunes"] == 1.0
    assert matriz.loc["09:00", "martes"] == 5.0
    assert pd.isna(matriz.loc["10:00", "martes"])
