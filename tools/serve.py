"""Servidor HTTP local para probar ``dist/`` antes de publicar.

Sirve el sitio bajo un prefijo, por defecto el mismo que usara GitHub Pages,
para detectar cualquier ruta absoluta que solo funcione en la raiz:

    python tools/serve.py
    -> http://127.0.0.1:8000/seasonal-market-dashboard/

Con ``--raiz`` se sirve en la raiz, para comprobar que tambien funciona ahi.
No abra ``index.html`` con ``file://``: los modulos ES, ``fetch`` y los Web
Workers exigen un origen HTTP real.
"""

from __future__ import annotations

import argparse
import functools
import http.server
import socketserver
import sys
import webbrowser
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
PREFIJO_PAGES = "/seasonal-market-dashboard/"

TIPOS_EXTRA = {
    ".js": "text/javascript; charset=utf-8",
    ".mjs": "text/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".html": "text/html; charset=utf-8",
}


class Manejador(http.server.SimpleHTTPRequestHandler):
    """Sirve ``dist/`` bajo un prefijo y sin cachear, como haria Pages."""

    prefijo = PREFIJO_PAGES

    def __init__(self, *argumentos, **claves) -> None:
        super().__init__(*argumentos, **claves)

    def translate_path(self, path: str) -> str:  # noqa: N802 (API de la stdlib)
        if self.prefijo != "/" and path.startswith(self.prefijo.rstrip("/")):
            path = path[len(self.prefijo.rstrip("/")):] or "/"
        return super().translate_path(path)

    def guess_type(self, path):  # noqa: N802 (API de la stdlib)
        extension = Path(path).suffix.lower()
        if extension in TIPOS_EXTRA:
            return TIPOS_EXTRA[extension]
        return super().guess_type(path)

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, formato: str, *argumentos: object) -> None:
        codigo = str(argumentos[1]) if len(argumentos) > 1 else ""
        if codigo.startswith(("4", "5")):
            sys.stderr.write(f"  {formato % argumentos}\n")


def main() -> None:
    analizador = argparse.ArgumentParser(description=__doc__)
    analizador.add_argument("--puerto", type=int, default=8000)
    analizador.add_argument("--dist", type=Path, default=RAIZ / "dist")
    analizador.add_argument(
        "--raiz", action="store_true", help="Servir en / en lugar del prefijo de Pages."
    )
    analizador.add_argument("--abrir", action="store_true", help="Abrir el navegador.")
    argumentos = analizador.parse_args()

    if not (argumentos.dist / "index.html").is_file():
        raise SystemExit(
            f"No existe {argumentos.dist}/index.html. Ejecute antes: python tools/build_web.py"
        )

    Manejador.prefijo = "/" if argumentos.raiz else PREFIJO_PAGES
    manejador = functools.partial(Manejador, directory=str(argumentos.dist))
    socketserver.TCPServer.allow_reuse_address = True
    url = f"http://127.0.0.1:{argumentos.puerto}{Manejador.prefijo}"
    with socketserver.TCPServer(("127.0.0.1", argumentos.puerto), manejador) as servidor:
        print(f"Sirviendo {argumentos.dist} en {url}")
        print("Ctrl+C para detener.")
        if argumentos.abrir:
            webbrowser.open(url)
        try:
            servidor.serve_forever()
        except KeyboardInterrupt:
            print("\nServidor detenido.")


if __name__ == "__main__":
    main()
