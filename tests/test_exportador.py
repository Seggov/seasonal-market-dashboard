"""Pruebas del contrato JSON estatico."""

from __future__ import annotations

import json
import math
from datetime import datetime, timezone

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
# Zonas horarias
# --------------------------------------------------------------------------


def test_transiciones_de_nueva_york_incluyen_los_dos_cambios_anuales() -> None:
    zona = exportador.tabla_transiciones(
        "America/New_York",
        datetime(2024, 1, 1, tzinfo=timezone.utc),
        datetime(2024, 12, 31, tzinfo=timezone.utc),
    )
    assert zona["name"] == "America/New_York"
    desplazamientos = {offset for _, offset, *_ in zona["transitions"]}
    assert desplazamientos == {-18000, -14400}
    # 2024-03-10 07:00Z pasa a EDT y 2024-11-03 06:00Z vuelve a EST.
    instantes = {marca for marca, *_ in zona["transitions"]}
    assert int(datetime(2024, 3, 10, 7, tzinfo=timezone.utc).timestamp()) in instantes
    assert int(datetime(2024, 11, 3, 6, tzinfo=timezone.utc).timestamp()) in instantes
    abreviaturas = {abreviatura for _, _, abreviatura in zona["transitions"]}
    assert abreviaturas == {"EST", "EDT"}


