"""Nucleo estadistico para DataFrames de velas OHLC.

El modulo no descarga datos, no supone calendarios de mercado y no calcula
indicadores ni predicciones. Los cambios de una vela o periodo se calculan con
la formula declarada para el activo; no se suman cambios simples entre velas.
"""

from __future__ import annotations

from datetime import time
import re
from typing import Sequence

import numpy as np
import pandas as pd


TOLERANCIA = 1e-10

FORMULA_PORCENTUAL = "(close_final / open_inicial - 1) * 100"
FORMULA_PUNTOS_BASICOS = "(close_final - open_inicial) * 100"
FORMULA_CAMBIO_ABSOLUTO = "close_final - open_inicial"


def calcular_retorno(
    apertura: pd.Series | np.ndarray | float,
    cierre: pd.Series | np.ndarray | float,
    formula: str = FORMULA_PORCENTUAL,
) -> pd.Series | np.ndarray | float:
    """Calcula la variacion segun la formula declarada para el instrumento."""

    apertura_num = pd.to_numeric(apertura, errors="coerce")
    cierre_num = pd.to_numeric(cierre, errors="coerce")
    if formula == FORMULA_PUNTOS_BASICOS:
        return (cierre_num - apertura_num) * 100.0
    if formula == FORMULA_CAMBIO_ABSOLUTO:
        return cierre_num - apertura_num
    if formula not in {FORMULA_PORCENTUAL, "(close / open - 1) * 100"}:
        raise ValueError(f"Formula de retorno no reconocida: {formula!r}.")
    precios_positivos = (apertura_num > TOLERANCIA) & (cierre_num > TOLERANCIA)
    return np.where(
        precios_positivos,
        (cierre_num / apertura_num - 1.0) * 100.0,
        np.nan,
    )

MESES_ES = (
    "enero",
    "febrero",
    "marzo",
    "abril",
    "mayo",
    "junio",
    "julio",
    "agosto",
    "septiembre",
    "octubre",
    "noviembre",
    "diciembre",
)

DIAS_SEMANA_ES = (
    "lunes",
    "martes",
    "miercoles",
    "jueves",
    "viernes",
    "sabado",
    "domingo",
)

_COLUMNAS_FECHA = ("timestamp", "inicio", "fecha_analisis", "fecha_sesion", "fecha")
_COLUMNAS_TEMPORALIDAD = ("temporalidad", "timeframe")
_PERIODOS = {
    "hour": "hour",
    "hora": "hour",
    "h": "hour",
    "day": "day",
    "dia": "day",
    "d": "day",
    "week": "week",
    "semana": "week",
    "iso_week": "week",
    "month": "month",
    "mes": "month",
    "year": "year",
    "ano": "year",
    "año": "year",
}


def temporalidad_a_minutos(temporalidad: str) -> int:
    """Convierte una temporalidad fija a minutos.

    Admite, entre otras formas, ``15m``, ``1h``, ``1d`` y ``1w``. Meses y
    anos no se convierten porque no tienen una duracion fija. La ``m``
    minuscula siempre significa minutos.
    """

    if not isinstance(temporalidad, str) or not temporalidad.strip():
        raise ValueError("La temporalidad debe ser un texto no vacio.")

    valor = temporalidad.strip().lower().replace(" ", "")
    aliases = {
        "minuto": "1m",
        "minutos": "1m",
        "hora": "1h",
        "horas": "1h",
        "dia": "1d",
        "dias": "1d",
        "día": "1d",
        "días": "1d",
        "semana": "1w",
        "semanas": "1w",
    }
    valor = aliases.get(valor, valor)
    coincidencia = re.fullmatch(
        r"(\d+)(m|min|mins|minute|minutes|h|hr|hour|hours|d|day|days|w|wk|week|weeks)",
        valor,
    )
    if not coincidencia:
        if re.fullmatch(r"\d+(mo|mon|month|months|y|yr|year|years)", valor):
            raise ValueError("Meses y anos no tienen una duracion fija en minutos.")
        raise ValueError(f"Temporalidad no reconocida: {temporalidad!r}.")

    cantidad = int(coincidencia.group(1))
    if cantidad <= 0:
        raise ValueError("La temporalidad debe ser mayor que cero.")
    unidad = coincidencia.group(2)
    if unidad in {"m", "min", "mins", "minute", "minutes"}:
        factor = 1
    elif unidad in {"h", "hr", "hour", "hours"}:
        factor = 60
    elif unidad in {"d", "day", "days"}:
        factor = 24 * 60
    else:
        factor = 7 * 24 * 60
    return cantidad * factor


