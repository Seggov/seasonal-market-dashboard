"""Genera las fixturas doradas de paridad para filtros NO predeterminados.

``report.json`` solo lleva las vistas por defecto. Este script calcula, con el
mismo nucleo Python, una bateria de configuraciones de sesion, IQR, matriz y
eventos extremos, y las guarda en ``tests/fixtures/paridad-filtros.json``.

Las pruebas de Node recalculan cada configuracion en JavaScript y comparan.

    python tools/generar_paridad_filtros.py

Se guarda un digesto numerico de cada carga -- conteos, suma, minimo, maximo y
una suma PONDERADA POR POSICION -- en lugar de la carga completa. El digesto
detecta tanto un valor distinto como una reordenacion, y mantiene la fixtura en
unas decenas de kilobytes. La paridad de carga completa ya la cubre
`web/tests/paridad.test.js` contra `defaultViews` de cada report.json.
"""

from __future__ import annotations

import argparse
import functools
import json
import math
import sys
from pathlib import Path
from typing import Any

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from src import exportador, vistas  # noqa: E402
from src.configuracion import cargar_activos  # noqa: E402
from src.datos import leer_y_validar_datos  # noqa: E402

DESTINO = RAIZ / "tests" / "fixtures" / "paridad-filtros.json"

CONFIGURACIONES: list[dict[str, Any]] = [
    {
        "nombre": "sesion-observada-manana",
        "sesion": {"modo": "Observada", "dias": [0, 1, 2, 3, 4], "horas": [9, 10, 11, 12]},
    },
    {
        "nombre": "sesion-observada-lunes-martes",
        "sesion": {"modo": "Observada", "dias": [0, 1], "horas": None},
    },
    {
        "nombre": "sesion-personalizada-diurna",
        "sesion": {"modo": "Personalizada", "dias": None, "horaInicio": "09:00", "horaFin": "17:00"},
    },
    {
        "nombre": "sesion-personalizada-nocturna",
        "sesion": {"modo": "Personalizada", "dias": None, "horaInicio": "22:00", "horaFin": "03:00"},
        "comentario": "Sesion que cruza medianoche (ambiguedad A-9).",
    },
    {
        "nombre": "sesion-personalizada-24h",
        "sesion": {"modo": "Personalizada", "dias": None, "horaInicio": "00:00", "horaFin": "00:00"},
        "comentario": "inicio == fin significa 24 horas (ambiguedad A-11).",
    },
    {
        "nombre": "iqr-semanal",
        "sesion": {"modo": "Declarada"},
        "semanal": {"quitarAtipicos": True, "factor": 1.5},
    },
    {
        "nombre": "matriz-mediana-estricta",
        "sesion": {"modo": "Declarada"},
        "matriz": {"metrica": "median", "quitarAtipicos": True, "factor": 1.0, "minimoObservaciones": 20},
    },
    {
        "nombre": "matriz-positivos",
        "sesion": {"modo": "Declarada"},
        "matriz": {"metrica": "positive_pct", "quitarAtipicos": False, "factor": 1.5, "minimoObservaciones": 1},
    },
    {
        "nombre": "matriz-conteo",
        "sesion": {"modo": "Declarada"},
        "matriz": {"metrica": "count", "quitarAtipicos": False, "factor": 1.5, "minimoObservaciones": 5},
    },
    {
        "nombre": "matriz-desviacion",
        "sesion": {"modo": "Declarada"},
        "matriz": {"metrica": "std", "quitarAtipicos": False, "factor": 1.5, "minimoObservaciones": 5},
    },
    {
        "nombre": "extremos-semana-veinte",
        "sesion": {"modo": "Declarada"},
        "extremos": {"periodo": "Semana ISO", "n": 20, "umbral": None},
    },
    {
        "nombre": "extremos-umbral-vela-base",
        "sesion": {"modo": "Declarada"},
        "extremos": {"periodo": "Vela base", "n": 5, "umbral": 3.0},
    },
    {
        "nombre": "extremos-hora",
        "sesion": {"modo": "Declarada"},
        "extremos": {"periodo": "Hora", "n": 8, "umbral": None},
    },
    {
        "nombre": "extremos-anual",
        "sesion": {"modo": "Declarada"},
        "extremos": {"periodo": "Año", "n": 3, "umbral": None},
    },
]


