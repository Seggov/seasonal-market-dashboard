"""Generador del contrato JSON estatico documentado en ``docs/CONTRATO_JSON.md``.

El sitio publicado solo dibuja: cada vista viaja ya calculada. Por eso aqui se
serializan resultados agregados, no las series de velas.

No escribe archivos: construye estructuras Python ya saneadas (sin ``NaN`` ni
infinitos, sin rutas absolutas) que ``tools/build_web.py`` serializa.
"""

from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd

from . import vistas
from .analisis import (
    dia_mes,
    dia_semana,
    estacionalidad_mes,
    eventos_extremos,
    filtrar_iqr,
    hora as estacionalidad_hora,
    permite_analisis_horario,
    semana_iso,
    temporalidad_a_minutos,
)
from .configuracion import ActivoConfig
from .datos import ResultadoValidacion


SCHEMA_VERSION = 2
PROCESSING_VERSION = "2.0.0"

METRICA_MATRIZ = "mean"
MINIMO_MATRIZ = 5
N_EXTREMOS = 10
PERIODO_EXTREMOS = "Día"


# --------------------------------------------------------------------------
# Saneamiento
# --------------------------------------------------------------------------


def limpiar(valor: Any) -> Any:
    """Convierte tipos de NumPy/pandas y todo valor no finito en ``null``.

    JSON estricto no admite ``NaN``, ``Infinity`` ni ``-Infinity``; el contrato
    exige que se publiquen como ``null``.
    """

    if valor is None or valor is pd.NaT:
        return None
    if isinstance(valor, (bool, np.bool_)):
        return bool(valor)
    if isinstance(valor, (int, np.integer)):
        return int(valor)
    if isinstance(valor, (float, np.floating)):
        numero = float(valor)
        return numero if math.isfinite(numero) else None
    if isinstance(valor, (str, bytes)):
        return valor.decode() if isinstance(valor, bytes) else valor
    if isinstance(valor, (pd.Timestamp, datetime)):
        return pd.Timestamp(valor).isoformat()
    if isinstance(valor, dict):
        return {str(clave): limpiar(item) for clave, item in valor.items()}
    if isinstance(valor, (list, tuple, set, np.ndarray, pd.Series, pd.Index)):
        return [limpiar(item) for item in valor]
    try:
        if pd.isna(valor):
            return None
    except (TypeError, ValueError):
        pass
    return str(valor)


def volcar_json(datos: Any) -> str:
    """Serializa en JSON estricto y compacto."""

    return json.dumps(
        limpiar(datos), ensure_ascii=False, allow_nan=False, separators=(",", ":")
    )


def hash_contenido(texto: str, longitud: int = 10) -> str:
    """Devuelve el prefijo SHA-256 usado para invalidar la cache HTTP."""

    return hashlib.sha256(texto.encode("utf-8")).hexdigest()[:longitud]


# --------------------------------------------------------------------------
# Tiempo
# --------------------------------------------------------------------------


def epochs(fechas: pd.Series) -> tuple[list[int], list[int]]:
    """Devuelve el instante absoluto y el epoch local de cada marca.

    El cliente formatea la hora del mercado a partir del epoch local, de modo
    que nunca necesita la zona horaria del navegador. ``Timestamp.timestamp()``
    es correcto en cualquier resolucion interna de pandas.
    """

    marcas = pd.to_datetime(fechas)
    absolutos = [int(marca.timestamp()) for marca in marcas]
    locales = [
        instante + int(marca.utcoffset().total_seconds() if marca.utcoffset() else 0)
        for instante, marca in zip(absolutos, marcas)
    ]
    return absolutos, locales


# --------------------------------------------------------------------------
# Vistas
# --------------------------------------------------------------------------


def _filas(marco: pd.DataFrame) -> list[dict[str, Any]]:
    return [limpiar(fila) for fila in marco.to_dict(orient="records")]


