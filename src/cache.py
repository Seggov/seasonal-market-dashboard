"""Cache Parquet verificable para datos procesados."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any
from uuid import uuid4

import pandas as pd


VERSION_CACHE = "3"


class ErrorCache(RuntimeError):
    """Indica un fallo al guardar o recuperar la cache."""


def _hash_archivo(ruta: Path) -> str:
    digest = hashlib.sha256()
    try:
        with ruta.open("rb") as archivo:
            for bloque in iter(lambda: archivo.read(1024 * 1024), b""):
                digest.update(bloque)
    except OSError as exc:
        raise ErrorCache(f"No se pudo calcular el hash de {ruta}: {exc}.") from exc
    return digest.hexdigest()


def _identidad_archivo(ruta: str | Path) -> dict[str, Any]:
    archivo = Path(ruta).expanduser().resolve()
    if not archivo.is_file():
        raise ErrorCache(f"No existe el archivo para firmar: {archivo}.")
    try:
        estado = archivo.stat()
    except OSError as exc:
        raise ErrorCache(f"No se pudo inspeccionar {archivo}: {exc}.") from exc
    return {
        "ruta": str(archivo),
        "tamano": estado.st_size,
        "mtime_ns": estado.st_mtime_ns,
        "sha256": _hash_archivo(archivo),
    }


def generar_firma_cache(
    ruta_datos: str | Path,
    ruta_activos: str | Path,
    version: str = VERSION_CACHE,
) -> str:
    """Firma CSV y ``activos.json`` por ruta, tamano, mtime_ns y contenido."""

    identidad = {
        "version": version,
        "datos": _identidad_archivo(ruta_datos),
        "activos": _identidad_archivo(ruta_activos),
    }
    serializado = json.dumps(
        identidad, ensure_ascii=True, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(serializado).hexdigest()


def _rutas_cache(firma: str, directorio_cache: str | Path) -> tuple[Path, Path]:
    if not firma or any(caracter not in "0123456789abcdef" for caracter in firma.lower()):
        raise ErrorCache("La firma de cache no es hexadecimal valida.")
    directorio = Path(directorio_cache).expanduser().resolve()
    return directorio / f"{firma}.parquet", directorio / f"{firma}.json"


def guardar_cache(
    datos_procesados: pd.DataFrame,
    firma: str,
    directorio_cache: str | Path = ".cache",
    metadatos: dict[str, Any] | None = None,
) -> Path:
    """Guarda el Parquet y su indice JSON de forma atomica.

    Returns:
        Ruta del archivo Parquet definitivo.
    """

    ruta_parquet, ruta_indice = _rutas_cache(firma, directorio_cache)
    try:
        ruta_parquet.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise ErrorCache(f"No se pudo crear {ruta_parquet.parent}: {exc}.") from exc

    sufijo = uuid4().hex
    parquet_temporal = ruta_parquet.with_name(f".{ruta_parquet.name}.{sufijo}.tmp")
    indice_temporal = ruta_indice.with_name(f".{ruta_indice.name}.{sufijo}.tmp")
    try:
        datos_procesados.to_parquet(parquet_temporal, index=False)
        indice = {
            "version": VERSION_CACHE,
            "firma": firma,
            "parquet": ruta_parquet.name,
            "sha256_parquet": _hash_archivo(parquet_temporal),
            "filas": len(datos_procesados),
            "columnas": list(datos_procesados.columns),
            "metadatos": metadatos or {},
        }
        indice_temporal.write_text(
            json.dumps(indice, ensure_ascii=False, sort_keys=True, indent=2, default=str),
            encoding="utf-8",
        )
        parquet_temporal.replace(ruta_parquet)
        indice_temporal.replace(ruta_indice)
    except (OSError, ValueError, TypeError, ImportError) as exc:
        parquet_temporal.unlink(missing_ok=True)
        indice_temporal.unlink(missing_ok=True)
        raise ErrorCache(f"No se pudo guardar la cache {firma}: {exc}.") from exc
    return ruta_parquet


def invalidar_cache(
    firma: str | None = None, directorio_cache: str | Path = ".cache"
) -> int:
    """Elimina una entrada o todas las entradas administradas de la cache."""

    directorio = Path(directorio_cache).expanduser().resolve()
    if not directorio.exists():
        return 0
    if firma is None:
        candidatos = [*directorio.glob("*.parquet"), *directorio.glob("*.json")]
    else:
        candidatos = list(_rutas_cache(firma, directorio))
    eliminados = 0
    for ruta in candidatos:
        try:
            if ruta.is_file():
                ruta.unlink()
                eliminados += 1
        except OSError as exc:
            raise ErrorCache(f"No se pudo invalidar {ruta}: {exc}.") from exc
    return eliminados


def cargar_cache(
    firma: str, directorio_cache: str | Path = ".cache"
) -> pd.DataFrame | None:
    """Carga una entrada integra; invalida y devuelve ``None`` si esta corrupta."""

    ruta_parquet, ruta_indice = _rutas_cache(firma, directorio_cache)
    if not ruta_parquet.is_file() or not ruta_indice.is_file():
        if ruta_parquet.exists() or ruta_indice.exists():
            invalidar_cache(firma, directorio_cache)
        return None
    try:
        indice = json.loads(ruta_indice.read_text(encoding="utf-8"))
        indice_valido = (
            isinstance(indice, dict)
            and indice.get("version") == VERSION_CACHE
            and indice.get("firma") == firma
            and indice.get("parquet") == ruta_parquet.name
            and indice.get("sha256_parquet") == _hash_archivo(ruta_parquet)
        )
        if not indice_valido:
            raise ValueError("indice o hash inconsistente")
        datos = pd.read_parquet(ruta_parquet)
        if len(datos) != indice.get("filas") or list(datos.columns) != indice.get(
            "columnas"
        ):
            raise ValueError("estructura Parquet inconsistente con el indice")
        return datos
    except (OSError, ValueError, TypeError, json.JSONDecodeError, ImportError):
        invalidar_cache(firma, directorio_cache)
        return None


def cargar_o_generar_cache(
    ruta_datos: str | Path,
    ruta_activos: str | Path,
    generador: Callable[[], pd.DataFrame],
    directorio_cache: str | Path = ".cache",
    metadatos: dict[str, Any] | None = None,
    version: str = VERSION_CACHE,
) -> pd.DataFrame:
    """Carga datos vigentes o los regenera automaticamente ante cambio o dano."""

    firma = generar_firma_cache(ruta_datos, ruta_activos, version=version)
    datos = cargar_cache(firma, directorio_cache)
    if datos is not None:
        return datos
    generados = generador()
    if not isinstance(generados, pd.DataFrame):
        raise ErrorCache("El generador de cache debe devolver un pandas.DataFrame.")
    guardar_cache(generados, firma, directorio_cache, metadatos)
    return generados