def permite_analisis_horario(temporalidad: str) -> bool:
    """Indica si la temporalidad permite agregar o analizar por hora.

    Requiere que la temporalidad sea sub-horaria o de 1 hora exacta (debe
    dividir 60 minutos sin residuo). Temporalidades superiores (como 4h o 1d)
    no se pueden subdividir en horas.
    """

    try:
        minutos = temporalidad_a_minutos(temporalidad)
        return minutos <= 60 and (60 % minutos == 0)
    except ValueError:
        return False


def _resolver_columna_fecha(datos: pd.DataFrame, columna_fecha: str | None) -> str:
    if columna_fecha is not None:
        if columna_fecha not in datos.columns:
            raise ValueError(f"No existe la columna de fecha {columna_fecha!r}.")
        return columna_fecha
    for candidata in _COLUMNAS_FECHA:
        if candidata in datos.columns:
            return candidata
    raise ValueError(
        "Falta una columna temporal: timestamp, fecha_analisis, fecha_sesion o fecha."
    )


def _resolver_temporalidad(
    datos: pd.DataFrame, temporalidad: str | None
) -> str:
    if temporalidad is not None:
        temporalidad_a_minutos(temporalidad)
        return temporalidad
    for columna in _COLUMNAS_TEMPORALIDAD:
        if columna in datos.columns:
            valores = datos[columna].dropna().astype(str).unique()
            if len(valores) == 1:
                temporalidad_a_minutos(valores[0])
                return valores[0]
            if len(valores) > 1:
                raise ValueError(
                    f"La columna {columna!r} contiene mas de una temporalidad."
                )
    raise ValueError(
        "No se pudo determinar la temporalidad; indiquela como parametro."
    )


def _fechas(
    datos: pd.DataFrame, columna_fecha: str | None
) -> tuple[str, pd.Series]:
    columna = _resolver_columna_fecha(datos, columna_fecha)
    try:
        fechas = pd.to_datetime(datos[columna], errors="raise")
    except (TypeError, ValueError) as exc:
        raise ValueError(f"La columna {columna!r} contiene fechas invalidas.") from exc
    if fechas.isna().any():
        raise ValueError(f"La columna {columna!r} contiene fechas nulas.")
    return columna, fechas


def _validar_ohlc(datos: pd.DataFrame) -> None:
    faltantes = [c for c in ("open", "high", "low", "close") if c not in datos]
    if faltantes:
        raise ValueError(f"Faltan columnas OHLC requeridas: {', '.join(faltantes)}.")


def _retornos(
    datos: pd.DataFrame, columna_retorno: str = "return_percent"
) -> pd.Series:
    if columna_retorno in datos.columns:
        return pd.to_numeric(datos[columna_retorno], errors="coerce").astype(float)
    if "open" not in datos.columns or "close" not in datos.columns:
        raise ValueError(
            f"No existe {columna_retorno!r} ni las columnas open/close para calcularla."
        )
    apertura = pd.to_numeric(datos["open"], errors="coerce")
    cierre = pd.to_numeric(datos["close"], errors="coerce")
    apertura = apertura.mask(apertura.abs() <= TOLERANCIA)
    return ((cierre / apertura) - 1.0) * 100.0


def _exigir_intradia(datos: pd.DataFrame, temporalidad: str | None) -> str:
    valor = _resolver_temporalidad(datos, temporalidad)
    if not permite_analisis_horario(valor):
        raise ValueError(
            f"El analisis horario requiere datos intradia; la temporalidad {valor!r} "
            "no contiene una hora observable."
        )
    return valor


def _normalizar_periodo(periodo: str) -> str:
    clave = str(periodo).strip().lower()
    try:
        return _PERIODOS[clave]
    except KeyError as exc:
        permitidos = "hour, day, week, month, year"
        raise ValueError(f"Periodo no valido. Use uno de: {permitidos}.") from exc


def _clave_periodo(fecha: pd.Timestamp, periodo: str) -> tuple[int, ...]:
    if periodo == "hour":
        desplazamiento = int(fecha.utcoffset().total_seconds()) if fecha.tzinfo else 0
        return (fecha.year, fecha.month, fecha.day, fecha.hour, desplazamiento)
    if periodo == "day":
        return (fecha.year, fecha.month, fecha.day)
    if periodo == "week":
        iso = fecha.isocalendar()
        return (int(iso.year), int(iso.week))
    if periodo == "month":
        return (fecha.year, fecha.month)
    return (fecha.year,)