def _curvas_por_clave(
    marco: pd.DataFrame, clave: str, eje: str, valor: str
) -> list[dict[str, Any]]:
    """Agrupa una tabla larga en una curva por cada valor de ``clave``."""

    salida: list[dict[str, Any]] = []
    if marco.empty:
        return salida
    for valor_clave, grupo in marco.groupby(clave, sort=True, observed=True):
        ordenado = grupo.sort_values(eje)
        salida.append(
            {
                "clave": int(valor_clave),
                eje: [limpiar(item) for item in ordenado[eje]],
                "retorno": [limpiar(item) for item in ordenado[valor]],
            }
        )
    return salida


def vista_resumen(
    datos: pd.DataFrame, activo: ActivoConfig, columna_fecha: str
) -> dict[str, Any]:
    """Metricas generales y velas OHLC ya reducidas para el grafico."""

    metricas = vistas.metricas_resumen(datos, activo, columna_fecha)
    grafico, resumido = vistas.downsample_ohlc(datos, columna_fecha)
    absolutos, locales = epochs(grafico[columna_fecha]) if len(grafico) else ([], [])
    return {
        "metricas": limpiar(metricas),
        "velas": {
            "resumido": bool(resumido),
            "total": int(len(datos)),
            "mostradas": int(len(grafico)),
            "lt": locales,
            "o": [limpiar(v) for v in grafico["open"]] if len(grafico) else [],
            "h": [limpiar(v) for v in grafico["high"]] if len(grafico) else [],
            "l": [limpiar(v) for v in grafico["low"]] if len(grafico) else [],
            "c": [limpiar(v) for v in grafico["close"]] if len(grafico) else [],
        },
    }


def vista_periodo(
    datos: pd.DataFrame, activo: ActivoConfig, columna_fecha: str
) -> dict[str, Any]:
    """Retorno anual y pivote año x mes."""

    anual = vistas.agregar(datos, "year", activo, columna_fecha)
    mensual = vistas.agregar(datos, "month", activo, columna_fecha)
    if anual.empty or mensual.empty:
        return {"anual": [], "pivote": {"años": [], "meses": []}}
    años_anual = pd.to_datetime(anual["inicio"]).dt.year
    pivote = vistas.pivote_anual_mensual(anual, mensual)
    return {
        "anual": [
            {"año": int(año), "returnPercent": limpiar(valor)}
            for año, valor in zip(años_anual, anual["return_percent"])
        ],
        "pivote": {
            "años": [int(v) for v in pivote["año"]],
            "meses": [
                [limpiar(pivote.iloc[fila][mes]) for mes in range(1, 13)]
                for fila in range(len(pivote))
            ],
        },
    }


def _estacional(marco: pd.DataFrame, columnas: tuple[str, ...]) -> list[dict[str, Any]]:
    """Publica solo las columnas que la vista dibuja."""

    if marco.empty:
        return []
    return _filas(marco[list(columnas)])


def vista_mensual(
    datos: pd.DataFrame, activo: ActivoConfig, columna_fecha: str
) -> dict[str, Any]:
    """Estacionalidad mensual y las doce curvas historicas."""

    mensual = vistas.agregar(datos, "month", activo, columna_fecha)
    if mensual.empty:
        return {"estacional": [], "curvas": []}
    estacional = estacionalidad_mes(mensual, columna_fecha="inicio")
    diarios = vistas.datos_diarios(datos, activo, columna_fecha)
    curvas = vistas.curvas_mensuales(diarios, activo)
    return {
        "estacional": _estacional(estacional, ("numero_mes", "promedio", "n")),
        "curvas": _curvas_por_clave(curvas, "numero_mes", "dia_mes", "retorno_ponderado"),
    }


