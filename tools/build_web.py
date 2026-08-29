"""Genera ``dist/``: la aplicacion estatica completa lista para GitHub Pages.

Uso:

    python tools/build_web.py                 # build completo
    python tools/build_web.py --solo-datos    # regenera solo dist/data
    python tools/build_web.py --activos BTCUSDT XAUUSD

Python solo interviene aqui, en tiempo de construccion. El sitio publicado no
ejecuta Python en ningun momento.
"""

from __future__ import annotations

import argparse
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from src import exportador, vistas  # noqa: E402
from src.configuracion import ActivoConfig, cargar_activos  # noqa: E402
from src.datos import leer_y_validar_datos  # noqa: E402


RUTA_CONFIGURACION = RAIZ / "data" / "activos.json"
RUTA_WEB = RAIZ / "web"
RUTA_DIST = RAIZ / "dist"

ETIQUETAS_CATEGORIAS = {
    "crypto": "Criptomonedas",
    "indice_oficial": "Índices oficiales",
    "cfd_indice": "CFD de índices",
    "metal_spot": "Metales spot",
    "energia_cfd": "Energía CFD",
}


def _escribir(ruta: Path, texto: str) -> int:
    """Escribe UTF-8 sin BOM y devuelve el tamaño en bytes."""

    ruta.parent.mkdir(parents=True, exist_ok=True)
    datos = texto.encode("utf-8")
    ruta.write_bytes(datos)
    return len(datos)


def _vaciar(destino: Path) -> None:
    """Borra el contenido de ``dist/`` sin exigir borrar el propio directorio.

    En Windows un servidor local abierto sobre ``dist/`` impide ``rmtree``; los
    archivos si se pueden eliminar, y el build recrea los directorios.
    """

    for ruta in sorted(destino.rglob("*"), key=lambda item: len(item.parts), reverse=True):
        try:
            if ruta.is_file() or ruta.is_symlink():
                ruta.unlink()
            else:
                ruta.rmdir()
        except OSError:
            pass


# Nada de esto debe llegar al sitio publicado.
_EXCLUIDOS = ("tests", "__tests__", "node_modules", "__pycache__")


def _copiar_shell(destino: Path) -> None:
    """Copia el HTML, el CSS y los modulos JavaScript a ``dist/``.

    Las pruebas se quedan fuera: solo se publica lo que sirve al navegador.
    """

    for origen in sorted(RUTA_WEB.rglob("*")):
        relativo = origen.relative_to(RUTA_WEB)
        if origen.is_dir() or any(parte in _EXCLUIDOS for parte in relativo.parts):
            continue
        final = destino / relativo
        final.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(origen, final)
    (destino / ".nojekyll").write_bytes(b"")


def _procesar_activo(
    activo: ActivoConfig, destino_datos: Path, verboso: bool
) -> dict[str, object]:
    """Valida un CSV y emite ``report.json`` y las series por año."""

    comienzo = time.perf_counter()
    resultado = leer_y_validar_datos(activo)
    datos, columna_fecha = vistas.preparar_datos(resultado.datos_validos, activo)

    informe = exportador.construir_informe(resultado, activo, datos, columna_fecha)
    texto_informe = exportador.volcar_json(informe)
    nombre_informe = f"report.{exportador.hash_contenido(texto_informe)}.json"
    bytes_informe = _escribir(destino_datos / activo.simbolo / nombre_informe, texto_informe)

    fragmentos = exportador.fragmentar_por_año(datos, columna_fecha)
    series: dict[str, str] = {}
    bytes_series = 0
    for año, marco in fragmentos:
        carga = exportador.construir_serie(marco, activo.simbolo, año, columna_fecha)
        texto = exportador.volcar_json(carga)
        nombre = f"series-{año}.{exportador.hash_contenido(texto)}.json"
        bytes_series += _escribir(destino_datos / activo.simbolo / nombre, texto)
        series[str(año)] = f"{activo.simbolo}/{nombre}"

    fechas = pd.to_datetime(datos[columna_fecha])
    zona = exportador.tabla_transiciones(
        activo.zona_horaria, fechas.min().to_pydatetime(), fechas.max().to_pydatetime()
    )
    entrada = exportador.entrada_manifiesto(
        activo, informe, [año for año, _ in fragmentos], zona
    )
    entrada["report"] = f"{activo.simbolo}/{nombre_informe}"
    entrada["series"] = series
    entrada["bytes"] = {"report": bytes_informe, "series": bytes_series}

    if verboso:
        transcurrido = time.perf_counter() - comienzo
        print(
            f"  {activo.simbolo:<16} {len(datos):>7,} velas  "
            f"{len(fragmentos):>3} años  "
            f"{(bytes_informe + bytes_series) / 1_048_576:>6.2f} MB  "
            f"{transcurrido:>5.1f}s"
        )
    return entrada