def _limites_periodo(
    fecha: pd.Timestamp, periodo: str
) -> tuple[pd.Timestamp, pd.Timestamp]:
    if periodo == "hour":
        inicio = fecha.replace(minute=0, second=0, microsecond=0, nanosecond=0)
        return inicio, inicio + pd.Timedelta(hours=1)

    tz = fecha.tzinfo
    inicio_dia = pd.Timestamp(
        year=fecha.year, month=fecha.month, day=fecha.day, tz=tz
    )
    if periodo == "day":
        return inicio_dia, inicio_dia + pd.DateOffset(days=1)
    if periodo == "week":
        inicio = inicio_dia - pd.DateOffset(days=fecha.weekday())
        return inicio, inicio + pd.DateOffset(days=7)
    if periodo == "month":
        inicio = pd.Timestamp(year=fecha.year, month=fecha.month, day=1, tz=tz)
        return inicio, inicio + pd.DateOffset(months=1)
    inicio = pd.Timestamp(year=fecha.year, month=1, day=1, tz=tz)
    return inicio, inicio + pd.DateOffset(years=1)


def agregar_periodos(
    datos: pd.DataFrame,
    periodo: str,
    *,
    columna_fecha: str | None = None,
    temporalidad: str | None = None,
    registros_esperados: int | None = None,
    formula_retorno: str = FORMULA_PORCENTUAL,
) -> pd.DataFrame:
    """Agrega velas por hora, dia, semana ISO, mes o ano.

    Cada retorno usa la primera apertura y el ultimo cierre cronologicos. Un
    periodo se marca ``completo`` solo si contiene todas las marcas separadas
    por la temporalidad base, desde el inicio hasta el final calendario. Es un
    criterio deliberadamente conservador: no presupone fines de semana,
    festivos ni horarios bursatiles. Para datos de una sesion ya filtrada puede
    darse ``registros_esperados``; en ese caso se exige esa cantidad y
    continuidad entre velas. El inicio y el fin devueltos son las marcas
    observadas de la primera y la ultima vela.
    """

    _validar_ohlc(datos)
    periodo_normalizado = _normalizar_periodo(periodo)
    valor_temporalidad = _resolver_temporalidad(datos, temporalidad)
    minutos_base = temporalidad_a_minutos(valor_temporalidad)
    if periodo_normalizado == "hour":
        _exigir_intradia(datos, valor_temporalidad)
        if 60 % minutos_base != 0:
            raise ValueError(
                "La temporalidad base debe dividir exactamente una hora para agregar por hora."
            )
    if registros_esperados is not None and registros_esperados <= 0:
        raise ValueError("registros_esperados debe ser mayor que cero.")

    _, fechas = _fechas(datos, columna_fecha)
    columnas_salida = (
        "inicio",
        "fin",
        "open",
        "close",
        "return_percent",
        "cantidad_registros",
        "completo",
    )
    if datos.empty:
        return pd.DataFrame(columns=columnas_salida)

    trabajo = datos.copy()
    trabajo["__fecha"] = fechas
    trabajo = trabajo.sort_values("__fecha", kind="stable")
    if periodo_normalizado == "hour":
        # El desplazamiento UTC distingue correctamente la hora repetida al
        # finalizar el horario de verano.
        trabajo["__periodo"] = trabajo["__fecha"].map(
            lambda fecha: _clave_periodo(pd.Timestamp(fecha), periodo_normalizado)
        )
    elif periodo_normalizado == "day":
        trabajo["__periodo"] = trabajo["__fecha"].dt.normalize()
    elif periodo_normalizado == "week":
        iso = trabajo["__fecha"].dt.isocalendar()
        trabajo["__periodo"] = iso["year"].astype(int) * 100 + iso["week"].astype(int)
    elif periodo_normalizado == "month":
        trabajo["__periodo"] = (
            trabajo["__fecha"].dt.year * 100 + trabajo["__fecha"].dt.month
        )
    else:
        trabajo["__periodo"] = trabajo["__fecha"].dt.year

    trabajo["open"] = pd.to_numeric(trabajo["open"], errors="raise")
    trabajo["close"] = pd.to_numeric(trabajo["close"], errors="raise")
    paso = pd.Timedelta(minutes=minutos_base)
    cambio_grupo = trabajo["__periodo"].ne(trabajo["__periodo"].shift())
    trabajo["__continuo"] = cambio_grupo | trabajo["__fecha"].diff().eq(paso)

    grupos = trabajo.groupby("__periodo", sort=True, observed=True)
    resultado = grupos.agg(
        inicio=("__fecha", "first"),
        fin=("__fecha", "last"),
        open=("open", "first"),
        close=("close", "last"),
        cantidad_registros=("__fecha", "size"),
        marcas_unicas=("__fecha", "nunique"),
        continuo=("__continuo", "all"),
    ).reset_index(drop=True)

    resultado["return_percent"] = calcular_retorno(
        resultado["open"], resultado["close"], formula_retorno
    )
    sin_duplicados = resultado["cantidad_registros"].eq(resultado["marcas_unicas"])
    estructura_valida = sin_duplicados & resultado["continuo"]
    if registros_esperados is not None:
        resultado["completo"] = estructura_valida & resultado[
            "cantidad_registros"
        ].eq(registros_esperados)
    else:
        limites = resultado["inicio"].map(
            lambda fecha: _limites_periodo(pd.Timestamp(fecha), periodo_normalizado)
        )
        inicios_esperados = limites.map(lambda par: par[0])
        finales_exclusivos = limites.map(lambda par: par[1])
        cantidades_esperadas = (
            (finales_exclusivos - inicios_esperados) / paso
        ).astype(int)
        resultado["completo"] = (
            estructura_valida
            & resultado["inicio"].eq(inicios_esperados)
            & resultado["fin"].eq(finales_exclusivos - paso)
            & resultado["cantidad_registros"].eq(cantidades_esperadas)
        )

    return resultado[list(columnas_salida)]