def digerir(valor: Any, acumulador: dict[str, Any] | None = None) -> dict[str, Any]:
    """Resume una estructura recorriendola en orden determinista.

    Ademas de los agregados habituales calcula ``sumaPonderada``, que multiplica
    cada valor por su posicion de recorrido: asi el digesto cambia tambien
    cuando dos valores se intercambian de sitio.
    """

    if acumulador is None:
        acumulador = {
            "numeros": 0, "nulos": 0, "textos": 0, "booleanos": 0, "hojas": 0,
            "suma": 0.0, "sumaPonderada": 0.0,
            "minimo": None, "maximo": None, "hashTextos": 0,
        }

    def contar(numero: float) -> None:
        acumulador["hojas"] += 1
        acumulador["numeros"] += 1
        acumulador["suma"] += numero
        acumulador["sumaPonderada"] += numero * acumulador["hojas"]
        minimo = acumulador["minimo"]
        maximo = acumulador["maximo"]
        acumulador["minimo"] = numero if minimo is None else min(minimo, numero)
        acumulador["maximo"] = numero if maximo is None else max(maximo, numero)

    if valor is None:
        acumulador["hojas"] += 1
        acumulador["nulos"] += 1
    elif isinstance(valor, bool):
        acumulador["hojas"] += 1
        acumulador["booleanos"] += 1
        acumulador["sumaPonderada"] += (1 if valor else 0) * acumulador["hojas"]
    elif isinstance(valor, (int, float)):
        numero = float(valor)
        if math.isfinite(numero):
            contar(numero)
        else:
            acumulador["hojas"] += 1
            acumulador["nulos"] += 1
    elif isinstance(valor, str):
        acumulador["hojas"] += 1
        acumulador["textos"] += 1
        codigos = sum(map(ord, valor))
        acumulador["hashTextos"] = (
            acumulador["hashTextos"] + codigos * acumulador["hojas"]
        ) % 2_147_483_647
    elif isinstance(valor, dict):
        for clave in sorted(valor):
            digerir(clave, acumulador)
            digerir(valor[clave], acumulador)
    elif isinstance(valor, (list, tuple)):
        for elemento in valor:
            digerir(elemento, acumulador)
    return acumulador


def _redondear(acumulador: dict[str, Any]) -> dict[str, Any]:
    """Recorta la suma a 9 decimales, dentro de la tolerancia documentada."""

    salida = dict(acumulador)
    for clave in ("suma", "sumaPonderada", "minimo", "maximo"):
        if isinstance(salida[clave], float):
            salida[clave] = round(salida[clave], 9)
    return salida


@functools.lru_cache(maxsize=None)
def _preparado(simbolo: str):
    """Valida y prepara un CSV una sola vez por simbolo.

    Sin cache, cada configuracion volveria a leer y validar el archivo entero:
    con catorce configuraciones y ocho activos eso son 112 validaciones.
    """

    activo = cargar_activos()[simbolo]
    resultado = leer_y_validar_datos(activo)
    datos, columna_fecha = vistas.preparar_datos(resultado.datos_validos, activo)
    return activo, datos, columna_fecha