def vista_semanal(
    datos: pd.DataFrame, activo: ActivoConfig, columna_fecha: str
) -> dict[str, Any]:
    """Estacionalidad por semana ISO."""

    semanal = vistas.agregar(datos, "week", activo, columna_fecha)
    filtrado, _ = filtrar_iqr(semanal, activo=False)
    if filtrado.empty:
        return {"estacional": [], "promedioGeneral": None}
    estacional = semana_iso(filtrado, columna_fecha="inicio")
    return {
        "estacional": _estacional(estacional, ("semana_iso", "promedio", "n")),
        "promedioGeneral": limpiar(float(filtrado["return_percent"].mean())),
    }


def vista_dia_semana(
    datos: pd.DataFrame, activo: ActivoConfig, columna_fecha: str
) -> dict[str, Any]:
    """Estacionalidad por dia y trayectoria intradia acumulada."""

    diarios = vistas.datos_diarios(datos, activo, columna_fecha)
    estacional = dia_semana(diarios, columna_fecha="inicio")
    trayectorias, _ = vistas.curvas_intradia_por_dia(datos, activo, columna_fecha)
    return {
        "estacional": _estacional(estacional, ("numero_dia", "promedio", "n")),
        "trayectorias": _curvas_por_clave(trayectorias, "numero_dia", "hora", "retorno"),
    }


def vista_diaria(
    datos: pd.DataFrame, activo: ActivoConfig, columna_fecha: str
) -> dict[str, Any]:
    """Estacionalidad por dia del mes."""

    diarios = vistas.datos_diarios(datos, activo, columna_fecha)
    estacional = dia_mes(diarios, columna_fecha="inicio")
    if estacional.empty:
        return {"estacional": []}
    return {"estacional": _estacional(estacional, ("dia_mes", "promedio", "n"))}


def vista_horaria(
    datos: pd.DataFrame, activo: ActivoConfig, columna_fecha: str
) -> dict[str, Any]:
    """Estacionalidad horaria y retorno medio por hora y dia de semana."""

    if not permite_analisis_horario(activo.temporalidad):
        return {"disponible": False, "estacional": [], "curvas": []}
    horas = vistas.agregar(datos, "hour", activo, columna_fecha)
    if horas.empty:
        return {"disponible": True, "estacional": [], "curvas": []}
    estacional = estacionalidad_hora(horas, columna_fecha="inicio", temporalidad="1h")
    _, retornos = vistas.curvas_intradia_por_dia(datos, activo, columna_fecha)
    return {
        "disponible": True,
        "estacional": _estacional(estacional, ("hora", "promedio", "n")),
        "curvas": _curvas_por_clave(retornos, "numero_dia", "hora", "retorno"),
    }


def vista_matriz(
    datos: pd.DataFrame, activo: ActivoConfig, columna_fecha: str
) -> dict[str, Any]:
    """Matriz dia-hora del retorno medio, enmascarada por observaciones."""

    if not permite_analisis_horario(activo.temporalidad):
        return {"disponible": False}
    horas = vistas.agregar(datos, "hour", activo, columna_fecha)
    if horas.empty:
        return {"disponible": True, "dias": [], "horas": [], "valores": []}
    matriz, _, _ = vistas.matriz_con_minimo(
        horas, METRICA_MATRIZ, minimo_observaciones=MINIMO_MATRIZ
    )
    return {
        "disponible": True,
        "dias": [str(columna) for columna in matriz.columns],
        "horas": [str(indice) for indice in matriz.index],
        "valores": [[limpiar(v) for v in fila] for fila in matriz.to_numpy()],
        "minimoObservaciones": MINIMO_MATRIZ,
    }


