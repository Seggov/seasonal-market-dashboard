"""Lectura, validacion y medicion de calidad de series OHLC."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .configuracion import ActivoConfig


COLUMNAS_OBLIGATORIAS = (
    "timestamp_utc",
    "open",
    "high",
    "low",
    "close",
    "volume",
)
TOLERANCIA_NEUTRA = 1e-10
_COLUMNAS_OHLC = ("open", "high", "low", "close")
_COLUMNAS_NUMERICAS_OPCIONALES = ("volume", "change_percent", "return_percent")


class ErrorDatos(ValueError):
    """Indica que el CSV no tiene una estructura utilizable."""


@dataclass(slots=True)
class ResultadoValidacion:
    """Resultado completo sin perder la representacion original del CSV."""

    datos_originales: pd.DataFrame
    datos_validos: pd.DataFrame
    invalidos: pd.DataFrame
    resumen: dict[str, Any]
    advertencias: list[str]


def _agregar_motivo(
    motivos: list[list[str]], mascara: pd.Series | np.ndarray, mensaje: str
) -> None:
    for posicion in np.flatnonzero(np.asarray(mascara, dtype=bool)):
        motivos[int(posicion)].append(mensaje)


def _parsear_fecha_sesion(valor: object) -> pd.Timestamp:
    texto = str(valor).strip()
    if not texto:
        return pd.NaT
    try:
        fecha = pd.Timestamp(texto)
    except (TypeError, ValueError, OverflowError):
        return pd.NaT
    if fecha.tzinfo is not None:
        fecha = fecha.tz_localize(None)
    return fecha.normalize()


def _duracion_temporalidad(temporalidad: str) -> pd.Timedelta | None:
    coincidencia = re.fullmatch(
        r"\s*(\d+)\s*(m|min|h|d|dia|dias)\s*", temporalidad, re.IGNORECASE
    )
    if not coincidencia or int(coincidencia.group(1)) < 1:
        return None
    cantidad = int(coincidencia.group(1))
    unidad = coincidencia.group(2).lower()
    if unidad in {"m", "min"}:
        return pd.Timedelta(minutes=cantidad)
    if unidad == "h":
        return pd.Timedelta(hours=cantidad)
    return pd.Timedelta(days=cantidad)


def calcular_cobertura(
    datos_validos: pd.DataFrame, activo: ActivoConfig
) -> tuple[dict[str, Any], list[str]]:
    """Calcula intervalos esperados solo cuando el calendario es riguroso.

    Se admiten sesiones 24/7 y 24/5. En 24/5 se eliminan sabado y domingo
    segun la zona declarada. Para USA, Japon u otra sesion no se aproximan
    festivos ni horarios bursatiles: se informa que la cobertura no esta
    disponible.
    """

    sesion = activo.sesion.strip().lower()
    if sesion not in {"24/7", "24/5"}:
        aviso = (
            f"Cobertura no disponible para {activo.simbolo}: la sesion "
            f"{activo.sesion!r} requiere un calendario de mercado exacto."
        )
        return {"disponible": False, "razon": aviso}, [aviso]

    intervalo = _duracion_temporalidad(activo.temporalidad)
    if intervalo is None or intervalo > pd.Timedelta(days=1):
        aviso = (
            f"Cobertura no disponible para {activo.simbolo}: temporalidad "
            f"no soportada {activo.temporalidad!r}."
        )
        return {"disponible": False, "razon": aviso}, [aviso]

    columna_tiempo = (
        "timestamp_local" if activo.tipo_timestamp == "instante_utc" else "fecha_sesion"
    )
    if datos_validos.empty or columna_tiempo not in datos_validos:
        return {
            "disponible": True,
            "esperados": 0,
            "observados": 0,
            "faltantes": 0,
            "porcentaje": 0.0,
            "intervalos_faltantes": [],
        }, []

    observados = pd.DatetimeIndex(datos_validos[columna_tiempo].dropna().unique()).sort_values()
    if observados.empty:
        return {
            "disponible": True,
            "esperados": 0,
            "observados": 0,
            "faltantes": 0,
            "porcentaje": 0.0,
            "intervalos_faltantes": [],
        }, []

    esperados = pd.date_range(observados.min(), observados.max(), freq=intervalo)
    if sesion == "24/5":
        esperados = esperados[esperados.dayofweek < 5]
    faltantes = esperados.difference(observados)
    observados_esperados = len(esperados.intersection(observados))
    porcentaje = (
        observados_esperados / len(esperados) * 100.0 if len(esperados) else 0.0
    )
    return {
        "disponible": True,
        "esperados": len(esperados),
        "observados": observados_esperados,
        "faltantes": len(faltantes),
        "porcentaje": porcentaje,
        "intervalos_faltantes": [marca.isoformat() for marca in faltantes],
    }, []


def leer_y_validar_datos(
    activo: ActivoConfig, ruta_csv: str | Path | None = None
) -> ResultadoValidacion:
    """Lee un CSV sin escribirlo y valida cada fila contra su metadata.

    El formato fuente es deliberadamente especifico para los historiales H1
    locales: ``timestamp_utc,open,high,low,close,volume``. La metadata del
    activo se deriva de ``activos.json`` y nunca se confia a cada fila del CSV.
    Los duplicados conservan deterministicamente la primera aparicion.
    """

    ruta = Path(ruta_csv).expanduser().resolve() if ruta_csv else activo.archivo
    if not ruta.is_file():
        raise ErrorDatos(f"No existe el CSV de {activo.simbolo}: {ruta}.")
    try:
        originales = pd.read_csv(
            ruta,
            dtype=str,
            keep_default_na=False,
            skip_blank_lines=False,
            encoding="utf-8-sig",
            on_bad_lines="error",
        )
    except (OSError, pd.errors.ParserError, UnicodeError) as exc:
        raise ErrorDatos(f"No se pudo leer el CSV {ruta}: {exc}.") from exc

    faltantes = [columna for columna in COLUMNAS_OBLIGATORIAS if columna not in originales]
    adicionales = [columna for columna in originales if columna not in COLUMNAS_OBLIGATORIAS]
    if faltantes or adicionales:
        detalles = []
        if faltantes:
            detalles.append(f"faltan columnas obligatorias: {', '.join(faltantes)}")
        if adicionales:
            detalles.append(f"sobran columnas no admitidas: {', '.join(adicionales)}")
        raise ErrorDatos(
            f"CSV {ruta}: {'; '.join(detalles)}. "
            f"Se requieren exactamente: {', '.join(COLUMNAS_OBLIGATORIAS)}."
        )

    trabajo = originales.copy(deep=True)
    trabajo["symbol"] = activo.simbolo
    trabajo["timestamp"] = trabajo["timestamp_utc"]
    trabajo["timeframe"] = activo.temporalidad
    trabajo["change_percent"] = ""
    trabajo["return_percent"] = ""
    trabajo["source_file"] = ruta.name
    trabajo["ohlc_valid"] = "true"
    motivos: list[list[str]] = [[] for _ in range(len(trabajo))]
    filas_vacias = trabajo.loc[:, list(COLUMNAS_OBLIGATORIAS)].apply(
        lambda columna: columna.str.strip().eq("")
    ).all(axis=1)
    _agregar_motivo(motivos, filas_vacias, "fila vacia")

    simbolos = trabajo["symbol"]
    temporalidades = trabajo["timeframe"]

    convertidos: dict[str, pd.Series] = {}
    for columna in (*_COLUMNAS_OHLC, *_COLUMNAS_NUMERICAS_OPCIONALES):
        texto = trabajo[columna].str.strip()
        numero = pd.to_numeric(texto, errors="coerce")
        convertidos[columna] = numero
        obligatorio = columna in _COLUMNAS_OHLC
        invalido = numero.isna() & (texto.ne("") | obligatorio)
        no_finito = numero.notna() & ~np.isfinite(numero)
        _agregar_motivo(motivos, invalido | no_finito, f"{columna} no es numerico finito")

    for columna in _COLUMNAS_OHLC:
        _agregar_motivo(
            motivos, convertidos[columna].lt(0), f"{columna} no puede ser negativo"
        )
    _agregar_motivo(
        motivos, convertidos["volume"].lt(0), "volume no puede ser negativo"
    )

    apertura = convertidos["open"]
    maximo = convertidos["high"]
    minimo = convertidos["low"]
    cierre = convertidos["close"]
    incoherente = (
        maximo.lt(minimo)
        | maximo.lt(apertura)
        | maximo.lt(cierre)
        | minimo.gt(apertura)
        | minimo.gt(cierre)
    )
    _agregar_motivo(motivos, incoherente, "OHLC incoherente")

    texto_timestamp = trabajo["timestamp_utc"].str.strip()
    if activo.tipo_timestamp == "instante_utc":
        timestamp_utc = pd.to_datetime(
            texto_timestamp, errors="coerce", utc=True, format="mixed"
        )
        timestamp_local = timestamp_utc.dt.tz_convert(activo.zona)
        trabajo["timestamp_utc"] = timestamp_utc
        trabajo["timestamp_local"] = timestamp_local
        trabajo["timestamp_visual"] = timestamp_local
        tiempo_analisis = timestamp_utc
    else:
        fecha_sesion = pd.Series(
            (_parsear_fecha_sesion(valor) for valor in texto_timestamp),
            index=trabajo.index,
            dtype="datetime64[ns]",
        )
        trabajo["fecha_sesion"] = fecha_sesion
        trabajo["timestamp_visual"] = fecha_sesion
        tiempo_analisis = fecha_sesion
    _agregar_motivo(motivos, tiempo_analisis.isna(), "timestamp invalido")

    clave_tiempo = tiempo_analisis.astype("string").where(
        tiempo_analisis.notna(), texto_timestamp
    )
    claves_duplicado = pd.DataFrame(
        {
            "symbol": simbolos,
            "timestamp": clave_tiempo,
            "timeframe": temporalidades,
        }
    )
    duplicados = claves_duplicado.duplicated(keep="first")
    _agregar_motivo(
        motivos, duplicados, "duplicado; se conserva la primera aparicion"
    )

    mascara_valida = pd.Series([not fila for fila in motivos], index=trabajo.index)
    validos = trabajo.loc[mascara_valida].copy()
    for columna, valores in convertidos.items():
        validos[columna] = valores.loc[mascara_valida].astype(float)
    validos["ohlc_valid"] = True
    validos["symbol"] = simbolos.loc[mascara_valida]
    validos["timeframe"] = temporalidades.loc[mascara_valida]
    if activo.tipo_timestamp == "instante_utc":
        validos["timestamp"] = validos["timestamp_utc"]
    else:
        validos["timestamp"] = validos["fecha_sesion"]
    validos.reset_index(drop=True, inplace=True)

    invalidos = originales.loc[~mascara_valida].copy()
    invalidos.insert(0, "fila_csv", invalidos.index + 2)
    invalidos["motivo_invalidez"] = [
        "; ".join(motivos[posicion])
        for posicion in np.flatnonzero(~mascara_valida.to_numpy())
    ]
    invalidos.reset_index(drop=True, inplace=True)

    # El signo de una vela depende siempre de sus precios, no del porcentaje
    # publicado o precalculado por la fuente.
    retornos = pd.Series(np.nan, index=validos.index, dtype=float)
    apertura_valida = validos["open"]
    apertura_no_cero = apertura_valida.abs().gt(TOLERANCIA_NEUTRA)
    retornos.loc[apertura_no_cero] = (
        validos.loc[apertura_no_cero, "close"] / apertura_valida.loc[apertura_no_cero] - 1
    ) * 100
    validos["return_percent"] = retornos
    positivas = int(retornos.gt(TOLERANCIA_NEUTRA).sum())
    negativas = int(retornos.lt(-TOLERANCIA_NEUTRA).sum())
    neutras = int(retornos.abs().le(TOLERANCIA_NEUTRA).sum())

    cobertura, advertencias = calcular_cobertura(validos, activo)
    total = len(originales)
    cantidad_validos = len(validos)
    resumen: dict[str, Any] = {
        "filas_totales": total,
        "filas_validas": cantidad_validos,
        "filas_invalidas": len(invalidos),
        "porcentaje_valido": cantidad_validos / total * 100.0 if total else 0.0,
        "positivas": positivas,
        "negativas": negativas,
        "neutras": neutras,
        "tolerancia_neutra": TOLERANCIA_NEUTRA,
        "cobertura": cobertura,
    }
    if duplicados.any():
        advertencias.append(
            f"Se excluyeron {int(duplicados.sum())} duplicados; "
            "se conservo la primera aparicion."
        )

    return ResultadoValidacion(
        datos_originales=originales,
        datos_validos=validos,
        invalidos=invalidos,
        resumen=resumen,
        advertencias=advertencias,
    )