def estadisticas_retornos(
    datos: pd.DataFrame | pd.Series | Sequence[float],
    *,
    columna_retorno: str = "return_percent",
) -> dict[str, float | int]:
    """Resume retornos finitos usando una tolerancia neutral de ``1e-10``.

    ``std`` es la desviacion estandar muestral (``ddof=1``), por lo que vale
    ``NaN`` con menos de dos observaciones. Los porcentajes usan como
    denominador ``n`` y mejor/peor repiten los extremos con nombres semanticos.
    """

    if isinstance(datos, pd.DataFrame):
        valores = _retornos(datos, columna_retorno)
    elif isinstance(datos, pd.Series):
        valores = pd.to_numeric(datos, errors="coerce")
    else:
        valores = pd.to_numeric(pd.Series(datos, dtype=float), errors="coerce")
    valores = valores[np.isfinite(valores.astype(float))].astype(float)
    n = int(len(valores))
    if n == 0:
        return {
            "promedio": np.nan,
            "mediana": np.nan,
            "maximo": np.nan,
            "minimo": np.nan,
            "std": np.nan,
            "positivo_pct": np.nan,
            "negativo_pct": np.nan,
            "neutro_pct": np.nan,
            "n": 0,
            "mejor": np.nan,
            "peor": np.nan,
            "rango": np.nan,
        }

    maximo = float(valores.max())
    minimo = float(valores.min())
    return {
        "promedio": float(valores.mean()),
        "mediana": float(valores.median()),
        "maximo": maximo,
        "minimo": minimo,
        "std": float(valores.std(ddof=1)) if n > 1 else np.nan,
        "positivo_pct": float((valores > TOLERANCIA).mean() * 100.0),
        "negativo_pct": float((valores < -TOLERANCIA).mean() * 100.0),
        "neutro_pct": float((valores.abs() <= TOLERANCIA).mean() * 100.0),
        "n": n,
        "mejor": maximo,
        "peor": minimo,
        "rango": maximo - minimo,
    }


def _estadisticas_agrupadas(
    claves: pd.DataFrame, retornos: pd.Series
) -> pd.DataFrame:
    trabajo = claves.copy()
    trabajo["__retorno"] = retornos
    nombres = list(claves.columns)
    filas: list[dict[str, object]] = []
    for valores_clave, grupo in trabajo.groupby(
        nombres, sort=True, observed=True, dropna=True
    ):
        if len(nombres) == 1 and not isinstance(valores_clave, tuple):
            valores_clave = (valores_clave,)
        fila = dict(zip(nombres, valores_clave))
        fila.update(estadisticas_retornos(grupo["__retorno"]))
        filas.append(fila)
    return pd.DataFrame(filas, columns=nombres + list(estadisticas_retornos([])))


def estacionalidad_mes(
    datos: pd.DataFrame,
    *,
    columna_fecha: str | None = None,
    columna_retorno: str = "return_percent",
) -> pd.DataFrame:
    """Devuelve estadisticas por mes en orden calendario y nombres en espanol."""

    _, fechas = _fechas(datos, columna_fecha)
    claves = pd.DataFrame({"numero_mes": fechas.dt.month}, index=datos.index)
    resultado = _estadisticas_agrupadas(claves, _retornos(datos, columna_retorno))
    if resultado.empty:
        resultado.insert(1, "mes", pd.Series(dtype=object))
        return resultado
    resultado.insert(1, "mes", resultado["numero_mes"].map(lambda n: MESES_ES[int(n) - 1]))
    return resultado.sort_values("numero_mes", ignore_index=True)