def vista_extremos(
    datos: pd.DataFrame, activo: ActivoConfig, columna_fecha: str
) -> dict[str, Any]:
    """Mejores y peores periodos, con el orden real documentado en A-6."""

    periodos, fecha_periodo = vistas.periodo_seleccionado(
        PERIODO_EXTREMOS, datos, activo, columna_fecha
    )
    if periodos.empty:
        return {"periodo": PERIODO_EXTREMOS, "filas": []}
    extremos = eventos_extremos(
        periodos, n=N_EXTREMOS, umbral=None, columna_fecha=fecha_periodo
    )
    _, inicio_local = epochs(extremos["inicio"])
    filas = [
        {
            "inicioLocal": inicio_local[posicion],
            "return_percent": limpiar(fila["return_percent"]),
            "cantidad_registros": int(fila["cantidad_registros"]),
        }
        for posicion, fila in enumerate(extremos.to_dict(orient="records"))
    ]
    return {"periodo": PERIODO_EXTREMOS, "filas": filas}


def calcular_vistas(
    datos: pd.DataFrame, activo: ActivoConfig, columna_fecha: str
) -> dict[str, Any]:
    """Calcula las nueve vistas que dibuja el sitio."""

    return {
        "resumen": vista_resumen(datos, activo, columna_fecha),
        "periodo": vista_periodo(datos, activo, columna_fecha),
        "mensual": vista_mensual(datos, activo, columna_fecha),
        "semanal": vista_semanal(datos, activo, columna_fecha),
        "diaSemana": vista_dia_semana(datos, activo, columna_fecha),
        "diaria": vista_diaria(datos, activo, columna_fecha),
        "horaria": vista_horaria(datos, activo, columna_fecha),
        "matriz": vista_matriz(datos, activo, columna_fecha),
        "extremos": vista_extremos(datos, activo, columna_fecha),
    }


# --------------------------------------------------------------------------
# Informe y manifiesto
# --------------------------------------------------------------------------


def construir_informe(
    activo: ActivoConfig, datos: pd.DataFrame, columna_fecha: str
) -> dict[str, Any]:
    """Arma ``report.json``: identidad del activo y sus nueve vistas."""

    datos_sesion, _ = vistas.aplicar_sesion(
        datos, activo, columna_fecha, modo="Declarada"
    )
    return {
        "schemaVersion": SCHEMA_VERSION,
        "processingVersion": PROCESSING_VERSION,
        "symbol": activo.simbolo,
        "unidadMetrica": activo.unidad_retorno,
        "nombreMetrica": (
            "Cambio del rendimiento" if activo.unidad_retorno == "bps"
            else "Variación del precio" if activo.unidad_retorno == "puntos"
            else "Retorno"
        ),
        "vistas": calcular_vistas(datos_sesion, activo, columna_fecha),
    }


def entrada_manifiesto(
    activo: ActivoConfig, resultado: ResultadoValidacion, datos: pd.DataFrame,
    columna_fecha: str,
) -> dict[str, Any]:
    """Construye la ficha de catalogo de un activo, sin rutas absolutas."""

    fechas = pd.to_datetime(datos[columna_fecha]) if not datos.empty else pd.Series(dtype=object)
    return {
        "symbol": activo.simbolo,
        "nombre": activo.nombre,
        "categoria": activo.categoria,
        "mercado": activo.mercado,
        "zonaHoraria": activo.zona_horaria,
        "temporalidad": activo.temporalidad,
        "intradia": permite_analisis_horario(activo.temporalidad),
        "baseMinutes": temporalidad_a_minutos(activo.temporalidad),
        "primeraFecha": limpiar(fechas.min()) if len(fechas) else None,
        "ultimaFecha": limpiar(fechas.max()) if len(fechas) else None,
        "filasValidas": int(resultado.resumen["filas_validas"]),
    }


__all__ = [
    "PROCESSING_VERSION",
    "SCHEMA_VERSION",
    "calcular_vistas",
    "construir_informe",
    "entrada_manifiesto",
    "epochs",
    "hash_contenido",
    "limpiar",
    "vista_dia_semana",
    "vista_diaria",
    "vista_extremos",
    "vista_horaria",
    "vista_matriz",
    "vista_mensual",
    "vista_periodo",
    "vista_resumen",
    "vista_semanal",
    "volcar_json",
]
