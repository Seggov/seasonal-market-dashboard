"""Generador del contrato JSON estatico documentado en ``docs/CONTRATO_JSON.md``.

No escribe archivos: construye estructuras Python ya saneadas (sin ``NaN`` ni
infinitos, sin rutas absolutas) que ``tools/build_web.py`` serializa.
"""

from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Sequence
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from . import vistas
from .analisis import (
    DIAS_SEMANA_ES,
    MESES_ES,
    dia_mes,
    dia_semana,
    estacionalidad_mes,
    estadisticas_retornos,
    eventos_extremos,
    filtrar_iqr,
    hora as estacionalidad_hora,
    permite_analisis_horario,
    semana_iso,
    temporalidad_a_minutos,
)
from .configuracion import ActivoConfig
from .datos import ResultadoValidacion


SCHEMA_VERSION = 1
PROCESSING_VERSION = "1.0.0"

# Un entero escalado debe seguir siendo exacto en un doble IEEE-754.
_MAX_ENTERO_EXACTO = 2**53
_MAX_DECIMALES = 12

METRICAS_MATRIZ_DEFECTO = "mean"
MINIMO_MATRIZ_DEFECTO = 5
FACTOR_IQR_DEFECTO = 1.5
N_EXTREMOS_DEFECTO = 5
PERIODO_EXTREMOS_DEFECTO = "Día"


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
    """Serializa en JSON estricto, compacto y con orden estable de claves."""

    return json.dumps(
        limpiar(datos),
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    )


def hash_contenido(texto: str, longitud: int = 10) -> str:
    """Devuelve el prefijo SHA-256 usado para invalidar la cache HTTP."""

    return hashlib.sha256(texto.encode("utf-8")).hexdigest()[:longitud]


# --------------------------------------------------------------------------
# Zonas horarias
# --------------------------------------------------------------------------


def tabla_transiciones(
    nombre_zona: str, desde: datetime, hasta: datetime
) -> dict[str, Any]:
    """Enumera los cambios de desplazamiento UTC de una zona IANA.

    Se explora dia a dia y se afina al segundo con busqueda binaria. El
    resultado permite convertir hora local a instante absoluto en el navegador
    sin consultar jamas la zona horaria del sistema.
    """

    zona = ZoneInfo(nombre_zona)
    inicio = (desde - timedelta(days=400)).astimezone(timezone.utc)
    fin = (hasta + timedelta(days=400)).astimezone(timezone.utc)

    def desplazamiento(instante: datetime) -> int:
        return int(instante.astimezone(zona).utcoffset().total_seconds())

    def abreviatura(instante: datetime) -> str:
        return instante.astimezone(zona).tzname() or nombre_zona

    inicial = desplazamiento(inicio)
    abreviatura_inicial = abreviatura(inicio)
    transiciones: list[list[int]] = []
    anterior = inicial
    cursor = inicio
    un_dia = timedelta(days=1)
    while cursor < fin:
        siguiente = min(cursor + un_dia, fin)
        actual = desplazamiento(siguiente)
        if actual != anterior:
            bajo, alto = cursor, siguiente
            while (alto - bajo) > timedelta(seconds=1):
                medio = bajo + (alto - bajo) / 2
                if desplazamiento(medio) == anterior:
                    bajo = medio
                else:
                    alto = medio
            transiciones.append([int(alto.timestamp()), actual, abreviatura(alto)])
            anterior = actual
        cursor = siguiente
    return {
        "name": nombre_zona,
        "initialOffset": inicial,
        "initialAbbr": abreviatura_inicial,
        "transitions": transiciones,
    }


# --------------------------------------------------------------------------
# Codificacion de series
# --------------------------------------------------------------------------


def _segundos_epoch(fechas: pd.Series) -> np.ndarray:
    """Convierte marcas a segundos enteros desde la epoca, sea cual sea su unidad.

    pandas 2 almacena ``datetime64`` con resolucion variable -- ``ns``, ``us``,
    ``ms`` o ``s`` -- y la elige al analizar el texto, de modo que puede
    diferir entre versiones y plataformas. Asumir nanosegundos produce marcas
    mil veces menores en un entorno que resuelva en microsegundos, asi que la
    unidad se normaliza explicitamente antes de convertir.
    """

    return pd.to_datetime(fechas).dt.as_unit("s").astype("int64").to_numpy()


def _decimales_necesarios(valores: np.ndarray) -> int | None:
    """Menor numero de decimales que representa exactamente todos los valores."""

    finitos = valores[np.isfinite(valores)]
    if finitos.size == 0:
        return 0
    for decimales in range(_MAX_DECIMALES + 1):
        if np.array_equal(np.round(finitos, decimales), finitos):
            return decimales
    return None