def semana_iso(
    datos: pd.DataFrame,
    *,
    columna_fecha: str | None = None,
    columna_retorno: str = "return_percent",
) -> pd.DataFrame:
    """Devuelve estadisticas estacionales por numero de semana ISO (1 a 53)."""

    _, fechas = _fechas(datos, columna_fecha)
    claves = pd.DataFrame(
        {"semana_iso": fechas.dt.isocalendar().week.astype(int)}, index=datos.index
    )
    return _estadisticas_agrupadas(claves, _retornos(datos, columna_retorno)).sort_values(
        "semana_iso", ignore_index=True
    )


def dia_semana(
    datos: pd.DataFrame,
    *,
    columna_fecha: str | None = None,
    columna_retorno: str = "return_percent",
) -> pd.DataFrame:
    """Devuelve estadisticas de lunes a domingo, con etiquetas en espanol."""

    _, fechas = _fechas(datos, columna_fecha)
    claves = pd.DataFrame({"numero_dia": fechas.dt.dayofweek}, index=datos.index)
    resultado = _estadisticas_agrupadas(claves, _retornos(datos, columna_retorno))
    if resultado.empty:
        resultado.insert(1, "dia_semana", pd.Series(dtype=object))
        return resultado
    resultado.insert(
        1,
        "dia_semana",
        resultado["numero_dia"].map(lambda n: DIAS_SEMANA_ES[int(n)]),
    )
    return resultado.sort_values("numero_dia", ignore_index=True)


def dia_mes(
    datos: pd.DataFrame,
    *,
    columna_fecha: str | None = None,
    columna_retorno: str = "return_percent",
) -> pd.DataFrame:
    """Devuelve estadisticas por dia calendario del mes (1 a 31)."""

    _, fechas = _fechas(datos, columna_fecha)
    claves = pd.DataFrame({"dia_mes": fechas.dt.day}, index=datos.index)
    return _estadisticas_agrupadas(claves, _retornos(datos, columna_retorno)).sort_values(
        "dia_mes", ignore_index=True
    )


def hora(
    datos: pd.DataFrame,
    *,
    columna_fecha: str | None = None,
    temporalidad: str | None = None,
    columna_retorno: str = "return_percent",
) -> pd.DataFrame:
    """Devuelve estadisticas por hora observada; rechaza datos diarios."""

    _exigir_intradia(datos, temporalidad)
    _, fechas = _fechas(datos, columna_fecha)
    claves = pd.DataFrame({"hora": fechas.dt.hour}, index=datos.index)
    return _estadisticas_agrupadas(claves, _retornos(datos, columna_retorno)).sort_values(
        "hora", ignore_index=True
    )


def matriz_dia_hora(
    datos: pd.DataFrame,
    metrica: str = "mean",
    *,
    dias: Sequence[int | str] | None = None,
    horas: Sequence[int] | None = None,
    columna_fecha: str | None = None,
    temporalidad: str | None = None,
    columna_retorno: str = "return_percent",
) -> pd.DataFrame:
    """Construye una matriz con dias en X y horas en Y.

    ``metrica`` puede ser ``mean``, ``median``, ``positive_pct``, ``std`` o
    ``count``. Si no se indican ejes se incluyen, en orden, solo los dias y
    horas observados. ``positive_pct`` usa la tolerancia global.
    """

    metricas = {"mean", "median", "positive_pct", "std", "count"}
    if metrica not in metricas:
        raise ValueError(f"Metrica no valida. Use una de: {', '.join(sorted(metricas))}.")
    _exigir_intradia(datos, temporalidad)
    _, fechas = _fechas(datos, columna_fecha)
    trabajo = pd.DataFrame(
        {
            "numero_dia": fechas.dt.dayofweek,
            "hora": fechas.dt.hour,
            "retorno": _retornos(datos, columna_retorno),
        },
        index=datos.index,
    ).dropna(subset=["retorno"])

    def calcular(grupo: pd.Series) -> float:
        if metrica == "mean":
            return float(grupo.mean())
        if metrica == "median":
            return float(grupo.median())
        if metrica == "positive_pct":
            return float((grupo > TOLERANCIA).mean() * 100.0)
        if metrica == "std":
            return float(grupo.std(ddof=1)) if len(grupo) > 1 else np.nan
        return float(grupo.count())

    agrupada = (
        trabajo.groupby(["numero_dia", "hora"], sort=True)["retorno"]
        .apply(calcular)
        .rename("valor")
        .reset_index()
    )
    matriz = agrupada.pivot(index="hora", columns="numero_dia", values="valor")
    dias_normalizados = _normalizar_dias(dias)
    if dias_normalizados is None:
        dias_normalizados = sorted(trabajo["numero_dia"].dropna().astype(int).unique())
    horas_normalizadas = _normalizar_horas(horas)
    if horas_normalizadas is None:
        horas_normalizadas = sorted(trabajo["hora"].dropna().astype(int).unique())
    matriz = matriz.reindex(index=horas_normalizadas, columns=dias_normalizados)
    matriz.index = [f"{int(hora_):02d}:00" for hora_ in matriz.index]
    matriz.columns = [DIAS_SEMANA_ES[int(dia)] for dia in matriz.columns]
    matriz.index.name = "hora"
    matriz.columns.name = "dia_semana"
    return matriz