def construir(
    simbolos: list[str] | None = None,
    *,
    solo_datos: bool = False,
    destino: Path = RUTA_DIST,
    verboso: bool = True,
) -> dict[str, object]:
    """Genera el sitio completo y devuelve el manifiesto resultante."""

    comienzo = time.perf_counter()
    activos = cargar_activos(RUTA_CONFIGURACION, tolerante=True)
    if simbolos:
        desconocidos = [clave for clave in simbolos if clave not in activos]
        if desconocidos:
            raise SystemExit(f"Activos desconocidos: {', '.join(desconocidos)}")
        activos = {clave: activos[clave] for clave in simbolos}
    if not activos:
        raise SystemExit("No hay activos validos que exportar.")

    if not solo_datos and destino.exists():
        _vaciar(destino)
    destino.mkdir(parents=True, exist_ok=True)
    if not solo_datos:
        if verboso:
            print("Copiando la aplicacion estatica...")
        _copiar_shell(destino)

    destino_datos = destino / "data"
    if verboso:
        print(f"Procesando {len(activos)} activo(s):")
    entradas = [
        _procesar_activo(activo, destino_datos, verboso) for activo in activos.values()
    ]

    manifiesto = {
        "schemaVersion": exportador.SCHEMA_VERSION,
        "processingVersion": exportador.PROCESSING_VERSION,
        "generatedAt": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "basePath": "./",
        "sourceRowCount": sum(int(entrada["filasValidas"]) for entrada in entradas),
        "categories": ETIQUETAS_CATEGORIAS,
        "assets": entradas,
    }
    manifiesto["contentHash"] = exportador.hash_contenido(
        exportador.volcar_json(manifiesto), 16
    )
    _escribir(destino_datos / "manifest.json", exportador.volcar_json(manifiesto))

    if verboso:
        total = sum(
            archivo.stat().st_size for archivo in destino.rglob("*") if archivo.is_file()
        )
        try:
            etiqueta = destino.relative_to(RAIZ).as_posix()
        except ValueError:
            etiqueta = destino.as_posix()
        print(
            f"\nListo en {time.perf_counter() - comienzo:.1f}s · "
            f"{total / 1_048_576:.1f} MB en {etiqueta}/"
        )
    return manifiesto


def main() -> None:
    analizador = argparse.ArgumentParser(description=__doc__)
    analizador.add_argument("--activos", nargs="*", help="Subconjunto de simbolos.")
    analizador.add_argument(
        "--solo-datos",
        action="store_true",
        help="Regenera dist/data sin volver a copiar la aplicacion.",
    )
    analizador.add_argument(
        "--destino", type=Path, default=RUTA_DIST, help="Directorio de salida."
    )
    analizador.add_argument("--silencioso", action="store_true")
    argumentos = analizador.parse_args()
    construir(
        argumentos.activos,
        solo_datos=argumentos.solo_datos,
        destino=argumentos.destino,
        verboso=not argumentos.silencioso,
    )


if __name__ == "__main__":
    main()