def _escala_comun(columnas: Sequence[np.ndarray]) -> int | None:
    """Elige una escala entera comun o ``None`` si no es representable."""

    decimales = 0
    for columna in columnas:
        necesarios = _decimales_necesarios(columna)
        if necesarios is None:
            return None
        decimales = max(decimales, necesarios)
    escala = 10**decimales
    for columna in columnas:
        finitos = columna[np.isfinite(columna)]
        if finitos.size and np.max(np.abs(finitos)) * escala >= _MAX_ENTERO_EXACTO:
            return None
        escalados = np.rint(finitos * escala)
        # La division de un entero exacto por una potencia de diez esta
        # correctamente redondeada: debe reproducir el doble original bit a bit.
        if not np.array_equal(escalados / escala, finitos):
            return None
    return escala


def _codificar_precios(valores: np.ndarray, escala: int | None) -> list[Any]:
    """Codifica una columna de precios como enteros delta o dobles literales."""

    if escala is None:
        return [limpiar(valor) for valor in valores]
    enteros = np.rint(valores * escala).astype(np.int64)
    salida = [int(enteros[0])]
    salida.extend(int(valor) for valor in np.diff(enteros))
    return salida


def _rle_desplazamientos(offsets: np.ndarray) -> list[list[int]]:
    """Comprime los desplazamientos UTC en tramos ``[indiceInicial, offset]``."""

    if offsets.size == 0:
        return []
    tramos = [[0, int(offsets[0])]]
    for indice in range(1, offsets.size):
        if int(offsets[indice]) != tramos[-1][1]:
            tramos.append([indice, int(offsets[indice])])
    return tramos


def construir_serie(
    marco: pd.DataFrame, simbolo: str, año: int, columna_fecha: str
) -> dict[str, Any]:
    """Empaqueta las velas de un año en el formato columnar del contrato."""

    fechas = pd.to_datetime(marco[columna_fecha])
    instantes = _segundos_epoch(fechas)
    offsets = np.array(
        [int(marca.utcoffset().total_seconds()) for marca in fechas], dtype=np.int64
    )
    columnas = {
        clave: pd.to_numeric(marco[clave], errors="coerce").to_numpy(dtype=float)
        for clave in ("open", "high", "low", "close")
    }
    escala = _escala_comun(list(columnas.values()))
    return {
        "schemaVersion": SCHEMA_VERSION,
        "symbol": simbolo,
        "year": int(año),
        "count": int(len(marco)),
        "scale": escala,
        "t0": int(instantes[0]),
        "dt": [int(valor) for valor in np.diff(instantes)],
        "off": _rle_desplazamientos(offsets),
        "o": _codificar_precios(columnas["open"], escala),
        "h": _codificar_precios(columnas["high"], escala),
        "l": _codificar_precios(columnas["low"], escala),
        "c": _codificar_precios(columnas["close"], escala),
    }


def fragmentar_por_año(
    datos: pd.DataFrame, columna_fecha: str
) -> list[tuple[int, pd.DataFrame]]:
    """Divide la serie por año local del mercado, en orden cronologico."""

    fechas = pd.to_datetime(datos[columna_fecha])
    años = fechas.dt.year
    return [
        (int(año), datos.loc[años.eq(año)].reset_index(drop=True))
        for año in sorted(años.unique())
    ]


# --------------------------------------------------------------------------
# Vistas precalculadas
# --------------------------------------------------------------------------


def _filas(marco: pd.DataFrame) -> list[dict[str, Any]]:
    return [limpiar(fila) for fila in marco.to_dict(orient="records")]


def epochs(fechas: pd.Series) -> tuple[list[int], list[int]]:
    """Devuelve el instante absoluto y el epoch local de cada marca.

    El cliente formatea la hora del mercado a partir del epoch local, de modo
    que nunca necesita la zona horaria del navegador ni un analizador de
    cadenas con desplazamiento.
    """

    marcas = pd.to_datetime(fechas)
    absolutos = [int(marca.timestamp()) for marca in marcas]
    locales = [
        instante + int(marca.utcoffset().total_seconds() if marca.utcoffset() else 0)
        for instante, marca in zip(absolutos, marcas)
    ]
    return absolutos, locales


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
                "muestras": [int(item) for item in ordenado["muestras"]],
            }
        )
    return salida


