"""Carga y validacion de la configuracion dinamica de activos."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


CAMPOS_OBLIGATORIOS = (
    "nombre",
    "categoria",
    "mercado",
    "sesion",
    "zona_horaria",
    "temporalidad",
    "archivo",
    "tipo_timestamp",
    "formula_retorno",
)


class ErrorConfiguracion(ValueError):
    """Indica que ``activos.json`` no se puede usar con seguridad."""


@dataclass(frozen=True, slots=True)
class ActivoConfig:
    """Metadata validada de un activo.

    ``archivo`` siempre es una ruta absoluta resuelta dentro del directorio de
    datos. ``zona`` evita volver a construir ``ZoneInfo`` en cada conversion.
    """

    simbolo: str
    nombre: str
    categoria: str
    mercado: str
    sesion: str
    zona_horaria: str
    temporalidad: str
    archivo: Path
    tipo_timestamp: str
    formula_retorno: str
    zona: ZoneInfo = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        """Normaliza la ruta y construye la zona horaria derivada."""

        object.__setattr__(self, "archivo", Path(self.archivo))
        try:
            zona = ZoneInfo(self.zona_horaria)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ErrorConfiguracion(
                f"Activo {self.simbolo!r}: zona horaria IANA desconocida "
                f"{self.zona_horaria!r}."
            ) from exc
        object.__setattr__(self, "zona", zona)


def _texto_obligatorio(datos: dict[str, Any], campo: str, simbolo: str) -> str:
    valor = datos.get(campo)
    if not isinstance(valor, str) or not valor.strip():
        raise ErrorConfiguracion(
            f"Activo {simbolo!r}: el campo {campo!r} debe ser texto no vacio."
        )
    return valor.strip()


def cargar_activos(
    ruta_configuracion: str | Path | None = None,
    directorio_datos: str | Path | None = None,
    *,
    tolerante: bool = False,
    errores: dict[str, str] | None = None,
) -> dict[str, ActivoConfig]:
    """Lee ``activos.json`` y devuelve todos sus activos validados.

    No existe una lista fija de simbolos. Cada clave valida del JSON se carga
    dinamicamente. Los archivos relativos se resuelven respecto al directorio
    indicado o, por defecto, respecto al directorio de ``activos.json``.

    Raises:
        ErrorConfiguracion: si el archivo, el JSON, un campo, una zona horaria
            o la ruta CSV declarada no son validos.
    """

    ruta_json = (
        Path(ruta_configuracion).expanduser().resolve()
        if ruta_configuracion is not None
        else Path(__file__).resolve().parents[1] / "data" / "activos.json"
    )
    if not ruta_json.is_file():
        raise ErrorConfiguracion(
            f"No existe el archivo de configuracion: {ruta_json}."
        )

    try:
        contenido = json.loads(ruta_json.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        raise ErrorConfiguracion(
            f"JSON invalido en {ruta_json}, linea {exc.lineno}, columna {exc.colno}: "
            f"{exc.msg}."
        ) from exc
    except OSError as exc:
        raise ErrorConfiguracion(f"No se pudo leer {ruta_json}: {exc}.") from exc

    if not isinstance(contenido, dict) or not contenido:
        raise ErrorConfiguracion(
            f"{ruta_json} debe contener un objeto JSON no vacio de activos."
        )

    base_datos = (
        Path(directorio_datos).expanduser().resolve()
        if directorio_datos is not None
        else ruta_json.parent
    )
    if not base_datos.is_dir():
        raise ErrorConfiguracion(f"No existe el directorio de datos: {base_datos}.")

    activos: dict[str, ActivoConfig] = {}
    for clave, datos in contenido.items():
        simbolo_error = str(clave).strip() or "<simbolo vacio>"
        try:
            if not isinstance(clave, str) or not clave.strip():
                raise ErrorConfiguracion("Cada activo debe tener un simbolo no vacio.")
            simbolo = clave.strip()
            if simbolo in activos:
                raise ErrorConfiguracion(
                    f"Simbolo duplicado tras normalizar: {simbolo!r}."
                )
            if not isinstance(datos, dict):
                raise ErrorConfiguracion(
                    f"Activo {simbolo!r}: la configuracion debe ser un objeto JSON."
                )

            faltantes = [campo for campo in CAMPOS_OBLIGATORIOS if campo not in datos]
            if faltantes:
                raise ErrorConfiguracion(
                    f"Activo {simbolo!r}: faltan campos obligatorios: "
                    f"{', '.join(faltantes)}."
                )

            valores = {
                campo: _texto_obligatorio(datos, campo, simbolo)
                for campo in CAMPOS_OBLIGATORIOS
            }
            if valores["tipo_timestamp"] not in {"instante_utc", "fecha_sesion"}:
                raise ErrorConfiguracion(
                    f"Activo {simbolo!r}: tipo_timestamp debe ser 'instante_utc' "
                    "o 'fecha_sesion'."
                )

            ruta_declarada = Path(valores["archivo"])
            if ruta_declarada.is_absolute():
                ruta_csv = ruta_declarada.expanduser().resolve()
            else:
                ruta_csv = (base_datos / ruta_declarada).resolve()
                try:
                    ruta_csv.relative_to(base_datos)
                except ValueError as exc:
                    raise ErrorConfiguracion(
                        f"Activo {simbolo!r}: el archivo sale del directorio de datos: "
                        f"{valores['archivo']!r}."
                    ) from exc
            if not ruta_csv.is_file():
                raise ErrorConfiguracion(
                    f"Activo {simbolo!r}: no existe el CSV declarado: {ruta_csv}."
                )

            activos[simbolo] = ActivoConfig(
                simbolo=simbolo,
                nombre=valores["nombre"],
                categoria=valores["categoria"],
                mercado=valores["mercado"],
                sesion=valores["sesion"],
                zona_horaria=valores["zona_horaria"],
                temporalidad=valores["temporalidad"],
                archivo=ruta_csv,
                tipo_timestamp=valores["tipo_timestamp"],
                formula_retorno=valores["formula_retorno"],
            )
        except ErrorConfiguracion as exc:
            if not tolerante:
                raise
            if errores is not None:
                errores[simbolo_error] = str(exc)

    return activos
