"""Transformaciones puras que alimentan cada vista del panel.

Este modulo concentra la logica que antes vivia mezclada con los controles de
Streamlit en ``src/interfaz.py``. No importa ninguna libreria de presentacion,
no lee configuracion global y no escribe archivos: recibe DataFrames y devuelve
DataFrames o diccionarios.

Es la unica fuente de verdad analitica del generador estatico, y su
comportamiento esta fijado por ``docs/PARIDAD.md``.
"""

from __future__ import annotations

from datetime import time
from typing import Any, Sequence

import numpy as np
import pandas as pd

from .analisis import (
    TOLERANCIA,
    agregar_periodos,
    calcular_retorno,
    dia_mes,
    dia_semana,
    estacionalidad_mes,
    estadisticas_retornos,
    filtrar_iqr,
    filtrar_sesion_observada,
    filtrar_sesion_personalizada,
    hora,
    matriz_dia_hora,
    permite_analisis_horario,
    semana_iso,
    temporalidad_a_minutos,
)
from .configuracion import ActivoConfig


MAX_VELAS_GRAFICO = 3_000

COLUMNAS_AGREGADO = (
    "inicio",
    "fin",
    "open",
    "close",
    "return_percent",
    "cantidad_registros",
    "completo",
)

PERIODOS_INTERFAZ = {
    "Vela base": None,
    "Hora": "hour",
    "Día": "day",
    "Semana ISO": "week",
    "Mes": "month",
    "Año": "year",
}

METRICAS_MATRIZ = {
    "Promedio": "mean",
    "Mediana": "median",
    "% positivos": "positive_pct",
    "Desv. estándar": "std",
    "Conteo": "count",
}


def columna_fecha_analisis(datos: pd.DataFrame, activo: ActivoConfig) -> str:
    """Selecciona la columna temporal semanticamente correcta."""

    preferida = (
        "timestamp_local" if activo.tipo_timestamp == "instante_utc" else "fecha_sesion"
    )
    if preferida in datos:
        return preferida
    for candidata in ("timestamp", "timestamp_visual", "fecha_sesion"):
        if candidata in datos:
            return candidata
    raise ValueError("Los datos válidos no contienen una columna temporal utilizable.")


def preparar_datos(
    datos: pd.DataFrame, activo: ActivoConfig
) -> tuple[pd.DataFrame, str]:
    """Ordena la serie y calcula el retorno propio de cada vela por OHLC."""

    columna = columna_fecha_analisis(datos, activo)
    trabajo = datos.copy()
    trabajo[columna] = pd.to_datetime(trabajo[columna], errors="coerce")
    trabajo = trabajo.dropna(subset=[columna]).sort_values(columna, kind="stable")
    trabajo["return_percent"] = calcular_retorno(
        trabajo["open"], trabajo["close"], activo.formula_retorno
    )
    return trabajo.reset_index(drop=True), columna


def agregar(
    datos: pd.DataFrame, periodo: str, activo: ActivoConfig, columna_fecha: str
) -> pd.DataFrame:
    """Agrega periodos usando siempre primera apertura y ultimo cierre.

    Para temporalidades que dividen exactamente una hora existe una ruta
    vectorizada equivalente que evita recorrer decenas de miles de grupos.
    """

    if periodo == "hour":
        minutos = temporalidad_a_minutos(activo.temporalidad)
        if minutos >= 60 or 60 % minutos != 0:
            return agregar_periodos(
                datos,
                periodo,
                columna_fecha=columna_fecha,
                temporalidad=activo.temporalidad,
                formula_retorno=activo.formula_retorno,
            )
        trabajo = datos.sort_values(columna_fecha, kind="stable").copy()
        fechas = pd.to_datetime(trabajo[columna_fecha])
        trabajo["__fecha"] = fechas
        trabajo["__hora"] = fechas.dt.floor("h")
        paso = pd.Timedelta(minutes=minutos)
        trabajo["__en_rejilla"] = ((fechas - trabajo["__hora"]) % paso).eq(
            pd.Timedelta(0)
        )
        grupos = trabajo.groupby("__hora", sort=True, observed=True)
        salida = grupos.agg(
            inicio=("__fecha", "first"),
            fin=("__fecha", "last"),
            open=("open", "first"),
            close=("close", "last"),
            cantidad_registros=("__fecha", "size"),
            marcas_unicas=("__fecha", "nunique"),
            en_rejilla=("__en_rejilla", "all"),
        ).reset_index(drop=True)
        esperados = 60 // minutos
        inicio_hora = pd.to_datetime(salida["inicio"]).dt.floor("h")
        salida["completo"] = (
            salida["cantidad_registros"].eq(esperados)
            & salida["marcas_unicas"].eq(esperados)
            & salida["en_rejilla"]
            & salida["inicio"].eq(inicio_hora)
            & salida["fin"].eq(inicio_hora + pd.Timedelta(hours=1) - paso)
        )
        apertura = pd.to_numeric(salida["open"], errors="coerce")
        cierre = pd.to_numeric(salida["close"], errors="coerce")
        salida["return_percent"] = calcular_retorno(
            apertura, cierre, activo.formula_retorno
        )
        return salida[list(COLUMNAS_AGREGADO)]
    return agregar_periodos(
        datos,
        periodo,
        columna_fecha=columna_fecha,
        temporalidad=activo.temporalidad,
        formula_retorno=activo.formula_retorno,
    )


