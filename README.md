# Analisis estacional H1

Aplicacion local Streamlit personalizada para ocho series OHLCV de una hora. El catalogo usa exclusivamente los CSV incluidos en `data/`: no descarga precios, no consulta APIs y no admite el formato historico anterior del proyecto.

## Activos incluidos

| Simbolo | Instrumento | Fuente | Cobertura inicial | Hora de analisis |
|---|---|---|---|---|
| `BTCUSDT` | Bitcoin / USDT spot | Binance | 2017 | UTC |
| `SP500` | S&P 500 oficial `^GSPC` | Yahoo Finance | 2023 | Nueva York |
| `NIKKEI225` | Nikkei 225 oficial `^N225` | Yahoo Finance | 2023 | Tokio |
| `USA500IDXUSD` | US 500 CFD | Dukascopy bid | 2011 | Nueva York |
| `JPNIDXJPY` | Japan 225 CFD | Dukascopy bid | 2011 | Tokio |
| `XAUUSD` | Oro spot / USD | Dukascopy bid | 2003 | Nueva York |
| `XAGUSD` | Plata spot / USD | Dukascopy bid | 2003 | Nueva York |
| `WTI_LIGHTCMDUSD` | Petroleo WTI CFD | Dukascopy bid | 2011 | Nueva York |

Los indices oficiales y sus CFD son instrumentos distintos. Nunca se combinan: tienen proveedores, sesiones, coberturas y semantica de volumen diferentes.

## Funcionalidad

- Catalogo cerrado de ocho activos, dividido por tipo de instrumento.
- Analisis de retornos por hora, dia, semana ISO, mes y ano.
- Estacionalidad mensual, semanal, diaria y horaria.
- Matriz dia-hora y eventos extremos.
- Conversion desde UTC a la zona local declarada para cada mercado.
- Sesion completa, observada o personalizada sin eliminar las aperturas dominicales de Dukascopy.
- Validacion de timestamps, valores numericos, precios no negativos, OHLC y duplicados.
- Cache Parquet local invalidada por cambios de datos, configuracion o version de procesamiento.

## Datos

Cada CSV fuente debe contener exclusivamente este contrato:

```text
timestamp_utc,open,high,low,close,volume
```

El lector deriva `symbol`, `timeframe`, archivo de origen y retorno desde `data/activos.json`. No confia en metadata repetida dentro de cada fila.

Reglas de validacion:

- `timestamp_utc` debe representar un instante valido.
- OHLC debe ser numerico, finito, no negativo y coherente.
- `volume` puede estar vacio, pero no puede ser negativo cuando existe.
- Los timestamps duplicados posteriores se excluyen del analisis.
- Los huecos de mercado no se rellenan y no se generan velas sinteticas.

`data/FUENTES_DATOS.txt` documenta cobertura, proveedor y ajustes realizados antes de incorporar los archivos. En particular, 41 velas WTI recibidas de Dukascopy tuvieron un ajuste maximo de `0.002` en `high/low` para mantener coherencia OHLC.

## Volumen y precios

- BTC usa volumen spot de Binance.
- Los indices Yahoo pueden publicar volumen cero o no disponible.
- Dukascopy aporta volumen del proveedor, no volumen oficial de la bolsa subyacente.
- Los precios de Dukascopy son `bid`.

El volumen no debe compararse directamente entre activos.

## Arquitectura

```text
Analisis Estacional de Activios/
|-- app.py
|-- data/
|   |-- activos.json
|   |-- FUENTES_DATOS.txt
|   `-- ocho CSV H1
|-- src/
|   |-- configuracion.py
|   |-- datos.py
|   |-- cache.py
|   |-- analisis.py
|   `-- interfaz.py
|-- cache/
|-- tests/
|-- requirements.txt
`-- README.md
```

## Instalacion

Desde PowerShell:

```powershell
Set-Location "C:\Users\PC\Desktop\Analisis Estacional de Activios\Analisis Estacional de Activios"
python -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## Ejecucion

```powershell
Set-Location "C:\Users\PC\Desktop\Analisis Estacional de Activios\Analisis Estacional de Activios"
.venv\Scripts\activate
streamlit run app.py
```

Pruebas:

```powershell
python -m pytest -q
```

## Retornos

Para cada periodo se usa la primera apertura y el ultimo cierre validos:

```text
retorno_porcentual = (cierre_final / apertura_inicial - 1) * 100
```

Los retornos simples de las velas no se suman para formar periodos mayores.

## Sesiones y cobertura

- `BTCUSDT` es `24/7` y permite calcular una rejilla continua exacta.
- Los indices oficiales conservan solo las observaciones publicadas por Yahoo.
- Los CFD y metales conservan toda la sesion extendida de Dukascopy, incluida su apertura dominical UTC.
- No se inventan calendarios bursatiles, festivos ni horarios ausentes.
- Las barras Yahoo pueden comenzar a `HH:30`; la hora estacional representa el inicio real de la vela.

## Limitaciones

- Las coberturas historicas son diferentes entre proveedores.
- No hay indicadores tecnicos, senales, backtesting ni predicciones.
- No se imputan precios, volumenes ni intervalos faltantes.
- Los resultados son descriptivos y no constituyen asesoramiento financiero.
