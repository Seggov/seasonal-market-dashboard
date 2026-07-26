"""Interfaz Streamlit para explorar y analizar las series OHLC configuradas."""

from __future__ import annotations

from datetime import time
import logging
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from .analisis import (
    DIAS_SEMANA_ES,
    MESES_ES,
    agregar_periodos,
    dia_mes,
    dia_semana,
    estadisticas_retornos,
    estacionalidad_mes,
    eventos_extremos,
    filtrar_iqr,
    filtrar_sesion_observada,
    filtrar_sesion_personalizada,
    hora,
    matriz_dia_hora,
    permite_analisis_horario,
    semana_iso,
    temporalidad_a_minutos,
)
from .cache import (
    ErrorCache,
    cargar_cache,
    generar_firma_cache,
    guardar_cache,
    invalidar_cache,
)
from .configuracion import ActivoConfig, ErrorConfiguracion, cargar_activos
from .datos import ErrorDatos, ResultadoValidacion, leer_y_validar_datos


RUTA_PROYECTO = Path(__file__).resolve().parents[1]
RUTA_CONFIGURACION = RUTA_PROYECTO / "data" / "activos.json"
RUTA_CACHE = RUTA_PROYECTO / "cache"
RUTA_LOG = RUTA_PROYECTO / "finance.log"

REGISTRO = logging.getLogger("finance")
if not REGISTRO.handlers:
    REGISTRO.setLevel(logging.INFO)
    manejador = logging.FileHandler(RUTA_LOG, encoding="utf-8")
    manejador.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    )
    REGISTRO.addHandler(manejador)

SECCIONES = (
    "Resumen",
    "Calidad de datos",
    "Análisis por periodo",
    "Análisis mensual",
    "Análisis semanal",
    "Día de la semana",
    "Análisis diario",
    "Análisis horario",
    "Matriz día-hora",
    "Eventos extremos",
)

GRUPOS_NAVEGACION = {
    "Visión general": ("Resumen", "Calidad de datos"),
    "Periodos": (
        "Análisis por periodo",
        "Análisis mensual",
        "Análisis semanal",
        "Análisis diario",
    ),
    "Estacionalidad": (
        "Día de la semana",
        "Análisis horario",
        "Matriz día-hora",
    ),
    "Eventos": ("Eventos extremos",),
}

COLORES = {
    "azul": "#315b7d",
    "azul_claro": "#78a6c8",
    "verde": "#2f7d69",
    "rojo": "#a75151",
    "gris": "#73808c",
    "arena": "#d5b36a",
}
MAX_VELAS_GRAFICO = 3_000

TEMAS = {
    "claro": {
        "fondo": "#f3f6f8",
        "superficie": "#ffffff",
        "superficie_secundaria": "#edf2f5",
        "texto": "#162b3a",
        "texto_secundario": "#5e6f7b",
        "borde": "#d8e0e5",
        "rejilla": "#e7ecef",
        "acento": "#2f6285",
        "acento_suave": "#dceaf3",
    },
    "oscuro": {
        "fondo": "#0d151b",
        "superficie": "#14212a",
        "superficie_secundaria": "#1b2b35",
        "texto": "#edf3f6",
        "texto_secundario": "#a8b7c1",
        "borde": "#2c404c",
        "rejilla": "#263943",
        "acento": "#6fa8cc",
        "acento_suave": "#203b4b",
    },
}

ETIQUETAS_CATEGORIAS = {
    "crypto": "Criptomonedas",
    "forex": "Forex",
    "commodity": "Materias primas",
    "indice": "Índices",
    "índice": "Índices",
}


@st.cache_resource(show_spinner=False)
def cargar_resultado_cacheado(simbolo: str, firma_archivos: str) -> ResultadoValidacion:
    """Valida y comparte un activo inmutable sin copiarlo en cada rerun.

    ``firma_archivos`` forma parte deliberadamente de la clave. Se usa
    ``cache_resource`` porque el resultado se trata como un recurso de solo
    lectura y las vistas siempre trabajan sobre copias; así se evita serializar
    cientos de miles de filas en cada interacción.
    """

    del firma_archivos
    activo = cargar_activos(RUTA_CONFIGURACION, tolerante=True)[simbolo]
    resultado = leer_y_validar_datos(activo)
    firma = generar_firma_cache(activo.archivo, RUTA_CONFIGURACION)
    try:
        datos_cache = cargar_cache(firma, RUTA_CACHE)
        if datos_cache is None:
            guardar_cache(
                resultado.datos_validos,
                firma,
                RUTA_CACHE,
                metadatos={"simbolo": simbolo, "temporalidad": activo.temporalidad},
            )
        else:
            resultado.datos_validos = datos_cache
    except ErrorCache as exc:
        REGISTRO.exception("Fallo la cache Parquet para %s", simbolo)
        resultado.advertencias.append(
            f"La cache Parquet no estuvo disponible; se usan los datos validados: {exc}"
        )
    return resultado


def _tema_actual() -> dict[str, str]:
    """Devuelve la paleta correspondiente al estado visual actual."""

    nombre = "oscuro" if st.session_state.get("modo_oscuro", False) else "claro"
    return TEMAS[nombre]


