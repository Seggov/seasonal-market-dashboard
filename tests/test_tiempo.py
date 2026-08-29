"""Pruebas de tiempo, DST y semanas ISO sobre los escenarios de paridad.

Fijan el comportamiento descrito en ``docs/PARIDAD.md`` seccion 3 antes de
reimplementarlo en JavaScript.
"""

from __future__ import annotations

import pandas as pd
import pytest

from src.analisis import agregar_periodos, filtrar_sesion_personalizada
from tests import escenarios
from tests.escenarios import COLUMNA_FECHA


def _agregar(escenario: escenarios.Escenario, periodo: str) -> pd.DataFrame:
    return agregar_periodos(
        escenario.datos,
        periodo,
        columna_fecha=COLUMNA_FECHA,
        temporalidad=escenario.temporalidad,
    )


def test_escenarios_son_deterministas() -> None:
    """Dos construcciones seguidas producen exactamente los mismos numeros."""

    for construir in escenarios.ESCENARIOS:
        primero = construir().datos
        segundo = construir().datos
        pd.testing.assert_frame_equal(primero, segundo)


def test_otono_repite_la_hora_local_con_dos_desplazamientos() -> None:
    """La hora local 01:00 del 2024-11-03 aparece con -14400 y con -18000."""

    escenario = escenarios.escenario_ny_otono()
    fechas = escenario.datos[COLUMNA_FECHA]
    una_de_la_madrugada = fechas[
        fechas.dt.strftime("%Y-%m-%d %H").eq("2024-11-03 01")
    ]
    assert len(una_de_la_madrugada) == 2
    desplazamientos = [
        int(marca.utcoffset().total_seconds()) for marca in una_de_la_madrugada
    ]
    assert desplazamientos == [-14400, -18000]


def test_otono_ordena_la_segunda_hora_antes_que_la_primera() -> None:
    """Ambiguedad A-1: la clave lexicografica invierte la hora repetida."""

    escenario = escenarios.escenario_ny_otono()
    horas = _agregar(escenario, "hour")
    inicios = pd.to_datetime(horas["inicio"])
    repetidas = horas[inicios.dt.strftime("%Y-%m-%d %H").eq("2024-11-03 01")]
    assert len(repetidas) == 2
    desplazamientos = [
        int(pd.Timestamp(marca).utcoffset().total_seconds())
        for marca in repetidas["inicio"]
    ]
    # -18000 (EST, cronologicamente posterior) queda primero.
    assert desplazamientos == [-18000, -14400]


def test_otono_espera_veinticinco_velas_en_el_dia_largo() -> None:
    """El 2024-11-03 local dura 25 horas y solo asi es completo."""

    escenario = escenarios.escenario_ny_otono()
    dias = _agregar(escenario, "day")
    dias["fecha"] = pd.to_datetime(dias["inicio"]).dt.strftime("%Y-%m-%d")
    largo = dias[dias["fecha"].eq("2024-11-03")].iloc[0]
    assert int(largo["cantidad_registros"]) == 25
    assert bool(largo["completo"]) is True


def test_primavera_espera_veintitres_velas_en_el_dia_corto() -> None:
    """El 2024-03-10 local dura 23 horas y la hora 02:00 no existe."""

    escenario = escenarios.escenario_ny_primavera()
    fechas = escenario.datos[COLUMNA_FECHA]
    horas_locales = fechas[fechas.dt.strftime("%Y-%m-%d").eq("2024-03-10")].dt.hour
    assert 2 not in set(horas_locales)

    dias = _agregar(escenario, "day")
    dias["fecha"] = pd.to_datetime(dias["inicio"]).dt.strftime("%Y-%m-%d")
    corto = dias[dias["fecha"].eq("2024-03-10")].iloc[0]
    assert int(corto["cantidad_registros"]) == 23
    assert bool(corto["completo"]) is True


