"""Valida ``dist/`` antes de publicarlo en GitHub Pages.

Comprueba los presupuestos de rendimiento, la ausencia de rutas absolutas y la
integridad de todos los enlaces declarados en ``manifest.json``.

    python tools/check_dist.py [--dist dist]

Devuelve codigo 1 si alguna comprobacion falla, para poder usarlo en CI.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]

# Presupuestos declarados en docs/CONTRATO_JSON.md.
MAX_SITIO_MB = 200.0
MAX_INICIAL_MB = 6.0
MAX_FRAGMENTO_MB = 8.0

ESQUEMA = 2

VISTAS_ESPERADAS = (
    "resumen", "periodo", "mensual", "semanal", "diaSemana",
    "diaria", "horaria", "matriz", "extremos",
)

# GitHub Pages ignora los directorios que empiezan por guion bajo sin .nojekyll.
ARCHIVOS_OBLIGATORIOS = ("index.html", ".nojekyll", "data/manifest.json")

# Rutas absolutas de sistema que nunca deben publicarse.
PATRONES_PROHIBIDOS = (
    (re.compile(r"[A-Za-z]:[\\/]Users[\\/]"), "ruta absoluta de Windows"),
    (re.compile(r"/home/[a-z0-9_-]+/"), "ruta absoluta de Linux"),
    (re.compile(r"/Users/[A-Za-z0-9_-]+/"), "ruta absoluta de macOS"),
)

# Referencias absolutas en HTML/CSS/JS que romperian bajo /seasonal-market-dashboard/.
REFERENCIA_ABSOLUTA = re.compile(
    r"""(?:src|href)\s*=\s*["']/(?!/)|url\(\s*["']?/(?!/)|fetch\(\s*["']/(?!/)""",
)

EXTENSIONES_TEXTO = {".html", ".css", ".js", ".mjs", ".json", ".txt", ".svg"}


class Informe:
    """Acumula fallos y avisos con un formato uniforme."""

    def __init__(self) -> None:
        self.fallos: list[str] = []
        self.avisos: list[str] = []
        self.notas: list[str] = []

    def fallo(self, mensaje: str) -> None:
        self.fallos.append(mensaje)

    def aviso(self, mensaje: str) -> None:
        self.avisos.append(mensaje)

    def nota(self, mensaje: str) -> None:
        self.notas.append(mensaje)


def _mb(bytes_: int) -> float:
    return bytes_ / 1_048_576


def comprobar_estructura(dist: Path, informe: Informe) -> None:
    for relativo in ARCHIVOS_OBLIGATORIOS:
        if not (dist / relativo).is_file():
            informe.fallo(f"Falta el archivo obligatorio: {relativo}")
    # Las pruebas y las dependencias de desarrollo no se publican.
    for prohibido in ("tests", "node_modules", "__pycache__"):
        if (dist / prohibido).exists():
            informe.fallo(f"El artefacto no debe contener {prohibido}/.")
    sobrantes = sorted(
        ruta.relative_to(dist).as_posix()
        for ruta in dist.rglob("*.test.js")
        if ruta.is_file()
    )
    if sobrantes:
        informe.fallo(f"Archivos de prueba publicados: {', '.join(sobrantes)}")


def comprobar_presupuestos(dist: Path, informe: Informe) -> dict[str, float]:
    archivos = [ruta for ruta in dist.rglob("*") if ruta.is_file()]
    total = sum(ruta.stat().st_size for ruta in archivos)
    if _mb(total) > MAX_SITIO_MB:
        informe.fallo(f"El sitio pesa {_mb(total):.1f} MB (máximo {MAX_SITIO_MB:.0f} MB).")

    inicial = 0
    for relativo in ("index.html", "data/manifest.json"):
        ruta = dist / relativo
        if ruta.is_file():
            inicial += ruta.stat().st_size
    for ruta in (dist / "assets").rglob("*"):
        if ruta.is_file():
            inicial += ruta.stat().st_size
    if _mb(inicial) > MAX_INICIAL_MB:
        informe.fallo(f"La carga inicial pesa {_mb(inicial):.2f} MB (máximo {MAX_INICIAL_MB} MB).")

    mayor = max(archivos, key=lambda ruta: ruta.stat().st_size, default=None)
    if mayor is not None and _mb(mayor.stat().st_size) > MAX_FRAGMENTO_MB:
        informe.fallo(
            f"El fragmento {mayor.relative_to(dist).as_posix()} pesa "
            f"{_mb(mayor.stat().st_size):.2f} MB (máximo {MAX_FRAGMENTO_MB} MB)."
        )

    informe.nota(f"{len(archivos)} archivos · sitio {_mb(total):.1f} MB · inicial {_mb(inicial):.2f} MB")
    if mayor is not None:
        informe.nota(
            f"mayor archivo: {mayor.relative_to(dist).as_posix()} "
            f"({_mb(mayor.stat().st_size):.2f} MB)"
        )
    return {"total_mb": _mb(total), "inicial_mb": _mb(inicial)}


def comprobar_rutas(dist: Path, informe: Informe) -> None:
    for ruta in dist.rglob("*"):
        if not ruta.is_file() or ruta.suffix.lower() not in EXTENSIONES_TEXTO:
            continue
        if ruta.name.startswith("plotly-"):
            continue  # Biblioteca de terceros, no la editamos.
        try:
            texto = ruta.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        relativo = ruta.relative_to(dist).as_posix()
        for patron, descripcion in PATRONES_PROHIBIDOS:
            if patron.search(texto):
                informe.fallo(f"{relativo}: contiene una {descripcion}.")
        if REFERENCIA_ABSOLUTA.search(texto):
            informe.fallo(
                f"{relativo}: referencia que empieza por '/' y se romperá "
                "bajo el subdirectorio de GitHub Pages."
            )


def comprobar_manifiesto(dist: Path, informe: Informe) -> None:
    ruta = dist / "data" / "manifest.json"
    if not ruta.is_file():
        return
    manifiesto = json.loads(ruta.read_text(encoding="utf-8"))
    if manifiesto.get("schemaVersion") != ESQUEMA:
        informe.fallo(f"schemaVersion inesperada: {manifiesto.get('schemaVersion')!r}.")
    for campo in ("generatedAt", "processingVersion", "contentHash", "assets"):
        if not manifiesto.get(campo):
            informe.fallo(f"El manifiesto no declara {campo!r}.")

    base = dist / "data"
    referenciados = {ruta}
    for activo in manifiesto.get("assets", []):
        simbolo = activo.get("symbol", "<sin simbolo>")
        enlace = activo.get("report", "")
        if not enlace:
            informe.fallo(f"{simbolo}: sin informe en el manifiesto.")
            continue
        if enlace.startswith("/") or ".." in enlace:
            informe.fallo(f"{simbolo}: el enlace {enlace!r} no es relativo y seguro.")
        destino = base / enlace
        if not destino.is_file():
            informe.fallo(f"{simbolo}: el manifiesto apunta a {enlace!r}, que no existe.")
        referenciados.add(destino)
        # Cada informe debe traer las nueve vistas ya calculadas.
        if destino.is_file():
            vistas = json.loads(destino.read_text(encoding="utf-8")).get("vistas", {})
            faltan = [clave for clave in VISTAS_ESPERADAS if clave not in vistas]
            if faltan:
                informe.fallo(f"{simbolo}: faltan vistas en el informe: {', '.join(faltan)}.")

    huerfanos = [
        item.relative_to(dist).as_posix()
        for item in base.rglob("*.json")
        if item.is_file() and item not in referenciados
    ]
    if huerfanos:
        informe.aviso(
            f"{len(huerfanos)} archivo(s) de datos no referenciados: "
            + ", ".join(sorted(huerfanos)[:5])
        )


def comprobar_json_estricto(dist: Path, informe: Informe) -> None:
    for ruta in (dist / "data").rglob("*.json"):
        texto = ruta.read_text(encoding="utf-8")
        if re.search(r"\b(NaN|-?Infinity)\b", texto):
            informe.fallo(f"{ruta.relative_to(dist).as_posix()}: contiene NaN o Infinity.")
        try:
            json.loads(texto)
        except json.JSONDecodeError as excepcion:
            informe.fallo(f"{ruta.relative_to(dist).as_posix()}: JSON inválido ({excepcion}).")


def main() -> int:
    analizador = argparse.ArgumentParser(description=__doc__)
    analizador.add_argument("--dist", type=Path, default=RAIZ / "dist")
    argumentos = analizador.parse_args()
    dist = argumentos.dist

    if not dist.is_dir():
        print(f"No existe {dist}. Ejecute antes: python tools/build_web.py", file=sys.stderr)
        return 1

    informe = Informe()
    comprobar_estructura(dist, informe)
    comprobar_presupuestos(dist, informe)
    comprobar_rutas(dist, informe)
    comprobar_manifiesto(dist, informe)
    comprobar_json_estricto(dist, informe)

    for nota in informe.notas:
        print(f"  · {nota}")
    for aviso in informe.avisos:
        print(f"  ! {aviso}")
    for fallo in informe.fallos:
        print(f"  x {fallo}", file=sys.stderr)

    if informe.fallos:
        print(f"\n{len(informe.fallos)} comprobación(es) fallida(s).", file=sys.stderr)
        return 1
    print("\nTodas las comprobaciones del artefacto han pasado.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
