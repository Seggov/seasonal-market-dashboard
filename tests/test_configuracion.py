"""Pruebas de carga y validacion de activos.json."""

import json
from pathlib import Path

import pytest

from src.configuracion import ErrorConfiguracion, cargar_activos


def _datos_activo(archivo: str) -> dict[str, str]:
    """Construye la configuracion minima de un activo valido."""

    return {
        "nombre": "Activo pequeno",
        "categoria": "prueba",
        "mercado": "Pruebas",
        "sesion": "24/7",
        "zona_horaria": "America/New_York",
        "temporalidad": "1h",
        "archivo": archivo,
        "tipo_timestamp": "instante_utc",
        "formula_retorno": "(close / open - 1) * 100",
    }


def test_carga_activos_json_valido(tmp_path: Path) -> None:
    """Carga un activos.json valido y resuelve su CSV relativo."""

    ruta_csv = tmp_path / "activo.csv"
    ruta_csv.write_text("contenido minimo", encoding="utf-8")
    ruta_json = tmp_path / "activos.json"
    ruta_json.write_text(
        json.dumps({"ABC": _datos_activo(ruta_csv.name)}), encoding="utf-8"
    )

    activos = cargar_activos(ruta_json)

    assert list(activos) == ["ABC"]
    assert activos["ABC"].archivo == ruta_csv.resolve()
    assert activos["ABC"].zona.key == "America/New_York"


def test_rechaza_archivo_de_configuracion_inexistente(tmp_path: Path) -> None:
    """Informa cuando activos.json no existe."""

    with pytest.raises(ErrorConfiguracion, match="No existe el archivo"):
        cargar_activos(tmp_path / "inexistente.json")


@pytest.mark.parametrize("contenido", ["{", "[]"])
def test_rechaza_configuracion_invalida(tmp_path: Path, contenido: str) -> None:
    """Rechaza tanto JSON mal formado como una raiz de tipo incorrecto."""

    ruta_json = tmp_path / "activos.json"
    ruta_json.write_text(contenido, encoding="utf-8")

    with pytest.raises(ErrorConfiguracion):
        cargar_activos(ruta_json)


def test_rechaza_csv_declarado_inexistente(tmp_path: Path) -> None:
    """Rechaza un activo cuyo archivo de datos no existe."""

    ruta_json = tmp_path / "activos.json"
    ruta_json.write_text(
        json.dumps({"ABC": _datos_activo("ausente.csv")}), encoding="utf-8"
    )

    with pytest.raises(ErrorConfiguracion, match="no existe el CSV declarado"):
        cargar_activos(ruta_json)


def test_modo_tolerante_conserva_activos_validos(tmp_path: Path) -> None:
    """Un activo roto no bloquea el catalogo cuando la interfaz usa tolerancia."""

    ruta_csv = tmp_path / "valido.csv"
    ruta_csv.write_text("contenido minimo", encoding="utf-8")
    ruta_json = tmp_path / "activos.json"
    ruta_json.write_text(
        json.dumps(
            {
                "VALIDO": _datos_activo(ruta_csv.name),
                "ROTO": _datos_activo("ausente.csv"),
            }
        ),
        encoding="utf-8",
    )
    errores: dict[str, str] = {}

    activos = cargar_activos(ruta_json, tolerante=True, errores=errores)

    assert list(activos) == ["VALIDO"]
    assert "ROTO" in errores
    assert "no existe el CSV declarado" in errores["ROTO"]