def test_semana_iso_2020_w53_cruza_el_ano() -> None:
    """La semana ISO 53 de 2020 empieza el 28-12-2020 y acaba el 03-01-2021."""

    escenario = escenarios.escenario_tokio_semana_iso()
    semanas = _agregar(escenario, "week")
    inicios = pd.to_datetime(semanas["inicio"])
    finales = pd.to_datetime(semanas["fin"])
    calendario = inicios.dt.isocalendar()
    posicion = calendario.index[
        calendario["year"].eq(2020) & calendario["week"].eq(53)
    ]
    assert len(posicion) == 1
    indice = posicion[0]
    assert inicios[indice].strftime("%Y-%m-%d") == "2020-12-28"
    assert finales[indice].strftime("%Y-%m-%d") == "2021-01-03"


def test_semana_iso_ordena_por_ano_iso_y_no_por_ano_calendario() -> None:
    """El orden es ``año_iso * 100 + semana_iso``, sin saltos."""

    escenario = escenarios.escenario_tokio_semana_iso()
    semanas = _agregar(escenario, "week")
    calendario = pd.to_datetime(semanas["inicio"]).dt.isocalendar()
    claves = (calendario["year"].astype(int) * 100 + calendario["week"].astype(int))
    assert list(claves) == sorted(claves)


def test_marcas_en_media_hora_nunca_producen_horas_completas() -> None:
    """Ambiguedad A-2: si la vela empieza en ``HH:30`` la hora no es completa."""

    escenario = escenarios.escenario_media_hora()
    minutos = set(escenario.datos[COLUMNA_FECHA].dt.minute)
    assert minutos == {30}
    horas = _agregar(escenario, "hour")
    assert not horas.empty
    assert not horas["completo"].any()


def test_los_huecos_impiden_la_completitud_diaria() -> None:
    """Un dia al que le falta una vela nunca se marca completo."""

    escenario = escenarios.escenario_huecos()
    dias = _agregar(escenario, "day")
    dias["fecha"] = pd.to_datetime(dias["inicio"]).dt.strftime("%Y-%m-%d")
    incompletos = set(dias.loc[~dias["completo"], "fecha"])
    assert {"2022-06-01", "2022-06-02", "2022-06-04", "2022-06-05"} <= incompletos
    assert dias.loc[dias["fecha"].eq("2022-06-03"), "completo"].all()


@pytest.mark.parametrize(
    ("inicio", "fin", "esperado_horas"),
    [
        ("09:00", "17:00", set(range(9, 17))),
        ("22:00", "03:00", {22, 23, 0, 1, 2}),
        ("00:00", "00:00", set(range(24))),
    ],
)
def test_sesion_personalizada_incluye_el_inicio_y_excluye_el_fin(
    inicio: str, fin: str, esperado_horas: set[int]
) -> None:
    """Ambiguedades A-9 y A-11: intervalo semiabierto que puede cruzar medianoche."""

    escenario = escenarios.escenario_utc_continuo()
    filtrado = filtrar_sesion_personalizada(
        escenario.datos,
        inicio,
        fin,
        columna_fecha=COLUMNA_FECHA,
        temporalidad=escenario.temporalidad,
    )
    assert set(filtrado[COLUMNA_FECHA].dt.hour) == esperado_horas


def test_sesion_nocturna_se_reparte_entre_dos_dias_calendario() -> None:
    """Ambiguedad A-9: la agregacion diaria no reasigna la sesion nocturna."""

    escenario = escenarios.escenario_utc_continuo()
    filtrado = filtrar_sesion_personalizada(
        escenario.datos,
        "22:00",
        "03:00",
        columna_fecha=COLUMNA_FECHA,
        temporalidad=escenario.temporalidad,
    )
    dias = agregar_periodos(
        filtrado,
        "day",
        columna_fecha=COLUMNA_FECHA,
        temporalidad=escenario.temporalidad,
    )
    primero = dias.iloc[0]
    horas_primer_dia = set(
        filtrado.loc[
            filtrado[COLUMNA_FECHA].dt.normalize().eq(
                pd.Timestamp(primero["inicio"]).normalize()
            ),
            COLUMNA_FECHA,
        ].dt.hour
    )
    # El primer dia contiene el tramo 22:00-23:00 y tambien 00:00-02:00.
    assert {22, 23} <= horas_primer_dia
    assert {0, 1, 2} <= horas_primer_dia
    assert not dias["completo"].any()