def vista_resumen(
    datos: pd.DataFrame, activo: ActivoConfig, columna_fecha: str
) -> dict[str, Any]:
    """Metricas generales y velas OHLC ya reducidas para el grafico."""

    metricas = vistas.metricas_resumen(datos, activo, columna_fecha)
    grafico, resumido = vistas.downsample_ohlc(datos, columna_fecha)
    absolutos, locales = (
        epochs(grafico[columna_fecha]) if len(grafico) else ([], [])
    )
    return {
        "metricas": limpiar(metricas),
        "velas": {
            "resumido": bool(resumido),
            "total": int(len(datos)),
            "mostradas": int(len(grafico)),
            "t": absolutos,
            "lt": locales,
            "o": [limpiar(valor) for valor in grafico["open"]] if len(grafico) else [],
            "h": [limpiar(valor) for valor in grafico["high"]] if len(grafico) else [],
            "l": [limpiar(valor) for valor in grafico["low"]] if len(grafico) else [],
            "c": [limpiar(valor) for valor in grafico["close"]] if len(grafico) else [],
        },
    }


def vista_periodo(
    datos: pd.DataFrame, activo: ActivoConfig, columna_fecha: str
) -> dict[str, Any]:
    """Retorno anual y pivote año x mes."""

    anual = vistas.agregar(datos, "year", activo, columna_fecha)
    mensual = vistas.agregar(datos, "month", activo, columna_fecha)
    if anual.empty or mensual.empty:
        return {"anual": [], "pivote": {"años": [], "meses": [], "retornoAnual": []}}
    años_anual = pd.to_datetime(anual["inicio"]).dt.year
    pivote = vistas.pivote_anual_mensual(anual, mensual)
    return {
        "anual": [
            {"año": int(año), "returnPercent": limpiar(valor)}
            for año, valor in zip(años_anual, anual["return_percent"])
        ],
        "pivote": {
            "años": [int(valor) for valor in pivote["año"]],
            "meses": [
                [limpiar(pivote.iloc[fila][mes]) for mes in range(1, 13)]
                for fila in range(len(pivote))
            ],
            "retornoAnual": [limpiar(valor) for valor in pivote["retorno_anual"]],
        },
    }


def vista_mensual(
    datos: pd.DataFrame, activo: ActivoConfig, columna_fecha: str
) -> dict[str, Any]:
    """Estacionalidad mensual y las doce curvas historicas."""

    mensual = vistas.agregar(datos, "month", activo, columna_fecha)
    if mensual.empty:
        return {"estacional": [], "curvas": []}
    estacional = estacionalidad_mes(mensual, columna_fecha="inicio")
    diarios = vistas.datos_diarios(datos, activo, columna_fecha)
    curvas = vistas.curvas_mensuales(diarios)
    return {
        "estacional": _filas(estacional),
        "curvas": _curvas_por_clave(
            curvas, "numero_mes", "dia_mes", "retorno_ponderado"
        ),
    }


def vista_semanal(
    datos: pd.DataFrame,
    activo: ActivoConfig,
    columna_fecha: str,
    *,
    quitar_atipicos: bool = False,
) -> dict[str, Any]:
    """Estacionalidad por semana ISO con filtro IQR opcional."""

    semanal = vistas.agregar(datos, "week", activo, columna_fecha)
    filtrado, eliminados = filtrar_iqr(semanal, activo=quitar_atipicos)
    if filtrado.empty:
        return {"estacional": [], "promedioGeneral": None, "eliminados": int(eliminados)}
    estacional = semana_iso(filtrado, columna_fecha="inicio")
    return {
        "estacional": _filas(estacional),
        "promedioGeneral": limpiar(float(filtrado["return_percent"].mean())),
        "eliminados": int(eliminados),
    }


def vista_dia_semana(
    datos: pd.DataFrame, activo: ActivoConfig, columna_fecha: str
) -> dict[str, Any]:
    """Estacionalidad por dia y trayectoria intradia acumulada."""

    diarios = vistas.datos_diarios(datos, activo, columna_fecha)
    estacional = dia_semana(diarios, columna_fecha="inicio")
    trayectorias, _ = vistas.curvas_intradia_por_dia(datos, activo, columna_fecha)
    return {
        "estacional": _filas(estacional),
        "trayectorias": _curvas_por_clave(
            trayectorias, "numero_dia", "hora", "retorno"
        ),
    }


