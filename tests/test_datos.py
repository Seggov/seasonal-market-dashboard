"""Pruebas de lectura, normalizacion y cobertura de datos OHLC."""

from collections.abc import Callable
from pathlib import Path

import pandas as pd
import pytest

from src.configuracion import ActivoConfig
from src.datos import (
    COLUMNAS_OBLIGATORIAS,
    ErrorDatos,
    calcular_cobertura,
    leer_y_validar_datos,
)


def test_rechaza_columnas_obligatorias_faltantes(
    crear_csv: Callable[..., Path], crear_activo: Callable[..., ActivoConfig]
) -> None:
    """Detalla las columnas requeridas que no aparecen en el CSV."""

    ruta_csv = crear_csv()
    tabla = pd.read_csv(ruta_csv)
    tabla.drop(columns="high").to_csv(ruta_csv, index=False)

    with pytest.raises(ErrorDatos, match="faltan columnas obligatorias: high"):
        leer_y_validar_datos(crear_activo(archivo=ruta_csv))


def test_rechaza_columnas_adicionales(
    crear_csv: Callable[..., Path], crear_activo: Callable[..., ActivoConfig]
) -> None:
    """Impide reintroducir metadata del formato historico anterior."""

    ruta_csv = crear_csv()
    tabla = pd.read_csv(ruta_csv)
    tabla["symbol"] = "PRUEBA"
    tabla.to_csv(ruta_csv, index=False)

    with pytest.raises(ErrorDatos, match="sobran columnas no admitidas: symbol"):
        leer_y_validar_datos(crear_activo(archivo=ruta_csv))


def test_deriva_metadata_desde_activo_sin_alterar_fuente(
    crear_csv: Callable[..., Path], crear_activo: Callable[..., ActivoConfig]
) -> None:
    """El CSV conserva seis columnas y la metadata se agrega al resultado valido."""

    ruta_csv = crear_csv([{"timestamp_utc": "2024-01-01T00:00:00Z"}])
    resultado = leer_y_validar_datos(crear_activo(archivo=ruta_csv))
    fila = resultado.datos_validos.iloc[0]

    assert list(resultado.datos_originales.columns) == list(COLUMNAS_OBLIGATORIAS)
    assert fila["symbol"] == "PRUEBA"
    assert fila["timeframe"] == "1h"
    assert fila["source_file"] == ruta_csv.name
    assert fila["return_percent"] == pytest.approx(5.0)
    assert str(resultado.datos_validos["timestamp"].dt.tz) == "UTC"


def test_separa_ohlc_coherente_e_incoherente(
    crear_csv: Callable[..., Path], crear_activo: Callable[..., ActivoConfig]
) -> None:
    """Conserva una vela coherente y explica una incoherencia OHLC."""

    ruta_csv = crear_csv(
        [
            {"timestamp_utc": "2024-01-01 00:00:00"},
            {"timestamp_utc": "2024-01-01 01:00:00", "high": 104},
        ]
    )

    resultado = leer_y_validar_datos(crear_activo(archivo=ruta_csv))

    assert len(resultado.datos_validos) == 1
    assert len(resultado.invalidos) == 1
    assert "OHLC incoherente" in resultado.invalidos.loc[0, "motivo_invalidez"]


def test_clasifica_signo_desde_open_close(
    crear_csv: Callable[..., Path], crear_activo: Callable[..., ActivoConfig]
) -> None:
    """El signo se deriva de precios porque el CSV no publica retornos."""

    ruta_csv = crear_csv(
        [
            {"timestamp_utc": "2024-01-01T00:00:00Z"},
            {
                "timestamp_utc": "2024-01-01T01:00:00Z",
                "open": 100,
                "close": 100,
            },
        ]
    )

    resumen = leer_y_validar_datos(crear_activo(archivo=ruta_csv)).resumen

    assert resumen["positivas"] == 1
    assert resumen["negativas"] == 0
    assert resumen["neutras"] == 1


def test_convierte_utc_a_zona_local_respetando_dst(
    crear_csv: Callable[..., Path], crear_activo: Callable[..., ActivoConfig]
) -> None:
    """Convierte instantes UTC a ambos lados del salto DST de Nueva York."""

    ruta_csv = crear_csv(
        [
            {"timestamp_utc": "2024-03-10T06:30:00Z"},
            {"timestamp_utc": "2024-03-10T07:30:00Z"},
        ]
    )
    activo = crear_activo(
        archivo=ruta_csv,
        zona_horaria="America/New_York",
        tipo_timestamp="instante_utc",
    )

    validos = leer_y_validar_datos(activo).datos_validos
    marcas = list(validos["timestamp_local"])

    assert [marca.hour for marca in marcas] == [1, 3]
    assert [marca.utcoffset().total_seconds() / 3600 for marca in marcas] == [-5, -4]
    assert str(validos["timestamp"].dt.tz) == "UTC"


def test_fecha_sesion_es_naive_y_se_normaliza_a_medianoche(
    crear_csv: Callable[..., Path], crear_activo: Callable[..., ActivoConfig]
) -> None:
    """Quita la hora sin inventar zona para una fecha de sesion."""

    ruta_csv = crear_csv(
        [{"timestamp_utc": "2024-07-15 18:45:30"}]
    )
    activo = crear_activo(
        archivo=ruta_csv, temporalidad="1d", tipo_timestamp="fecha_sesion"
    )

    fecha = leer_y_validar_datos(activo).datos_validos.loc[0, "fecha_sesion"]

    assert fecha == pd.Timestamp("2024-07-15")
    assert fecha.tzinfo is None
    assert fecha == fecha.normalize()


def test_cobertura_24_7_detecta_intervalo_faltante(
    crear_activo: Callable[..., ActivoConfig],
) -> None:
    """Cuenta como faltante un sabado dentro de una sesion continua."""

    activo = crear_activo(
        sesion="24/7", temporalidad="1d", tipo_timestamp="fecha_sesion"
    )
    datos = pd.DataFrame(
        {"fecha_sesion": pd.to_datetime(["2024-01-05", "2024-01-07"])}
    )

    cobertura, advertencias = calcular_cobertura(datos, activo)

    assert advertencias == []
    assert cobertura["esperados"] == 3
    assert cobertura["faltantes"] == 1
    assert cobertura["intervalos_faltantes"] == ["2024-01-06T00:00:00"]


def test_cobertura_24_5_no_se_estima_sin_calendario_exacto(
    crear_activo: Callable[..., ActivoConfig],
) -> None:
    """No infiere cobertura 24/5 con una rejilla que ignora pausas de mercado."""

    activo = crear_activo(
        sesion="24/5", temporalidad="1d", tipo_timestamp="fecha_sesion"
    )
    datos = pd.DataFrame(
        {"fecha_sesion": pd.to_datetime(["2024-01-05", "2024-01-08"])}
    )

    cobertura, advertencias = calcular_cobertura(datos, activo)

    assert cobertura["disponible"] is False
    assert "calendario" in cobertura["razon"]
    assert advertencias == [cobertura["razon"]]