def filtrar_iqr(
    datos: pd.DataFrame,
    *,
    activo: bool = False,
    agrupar_por: str | Sequence[str] | None = None,
    factor: float = 1.5,
    columna_retorno: str = "return_percent",
) -> tuple[pd.DataFrame, int]:
    """Filtra retornos fuera de Q1/Q3 por IQR y devuelve datos y eliminados.

    El filtro esta desactivado por defecto. Puede aplicarse globalmente o por
    una o varias columnas con ``agrupar_por``. Los retornos no finitos se
    conservan para no ocultar problemas de calidad ajenos al criterio IQR.
    """

    if not activo:
        return datos.copy(), 0
    if factor < 0:
        raise ValueError("El factor IQR no puede ser negativo.")
    trabajo = datos.copy()
    trabajo["__retorno_iqr"] = _retornos(trabajo, columna_retorno)
    columnas_grupo = [agrupar_por] if isinstance(agrupar_por, str) else agrupar_por
    if columnas_grupo:
        faltantes = [col for col in columnas_grupo if col not in trabajo]
        if faltantes:
            raise ValueError(f"No existen columnas de agrupacion: {', '.join(faltantes)}.")
        grupos = trabajo.groupby(list(columnas_grupo), dropna=False)["__retorno_iqr"]
        q1 = grupos.transform(lambda serie: serie.quantile(0.25))
        q3 = grupos.transform(lambda serie: serie.quantile(0.75))
    else:
        q1 = pd.Series(trabajo["__retorno_iqr"].quantile(0.25), index=trabajo.index)
        q3 = pd.Series(trabajo["__retorno_iqr"].quantile(0.75), index=trabajo.index)
    iqr = q3 - q1
    retorno = trabajo["__retorno_iqr"]
    finito = np.isfinite(retorno)
    conservar = ~finito | (
        (retorno >= q1 - factor * iqr - TOLERANCIA)
        & (retorno <= q3 + factor * iqr + TOLERANCIA)
    )
    eliminados = int((~conservar).sum())
    return trabajo.loc[conservar].drop(columns="__retorno_iqr"), eliminados


def distribucion(
    datos: pd.DataFrame | pd.Series | Sequence[float],
    *,
    bins: int | Sequence[float] = 20,
    columna_retorno: str = "return_percent",
) -> pd.DataFrame:
    """Devuelve intervalos de histograma, frecuencia y porcentaje de retornos."""

    if isinstance(datos, pd.DataFrame):
        valores = _retornos(datos, columna_retorno)
    else:
        valores = pd.Series(datos) if not isinstance(datos, pd.Series) else datos
        valores = pd.to_numeric(valores, errors="coerce")
    valores = valores[np.isfinite(valores.astype(float))].astype(float)
    columnas = ("limite_inferior", "limite_superior", "frecuencia", "porcentaje")
    if valores.empty:
        return pd.DataFrame(columns=columnas)
    frecuencias, limites = np.histogram(valores.to_numpy(), bins=bins)
    return pd.DataFrame(
        {
            "limite_inferior": limites[:-1],
            "limite_superior": limites[1:],
            "frecuencia": frecuencias.astype(int),
            "porcentaje": frecuencias / frecuencias.sum() * 100.0,
        },
        columns=columnas,
    )


def percentiles(
    datos: pd.DataFrame | pd.Series | Sequence[float],
    *,
    valores_percentil: Sequence[float] = (1, 5, 10, 25, 50, 75, 90, 95, 99),
    columna_retorno: str = "return_percent",
) -> pd.DataFrame:
    """Calcula percentiles expresados en la escala de 0 a 100."""

    niveles = np.asarray(list(valores_percentil), dtype=float)
    if np.any(~np.isfinite(niveles)) or np.any((niveles < 0) | (niveles > 100)):
        raise ValueError("Los percentiles deben estar entre 0 y 100.")
    if isinstance(datos, pd.DataFrame):
        retornos = _retornos(datos, columna_retorno)
    else:
        retornos = pd.Series(datos) if not isinstance(datos, pd.Series) else datos
        retornos = pd.to_numeric(retornos, errors="coerce")
    retornos = retornos[np.isfinite(retornos.astype(float))].astype(float)
    calculados = (
        np.percentile(retornos.to_numpy(), niveles)
        if not retornos.empty
        else np.full(len(niveles), np.nan)
    )
    return pd.DataFrame({"percentil": niveles, "return_percent": calculados})