def _inyectar_estilos() -> None:
    """Aplica una identidad legible y coherente en temas claro y oscuro."""

    tema = _tema_actual()

    st.markdown(
        f"""
        <style>
        :root {{
            --finance-bg: {tema['fondo']};
            --finance-surface: {tema['superficie']};
            --finance-surface-2: {tema['superficie_secundaria']};
            --finance-ink: {tema['texto']};
            --finance-muted: {tema['texto_secundario']};
            --finance-border: {tema['borde']};
            --finance-accent: {tema['acento']};
            --finance-accent-soft: {tema['acento_suave']};
        }}
        .stApp {{ background: var(--finance-bg); color: var(--finance-ink); }}
        [data-testid="stHeader"] {{ background: color-mix(in srgb, var(--finance-bg) 88%, transparent); }}
        [data-testid="stSidebar"] {{
            background: var(--finance-surface); border-right: 1px solid var(--finance-border);
        }}
        [data-testid="stSidebar"] * {{ color: var(--finance-ink); }}
        [data-testid="stMainBlockContainer"] {{ padding-top: 2.2rem; max-width: 1480px; }}
        h1, h2, h3, h4, h5, h6, p, label, .stCaption {{ color: var(--finance-ink) !important; }}
        [data-testid="stCaptionContainer"] p {{ color: var(--finance-muted) !important; }}
        [data-testid="stMetric"] {{
            background: var(--finance-surface); border: 1px solid var(--finance-border);
            border-radius: 12px; padding: 15px 17px; min-height: 106px;
            box-shadow: 0 2px 10px rgba(0,0,0,.04);
        }}
        [data-testid="stMetricLabel"] {{ color: var(--finance-muted); }}
        [data-testid="stMetricValue"] {{ color: var(--finance-ink); font-size: 1.55rem; }}
        .finance-kicker {{
            color: var(--finance-accent); font-size: .72rem; font-weight: 750;
            letter-spacing: .12em; text-transform: uppercase; margin-bottom: .25rem;
        }}
        .finance-title {{ color: var(--finance-ink); margin: 0; line-height: 1.15; }}
        .finance-subtitle {{ color: var(--finance-muted); margin: .45rem 0 1.35rem; max-width: 850px; }}
        .metadata {{
            background: var(--finance-surface); border: 1px solid var(--finance-border);
            border-left: 4px solid var(--finance-accent); border-radius: 10px;
            padding: .9rem 1.05rem; color: var(--finance-muted); margin-bottom: 1rem;
            line-height: 1.65;
        }}
        .metadata b {{ color: var(--finance-ink); }}
        .finance-panel {{
            background: var(--finance-surface); border: 1px solid var(--finance-border);
            border-radius: 12px; padding: 1rem 1.1rem; margin: .45rem 0 1rem;
        }}
        .finance-panel-title {{ color: var(--finance-ink); font-weight: 700; font-size: 1rem; }}
        .finance-panel-copy {{ color: var(--finance-muted); font-size: .88rem; margin-top: .2rem; }}
        div[data-testid="stDataFrame"] {{
            border: 1px solid var(--finance-border); border-radius: 10px;
            background: var(--finance-surface); overflow: hidden;
        }}
        div[data-testid="stVerticalBlockBorderWrapper"] {{
            background: var(--finance-surface); border-color: var(--finance-border) !important;
            border-radius: 12px;
        }}
        div[data-testid="stSelectbox"] div[data-baseweb="select"] > div,
        div[data-testid="stNumberInput"] input,
        div[data-testid="stTimeInput"] input {{
            background: var(--finance-surface); color: var(--finance-ink);
            border-color: var(--finance-border);
        }}
        div[data-baseweb="popover"] ul {{ background: var(--finance-surface); }}
        div[data-baseweb="popover"] li {{ color: var(--finance-ink); }}
        .stButton > button {{ border-radius: 9px; font-weight: 650; min-height: 2.6rem; }}
        .stButton > button[kind="secondary"] {{
            background: var(--finance-surface); color: var(--finance-ink);
            border-color: var(--finance-border);
        }}
        .stButton > button[kind="secondary"]:hover {{
            border-color: var(--finance-accent); color: var(--finance-accent);
        }}
        hr {{ border-color: var(--finance-border) !important; }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def _firma(activo: ActivoConfig) -> str:
    """Genera la firma conjunta de datos y configuración de un activo."""

    return generar_firma_cache(activo.archivo, RUTA_CONFIGURACION)


def _resultado(activo: ActivoConfig) -> ResultadoValidacion:
    """Obtiene un resultado cacheado usando la firma vigente de archivos."""

    return cargar_resultado_cacheado(activo.simbolo, _firma(activo))


def _texto_numero(valor: Any, decimales: int = 2, sufijo: str = "") -> str:
    """Formatea números finitos y representa el resto de forma explícita."""

    try:
        numero = float(valor)
    except (TypeError, ValueError):
        return "No disponible"
    if not np.isfinite(numero):
        return "No disponible"
    return f"{numero:,.{decimales}f}{sufijo}"


def _texto_entero(valor: Any) -> str:
    """Formatea un conteo o devuelve la etiqueta de ausencia."""

    try:
        numero = float(valor)
    except (TypeError, ValueError):
        return "No disponible"
    return f"{int(numero):,}" if np.isfinite(numero) else "No disponible"


def _texto_fecha(valor: Any) -> str:
    """Formatea una fecha conservando hora y zona cuando existen."""

    if valor is None or pd.isna(valor):
        return "No disponible"
    fecha = pd.Timestamp(valor)
    if (
        fecha.tzinfo is None
        and fecha.hour == 0
        and fecha.minute == 0
        and fecha.second == 0
    ):
        return fecha.strftime("%Y-%m-%d")
    zona = f" {fecha.tzname()}" if fecha.tzinfo is not None else ""
    return fecha.strftime("%Y-%m-%d %H:%M") + zona


def _columna_fecha(datos: pd.DataFrame, activo: ActivoConfig) -> str:
    """Selecciona la columna temporal semánticamente correcta."""

    preferida = "timestamp_local" if activo.tipo_timestamp == "instante_utc" else "fecha_sesion"
    if preferida in datos:
        return preferida
    for candidata in ("timestamp", "timestamp_visual", "fecha_sesion"):
        if candidata in datos:
            return candidata
    raise ValueError("Los datos válidos no contienen una columna temporal utilizable.")


def _preparar_datos(datos: pd.DataFrame, activo: ActivoConfig) -> tuple[pd.DataFrame, str]:
    """Ordena la serie y calcula el retorno propio de cada vela por OHLC."""

    columna = _columna_fecha(datos, activo)
    trabajo = datos.copy()
    trabajo[columna] = pd.to_datetime(trabajo[columna], errors="coerce")
    trabajo = trabajo.dropna(subset=[columna]).sort_values(columna, kind="stable")
    apertura = pd.to_numeric(trabajo["open"], errors="coerce")
    cierre = pd.to_numeric(trabajo["close"], errors="coerce")
    trabajo["return_percent"] = np.where(
        apertura.abs() > 1e-10, (cierre / apertura - 1.0) * 100.0, np.nan
    )
    return trabajo.reset_index(drop=True), columna


def _tabla_presentacion(tabla: pd.DataFrame, renombres: dict[str, str] | None = None) -> pd.DataFrame:
    """Prepara una copia legible, sin mostrar NaN ni infinitos al usuario."""

    salida = tabla.copy()
    for columna in salida.columns:
        if pd.api.types.is_datetime64_any_dtype(salida[columna].dtype):
            salida[columna] = salida[columna].map(_texto_fecha)
        elif pd.api.types.is_float_dtype(salida[columna].dtype):
            salida[columna] = salida[columna].map(
                lambda valor: f"{float(valor):,.4f}"
                if pd.notna(valor) and np.isfinite(valor)
                else "No disponible"
            )
        else:
            salida[columna] = salida[columna].where(pd.notna(salida[columna]), "No disponible")
    if renombres:
        salida = salida.rename(columns=renombres)
    return salida


def _mostrar_tabla(tabla: pd.DataFrame, renombres: dict[str, str] | None = None) -> None:
    """Muestra una tabla fluida o informa que no hay observaciones."""

    if tabla.empty:
        st.info("No hay observaciones disponibles para esta vista.")
        return
    tema = _tema_actual()
    presentacion = _tabla_presentacion(tabla, renombres)
    estilo = presentacion.style.set_properties(
        **{
            "background-color": tema["superficie"],
            "color": tema["texto"],
            "border-color": tema["borde"],
        }
    ).set_table_styles(
        [
            {
                "selector": "th",
                "props": [
                    ("background-color", tema["superficie_secundaria"]),
                    ("color", tema["texto"]),
                    ("font-weight", "700"),
                ],
            }
        ]
    )
    st.dataframe(estilo, width="stretch", hide_index=True)


def _estilo_figura(figura: go.Figure, titulo: str, eje_y: str = "Retorno (%)") -> go.Figure:
    """Uniforma los gráficos Plotly de la aplicación."""

    tema = _tema_actual()
    figura.update_layout(
        title={"text": titulo, "font": {"size": 17, "color": tema["texto"]}},
        paper_bgcolor=tema["superficie"],
        plot_bgcolor=tema["superficie"],
        font={"family": "Arial, sans-serif", "color": tema["texto_secundario"]},
        margin={"l": 30, "r": 20, "t": 55, "b": 35},
        hovermode="x unified",
        legend={"orientation": "h", "y": 1.08, "x": 1, "xanchor": "right"},
        yaxis_title=eje_y,
        hoverlabel={
            "bgcolor": tema["superficie_secundaria"],
            "font_color": tema["texto"],
            "bordercolor": tema["borde"],
        },
    )
    figura.update_xaxes(
        showgrid=False,
        linecolor=tema["borde"],
        tickfont={"color": tema["texto_secundario"]},
        title_font={"color": tema["texto_secundario"]},
    )
    figura.update_yaxes(
        gridcolor=tema["rejilla"],
        zerolinecolor=tema["borde"],
        tickfont={"color": tema["texto_secundario"]},
        title_font={"color": tema["texto_secundario"]},
    )
    return figura


def _grafico_barras(
    tabla: pd.DataFrame,
    x: str,
    y: str,
    titulo: str,
    *,
    etiquetas_x: str | None = None,
    eje_y: str = "Retorno (%)",
) -> None:
    """Dibuja barras positivas y negativas con una paleta contenida."""

    if tabla.empty or y not in tabla:
        st.info("No hay datos suficientes para construir el gráfico.")
        return
    valores = pd.to_numeric(tabla[y], errors="coerce")
    colores = np.where(valores >= 0, COLORES["verde"], COLORES["rojo"])
    textos = [f"{valor:.2f}%" if np.isfinite(valor) else "" for valor in valores]
    figura = go.Figure(
        go.Bar(
            x=tabla[x],
            y=valores,
            text=tabla[etiquetas_x] if etiquetas_x else textos,
            textposition="outside",
            cliponaxis=False,
            marker_color=colores,
            hovertemplate="%{x}<br>%{y:.2f}%<extra></extra>",
        )
    )
    figura.add_hline(y=0, line_width=1, line_color=_tema_actual()["borde"])
    figura.update_layout(height=450, bargap=0.22)
    st.plotly_chart(_estilo_figura(figura, titulo, eje_y), width="stretch")


def _grafico_linea(
    tabla: pd.DataFrame,
    x: str,
    y: str,
    titulo: str,
    *,
    promedio: float | None = None,
    altura: int = 390,
) -> None:
    """Dibuja una serie temporal de retornos."""

    if tabla.empty:
        st.info("No hay datos suficientes para construir el gráfico.")
        return
    tema = _tema_actual()
    figura = go.Figure(
        go.Scatter(
            x=tabla[x],
            y=tabla[y],
            mode="lines+markers",
            line={"color": tema["acento"], "width": 2},
            marker={"size": 5},
            hovertemplate="%{x}<br>%{y:.2f}%<extra></extra>",
        )
    )
    if promedio is not None and np.isfinite(promedio):
        figura.add_hline(
            y=float(promedio),
            line_dash="dash",
            line_color=COLORES["arena"],
            annotation_text=f"Promedio {promedio:.2f}%",
            annotation_position="top left",
        )
    figura.add_hline(y=0, line_width=1, line_color=tema["borde"])
    figura.update_layout(height=altura)
    st.plotly_chart(_estilo_figura(figura, titulo), width="stretch")


def _agregar(datos: pd.DataFrame, periodo: str, activo: ActivoConfig, columna_fecha: str) -> pd.DataFrame:
    """Agrega periodos usando siempre primera apertura y último cierre."""

    if periodo == "hour":
        # El agregador general recorre cada grupo. En series de varios años a
        # 15 minutos, esta ruta equivalente evita decenas de miles de iteraciones.
        minutos = temporalidad_a_minutos(activo.temporalidad)
        if minutos >= 60 or 60 % minutos != 0:
            return agregar_periodos(
                datos,
                periodo,
                columna_fecha=columna_fecha,
                temporalidad=activo.temporalidad,
            )
        trabajo = datos.sort_values(columna_fecha, kind="stable").copy()
        fechas = pd.to_datetime(trabajo[columna_fecha])
        trabajo["__fecha"] = fechas
        trabajo["__hora"] = fechas.dt.floor("h")
        paso = pd.Timedelta(minutes=minutos)
        trabajo["__en_rejilla"] = ((fechas - trabajo["__hora"]) % paso).eq(pd.Timedelta(0))
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
        salida["return_percent"] = np.where(
            apertura.abs() > 1e-10, (cierre / apertura - 1.0) * 100.0, np.nan
        )
        return salida[
            ["inicio", "fin", "open", "close", "return_percent", "cantidad_registros", "completo"]
        ]
    return agregar_periodos(
        datos,
        periodo,
        columna_fecha=columna_fecha,
        temporalidad=activo.temporalidad,
    )


def _datos_diarios(datos: pd.DataFrame, activo: ActivoConfig, columna_fecha: str) -> pd.DataFrame:
    """Agrega primero velas intradía; conserva velas diarias ya observadas."""

    if permite_analisis_horario(activo.temporalidad):
        return _agregar(datos, "day", activo, columna_fecha)
    salida = datos[[columna_fecha, "open", "close", "return_percent"]].copy()
    salida = salida.rename(columns={columna_fecha: "inicio"})
    salida["fin"] = salida["inicio"]
    salida["cantidad_registros"] = 1
    salida["completo"] = True
    return salida[["inicio", "fin", "open", "close", "return_percent", "cantidad_registros", "completo"]]


def _curvas_mensuales(diarios: pd.DataFrame) -> pd.DataFrame:
    """Promedia la trayectoria acumulada diaria de cada mes histórico."""

    if diarios.empty:
        return pd.DataFrame(columns=["numero_mes", "dia_mes", "retorno_ponderado", "muestras"])
    trabajo = diarios.sort_values("inicio", kind="stable").copy()
    fechas = pd.to_datetime(trabajo["inicio"])
    trabajo["ano"] = fechas.dt.year
    trabajo["numero_mes"] = fechas.dt.month
    trabajo["dia_mes"] = fechas.dt.day
    apertura_mes = trabajo.groupby(["ano", "numero_mes"], sort=False)["open"].transform("first")
    trabajo["retorno_acumulado"] = np.where(
        apertura_mes.abs() > 1e-10,
        (trabajo["close"] / apertura_mes - 1.0) * 100.0,
        np.nan,
    )
    return (
        trabajo.groupby(["numero_mes", "dia_mes"], observed=True)["retorno_acumulado"]
        .agg(retorno_ponderado="mean", muestras="count")
        .reset_index()
    )


def _curvas_intradia_por_dia(
    datos: pd.DataFrame, activo: ActivoConfig, columna_fecha: str
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Calcula trayectoria acumulada y retorno horario por día de semana."""

    if not permite_analisis_horario(activo.temporalidad):
        vacio = pd.DataFrame(columns=["numero_dia", "hora", "retorno", "muestras"])
        return vacio, vacio.copy()
    horas = _agregar(datos, "hour", activo, columna_fecha)
    if horas.empty:
        vacio = pd.DataFrame(columns=["numero_dia", "hora", "retorno", "muestras"])
        return vacio, vacio.copy()
    trabajo = horas.sort_values("inicio", kind="stable").copy()
    fechas = pd.to_datetime(trabajo["inicio"])
    trabajo["fecha_dia"] = fechas.dt.normalize()
    trabajo["numero_dia"] = fechas.dt.dayofweek
    trabajo["hora"] = fechas.dt.hour
    apertura_dia = trabajo.groupby("fecha_dia", sort=False)["open"].transform("first")
    trabajo["retorno_acumulado"] = np.where(
        apertura_dia.abs() > 1e-10,
        (trabajo["close"] / apertura_dia - 1.0) * 100.0,
        np.nan,
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


def _mostrar_curvas_por_dia(curvas: pd.DataFrame, prefijo_titulo: str) -> None:
    """Muestra una curva individual para cada día, o su falta de datos."""

    columnas = st.columns(2)
    for numero_dia, nombre_dia in enumerate(DIAS_SEMANA_ES):
        with columnas[numero_dia % 2]:
            subconjunto = curvas[curvas["numero_dia"].eq(numero_dia)]
            if len(subconjunto) < 2:
                st.info(f"{nombre_dia.title()}: información insuficiente.")
                continue
            _grafico_linea(
                subconjunto,
                "hora",
                "retorno",
                f"{prefijo_titulo} · {nombre_dia.title()}",
                altura=330,
            )


def _periodo_seleccionado(
    etiqueta: str,
    datos: pd.DataFrame,
    activo: ActivoConfig,
    columna_fecha: str,
) -> tuple[pd.DataFrame, str]:
    """Resuelve el periodo elegido por controles de distribución o extremos."""

    equivalencias = {
        "Vela base": None,
        "Hora": "hour",
        "Día": "day",
        "Semana ISO": "week",
        "Mes": "month",
        "Año": "year",
    }
    periodo = equivalencias[etiqueta]
    if periodo is None:
        salida = datos.copy()
        salida["inicio"] = salida[columna_fecha]
        salida["fin"] = salida[columna_fecha]
        salida["cantidad_registros"] = 1
        salida["completo"] = True
        return salida, columna_fecha
    agregados = _agregar(datos, periodo, activo, columna_fecha)
    return agregados, "inicio"


def _opciones_periodo(activo: ActivoConfig) -> list[str]:
    """Lista periodos compatibles con la temporalidad del activo."""

    opciones = ["Vela base"]
    if permite_analisis_horario(activo.temporalidad):
        opciones.append("Hora")
    opciones.extend(("Día", "Semana ISO", "Mes", "Año"))
    return opciones


def _cobertura_texto(cobertura: dict[str, Any]) -> str:
    """Resume cobertura sin sugerir calendarios inexistentes."""

    if not cobertura.get("disponible", False):
        return "No disponible"
    return _texto_numero(cobertura.get("porcentaje"), 2, "%")


@st.cache_data(show_spinner=False)
def _resumen_catalogo_cacheado(simbolo: str, firma_archivos: str) -> dict[str, Any]:
    """Calcula solo el resumen pequeño y seguro que necesita el catálogo."""

    activo = cargar_activos(RUTA_CONFIGURACION, tolerante=True)[simbolo]
    resultado = cargar_resultado_cacheado(simbolo, firma_archivos)
    resumen = resultado.resumen
    fecha_inicial: Any = None
    fecha_final: Any = None
    if not resultado.datos_validos.empty:
        columna = _columna_fecha(resultado.datos_validos, activo)
        fechas = pd.to_datetime(resultado.datos_validos[columna], errors="coerce")
        fecha_inicial = fechas.min()
        fecha_final = fechas.max()
    return {
        "fecha_inicial": fecha_inicial,
        "fecha_final": fecha_final,
        "filas_totales": resumen["filas_totales"],
        "porcentaje_valido": resumen["porcentaje_valido"],
        "cobertura": resumen["cobertura"],
    }


def _fila_catalogo(activo: ActivoConfig) -> dict[str, Any]:
    """Construye una fila de catálogo aislando errores del activo."""

    base = {
        "Símbolo": activo.simbolo,
        "Activo": activo.nombre,
        "Categoría": activo.categoria,
        "Mercado": activo.mercado,
        "Sesión": activo.sesion,
        "Zona horaria": activo.zona_horaria,
        "Temporalidad": activo.temporalidad,
        "Tipo timestamp": activo.tipo_timestamp,
        "Desde": "No disponible",
        "Hasta": "No disponible",
        "Filas": "No disponible",
        "% válidas": "No disponible",
        "Cobertura": "No disponible",
        "Archivo": activo.archivo.name,
        "Estado": "Disponible",
    }
    try:
        resumen = _resumen_catalogo_cacheado(activo.simbolo, _firma(activo))
        base["Desde"] = _texto_fecha(resumen["fecha_inicial"])
        base["Hasta"] = _texto_fecha(resumen["fecha_final"])
        base["Filas"] = _texto_entero(resumen["filas_totales"])
        base["% válidas"] = _texto_numero(resumen["porcentaje_valido"], 2, "%")
        base["Cobertura"] = _cobertura_texto(resumen["cobertura"])
    except (ErrorDatos, ErrorCache, ErrorConfiguracion, KeyError, OSError, ValueError) as exc:
        REGISTRO.exception("No se pudo construir la fila de catalogo de %s", activo.simbolo)
        base["Estado"] = f"Error: {exc}"
    return base


def _actualizar_cache() -> None:
    """Vacía las dos capas de cache sin acceder a fuentes externas."""

    try:
        eliminados = invalidar_cache(directorio_cache=RUTA_CACHE)
    except ErrorCache as exc:
        st.error(f"No se pudo limpiar la cache local: {exc}")
        return
    st.cache_data.clear()
    st.cache_resource.clear()
    st.session_state["mensaje_cache"] = (
        f"Cache actualizada: {eliminados} archivo(s) local(es) eliminado(s). "
        "No se descargaron datos."
    )
    st.rerun()


def _etiqueta_categoria(categoria: str) -> str:
    """Convierte una clave dinámica en una etiqueta de presentación."""

    return ETIQUETAS_CATEGORIAS.get(
        categoria.strip().lower(), categoria.replace("_", " ").title()
    )


def _activar_categoria(categoria: str) -> None:
    """Actualiza la categoría desde los botones del catálogo."""

    st.session_state["categoria_seleccion"] = categoria


def _activar_seccion(seccion: str) -> None:
    """Actualiza la sección desde el panel de navegación principal."""

    st.session_state["seccion_actual"] = seccion


def _pantalla_seleccion(activos: dict[str, ActivoConfig]) -> None:
    """Muestra categorías dinámicas, catálogo y selector del activo."""

    cabecera, tema_columna = st.columns([5, 1], vertical_alignment="top")
    with cabecera:
        st.markdown('<div class="finance-kicker">Catálogo local</div>', unsafe_allow_html=True)
        st.markdown('<h1 class="finance-title">Análisis histórico de mercados</h1>', unsafe_allow_html=True)
        st.markdown(
            '<p class="finance-subtitle">Seleccione un mercado, revise la cobertura disponible y abra un panel estadístico dedicado al activo.</p>',
            unsafe_allow_html=True,
        )
    with tema_columna:
        st.toggle("Modo oscuro", key="modo_oscuro", help="Cambia la apariencia sin alterar los datos.")

    st.markdown(
        '<div class="finance-panel"><div class="finance-panel-title">1. Seleccione una categoría</div>'
        '<div class="finance-panel-copy">Los activos nunca se mezclan entre categorías. La lista se genera desde activos.json.</div></div>',
        unsafe_allow_html=True,
    )

    categorias = sorted({activo.categoria for activo in activos.values()}, key=str.casefold)
    categoria_previa = st.session_state.get("categoria_seleccion")
    if categoria_previa not in categorias:
        st.session_state["categoria_seleccion"] = categorias[0]
    categoria = st.session_state["categoria_seleccion"]
    columnas_categoria = st.columns(min(4, len(categorias)))
    for indice, opcion in enumerate(categorias):
        cantidad = sum(activo.categoria == opcion for activo in activos.values())
        etiqueta = f"{_etiqueta_categoria(opcion)} · {cantidad}"
        columnas_categoria[indice % len(columnas_categoria)].button(
            etiqueta,
            key=f"categoria_{opcion}",
            type="primary" if opcion == categoria else "secondary",
            width="stretch",
            on_click=_activar_categoria,
            args=(opcion,),
        )

    activos_categoria = {
        simbolo: activo for simbolo, activo in activos.items() if activo.categoria == categoria
    }
    st.markdown(
        f"### {_etiqueta_categoria(categoria)}",
        help="Categoría declarada en activos.json.",
    )
    with st.spinner("Validando disponibilidad y cobertura local..."):
        filas = [_fila_catalogo(activo) for activo in activos_categoria.values()]
    _mostrar_tabla(pd.DataFrame(filas))
    st.info(
        "Seleccione el activo y pulse “Analizar activo” desde el panel lateral izquierdo."
    )


def _cabecera_activo(activo: ActivoConfig, datos: pd.DataFrame, columna_fecha: str) -> None:
    """Presenta título y metadata verificable del activo analizado."""

    fechas = pd.to_datetime(datos[columna_fecha], errors="coerce")
    cabecera, controles = st.columns([5, 1], vertical_alignment="top")
    with cabecera:
        st.markdown('<div class="finance-kicker">Panel estadístico</div>', unsafe_allow_html=True)
        st.markdown(
            f'<h1 class="finance-title">{activo.simbolo} · {activo.nombre}</h1>',
            unsafe_allow_html=True,
        )
    with controles:
        st.toggle("Modo oscuro", key="modo_oscuro", help="Cambia la apariencia sin alterar los datos.")
    st.markdown(
        "<div class=\"metadata\">"
        f"<b>{activo.categoria.title()}</b> &nbsp;·&nbsp; {activo.mercado} &nbsp;·&nbsp; "
        f"Sesión declarada: {activo.sesion} &nbsp;·&nbsp; {activo.temporalidad}<br>"
        f"Zona: {activo.zona_horaria} &nbsp;·&nbsp; Timestamp: {activo.tipo_timestamp} &nbsp;·&nbsp; "
        f"Periodo observado: {_texto_fecha(fechas.min())} a {_texto_fecha(fechas.max())}"
        "</div>",
        unsafe_allow_html=True,
    )


def _panel_navegacion(seccion_actual: str) -> None:
    """Muestra siempre las áreas estadísticas dentro de la página principal."""

    st.markdown(
        '<div class="finance-panel"><div class="finance-panel-title">Explorar análisis estadísticos</div>'
        '<div class="finance-panel-copy">Seleccione una vista. La opción activa se resalta y también queda sincronizada con la barra lateral.</div></div>',
        unsafe_allow_html=True,
    )
    columnas = st.columns(len(GRUPOS_NAVEGACION))
    for columna, (grupo, secciones) in zip(columnas, GRUPOS_NAVEGACION.items()):
        columna.caption(grupo)
        for seccion in secciones:
            columna.button(
                seccion,
                key=f"navegacion_{seccion}",
                type="primary" if seccion == seccion_actual else "secondary",
                width="stretch",
                on_click=_activar_seccion,
                args=(seccion,),
            )


def _controles_sesion(
    datos: pd.DataFrame,
    activo: ActivoConfig,
    columna_fecha: str,
) -> tuple[pd.DataFrame, str]:
    """Configura sesión declarada, observada o personalizada sin inventar horarios."""

    if activo.sesion.strip().lower() == "24/7":
        return datos.copy(), f"Sesión declarada {activo.sesion}; sin filtro adicional."

    st.sidebar.markdown("### Sesión")
    modo = st.sidebar.radio(
        "Definición",
        ("Declarada", "Observada", "Personalizada"),
        key=f"sesion_modo_{activo.simbolo}",
        help="La sesión declarada es la opción predeterminada.",
    )
    intradia = permite_analisis_horario(activo.temporalidad)
    if not intradia:
        st.sidebar.info(
            "La temporalidad diaria no conserva horas observables. No se pueden filtrar "
            "horas ni construir una sesión intradía; se mantiene toda la serie."
        )
        if modo != "Declarada":
            return datos.copy(), f"{modo}: no aplicable a datos diarios; serie completa."
        if activo.sesion.strip().lower() not in {"24/7", "24/5"}:
            st.sidebar.caption(
                "La sesión declarada no incluye un calendario exacto. No se aproximan "
                "horarios, festivos ni cierres del mercado."
            )
        return datos.copy(), f"Sesión declarada {activo.sesion}; sin filtro horario."

    fechas = pd.to_datetime(datos[columna_fecha])
    dias_observados = sorted(fechas.dt.dayofweek.unique().astype(int))
    horas_observadas = sorted(fechas.dt.hour.unique().astype(int))

    if modo == "Declarada":
        sesion = activo.sesion.strip().lower()
        if sesion == "24/5":
            filtrados = filtrar_sesion_observada(
                datos,
                dias_semana=[0, 1, 2, 3, 4],
                columna_fecha=columna_fecha,
                temporalidad=activo.temporalidad,
            )
            return filtrados, "Sesión declarada 24/5: lunes a viernes; sin inventar horas."
        if sesion == "24/7":
            return datos.copy(), "Sesión declarada 24/7; serie completa."
        st.sidebar.caption(
            "No hay un calendario exacto para esta etiqueta de sesión. Se conservan "
            "todas las observaciones y no se presuponen horarios ni festivos."
        )
        return datos.copy(), f"Sesión declarada {activo.sesion}; calendario exacto no disponible."

    etiquetas_dias = {numero: DIAS_SEMANA_ES[numero].title() for numero in range(7)}
    dias = st.sidebar.multiselect(
        "Días",
        dias_observados,
        default=dias_observados,
        format_func=lambda numero: etiquetas_dias[numero],
        key=f"sesion_dias_{activo.simbolo}_{modo}",
    )
    if modo == "Observada":
        horas = st.sidebar.multiselect(
            "Horas observadas",
            horas_observadas,
            default=horas_observadas,
            format_func=lambda valor: f"{valor:02d}:00",
            key=f"sesion_horas_{activo.simbolo}",
        )
        filtrados = filtrar_sesion_observada(
            datos,
            dias_semana=dias,
            horas=horas,
            columna_fecha=columna_fecha,
            temporalidad=activo.temporalidad,
        )
        return filtrados, "Sesión observada: solo días y horas presentes en el archivo."

    inicio = st.sidebar.time_input(
        "Hora inicial",
        value=time(9, 0),
        key=f"sesion_inicio_{activo.simbolo}",
    )
    fin = st.sidebar.time_input(
        "Hora final (excluida)",
        value=time(17, 0),
        key=f"sesion_fin_{activo.simbolo}",
    )
    filtrados = filtrar_sesion_personalizada(
        datos,
        inicio,
        fin,
        dias_semana=dias,
        columna_fecha=columna_fecha,
        temporalidad=activo.temporalidad,
    )
    return filtrados, f"Sesión personalizada [{inicio:%H:%M}, {fin:%H:%M}); zona {activo.zona_horaria}."


def _seccion_resumen(datos: pd.DataFrame, activo: ActivoConfig, columna_fecha: str) -> None:
    """Muestra exclusivamente las cinco métricas generales solicitadas."""

    st.subheader("Resumen")
    if datos.empty:
        st.warning("La sesión seleccionada no contiene observaciones.")
        return
    cierre = float(datos.iloc[-1]["close"])
    estadisticas = estadisticas_retornos(datos)
    mensual = _agregar(datos, "month", activo, columna_fecha)
    anual = _agregar(datos, "year", activo, columna_fecha)
    retorno_ultimo_mes = mensual["return_percent"].iloc[-1] if not mensual.empty else np.nan
    retorno_ultimo_ano = anual["return_percent"].iloc[-1] if not anual.empty else np.nan
    columnas = st.columns(5)
    columnas[0].metric("Último cierre", _texto_numero(cierre, 4))
    columnas[1].metric("Retorno del último mes", _texto_numero(retorno_ultimo_mes, 2, "%"))
    columnas[2].metric("Retorno del último año", _texto_numero(retorno_ultimo_ano, 2, "%"))
    columnas[3].metric("Velas positivas", _texto_numero(estadisticas["positivo_pct"], 2, "%"))
    columnas[4].metric("Velas negativas", _texto_numero(estadisticas["negativo_pct"], 2, "%"))

    datos_grafico = datos
    if len(datos) > MAX_VELAS_GRAFICO:
        tamano_grupo = int(np.ceil(len(datos) / MAX_VELAS_GRAFICO))
        datos_grafico = (
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
        st.caption(
            f"El gráfico resume {len(datos):,} velas en {len(datos_grafico):,} bloques OHLC "
            "para acelerar la visualización. Las estadísticas usan todas las observaciones."
        )

    figura = go.Figure()
    figura.add_trace(
        go.Candlestick(
            x=datos_grafico[columna_fecha],
            open=datos_grafico["open"],
            high=datos_grafico["high"],
            low=datos_grafico["low"],
            close=datos_grafico["close"],
            increasing_line_color=COLORES["verde"],
            decreasing_line_color=COLORES["rojo"],
            name="OHLC",
        )
    )
    figura.update_layout(xaxis_rangeslider_visible=False)
    st.plotly_chart(_estilo_figura(figura, "Evolución del precio", "Precio"), width="stretch")


def _seccion_calidad(resultado: ResultadoValidacion, activo: ActivoConfig) -> None:
    """Muestra exclusivamente conteos y límites de la validación solicitados."""

    st.subheader("Calidad de datos")
    resumen = resultado.resumen
    validos = resultado.datos_validos
    columna_fecha = _columna_fecha(validos, activo) if not validos.empty else None
    fechas = (
        pd.to_datetime(validos[columna_fecha], errors="coerce")
        if columna_fecha is not None
        else pd.Series(dtype="datetime64[ns]")
    )
    valores = [
        ("Filas totales del archivo", resumen["filas_totales"], "entero"),
        ("Fecha inicial", fechas.min() if not fechas.empty else None, "fecha"),
        ("Fecha final", fechas.max() if not fechas.empty else None, "fecha"),
        ("Filas válidas", resumen["filas_validas"], "entero"),
        ("Velas utilizadas en los análisis", len(validos), "entero"),
        ("Filas eliminadas en la validación", resumen["filas_invalidas"], "entero"),
    ]
    for indice, (etiqueta, valor, tipo) in enumerate(valores):
        if indice % 3 == 0:
            columnas = st.columns(3)
        texto = _texto_fecha(valor) if tipo == "fecha" else _texto_entero(valor)
        columnas[indice % 3].metric(etiqueta, texto)


def _seccion_anual(datos: pd.DataFrame, activo: ActivoConfig, columna_fecha: str) -> None:
    """Muestra retorno anual y la historia mensual completa por año."""

    st.subheader("Análisis por periodo")
    anual = _agregar(datos, "year", activo, columna_fecha)
    mensual = _agregar(datos, "month", activo, columna_fecha)
    if anual.empty or mensual.empty:
        st.info("La información disponible no es suficiente para este análisis.")
        return
    anual["año"] = pd.to_datetime(anual["inicio"]).dt.year
    _grafico_barras(anual, "año", "return_percent", "Retorno por año")

    fechas_mensuales = pd.to_datetime(mensual["inicio"])
    mensual["año"] = fechas_mensuales.dt.year
    mensual["mes"] = fechas_mensuales.dt.month
    ano_inicial = int(mensual["año"].min())
    ano_final = int(mensual["año"].max())
    tabla = mensual.pivot(index="año", columns="mes", values="return_percent")
    tabla = tabla.reindex(index=range(ano_inicial, ano_final + 1), columns=range(1, 13))
    retorno_anual = anual.set_index("año")["return_percent"]
    tabla["retorno_anual"] = retorno_anual
    tabla = tabla.reset_index()
    tabla.columns = [
        "Año",
        *[mes.title() for mes in MESES_ES],
        "Retorno acumulado del año",
    ]
    for columna in tabla.columns[1:]:
        tabla[columna] = tabla[columna].map(
            lambda valor: f"{valor:.2f}%" if pd.notna(valor) and np.isfinite(valor) else "-"
        )
    st.markdown("#### Retornos mensuales por año")
    _mostrar_tabla(tabla)


def _seccion_mensual(datos: pd.DataFrame, activo: ActivoConfig, columna_fecha: str) -> None:
    """Compara meses y muestra doce trayectorias históricas ponderadas."""

    st.subheader("Análisis mensual")
    mensual = _agregar(datos, "month", activo, columna_fecha)
    if mensual.empty:
        st.info("La información disponible no es suficiente para el análisis mensual.")
        return
    estacional = estacionalidad_mes(mensual, columna_fecha="inicio")
    _grafico_barras(estacional, "mes", "promedio", "Retorno promedio histórico por mes")

    diarios = _datos_diarios(datos, activo, columna_fecha)
    curvas = _curvas_mensuales(diarios)
    st.markdown("#### Curva histórica ponderada de cada mes")
    st.caption(
        "Cada curva parte de la primera apertura del mes y promedia el retorno acumulado "
        "observado en el mismo día del mes a través de todos los años disponibles."
    )
    columnas = st.columns(2)
    for numero_mes, nombre_mes in enumerate(MESES_ES, start=1):
        with columnas[(numero_mes - 1) % 2]:
            subconjunto = curvas[curvas["numero_mes"].eq(numero_mes)]
            if len(subconjunto) < 2:
                st.info(f"{nombre_mes.title()}: información insuficiente.")
                continue
            _grafico_linea(
                subconjunto,
                "dia_mes",
                "retorno_ponderado",
                nombre_mes.title(),
                altura=330,
            )


def _seccion_semanal(datos: pd.DataFrame, activo: ActivoConfig, columna_fecha: str) -> None:
    """Compara semanas ISO con filtro opcional de valores atípicos."""

    st.subheader("Análisis semanal")
    semanal = _agregar(datos, "week", activo, columna_fecha)
    quitar_atipicos = st.toggle(
        "Excluir outliers semanales",
        value=False,
        key=f"iqr_semanal_{activo.simbolo}",
    )
    semanal_filtrado, eliminados = filtrar_iqr(semanal, activo=quitar_atipicos)
    if quitar_atipicos:
        st.caption(f"Método IQR Q1/Q3: {eliminados:,} semanas excluidas del cálculo.")
    if semanal_filtrado.empty:
        st.info("La información disponible no es suficiente para el análisis semanal.")
        return
    estacional = semana_iso(semanal_filtrado, columna_fecha="inicio")
    _grafico_barras(
        estacional,
        "semana_iso",
        "promedio",
        "Retorno histórico ponderado por semana ISO",
    )
    promedio_general = float(semanal_filtrado["return_percent"].mean())
    _grafico_linea(
        estacional,
        "semana_iso",
        "promedio",
        "Curva semanal comparada con el promedio general",
        promedio=promedio_general,
        altura=460,
    )


def _seccion_dia_semana(datos: pd.DataFrame, activo: ActivoConfig, columna_fecha: str) -> None:
    """Compara días y sus trayectorias intradía cuando existen horas."""

    st.subheader("Día de la semana")
    diarios = _datos_diarios(datos, activo, columna_fecha)
    estacional = dia_semana(diarios, columna_fecha="inicio")
    _grafico_barras(
        estacional,
        "dia_semana",
        "promedio",
        "Retorno promedio por día de la semana",
    )
    if not permite_analisis_horario(activo.temporalidad):
        st.info(
            "Los datos diarios permiten comparar el retorno de cada día, pero no contienen "
            "horas suficientes para construir las siete curvas intradía."
        )
        return
    trayectorias, _ = _curvas_intradia_por_dia(datos, activo, columna_fecha)
    st.markdown("#### Trayectoria histórica ponderada por día")
    _mostrar_curvas_por_dia(trayectorias, "Trayectoria acumulada")


def _seccion_diaria(datos: pd.DataFrame, activo: ActivoConfig, columna_fecha: str) -> None:
    """Muestra exclusivamente la estacionalidad por día del mes."""

    st.subheader("Análisis diario")
    diarios = _datos_diarios(datos, activo, columna_fecha)
    estacional = dia_mes(diarios, columna_fecha="inicio")
    if estacional.empty:
        st.info("La información disponible no es suficiente para el análisis diario.")
        return
    _grafico_barras(estacional, "dia_mes", "promedio", "Retorno promedio por día del mes")
    promedio = float(estacional["promedio"].mean())
    _grafico_linea(
        estacional,
        "dia_mes",
        "promedio",
        "Curva de retorno por día del mes",
        promedio=promedio,
        altura=440,
    )
    tema = _tema_actual()
    valores = estacional.set_index("dia_mes")["promedio"].reindex(range(1, 32))
    figura = go.Figure(
        go.Heatmap(
            z=[valores.to_numpy(dtype=float)],
            x=list(range(1, 32)),
            y=["Retorno"],
            text=[[f"{valor:.2f}%" if np.isfinite(valor) else "" for valor in valores]],
            texttemplate="%{text}",
            colorscale=[
                [0, COLORES["rojo"]],
                [0.5, tema["superficie_secundaria"]],
                [1, COLORES["verde"]],
            ],
            zmid=0,
            colorbar={"title": "Retorno (%)"},
            hovertemplate="Día %{x}<br>%{z:.2f}%<extra></extra>",
        )
    )
    figura.update_layout(height=300, xaxis_title="Día del mes")
    st.plotly_chart(
        _estilo_figura(figura, "Mapa de calor por día del mes", ""),
        width="stretch",
    )


def _seccion_horaria(datos: pd.DataFrame, activo: ActivoConfig, columna_fecha: str) -> None:
    """Analiza horas únicamente cuando existe información intradía."""

    st.subheader("Análisis horario")
    if not permite_analisis_horario(activo.temporalidad):
        st.info(
            f"La temporalidad {activo.temporalidad} es diaria o superior y no conserva "
            "horas observables. El análisis horario no está disponible."
        )
        return
    horas_agregadas = _agregar(datos, "hour", activo, columna_fecha)
    if horas_agregadas.empty:
        st.info("La información disponible no es suficiente para el análisis horario.")
        return
    estacional = hora(horas_agregadas, columna_fecha="inicio", temporalidad="1h")
    _grafico_barras(estacional, "hora", "promedio", "Retorno promedio por hora")
    _, retornos_hora = _curvas_intradia_por_dia(datos, activo, columna_fecha)
    st.markdown("#### Comportamiento horario por día de la semana")
    _mostrar_curvas_por_dia(retornos_hora, "Retorno por hora")


def _seccion_matriz(datos: pd.DataFrame, activo: ActivoConfig, columna_fecha: str) -> None:
    """Construye una matriz con días en X y horas en Y para datos intradía."""

    st.subheader("Matriz día-hora")
    if not permite_analisis_horario(activo.temporalidad):
        st.info("La matriz día-hora solo está disponible para datos intradía.")
        return
    metricas = {
        "Promedio": "mean",
        "Mediana": "median",
        "% positivos": "positive_pct",
        "Desv. estándar": "std",
        "Conteo": "count",
    }
    etiqueta = st.selectbox("Métrica", list(metricas), key=f"metrica_matriz_{activo.simbolo}")
    horas_agregadas = _agregar(datos, "hour", activo, columna_fecha)
    controles = st.columns(3)
    quitar_atipicos = controles[0].checkbox(
        "Quitar outliers",
        value=False,
        key=f"iqr_matriz_{activo.simbolo}",
    )
    factor_iqr = controles[1].number_input(
        "Factor IQR",
        min_value=0.0,
        value=1.5,
        step=0.1,
        disabled=not quitar_atipicos,
        key=f"iqr_factor_matriz_{activo.simbolo}",
    )
    minimo_observaciones = controles[2].number_input(
        "Mínimo por celda",
        min_value=1,
        value=5,
        step=1,
        key=f"minimo_matriz_{activo.simbolo}",
    )
    horas_filtradas, eliminados = filtrar_iqr(
        horas_agregadas,
        activo=quitar_atipicos,
        factor=float(factor_iqr),
    )
    matriz = matriz_dia_hora(
        horas_filtradas,
        metricas[etiqueta],
        columna_fecha="inicio",
        temporalidad="1h",
    )
    conteos = matriz_dia_hora(
        horas_filtradas,
        "count",
        columna_fecha="inicio",
        temporalidad="1h",
    )
    matriz = matriz.mask(conteos < int(minimo_observaciones))
    if quitar_atipicos:
        st.caption(
            f"Outliers: IQR Q1/Q3 con factor {factor_iqr:.1f}; "
            f"{eliminados:,} retornos horarios excluidos. Los CSV no fueron modificados."
        )
    else:
        st.caption("Outliers: filtro IQR desactivado. Los retornos horarios se conservan completos.")
    if matriz.empty:
        st.info("No hay observaciones para construir la matriz.")
        return
    tema = _tema_actual()
    es_porcentaje = metricas[etiqueta] != "count"
    if metricas[etiqueta] in {"mean", "median"}:
        escala = [
            [0, COLORES["rojo"]],
            [0.5, tema["superficie_secundaria"]],
            [1, COLORES["verde"]],
        ]
        centro = 0
    elif metricas[etiqueta] == "positive_pct":
        escala = [
            [0, COLORES["rojo"]],
            [0.5, tema["superficie_secundaria"]],
            [1, COLORES["verde"]],
        ]
        centro = 50
    else:
        escala = [[0, tema["superficie_secundaria"]], [1, tema["acento"]]]
        centro = None
    textos = np.array(
        [
            [
                ""
                if not np.isfinite(valor)
                else f"{valor:.2f}%"
                if es_porcentaje
                else f"{valor:.0f}"
                for valor in fila
            ]
            for fila in matriz.to_numpy(dtype=float)
        ]
    )
    sufijo = "%" if es_porcentaje else ""
    figura = go.Figure(
        go.Heatmap(
            z=matriz.to_numpy(dtype=float),
            x=list(matriz.columns),
            y=list(matriz.index),
            text=textos,
            texttemplate="%{text}",
            colorscale=escala,
            zmid=centro,
            colorbar={"title": etiqueta},
            hovertemplate=f"Día: %{{x}}<br>Hora: %{{y}}<br>Valor: %{{z:.2f}}{sufijo}<extra></extra>",
        )
    )
    figura.update_layout(height=760, xaxis_title="Días (X)", yaxis_title="Horas (Y)")
    st.plotly_chart(_estilo_figura(figura, f"{etiqueta} por día y hora", "Horas (Y)"), width="stretch")
    st.markdown("#### Detalle separado por día")
    pestañas = st.tabs(list(matriz.columns))
    for pestaña, nombre_dia in zip(pestañas, matriz.columns):
        with pestaña:
            valores_dia = matriz[nombre_dia].to_numpy(dtype=float)
            textos_dia = [
                ""
                if not np.isfinite(valor)
                else f"{valor:.2f}%"
                if es_porcentaje
                else f"{valor:.0f}"
                for valor in valores_dia
            ]
            detalle = go.Figure(
                go.Heatmap(
                    z=[valores_dia],
                    x=list(matriz.index),
                    y=[nombre_dia],
                    text=[textos_dia],
                    texttemplate="%{text}",
                    colorscale=escala,
                    zmid=centro,
                    showscale=False,
                    hovertemplate=f"Hora: %{{x}}<br>Valor: %{{z:.2f}}{sufijo}<extra></extra>",
                )
            )
            detalle.update_layout(height=260, xaxis_title="Hora")
            st.plotly_chart(
                _estilo_figura(detalle, f"{nombre_dia.title()} · {etiqueta}", ""),
                width="stretch",
            )


def _seccion_extremos(datos: pd.DataFrame, activo: ActivoConfig, columna_fecha: str) -> None:
    """Lista eventos extremos con trazabilidad OHLC y completitud."""

    st.subheader("Eventos extremos")
    izquierda, centro, derecha = st.columns(3)
    periodo = izquierda.selectbox(
        "Periodo",
        _opciones_periodo(activo),
        index=_opciones_periodo(activo).index("Día"),
        key=f"periodo_extremos_{activo.simbolo}",
    )
    usar_umbral = centro.checkbox("Usar umbral absoluto", value=False, key=f"umbral_activo_{activo.simbolo}")
    if usar_umbral:
        umbral = derecha.number_input(
            "Umbral (%)", min_value=0.0, value=2.0, step=0.1, key=f"umbral_{activo.simbolo}"
        )
        n = 5
    else:
        n = derecha.number_input(
            "Mejores y peores", min_value=1, max_value=100, value=5, step=1, key=f"n_extremos_{activo.simbolo}"
        )
        umbral = None
    periodos, fecha_periodo = _periodo_seleccionado(periodo, datos, activo, columna_fecha)
    extremos = eventos_extremos(
        periodos,
        n=int(n),
        umbral=float(umbral) if umbral is not None else None,
        columna_fecha=fecha_periodo,
    )
    columnas = ["inicio", "fin", "open", "close", "return_percent", "cantidad_registros", "completo", "tipo_extremo"]
    _mostrar_tabla(
        extremos[columnas],
        {
            "inicio": "fecha inicial",
            "fin": "fecha final",
            "return_percent": "retorno (%)",
            "cantidad_registros": "conteo",
            "completo": "completo",
            "tipo_extremo": "tipo",
        },
    )


def _barra_lateral_seleccion(activos: dict[str, ActivoConfig]) -> None:
    """Concentra en el lateral toda la selección del activo inicial."""

    st.sidebar.markdown("## Finance")
    st.sidebar.caption("Selección del activo")
    categorias = sorted({activo.categoria for activo in activos.values()}, key=str.casefold)
    if st.session_state.get("categoria_seleccion") not in categorias:
        st.session_state["categoria_seleccion"] = categorias[0]
    categoria = st.sidebar.selectbox(
        "Categoría",
        categorias,
        key="categoria_seleccion",
        format_func=_etiqueta_categoria,
    )
    simbolos = [
        simbolo for simbolo, activo in activos.items() if activo.categoria == categoria
    ]
    if st.session_state.get("activo_selector") not in simbolos:
        st.session_state["activo_selector"] = simbolos[0]
    simbolo = st.sidebar.selectbox(
        "Activo",
        simbolos,
        key="activo_selector",
        format_func=lambda clave: f"{clave} · {activos[clave].nombre}",
    )
    if st.sidebar.button("Analizar activo", type="primary", width="stretch"):
        try:
            with st.spinner(f"Preparando {simbolo}..."):
                resultado = _resultado(activos[simbolo])
            if resultado.datos_validos.empty:
                st.sidebar.error("El activo no contiene filas válidas para analizar.")
            else:
                st.session_state["activo_actual"] = simbolo
                st.session_state["analizando"] = True
                st.rerun()
        except (ErrorDatos, ErrorCache, ErrorConfiguracion, KeyError, OSError, ValueError) as exc:
            REGISTRO.exception("No se pudo iniciar el analisis de %s", simbolo)
            st.sidebar.error(f"No se pudo analizar {simbolo}: {exc}")
    st.sidebar.divider()
    if st.sidebar.button("Actualizar datos y cache", width="stretch"):
        _actualizar_cache()
    st.sidebar.caption("Relee únicamente los archivos locales.")


def _barra_lateral(
    activos: dict[str, ActivoConfig], activo: ActivoConfig
) -> str:
    """Construye navegación plegable, cambio de activo y cache local."""

    st.sidebar.markdown("## Finance")
    st.sidebar.caption(f"{activo.simbolo} · {activo.temporalidad} · {activo.zona_horaria}")
    st.sidebar.markdown("### Navegación")
    seccion = st.sidebar.selectbox(
        "Análisis actual",
        SECCIONES,
        key="seccion_actual",
        help="El mismo menú permanece visible en el panel principal.",
    )
    st.sidebar.divider()
    st.sidebar.markdown("### Cambiar mercado")
    categorias = sorted({config.categoria for config in activos.values()}, key=str.casefold)
    categoria_actual = activo.categoria
    categoria_nueva = st.sidebar.selectbox(
        "Categoría",
        categorias,
        index=categorias.index(categoria_actual),
        format_func=_etiqueta_categoria,
        key="categoria_cambio",
    )
    opciones = [
        simbolo for simbolo, config in activos.items() if config.categoria == categoria_nueva
    ]
    indice = opciones.index(activo.simbolo) if activo.simbolo in opciones else 0
    nuevo = st.sidebar.selectbox(
        "Activo",
        opciones,
        index=indice,
        format_func=lambda clave: f"{clave} · {activos[clave].nombre}",
        key=f"activo_cambio_{categoria_nueva}",
    )
    if st.sidebar.button("Cambiar activo", width="stretch"):
        try:
            resultado = _resultado(activos[nuevo])
            if resultado.datos_validos.empty:
                st.sidebar.error("El activo elegido no contiene filas válidas.")
            else:
                st.session_state["activo_actual"] = nuevo
                st.session_state["activo_selector"] = nuevo
                st.session_state["categoria_seleccion"] = activos[nuevo].categoria
                st.rerun()
        except (ErrorDatos, ErrorCache, ErrorConfiguracion, KeyError, OSError, ValueError) as exc:
            REGISTRO.exception("No se pudo cambiar al activo %s", nuevo)
            st.sidebar.error(f"No se pudo cambiar de activo: {exc}")
    if st.sidebar.button("Volver a selección", width="stretch"):
        st.session_state["analizando"] = False
        st.rerun()
    st.sidebar.divider()
    if st.sidebar.button("Actualizar datos y cache", width="stretch"):
        _actualizar_cache()
    st.sidebar.caption("Limpia caches y vuelve a leer archivos locales. No descarga datos.")
    return seccion


def _pantalla_analisis(activos: dict[str, ActivoConfig]) -> None:
    """Coordina carga, filtros globales y la sección de análisis elegida."""

    simbolo = st.session_state.get("activo_actual")
    if simbolo not in activos:
        st.session_state["analizando"] = False
        st.rerun()
    activo = activos[simbolo]
    seccion = _barra_lateral(activos, activo)
    try:
        resultado = _resultado(activo)
        datos, columna_fecha = _preparar_datos(resultado.datos_validos, activo)
    except (ErrorDatos, ErrorCache, ErrorConfiguracion, KeyError, OSError, ValueError) as exc:
        REGISTRO.exception("No se pudo cargar el activo %s", activo.simbolo)
        st.error(f"No se pudo cargar {activo.simbolo}: {exc}")
        st.info("Puede volver a la selección o elegir otro activo desde la barra lateral.")
        return

    _cabecera_activo(activo, datos, columna_fecha)
    _panel_navegacion(seccion)
    try:
        datos_sesion, detalle_sesion = _controles_sesion(datos, activo, columna_fecha)
    except ValueError as exc:
        st.error(f"La configuración de sesión no es válida: {exc}")
        datos_sesion = datos
        detalle_sesion = "Se conserva la serie completa por un error en el filtro."

    datos_filtrados = datos_sesion
    st.caption(detalle_sesion)

    if datos_filtrados.empty and seccion != "Calidad de datos":
        st.warning("Los filtros actuales no dejan observaciones para analizar.")
        return

    vistas: dict[str, Callable[[], None]] = {
        "Resumen": lambda: _seccion_resumen(datos_filtrados, activo, columna_fecha),
        "Calidad de datos": lambda: _seccion_calidad(resultado, activo),
        "Análisis por periodo": lambda: _seccion_anual(datos_filtrados, activo, columna_fecha),
        "Análisis mensual": lambda: _seccion_mensual(datos_filtrados, activo, columna_fecha),
        "Análisis semanal": lambda: _seccion_semanal(datos_filtrados, activo, columna_fecha),
        "Día de la semana": lambda: _seccion_dia_semana(datos_filtrados, activo, columna_fecha),
        "Análisis diario": lambda: _seccion_diaria(datos_filtrados, activo, columna_fecha),
        "Análisis horario": lambda: _seccion_horaria(datos_filtrados, activo, columna_fecha),
        "Matriz día-hora": lambda: _seccion_matriz(datos_filtrados, activo, columna_fecha),
        "Eventos extremos": lambda: _seccion_extremos(datos_filtrados, activo, columna_fecha),
    }
    try:
        vistas[seccion]()
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        REGISTRO.exception("Fallo la seccion %s para %s", seccion, activo.simbolo)
        st.error(f"No se pudo calcular esta sección: {exc}")


def ejecutar_aplicacion() -> None:
    """Inicializa estado y renderiza la selección o el análisis activo."""

    st.session_state.setdefault("analizando", False)
    st.session_state.setdefault("modo_oscuro", False)
    if st.session_state.get("seccion_actual") not in SECCIONES:
        st.session_state["seccion_actual"] = "Resumen"
    _inyectar_estilos()
    if mensaje := st.session_state.pop("mensaje_cache", None):
        st.success(mensaje)
    try:
        errores_configuracion: dict[str, str] = {}
        activos = cargar_activos(
            RUTA_CONFIGURACION,
            tolerante=True,
            errores=errores_configuracion,
        )
    except ErrorConfiguracion as exc:
        REGISTRO.exception("No se pudo cargar activos.json")
        st.error(f"No se pudo cargar la configuración de activos: {exc}")
        st.stop()
    if errores_configuracion:
        with st.expander(
            f"{len(errores_configuracion)} activo(s) omitido(s) por errores de configuración"
        ):
            for simbolo, mensaje in errores_configuracion.items():
                st.warning(f"{simbolo}: {mensaje}")
    if not activos:
        st.error("No existe ningún activo válido para mostrar.")
        st.stop()
    if st.session_state["analizando"]:
        _pantalla_analisis(activos)
    else:
        _barra_lateral_seleccion(activos)
        _pantalla_seleccion(activos)


__all__ = ["ejecutar_aplicacion"]