def vista_diaria(
    datos: pd.DataFrame, activo: ActivoConfig, columna_fecha: str
) -> dict[str, Any]:
    """Estacionalidad por dia del mes."""

    diarios = vistas.datos_diarios(datos, activo, columna_fecha)
    estacional = dia_mes(diarios, columna_fecha="inicio")
    if estacional.empty:
        return {"estacional": [], "promedio": None}
    return {
        "estacional": _filas(estacional),
        "promedio": limpiar(float(estacional["promedio"].mean())),
    }


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
        "estacional": _filas(estacional),
        "curvas": _curvas_por_clave(retornos, "numero_dia", "hora", "retorno"),
    }


def vista_matriz(
    datos: pd.DataFrame,
    activo: ActivoConfig,
    columna_fecha: str,
    *,
    metrica: str = METRICAS_MATRIZ_DEFECTO,
    quitar_atipicos: bool = False,
    factor: float = FACTOR_IQR_DEFECTO,
    minimo_observaciones: int = MINIMO_MATRIZ_DEFECTO,
) -> dict[str, Any]:
    """Matriz dia-hora enmascarada por el minimo de observaciones."""

    if not permite_analisis_horario(activo.temporalidad):
        return {"disponible": False}
    horas = vistas.agregar(datos, "hour", activo, columna_fecha)
    if horas.empty:
        return {"disponible": True, "dias": [], "horas": [], "valores": [], "conteos": []}
    matriz, conteos, eliminados = vistas.matriz_con_minimo(
        horas,
        metrica,
        quitar_atipicos=quitar_atipicos,
        factor=factor,
        minimo_observaciones=minimo_observaciones,
    )
    return {
        "disponible": True,
        "metrica": metrica,
        "dias": [str(columna) for columna in matriz.columns],
        "horas": [str(indice) for indice in matriz.index],
        "valores": [[limpiar(valor) for valor in fila] for fila in matriz.to_numpy()],
        "conteos": [[limpiar(valor) for valor in fila] for fila in conteos.to_numpy()],
        "eliminados": int(eliminados),
        "minimoObservaciones": int(minimo_observaciones),
    }


def vista_extremos(
    datos: pd.DataFrame,
    activo: ActivoConfig,
    columna_fecha: str,
    *,
    periodo: str = PERIODO_EXTREMOS_DEFECTO,
    n: int = N_EXTREMOS_DEFECTO,
    umbral: float | None = None,
) -> dict[str, Any]:
    """Mejores y peores periodos, con el orden real documentado en A-6."""

    periodos, fecha_periodo = vistas.periodo_seleccionado(
        periodo, datos, activo, columna_fecha
    )
    if periodos.empty:
        return {"periodo": periodo, "n": int(n), "umbral": umbral, "filas": []}
    extremos = eventos_extremos(
        periodos, n=int(n), umbral=umbral, columna_fecha=fecha_periodo
    )
    inicio_abs, inicio_local = epochs(extremos["inicio"])
    fin_abs, fin_local = epochs(extremos["fin"])
    filas = [
        {
            "inicio": inicio_abs[posicion],
            "inicioLocal": inicio_local[posicion],
            "fin": fin_abs[posicion],
            "finLocal": fin_local[posicion],
            "open": limpiar(fila["open"]),
            "close": limpiar(fila["close"]),
            "return_percent": limpiar(fila["return_percent"]),
            "cantidad_registros": int(fila["cantidad_registros"]),
            "completo": bool(fila["completo"]),
            "tipo_extremo": str(fila["tipo_extremo"]),
        }
        for posicion, fila in enumerate(extremos.to_dict(orient="records"))
    ]
    return {
        "periodo": periodo,
        "n": int(n),
        "umbral": umbral,
        "filas": filas,
    }


def vistas_por_defecto(
    datos: pd.DataFrame, activo: ActivoConfig, columna_fecha: str
) -> dict[str, Any]:
    """Precalcula las diez vistas con la configuracion predeterminada."""

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
# Informe por activo
# --------------------------------------------------------------------------


def _cobertura_publicable(cobertura: dict[str, Any]) -> dict[str, Any]:
    """Publica los conteos de cobertura, no la lista de intervalos ausentes.

    ``intervalos_faltantes`` puede tener miles de marcas y ninguna vista lo
    usa: la interfaz solo muestra el porcentaje, igual que Streamlit.
    """

    resumido = {
        clave: valor
        for clave, valor in cobertura.items()
        if clave != "intervalos_faltantes"
    }
    if "intervalos_faltantes" in cobertura:
        resumido["muestraFaltantes"] = list(cobertura["intervalos_faltantes"])[:10]
    return resumido