def test_transiciones_de_tokio_estan_vacias() -> None:
    """Asia/Tokyo no aplica horario de verano desde 1951."""

    zona = exportador.tabla_transiciones(
        "Asia/Tokyo",
        datetime(2000, 1, 1, tzinfo=timezone.utc),
        datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    assert zona["transitions"] == []
    assert zona["initialOffset"] == 32400


def test_transiciones_de_utc_estan_vacias() -> None:
    zona = exportador.tabla_transiciones(
        "UTC",
        datetime(2017, 1, 1, tzinfo=timezone.utc),
        datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    assert zona["transitions"] == []
    assert zona["initialOffset"] == 0


# --------------------------------------------------------------------------
# Codificacion de series
# --------------------------------------------------------------------------


def _decodificar(serie: dict[str, object], clave: str) -> np.ndarray:
    valores = serie[clave]
    if serie["scale"] is None:
        return np.array(valores, dtype=float)
    return np.cumsum(np.array(valores, dtype=np.int64)) / serie["scale"]


def test_la_serie_codificada_reproduce_los_precios_bit_a_bit() -> None:
    for construir in escenarios.ESCENARIOS:
        escenario = construir()
        serie = exportador.construir_serie(
            escenario.datos, escenario.nombre, 2024, COLUMNA_FECHA
        )
        for clave, columna in (("o", "open"), ("h", "high"), ("l", "low"), ("c", "close")):
            esperado = escenario.datos[columna].to_numpy(dtype=float)
            np.testing.assert_array_equal(_decodificar(serie, clave), esperado)


def test_la_serie_codificada_reproduce_las_marcas_de_tiempo() -> None:
    escenario = escenarios.escenario_ny_otono()
    serie = exportador.construir_serie(
        escenario.datos, escenario.nombre, 2024, COLUMNA_FECHA
    )
    epochs = np.concatenate(
        ([serie["t0"]], serie["t0"] + np.cumsum(np.array(serie["dt"], dtype=np.int64)))
    )
    esperado = (
        pd.to_datetime(escenario.datos[COLUMNA_FECHA]).astype("int64") // 1_000_000_000
    ).to_numpy()
    np.testing.assert_array_equal(epochs, esperado)


def test_los_desplazamientos_rle_se_expanden_correctamente() -> None:
    escenario = escenarios.escenario_ny_otono()
    serie = exportador.construir_serie(
        escenario.datos, escenario.nombre, 2024, COLUMNA_FECHA
    )
    expandido = np.empty(serie["count"], dtype=np.int64)
    tramos = serie["off"]
    for posicion, (indice, offset) in enumerate(tramos):
        fin = tramos[posicion + 1][0] if posicion + 1 < len(tramos) else serie["count"]
        expandido[indice:fin] = offset
    esperado = np.array(
        [
            int(marca.utcoffset().total_seconds())
            for marca in pd.to_datetime(escenario.datos[COLUMNA_FECHA])
        ]
    )
    np.testing.assert_array_equal(expandido, esperado)
    # El escenario cruza el cambio de horario: hay exactamente dos tramos.
    assert len(tramos) == 2
    assert [offset for _, offset in tramos] == [-14400, -18000]


def _marco_precios(aperturas: list[float]) -> pd.DataFrame:
    marcas = pd.to_datetime(
        [f"2024-01-01T{indice:02d}:00:00Z" for indice in range(len(aperturas))], utc=True
    )
    return pd.DataFrame(
        {
            COLUMNA_FECHA: marcas,
            "open": aperturas,
            # Se mantienen los mismos decimales para no forzar otra escala.
            "high": list(aperturas),
            "low": list(aperturas),
            "close": aperturas,
        }
    )


@pytest.mark.parametrize(
    ("aperturas", "motivo"),
    [
        ([1.0, 0.12345678901234567], "mas decimales de los admitidos"),
        ([1e12 + 0.5, 1.000001], "el entero escalado desbordaria 2**53"),
    ],
)
def test_la_escala_se_desactiva_cuando_no_es_exacta(
    aperturas: list[float], motivo: str
) -> None:
    """Si el escalado entero no es demostrablemente exacto se usan dobles."""

    serie = exportador.construir_serie(_marco_precios(aperturas), "RAW", 2024, COLUMNA_FECHA)
    assert serie["scale"] is None, motivo
    np.testing.assert_array_equal(
        _decodificar(serie, "o"), np.array(aperturas, dtype=float)
    )


def test_la_escala_se_usa_cuando_es_demostrablemente_exacta() -> None:
    """Un CSV con decimales acotados se publica como enteros escalados."""

    serie = exportador.construir_serie(
        _marco_precios([340.345, 341.255, 339.81]), "ESC", 2024, COLUMNA_FECHA
    )
    assert serie["scale"] is not None
    assert all(isinstance(valor, int) for valor in serie["o"])
    np.testing.assert_array_equal(
        _decodificar(serie, "o"), np.array([340.345, 341.255, 339.81], dtype=float)
    )


def test_fragmentar_por_año_usa_el_año_local() -> None:
    escenario = escenarios.escenario_tokio_semana_iso()
    fragmentos = exportador.fragmentar_por_año(escenario.datos, COLUMNA_FECHA)
    assert [año for año, _ in fragmentos] == [2020, 2021]
    total = sum(len(marco) for _, marco in fragmentos)
    assert total == len(escenario.datos)
    primero = fragmentos[0][1]
    assert set(pd.to_datetime(primero[COLUMNA_FECHA]).dt.year) == {2020}


# --------------------------------------------------------------------------
# Vistas precalculadas
# --------------------------------------------------------------------------


@pytest.fixture
def entorno() -> tuple[pd.DataFrame, ActivoConfig]:
    escenario = escenarios.escenario_utc_continuo()
    return escenario.datos, _activo(escenario)


def test_vistas_por_defecto_cubren_las_diez_vistas(entorno) -> None:
    datos, activo = entorno
    salida = exportador.vistas_por_defecto(datos, activo, COLUMNA_FECHA)
    assert set(salida) == {
        "resumen",
        "periodo",
        "mensual",
        "semanal",
        "diaSemana",
        "diaria",
        "horaria",
        "matriz",
        "extremos",
    }


def test_vistas_por_defecto_son_json_estricto(entorno) -> None:
    datos, activo = entorno
    texto = exportador.volcar_json(
        exportador.vistas_por_defecto(datos, activo, COLUMNA_FECHA)
    )
    recargado = json.loads(texto)
    assert recargado["resumen"]["metricas"]["velas"] == len(datos)


def test_vista_resumen_coincide_con_las_transformaciones(entorno) -> None:
    datos, activo = entorno
    salida = exportador.vista_resumen(datos, activo, COLUMNA_FECHA)
    metricas = vistas.metricas_resumen(datos, activo, COLUMNA_FECHA)
    assert salida["metricas"]["ultimo_cierre"] == metricas["ultimo_cierre"]
    assert salida["velas"]["total"] == len(datos)
    assert salida["velas"]["resumido"] is False
    assert len(salida["velas"]["t"]) == len(datos)


def test_vista_periodo_publica_pivote_de_doce_meses(entorno) -> None:
    datos, activo = entorno
    salida = exportador.vista_periodo(datos, activo, COLUMNA_FECHA)
    assert salida["pivote"]["años"] == [2021]
    assert len(salida["pivote"]["meses"][0]) == 12
    assert salida["pivote"]["meses"][0][2] is not None  # marzo
    assert salida["pivote"]["meses"][0][0] is None  # enero sin datos


def test_vista_matriz_enmascara_por_minimo(entorno) -> None:
    datos, activo = entorno
    salida = exportador.vista_matriz(
        datos, activo, COLUMNA_FECHA, minimo_observaciones=1000
    )
    assert salida["disponible"] is True
    assert all(valor is None for fila in salida["valores"] for valor in fila)


def test_vista_matriz_no_disponible_sin_intradia(entorno) -> None:
    datos, _ = entorno
    diario = _activo(escenarios.escenario_utc_continuo(), temporalidad="1d")
    assert exportador.vista_matriz(datos, diario, COLUMNA_FECHA) == {"disponible": False}
    assert exportador.vista_horaria(datos, diario, COLUMNA_FECHA)["disponible"] is False


def test_vista_extremos_respeta_el_orden_documentado(entorno) -> None:
    """Ambiguedad A-6: orden por retorno con signo, no por magnitud."""

    datos, activo = entorno
    salida = exportador.vista_extremos(datos, activo, COLUMNA_FECHA, n=3)
    retornos = [fila["return_percent"] for fila in salida["filas"]]
    assert retornos == sorted(retornos, reverse=True)
    assert len(salida["filas"]) <= 6


def test_vista_extremos_con_umbral(entorno) -> None:
    datos, activo = entorno
    salida = exportador.vista_extremos(
        datos, activo, COLUMNA_FECHA, umbral=0.5, periodo="Vela base"
    )
    assert salida["umbral"] == 0.5
    assert all(abs(fila["return_percent"]) >= 0.5 - 1e-10 for fila in salida["filas"])


def test_vista_semanal_informa_de_los_excluidos_por_iqr(entorno) -> None:
    datos, activo = entorno
    sin_filtro = exportador.vista_semanal(datos, activo, COLUMNA_FECHA)
    assert sin_filtro["eliminados"] == 0
    assert math.isfinite(sin_filtro["promedioGeneral"])


# --------------------------------------------------------------------------
# Informe y manifiesto
# --------------------------------------------------------------------------


def test_el_informe_no_publica_rutas_absolutas() -> None:
    from src.datos import ResultadoValidacion

    escenario = escenarios.escenario_utc_continuo()
    activo = _activo(escenario)
    resultado = ResultadoValidacion(
        datos_originales=escenario.datos,
        datos_validos=escenario.datos,
        invalidos=pd.DataFrame(columns=["motivo_invalidez"]),
        resumen={
            "filas_totales": len(escenario.datos),
            "filas_validas": len(escenario.datos),
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
    informe = exportador.construir_informe(
        resultado, activo, escenario.datos, COLUMNA_FECHA
    )
    texto = exportador.volcar_json(informe)
    assert "C:\\\\" not in texto and "/home/" not in texto
    assert informe["observado"]["dias"] == [0, 1, 2, 3, 4, 5, 6]
    assert informe["observado"]["horas"] == list(range(24))
    assert informe["schemaVersion"] == exportador.SCHEMA_VERSION

    entrada = exportador.entrada_manifiesto(
        activo, informe, [2021], {"name": "UTC", "initialOffset": 0, "transitions": []}
    )
    assert entrada["archivo"] == "sintetico.csv"
    assert entrada["sesionReconocida"] == "24/7"
    assert entrada["intradia"] is True
    assert entrada["baseMinutes"] == 60


@pytest.mark.parametrize(
    ("sesion", "esperado"),
    [
        ("24/7", "24/7"),
        ("24/5", "24/5"),
        ("Dukascopy 24/5 extendida", None),
        ("NYSE regular observada", None),
    ],
)
def test_sesion_reconocida_replica_la_igualdad_exacta(
    sesion: str, esperado: str | None
) -> None:
    """Ambiguedad A-3 expuesta explicitamente en el manifiesto."""

    escenario = escenarios.escenario_utc_continuo()
    activo = _activo(escenario, sesion=sesion)
    informe = {"calidad": {k: None for k in (
        "fechaInicial", "fechaFinal", "filasTotales", "filasValidas",
        "porcentajeValido", "cobertura",
    )}}
    entrada = exportador.entrada_manifiesto(activo, informe, [], {})
    assert entrada["sesionReconocida"] == esperado