def eventos_extremos(
    datos: pd.DataFrame,
    *,
    n: int = 5,
    umbral: float | None = None,
    columna_fecha: str | None = None,
    columna_retorno: str = "return_percent",
) -> pd.DataFrame:
    """Lista los mejores y peores periodos historicos.

    Sin ``umbral`` selecciona hasta ``n`` retornos positivos y ``n`` negativos.
    Con umbral selecciona todos los eventos cuya magnitud absoluta lo alcanza.
    La salida queda ordenada de mayor a menor magnitud absoluta.
    """

    if n < 0:
        raise ValueError("n no puede ser negativo.")
    if umbral is not None and umbral < 0:
        raise ValueError("El umbral no puede ser negativo.")
    columna, fechas = _fechas(datos, columna_fecha)
    faltantes = [nombre for nombre in ("open", "close") if nombre not in datos]
    if faltantes:
        raise ValueError(
            f"Faltan columnas requeridas para eventos: {', '.join(faltantes)}."
        )
    trabajo = datos.copy()
    trabajo[columna] = fechas
    trabajo["return_percent"] = _retornos(datos, columna_retorno)
    trabajo = trabajo[np.isfinite(trabajo["return_percent"])].copy()
    if umbral is None:
        positivos = trabajo[trabajo["return_percent"] > TOLERANCIA].nlargest(
            n, "return_percent"
        )
        negativos = trabajo[trabajo["return_percent"] < -TOLERANCIA].nsmallest(
            n, "return_percent"
        )
        seleccion = pd.concat((positivos, negativos)).drop_duplicates()
    else:
        seleccion = trabajo[
            trabajo["return_percent"].abs() >= umbral - TOLERANCIA
        ].copy()
    seleccion["tipo_extremo"] = np.select(
        [
            seleccion["return_percent"] > TOLERANCIA,
            seleccion["return_percent"] < -TOLERANCIA,
        ],
        ["positivo", "negativo"],
        default="neutro",
    )
    seleccion["magnitud_absoluta"] = seleccion["return_percent"].abs()
    seleccion["inicio"] = seleccion[columna]
    seleccion["fin"] = seleccion.get("fin", seleccion[columna])
    seleccion["cantidad_registros"] = seleccion.get("cantidad_registros", 1)
    seleccion["completo"] = seleccion.get("completo", True)
    columnas = [
        "inicio",
        "fin",
        "return_percent",
        "open",
        "close",
        "cantidad_registros",
        "completo",
        "tipo_extremo",
    ]
    return seleccion[columnas].sort_values(
        ["return_percent", "inicio"], ascending=[False, True], ignore_index=True
    )


def _normalizar_dias(
    dias: Sequence[int | str] | None,
) -> list[int] | None:
    if dias is None:
        return None
    equivalencias = {
        "lunes": 0,
        "martes": 1,
        "miercoles": 2,
        "miércoles": 2,
        "jueves": 3,
        "viernes": 4,
        "sabado": 5,
        "sábado": 5,
        "domingo": 6,
    }
    resultado: list[int] = []
    for dia in dias:
        if isinstance(dia, str):
            try:
                numero = equivalencias[dia.strip().lower()]
            except KeyError as exc:
                raise ValueError(f"Dia de semana no reconocido: {dia!r}.") from exc
        else:
            numero = int(dia)
        if numero not in range(7):
            raise ValueError("Los dias numericos deben estar entre 0 (lunes) y 6.")
        if numero not in resultado:
            resultado.append(numero)
    return sorted(resultado)


def _normalizar_horas(horas: Sequence[int] | None) -> list[int] | None:
    if horas is None:
        return None
    resultado = sorted({int(hora_) for hora_ in horas})
    if any(hora_ < 0 or hora_ > 23 for hora_ in resultado):
        raise ValueError("Las horas deben estar entre 0 y 23.")
    return resultado