def _motivos_invalidez(invalidos: pd.DataFrame) -> dict[str, int]:
    if invalidos.empty or "motivo_invalidez" not in invalidos:
        return {}
    conteo = invalidos["motivo_invalidez"].value_counts()
    return {str(motivo): int(cantidad) for motivo, cantidad in conteo.items()}


def construir_informe(
    resultado: ResultadoValidacion,
    activo: ActivoConfig,
    datos: pd.DataFrame,
    columna_fecha: str,
) -> dict[str, Any]:
    """Arma ``report.json``: calidad, sesion por defecto y vistas iniciales."""

    fechas = pd.to_datetime(datos[columna_fecha]) if not datos.empty else pd.Series(dtype=object)
    dias, horas = (
        vistas.dias_y_horas_observados(datos, columna_fecha)
        if not datos.empty
        else ([], [])
    )
    datos_sesion, detalle_sesion = vistas.aplicar_sesion(
        datos, activo, columna_fecha, modo="Declarada"
    )
    return {
        "schemaVersion": SCHEMA_VERSION,
        "processingVersion": PROCESSING_VERSION,
        "symbol": activo.simbolo,
        "calidad": {
            "filasTotales": int(resultado.resumen["filas_totales"]),
            "filasValidas": int(resultado.resumen["filas_validas"]),
            "filasInvalidas": int(resultado.resumen["filas_invalidas"]),
            "porcentajeValido": limpiar(resultado.resumen["porcentaje_valido"]),
            "velasUtilizadas": int(len(datos)),
            "fechaInicial": limpiar(fechas.min()) if len(fechas) else None,
            "fechaFinal": limpiar(fechas.max()) if len(fechas) else None,
            "positivas": int(resultado.resumen["positivas"]),
            "negativas": int(resultado.resumen["negativas"]),
            "neutras": int(resultado.resumen["neutras"]),
            "cobertura": limpiar(_cobertura_publicable(resultado.resumen["cobertura"])),
            "motivosInvalidez": _motivos_invalidez(resultado.invalidos),
            "advertencias": [str(aviso) for aviso in resultado.advertencias],
        },
        "sesionPorDefecto": {
            "modo": "Declarada",
            "detalle": detalle_sesion,
            "filtrado": bool(len(datos_sesion) != len(datos)),
            "velas": int(len(datos_sesion)),
        },
        "observado": {"dias": dias, "horas": horas},
        "opcionesPeriodo": vistas.opciones_periodo(activo),
        "etiquetas": {
            "meses": list(MESES_ES),
            "dias": list(DIAS_SEMANA_ES),
        },
        "defaultViews": vistas_por_defecto(datos_sesion, activo, columna_fecha),
    }


def entrada_manifiesto(
    activo: ActivoConfig,
    informe: dict[str, Any],
    años: Iterable[int],
    zona: dict[str, Any],
) -> dict[str, Any]:
    """Construye la ficha de catalogo de un activo, sin rutas absolutas."""

    sesion = activo.sesion.strip().lower()
    calidad = informe["calidad"]
    return {
        "symbol": activo.simbolo,
        "nombre": activo.nombre,
        "categoria": activo.categoria,
        "mercado": activo.mercado,
        "sesion": activo.sesion,
        "sesionReconocida": sesion if sesion in {"24/7", "24/5"} else None,
        "zonaHoraria": activo.zona_horaria,
        "temporalidad": activo.temporalidad,
        "tipoTimestamp": activo.tipo_timestamp,
        "formulaRetorno": activo.formula_retorno,
        "archivo": activo.archivo.name,
        "intradia": permite_analisis_horario(activo.temporalidad),
        "baseMinutes": temporalidad_a_minutos(activo.temporalidad),
        "primeraFecha": calidad["fechaInicial"],
        "ultimaFecha": calidad["fechaFinal"],
        "filasTotales": calidad["filasTotales"],
        "filasValidas": calidad["filasValidas"],
        "porcentajeValido": calidad["porcentajeValido"],
        "cobertura": calidad["cobertura"],
        "years": [int(año) for año in años],
        "tz": zona,
    }


__all__ = [
    "PROCESSING_VERSION",
    "SCHEMA_VERSION",
    "construir_informe",
    "construir_serie",
    "entrada_manifiesto",
    "fragmentar_por_año",
    "hash_contenido",
    "limpiar",
    "tabla_transiciones",
    "vista_diaria",
    "vista_dia_semana",
    "vista_extremos",
    "vista_horaria",
    "vista_matriz",
    "vista_mensual",
    "vista_periodo",
    "vista_resumen",
    "vista_semanal",
    "vistas_por_defecto",
    "volcar_json",
]
