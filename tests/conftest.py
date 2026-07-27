"""Fixtures pequenas y deterministas para las pruebas unitarias."""

from collections.abc import Callable
from pathlib import Path

import pandas as pd
import pytest

from src.configuracion import ActivoConfig
from src.datos import COLUMNAS_OBLIGATORIAS


@pytest.fixture
def crear_csv(tmp_path: Path) -> Callable[..., Path]:
    """Devuelve una fabrica de CSV con todas las columnas requeridas."""

    def fabrica(
        filas: list[dict[str, object]] | None = None,
        nombre: str = "precios.csv",
    ) -> Path:
        base: dict[str, object] = {
            "timestamp_utc": "2024-01-01 00:00:00",
            "open": 100,
            "high": 110,
            "low": 90,
            "close": 105,
            "volume": 1000,
        }
        registros = []
        for cambios in filas or [{}]:
            registro = base.copy()
            registro.update(cambios)
            registros.append(registro)
        ruta = tmp_path / nombre
        pd.DataFrame(registros, columns=COLUMNAS_OBLIGATORIAS).to_csv(
            ruta, index=False
        )
        return ruta

    return fabrica


@pytest.fixture
def crear_activo(tmp_path: Path) -> Callable[..., ActivoConfig]:
    """Devuelve una fabrica de configuraciones validas y ajustables."""

    def fabrica(
        *,
        archivo: Path | None = None,
        sesion: str = "24/7",
        zona_horaria: str = "UTC",
        temporalidad: str = "1h",
        tipo_timestamp: str = "instante_utc",
    ) -> ActivoConfig:
        return ActivoConfig(
            simbolo="PRUEBA",
            nombre="Activo de prueba",
            categoria="prueba",
            mercado="Pruebas",
            sesion=sesion,
            zona_horaria=zona_horaria,
            temporalidad=temporalidad,
            archivo=archivo or tmp_path / "precios.csv",
            tipo_timestamp=tipo_timestamp,
            formula_retorno="(close / open - 1) * 100",
        )

    return fabrica
