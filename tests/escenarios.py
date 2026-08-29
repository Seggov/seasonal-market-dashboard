"""Escenarios sinteticos deterministas para las pruebas de paridad.

Cada escenario devuelve un DataFrame con la misma forma que produce
``interfaz._preparar_datos``: una columna temporal local con zona, OHLC en
punto flotante y ``return_percent`` derivado de cada vela.

Los escenarios se comparten entre las pruebas de Python y la generacion de
fixtures doradas que consumen las pruebas de JavaScript, de modo que ambas
implementaciones se comparan sobre exactamente los mismos numeros.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd


COLUMNA_FECHA = "timestamp_local"


class _Aleatorio:
    """Generador congruencial lineal, estable en cualquier version."""

    def __init__(self, semilla: int) -> None:
        self._estado = semilla & 0xFFFFFFFF

    def siguiente(self) -> float:
        """Devuelve un flotante en ``[0, 1)`` reproducible bit a bit."""

        self._estado = (1103515245 * self._estado + 12345) & 0x7FFFFFFF
        return self._estado / 0x80000000


@dataclass(frozen=True, slots=True)
class Escenario:
    """Una serie sintetica con su metadata de activo."""

    nombre: str
    zona: str
    temporalidad: str
    sesion: str
    descripcion: str
    datos: pd.DataFrame


def _construir(
    *,
    nombre: str,
    zona: str,
    inicio_utc: datetime,
    cantidad: int,
    paso: timedelta,
    precio_inicial: float,
    decimales: int,
    semilla: int,
    sesion: str,
    descripcion: str,
    temporalidad: str = "1h",
    omitir: Callable[[int], bool] | None = None,
) -> Escenario:
    """Genera velas OHLC coherentes y reproducibles en una zona concreta."""

    aleatorio = _Aleatorio(semilla)
    tz = ZoneInfo(zona)
    marcas: list[pd.Timestamp] = []
    aperturas: list[float] = []
    maximos: list[float] = []
    minimos: list[float] = []
    cierres: list[float] = []

    precio = precio_inicial
    for indice in range(cantidad):
        instante = inicio_utc + paso * indice
        if omitir is not None and omitir(indice):
            continue
        variacion = (aleatorio.siguiente() - 0.5) * 0.02
        apertura = round(precio, decimales)
        cierre = round(apertura * (1.0 + variacion), decimales)
        maximo = round(max(apertura, cierre) * (1.0 + aleatorio.siguiente() * 0.004), decimales)
        minimo = round(min(apertura, cierre) * (1.0 - aleatorio.siguiente() * 0.004), decimales)
        marcas.append(pd.Timestamp(instante).tz_convert(tz))
        aperturas.append(apertura)
        maximos.append(maximo)
        minimos.append(minimo)
        cierres.append(cierre)
        precio = cierre

    datos = pd.DataFrame(
        {
            COLUMNA_FECHA: pd.DatetimeIndex(marcas),
            "open": aperturas,
            "high": maximos,
            "low": minimos,
            "close": cierres,
        }
    )
    datos["timeframe"] = temporalidad
    apertura_serie = datos["open"]
    datos["return_percent"] = np.where(
        apertura_serie.abs() > 1e-10,
        (datos["close"] / apertura_serie - 1.0) * 100.0,
        np.nan,
    )
    return Escenario(
        nombre=nombre,
        zona=zona,
        temporalidad=temporalidad,
        sesion=sesion,
        descripcion=descripcion,
        datos=datos,
    )


def _utc(año: int, mes: int, dia: int, hora: int = 0, minuto: int = 0) -> datetime:
    return datetime(año, mes, dia, hora, minuto, tzinfo=timezone.utc)


def escenario_utc_continuo() -> Escenario:
    """Diez dias horarios en UTC, sin cambios de horario."""

    return _construir(
        nombre="utc_continuo",
        zona="UTC",
        inicio_utc=_utc(2021, 3, 1),
        cantidad=24 * 10,
        paso=timedelta(hours=1),
        precio_inicial=100.0,
        decimales=2,
        semilla=20210301,
        sesion="24/7",
        descripcion="Serie 24/7 en UTC sin transiciones de horario.",
    )


def escenario_ny_otono() -> Escenario:
    """Nueva York alrededor del retroceso de horario (hora local repetida)."""

    return _construir(
        nombre="ny_dst_otono",
        zona="America/New_York",
        inicio_utc=_utc(2024, 11, 1),
        cantidad=24 * 6,
        paso=timedelta(hours=1),
        precio_inicial=1980.5,
        decimales=3,
        semilla=20241103,
        sesion="Dukascopy 24/5 extendida",
        descripcion=(
            "Cruza el 2024-11-03: la hora local 01:00 aparece dos veces, con "
            "desplazamientos -14400 y -18000."
        ),
    )


def escenario_ny_primavera() -> Escenario:
    """Nueva York alrededor del adelanto de horario (hora local inexistente)."""

    return _construir(
        nombre="ny_dst_primavera",
        zona="America/New_York",
        inicio_utc=_utc(2024, 3, 8),
        cantidad=24 * 6,
        paso=timedelta(hours=1),
        precio_inicial=76.25,
        decimales=3,
        semilla=20240310,
        sesion="Dukascopy 24/5 extendida",
        descripcion=(
            "Cruza el 2024-03-10: la hora local 02:00 no existe y el dia dura "
            "23 horas."
        ),
    )


def escenario_tokio_semana_iso() -> Escenario:
    """Tokio cruzando el fin de ano con semana ISO 2020-W53."""

    return _construir(
        nombre="tokio_semana_iso",
        zona="Asia/Tokyo",
        inicio_utc=_utc(2020, 12, 20),
        cantidad=24 * 22,
        paso=timedelta(hours=1),
        precio_inicial=26800.0,
        decimales=2,
        semilla=20201228,
        sesion="Tokyo regular observada",
        descripcion=(
            "Del 2020-12-20 al 2021-01-11 en Asia/Tokyo: incluye la semana ISO "
            "2020-W53, que empieza en diciembre y termina en enero."
        ),
    )


def escenario_media_hora() -> Escenario:
    """Velas que empiezan en ``HH:30``, como el CSV de SP500."""

    return _construir(
        nombre="ny_media_hora",
        zona="America/New_York",
        inicio_utc=_utc(2023, 9, 5, 13, 30),
        cantidad=24 * 8,
        paso=timedelta(hours=1),
        precio_inicial=4390.0,
        decimales=4,
        semilla=20230905,
        sesion="NYSE regular observada",
        descripcion="Marcas locales en el minuto 30; ninguna hora es completa.",
    )


def escenario_huecos() -> Escenario:
    """Serie con huecos deliberados para ejercitar la completitud."""

    return _construir(
        nombre="utc_con_huecos",
        zona="UTC",
        inicio_utc=_utc(2022, 6, 1),
        cantidad=24 * 9,
        paso=timedelta(hours=1),
        precio_inicial=42.75,
        decimales=2,
        semilla=20220601,
        sesion="24/5",
        descripcion="Faltan velas sueltas: ningun dia afectado es completo.",
        omitir=lambda indice: indice in {5, 6, 40, 77, 100, 101, 102, 150},
    )


ESCENARIOS: tuple[Callable[[], Escenario], ...] = (
    escenario_utc_continuo,
    escenario_ny_otono,
    escenario_ny_primavera,
    escenario_tokio_semana_iso,
    escenario_media_hora,
    escenario_huecos,
)


def todos() -> list[Escenario]:
    """Construye todos los escenarios en orden estable."""

    return [construir() for construir in ESCENARIOS]


__all__ = ["COLUMNA_FECHA", "Escenario", "ESCENARIOS", "todos"]