def datos_diarios(
    datos: pd.DataFrame, activo: ActivoConfig, columna_fecha: str
) -> pd.DataFrame:
    """Agrega primero velas intradia; conserva velas diarias ya observadas."""

    if permite_analisis_horario(activo.temporalidad):
        return agregar(datos, "day", activo, columna_fecha)
    salida = datos[[columna_fecha, "open", "close", "return_percent"]].copy()
    salida = salida.rename(columns={columna_fecha: "inicio"})
    salida["fin"] = salida["inicio"]
    salida["cantidad_registros"] = 1
    salida["completo"] = True
    return salida[list(COLUMNAS_AGREGADO)]


def curvas_mensuales(
    diarios: pd.DataFrame, activo: ActivoConfig | None = None
) -> pd.DataFrame:
    """Promedia la trayectoria acumulada diaria de cada mes historico.

    La columna se llama ``retorno_ponderado`` por compatibilidad historica pero
    el estadistico es una media simple (ambiguedad A-5 del contrato).
    """

    if diarios.empty:
        return pd.DataFrame(
            columns=["numero_mes", "dia_mes", "retorno_ponderado", "muestras"]
        )
    trabajo = diarios.sort_values("inicio", kind="stable").copy()
    fechas = pd.to_datetime(trabajo["inicio"])
    trabajo["ano"] = fechas.dt.year
    trabajo["numero_mes"] = fechas.dt.month
    trabajo["dia_mes"] = fechas.dt.day
    apertura_mes = trabajo.groupby(["ano", "numero_mes"], sort=False)[
        "open"
    ].transform("first")
    trabajo["retorno_acumulado"] = calcular_retorno(
        apertura_mes,
        trabajo["close"],
        activo.formula_retorno if activo is not None else "(close_final / open_inicial - 1) * 100",
    )
    return (
        trabajo.groupby(["numero_mes", "dia_mes"], observed=True)["retorno_acumulado"]
        .agg(retorno_ponderado="mean", muestras="count")
        .reset_index()
    )


