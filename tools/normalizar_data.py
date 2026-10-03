"""Normaliza los CSV de TradingView a la estructura estricta del proyecto.

Entrada (TradingView):  time,open,high,low,close (Unix epoch segundos)
Salida (Proyecto):      timestamp_utc,open,high,low,close,volume (ISO 8601 UTC)
"""

from __future__ import annotations

from pathlib import Path
import time
import pandas as pd

ORIGEN_BASE = Path(r"C:\Users\PC\Desktop\data-mercadosfinancieros-analisis")
DESTINO_BASE = Path(__file__).resolve().parents[1] / "data"

ARCHIVOS = [
    # Cripto
    ("crypto/CRYPTOCAP_TOTAL, 60.csv", "TOTAL_1h.csv", "TOTAL"),
    # Índices
    ("indices/SP_DLY_SPX, 60.csv", "SPX_1h.csv", "SPX"),
    ("indices/BME_DLY_IBC, 60.csv", "IBEX35_1h.csv", "IBEX35"),
    ("indices/OANDA_JP225USD, 60.csv", "JP225_1h.csv", "JP225"),
    ("indices/BCS_DLY_SPCLXIGL, 5.csv", "SPCLXIGL_5m.csv", "SPCLXIGL"),
    ("indices/NASDAQ_DLY_NDX, 240.csv", "NDX_4h.csv", "NDX"),
    # Metales
    ("commodities/COMEX_DL_GC1!, 60.csv", "GC1_1h.csv", "GC1"),
    ("commodities/COMEX_DL_SI1!, 60.csv", "SI1_1h.csv", "SI1"),
    ("commodities/COMEX_DL_HG1!, 60.csv", "HG1_1h.csv", "HG1"),
    ("commodities/OANDA_XAUUSD, 60.csv", "XAUUSD_1h.csv", "XAUUSD"),
    # Energía
    ("commodities/NYMEX_DL_CL1!, 60.csv", "CL1_1h.csv", "CL1"),
    ("commodities/NYMEX_DL_NG1!, 60.csv", "NG1_1h.csv", "NG1"),
    # Agrícolas
    ("commodities/CBOT_DL_ZS1!, 60.csv", "ZS1_1h.csv", "ZS1"),
    # Renta Fija
    ("renta_fija/TVC_US10Y, 60.csv", "US10Y_1h.csv", "US10Y"),
]


def normalizar_archivo(origen_rel: str, destino_nombre: str, simbolo: str) -> int:
    ruta_origen = ORIGEN_BASE / origen_rel
    ruta_destino = DESTINO_BASE / destino_nombre

    if not ruta_origen.is_file():
        raise FileNotFoundError(f"No existe el archivo origen: {ruta_origen}")

    inicio = time.perf_counter()
    df = pd.read_csv(ruta_origen)

    # Validar que contenga time, open, high, low, close
    for col in ("time", "open", "high", "low", "close"):
        if col not in df.columns:
            raise ValueError(f"Falta columna {col} en {ruta_origen}")

    # Convertir time a ISO 8601 UTC
    dt_series = pd.to_datetime(df["time"], unit="s", utc=True)
    df["timestamp_utc"] = dt_series.dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    # TradingView no aporta volumen en este conjunto. Dejarlo vacio distingue
    # "no disponible" de un volumen observado igual a cero.
    df["volume"] = pd.NA

    # Seleccionar y ordenar columnas requeridas
    salida = df[["timestamp_utc", "open", "high", "low", "close", "volume"]].copy()
    salida.sort_values("timestamp_utc", kind="stable", inplace=True)
    salida.drop_duplicates(subset=["timestamp_utc"], keep="first", inplace=True)

    salida.to_csv(ruta_destino, index=False, encoding="utf-8")
    duracion = time.perf_counter() - inicio
    print(f"  {simbolo:<10} -> {destino_nombre:<16} ({len(salida):>6,} filas) en {duracion:.2f}s")
    return len(salida)


def main() -> None:
    print(f"Normalizando {len(ARCHIVOS)} archivos desde {ORIGEN_BASE}:")
    total_filas = 0
    for origen, destino, simbolo in ARCHIVOS:
        total_filas += normalizar_archivo(origen, destino, simbolo)
    print(f"\nCompletado: {total_filas:,} filas normalizadas en {DESTINO_BASE}.")


if __name__ == "__main__":
    main()