def calcular(simbolo: str, configuracion: dict[str, Any]) -> dict[str, Any]:
    """Aplica una configuracion completa de filtros con el nucleo Python."""

    activo, datos, columna_fecha = _preparado(simbolo)

    sesion = configuracion.get("sesion", {})
    filtrados, detalle = vistas.aplicar_sesion(
        datos,
        activo,
        columna_fecha,
        modo=sesion.get("modo", "Declarada"),
        dias=sesion.get("dias"),
        horas=sesion.get("horas"),
        hora_inicio=sesion.get("horaInicio", "09:00"),
        hora_fin=sesion.get("horaFin", "17:00"),
    )

    salida: dict[str, Any] = {
        "detalleSesion": detalle,
        "velasFiltradas": int(len(filtrados)),
        "velasTotales": int(len(datos)),
    }
    if filtrados.empty:
        salida["vistas"] = None
        return salida

    semanal = configuracion.get("semanal", {})
    matriz = configuracion.get("matriz", {})
    extremos = configuracion.get("extremos", {})
    salida["vistas"] = {
        "resumen": exportador.vista_resumen(filtrados, activo, columna_fecha),
        "periodo": exportador.vista_periodo(filtrados, activo, columna_fecha),
        "mensual": exportador.vista_mensual(filtrados, activo, columna_fecha),
        "semanal": exportador.vista_semanal(
            filtrados, activo, columna_fecha,
            quitar_atipicos=semanal.get("quitarAtipicos", False),
        ),
        "diaSemana": exportador.vista_dia_semana(filtrados, activo, columna_fecha),
        "diaria": exportador.vista_diaria(filtrados, activo, columna_fecha),
        "horaria": exportador.vista_horaria(filtrados, activo, columna_fecha),
        "matriz": exportador.vista_matriz(
            filtrados, activo, columna_fecha,
            metrica=matriz.get("metrica", "mean"),
            quitar_atipicos=matriz.get("quitarAtipicos", False),
            factor=matriz.get("factor", 1.5),
            minimo_observaciones=matriz.get("minimoObservaciones", 5),
        ),
        "extremos": exportador.vista_extremos(
            filtrados, activo, columna_fecha,
            periodo=extremos.get("periodo", "Día"),
            n=extremos.get("n", 5),
            umbral=extremos.get("umbral"),
        ),
    }
    return salida


def main() -> None:
    analizador = argparse.ArgumentParser(description=__doc__)
    analizador.add_argument("--activos", nargs="*", help="Subconjunto de simbolos.")
    analizador.add_argument("--destino", type=Path, default=DESTINO)
    argumentos = analizador.parse_args()

    simbolos = argumentos.activos or list(cargar_activos())
    casos = []
    for simbolo in simbolos:
        for configuracion in CONFIGURACIONES:
            bruto = calcular(simbolo, configuracion)
            caso = {
                "symbol": simbolo,
                "caso": configuracion["nombre"],
                "filtros": {
                    clave: valor for clave, valor in configuracion.items()
                    if clave not in {"nombre", "comentario"}
                },
                "detalleSesion": bruto["detalleSesion"],
                "velasFiltradas": bruto["velasFiltradas"],
                "velasTotales": bruto["velasTotales"],
            }
            if configuracion.get("comentario"):
                caso["comentario"] = configuracion["comentario"]
            limpio = exportador.limpiar(bruto["vistas"])
            caso["digesto"] = None if limpio is None else _redondear(digerir(limpio))
            casos.append(caso)
            print(f"  {simbolo:<16} {configuracion['nombre']:<32} "
                  f"{bruto['velasFiltradas']:>7,} velas")

    argumentos.destino.parent.mkdir(parents=True, exist_ok=True)
    argumentos.destino.write_text(
        json.dumps(
            {
                "schemaVersion": exportador.SCHEMA_VERSION,
                "processingVersion": exportador.PROCESSING_VERSION,
                "casos": casos,
            },
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        ),
        encoding="utf-8",
    )
    tamano = argumentos.destino.stat().st_size / 1024
    print(f"\n{len(casos)} caso(s) en {argumentos.destino.name} ({tamano:.0f} KB)")


if __name__ == "__main__":
    main()
