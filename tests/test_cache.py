"""Pruebas de firmas y persistencia verificable de la cache."""

from importlib.util import find_spec
from pathlib import Path

import pandas as pd
import pytest

from src.cache import cargar_cache, generar_firma_cache, guardar_cache


def _exigir_motor_parquet() -> None:
    """Omite la prueba si pandas no dispone de un motor Parquet."""

    if find_spec("pyarrow") is None and find_spec("fastparquet") is None:
        pytest.skip("No hay motor Parquet instalado (pyarrow o fastparquet).")


@pytest.mark.parametrize("archivo_modificado", ["csv", "json"])
def test_firma_cambia_al_modificar_una_entrada(
    tmp_path: Path, archivo_modificado: str
) -> None:
    """Incluye en la firma tanto el CSV como activos.json."""

    ruta_csv = tmp_path / "datos.csv"
    ruta_json = tmp_path / "activos.json"
    ruta_csv.write_text("precio\n100\n", encoding="utf-8")
    ruta_json.write_text('{"version": 1}', encoding="utf-8")
    firma_inicial = generar_firma_cache(ruta_csv, ruta_json)

    if archivo_modificado == "csv":
        ruta_csv.write_text("precio\n101\n", encoding="utf-8")
    else:
        ruta_json.write_text('{"version": 2}', encoding="utf-8")
    firma_nueva = generar_firma_cache(ruta_csv, ruta_json)

    assert len(firma_inicial) == 64
    assert firma_nueva != firma_inicial


def test_roundtrip_parquet(tmp_path: Path) -> None:
    """Recupera sin cambios un DataFrame pequeno guardado en Parquet."""

    _exigir_motor_parquet()
    datos = pd.DataFrame(
        {"simbolo": ["ABC", "XYZ"], "close": [101.5, 202.25], "volumen": [3, 4]}
    )
    firma = "a" * 64

    ruta_parquet = guardar_cache(
        datos, firma, tmp_path, metadatos={"origen": "prueba"}
    )
    recuperados = cargar_cache(firma, tmp_path)

    assert ruta_parquet.is_file()
    assert recuperados is not None
    pd.testing.assert_frame_equal(recuperados, datos)


@pytest.mark.parametrize("archivo_corrupto", ["parquet", "indice"])
def test_corrupcion_invalida_la_entrada_completa(
    tmp_path: Path, archivo_corrupto: str
) -> None:
    """Descarta Parquet o indice corruptos y elimina la pareja incompleta."""

    _exigir_motor_parquet()
    firma = "b" * 64
    ruta_parquet = guardar_cache(pd.DataFrame({"valor": [1, 2]}), firma, tmp_path)
    ruta_indice = tmp_path / f"{firma}.json"
    if archivo_corrupto == "parquet":
        ruta_parquet.write_bytes(b"parquet corrupto")
    else:
        ruta_indice.write_text("{indice corrupto", encoding="utf-8")

    resultado = cargar_cache(firma, tmp_path)

    assert resultado is None
    assert not ruta_parquet.exists()
    assert not ruta_indice.exists()