def curvas_intradia_por_dia(
    datos: pd.DataFrame, activo: ActivoConfig, columna_fecha: str
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Calcula trayectoria acumulada y retorno horario por dia de semana."""

    columnas = ["numero_dia", "hora", "retorno", "muestras"]
    if not permite_analisis_horario(activo.temporalidad):
        vacio = pd.DataFrame(columns=columnas)
        return vacio, vacio.copy()
    horas = agregar(datos, "hour", activo, columna_fecha)
    if horas.empty:
        vacio = pd.DataFrame(columns=columnas)
        return vacio, vacio.copy()
    trabajo = horas.sort_values("inicio", kind="stable").copy()
    fechas = pd.to_datetime(trabajo["inicio"])
    trabajo["fecha_dia"] = fechas.dt.normalize()
    trabajo["numero_dia"] = fechas.dt.dayofweek
    trabajo["hora"] = fechas.dt.hour
    apertura_dia = trabajo.groupby("fecha_dia", sort=False)["open"].transform("first")
    trabajo["retorno_acumulado"] = calcular_retorno(
        apertura_dia, trabajo["close"], activo.formula_retorno
    )
    trayectoria = (
        trabajo.groupby(["numero_dia", "hora"], observed=True)["retorno_acumulado"]
        .agg(retorno="mean", muestras="count")
        .reset_index()
    )
    retornos_hora = (
        trabajo.groupby(["numero_dia", "hora"], observed=True)["return_percent"]
        .agg(retorno="mean", muestras="count")
        .reset_index()
    )
    return trayectoria, retornos_hora


def opciones_periodo(activo: ActivoConfig) -> list[str]:
    """Lista periodos compatibles con la temporalidad del activo."""

    opciones = ["Vela base"]
    if permite_analisis_horario(activo.temporalidad):
        opciones.append("Hora")
    opciones.extend(("Día", "Semana ISO", "Mes", "Año"))
    return opciones


def periodo_seleccionado(
    etiqueta: str, datos: pd.DataFrame, activo: ActivoConfig, columna_fecha: str
) -> tuple[pd.DataFrame, str]:
    """Resuelve el periodo elegido por controles de distribucion o extremos."""

    periodo = PERIODOS_INTERFAZ[etiqueta]
    if periodo is None:
        salida = datos.copy()
        salida["inicio"] = salida[columna_fecha]
        salida["fin"] = salida[columna_fecha]
        salida["cantidad_registros"] = 1
        salida["completo"] = True
        return salida, columna_fecha
    return agregar(datos, periodo, activo, columna_fecha), "inicio"


def downsample_ohlc(
    datos: pd.DataFrame, columna_fecha: str, maximo: int = MAX_VELAS_GRAFICO
) -> tuple[pd.DataFrame, bool]:
    """Resume velas consecutivas en bloques OHLC para acelerar el grafico."""

    if len(datos) <= maximo:
        return datos, False
    tamano_grupo = int(np.ceil(len(datos) / maximo))
    resumido = (
        datos.assign(__grupo=np.arange(len(datos)) // tamano_grupo)
        .groupby("__grupo", sort=True, observed=True)
        .agg(
            **{
                columna_fecha: (columna_fecha, "first"),
                "open": ("open", "first"),
                "high": ("high", "max"),
                "low": ("low", "min"),
                "close": ("close", "last"),
            }
        )
        .reset_index(drop=True)
    )
    return resumido, True


def metricas_resumen(
    datos: pd.DataFrame, activo: ActivoConfig, columna_fecha: str
) -> dict[str, Any]:
    """Calcula las cinco metricas generales de la vista Resumen."""

    if datos.empty:
        return {
            "ultimo_cierre": np.nan,
            "retorno_ultimo_mes": np.nan,
            "retorno_ultimo_ano": np.nan,
            "positivo_pct": np.nan,
            "negativo_pct": np.nan,
            "velas": 0,
        }
    estadisticas = estadisticas_retornos(datos)
    mensual = agregar(datos, "month", activo, columna_fecha)
    anual = agregar(datos, "year", activo, columna_fecha)
    return {
        "ultimo_cierre": float(datos.iloc[-1]["close"]),
        "retorno_ultimo_mes": (
            float(mensual["return_percent"].iloc[-1]) if not mensual.empty else np.nan
        ),
        "retorno_ultimo_ano": (
            float(anual["return_percent"].iloc[-1]) if not anual.empty else np.nan
        ),
        "positivo_pct": estadisticas["positivo_pct"],
        "negativo_pct": estadisticas["negativo_pct"],
        "velas": int(len(datos)),
    }


def pivote_anual_mensual(
    anual: pd.DataFrame, mensual: pd.DataFrame
) -> pd.DataFrame:
    """Construye la tabla año x mes con la columna de retorno anual.

    El indice cubre todos los años entre el primero y el ultimo observados y
    las columnas son los doce meses, aunque falten datos.
    """

    if anual.empty or mensual.empty:
        return pd.DataFrame(columns=["año", *range(1, 13), "retorno_anual"])
    trabajo = mensual.copy()
    fechas = pd.to_datetime(trabajo["inicio"])
    trabajo["año"] = fechas.dt.year
    trabajo["mes"] = fechas.dt.month
    ano_inicial = int(trabajo["año"].min())
    ano_final = int(trabajo["año"].max())
    tabla = trabajo.pivot(index="año", columns="mes", values="return_percent")
    tabla = tabla.reindex(
        index=range(ano_inicial, ano_final + 1), columns=range(1, 13)
    )
    anual_indexado = anual.copy()
    anual_indexado["año"] = pd.to_datetime(anual_indexado["inicio"]).dt.year
    tabla["retorno_anual"] = anual_indexado.set_index("año")["return_percent"]
    return tabla.reset_index()


def matriz_con_minimo(
    horas_agregadas: pd.DataFrame,
    metrica: str,
    *,
    quitar_atipicos: bool = False,
    factor: float = 1.5,
    minimo_observaciones: int = 5,
) -> tuple[pd.DataFrame, pd.DataFrame, int]:
    """Devuelve la matriz enmascarada, la matriz de conteos y los excluidos."""

    horas_filtradas, eliminados = filtrar_iqr(
        horas_agregadas, activo=quitar_atipicos, factor=float(factor)
    )
    matriz = matriz_dia_hora(
        horas_filtradas, metrica, columna_fecha="inicio", temporalidad="1h"
    )
    conteos = matriz_dia_hora(
        horas_filtradas, "count", columna_fecha="inicio", temporalidad="1h"
    )
    return matriz.mask(conteos < int(minimo_observaciones)), conteos, eliminados


def aplicar_sesion(
    datos: pd.DataFrame,
    activo: ActivoConfig,
    columna_fecha: str,
    *,
    modo: str = "Declarada",
    dias: Sequence[int] | None = None,
    horas: Sequence[int] | None = None,
    hora_inicio: str | time = time(9, 0),
    hora_fin: str | time = time(17, 0),
) -> tuple[pd.DataFrame, str]:
    """Aplica sesion declarada, observada o personalizada sin inventar horarios.

    Reproduce las ramas de ``interfaz._controles_sesion``, incluidas las
    ambiguedades A-3 y A-10 del contrato de paridad: una etiqueta de sesion que
    no sea exactamente ``24/7`` o ``24/5`` no filtra nada.
    """

    sesion = activo.sesion.strip().lower()
    if sesion == "24/7":
        return datos.copy(), f"Sesión declarada {activo.sesion}; sin filtro adicional."

    if not permite_analisis_horario(activo.temporalidad):
        if modo != "Declarada":
            return datos.copy(), f"{modo}: no aplicable a datos diarios; serie completa."
        return datos.copy(), f"Sesión declarada {activo.sesion}; sin filtro horario."

    if modo == "Declarada":
        if sesion == "24/5":
            filtrados = filtrar_sesion_observada(
                datos,
                dias_semana=[0, 1, 2, 3, 4],
                columna_fecha=columna_fecha,
                temporalidad=activo.temporalidad,
            )
            return filtrados, "Sesión declarada 24/5: lunes a viernes; sin inventar horas."
        return (
            datos.copy(),
            f"Sesión declarada {activo.sesion}; calendario exacto no disponible.",
        )

    if modo == "Observada":
        filtrados = filtrar_sesion_observada(
            datos,
            dias_semana=dias,
            horas=horas,
            columna_fecha=columna_fecha,
            temporalidad=activo.temporalidad,
        )
        return filtrados, "Sesión observada: solo días y horas presentes en el archivo."

    if modo != "Personalizada":
        raise ValueError(f"Modo de sesión no reconocido: {modo!r}.")

    inicio = time.fromisoformat(hora_inicio) if isinstance(hora_inicio, str) else hora_inicio
    fin = time.fromisoformat(hora_fin) if isinstance(hora_fin, str) else hora_fin
    filtrados = filtrar_sesion_personalizada(
        datos,
        inicio,
        fin,
        dias_semana=dias,
        columna_fecha=columna_fecha,
        temporalidad=activo.temporalidad,
    )
    return (
        filtrados,
        f"Sesión personalizada [{inicio:%H:%M}, {fin:%H:%M}); zona {activo.zona_horaria}.",
    )


def dias_y_horas_observados(
    datos: pd.DataFrame, columna_fecha: str
) -> tuple[list[int], list[int]]:
    """Enumera los dias de semana y las horas presentes en la serie."""

    fechas = pd.to_datetime(datos[columna_fecha])
    return (
        sorted(int(valor) for valor in fechas.dt.dayofweek.unique()),
        sorted(int(valor) for valor in fechas.dt.hour.unique()),
    )


__all__ = [
    "COLUMNAS_AGREGADO",
    "MAX_VELAS_GRAFICO",
    "METRICAS_MATRIZ",
    "PERIODOS_INTERFAZ",
    "agregar",
    "aplicar_sesion",
    "columna_fecha_analisis",
    "curvas_intradia_por_dia",
    "curvas_mensuales",
    "datos_diarios",
    "dia_mes",
    "dia_semana",
    "dias_y_horas_observados",
    "downsample_ohlc",
    "estacionalidad_mes",
    "hora",
    "matriz_con_minimo",
    "metricas_resumen",
    "opciones_periodo",
    "periodo_seleccionado",
    "pivote_anual_mensual",
    "preparar_datos",
    "semana_iso",
]