def _normalizar_hora(valor: str | time | int) -> time:
    if isinstance(valor, time):
        return valor
    if isinstance(valor, int):
        if valor not in range(24):
            raise ValueError("La hora entera debe estar entre 0 y 23.")
        return time(valor)
    try:
        return time.fromisoformat(str(valor))
    except ValueError as exc:
        raise ValueError(f"Hora no valida: {valor!r}; use, por ejemplo, '09:30'.") from exc


def filtrar_sesion_observada(
    datos: pd.DataFrame,
    *,
    dias_semana: Sequence[int | str] | None = None,
    horas: Sequence[int] | None = None,
    columna_fecha: str | None = None,
    temporalidad: str | None = None,
) -> pd.DataFrame:
    """Filtra por dias y horas discretas que existen en los datos intradia.

    Sin filtros devuelve una copia. No completa huecos ni presupone apertura,
    cierre, festivos o zona horaria de un mercado.
    """

    _exigir_intradia(datos, temporalidad)
    _, fechas = _fechas(datos, columna_fecha)
    dias = _normalizar_dias(dias_semana)
    horas_normalizadas = _normalizar_horas(horas)
    mascara = pd.Series(True, index=datos.index)
    if dias is not None:
        mascara &= fechas.dt.dayofweek.isin(dias)
    if horas_normalizadas is not None:
        mascara &= fechas.dt.hour.isin(horas_normalizadas)
    return datos.loc[mascara].copy()


def filtrar_sesion_personalizada(
    datos: pd.DataFrame,
    hora_inicio: str | time | int,
    hora_fin: str | time | int,
    *,
    dias_semana: Sequence[int | str] | None = None,
    incluir_fin: bool = False,
    zona_horaria: str | None = None,
    columna_fecha: str | None = None,
    temporalidad: str | None = None,
) -> pd.DataFrame:
    """Filtra una sesion intradia declarada explicitamente por el llamador.

    El intervalo normal es ``[inicio, fin)`` y admite sesiones que cruzan
    medianoche. ``inicio == fin`` representa 24 horas. Una zona horaria solo
    puede convertir timestamps que ya sean timezone-aware; nunca se localizan
    timestamps naive porque eso inventaria su significado.
    """

    _exigir_intradia(datos, temporalidad)
    _, fechas = _fechas(datos, columna_fecha)
    inicio = _normalizar_hora(hora_inicio)
    fin = _normalizar_hora(hora_fin)
    dias = _normalizar_dias(dias_semana)
    if zona_horaria is not None:
        if fechas.dt.tz is None:
            raise ValueError(
                "No se puede aplicar una zona horaria a timestamps naive sin inventar su origen."
            )
        fechas = fechas.dt.tz_convert(zona_horaria)

    minutos = (
        fechas.dt.hour * 3600
        + fechas.dt.minute * 60
        + fechas.dt.second
        + fechas.dt.microsecond / 1_000_000
    )
    inicio_segundos = inicio.hour * 3600 + inicio.minute * 60 + inicio.second
    fin_segundos = fin.hour * 3600 + fin.minute * 60 + fin.second
    if inicio_segundos == fin_segundos:
        mascara = pd.Series(True, index=datos.index)
    elif inicio_segundos < fin_segundos:
        limite_final = minutos <= fin_segundos if incluir_fin else minutos < fin_segundos
        mascara = (minutos >= inicio_segundos) & limite_final
    else:
        limite_final = minutos <= fin_segundos if incluir_fin else minutos < fin_segundos
        mascara = (minutos >= inicio_segundos) | limite_final
    if dias is not None:
        mascara &= fechas.dt.dayofweek.isin(dias)
    return datos.loc[mascara].copy()


# Nombres explicitos alternativos para consumidores que prefieren el prefijo.
estacionalidad_semana_iso = semana_iso
estacionalidad_dia_semana = dia_semana
estacionalidad_dia_mes = dia_mes
estacionalidad_hora = hora
filtrar_outliers_iqr = filtrar_iqr
distribucion_retornos = distribucion
percentiles_retornos = percentiles


__all__ = [
    "TOLERANCIA",
    "temporalidad_a_minutos",
    "permite_analisis_horario",
    "agregar_periodos",
    "estadisticas_retornos",
    "estacionalidad_mes",
    "semana_iso",
    "dia_semana",
    "dia_mes",
    "hora",
    "matriz_dia_hora",
    "filtrar_iqr",
    "distribucion",
    "percentiles",
    "eventos_extremos",
    "filtrar_sesion_observada",
    "filtrar_sesion_personalizada",
    "estacionalidad_semana_iso",
    "estacionalidad_dia_semana",
    "estacionalidad_dia_mes",
    "estacionalidad_hora",
    "filtrar_outliers_iqr",
    "distribucion_retornos",
    "percentiles_retornos",
]
