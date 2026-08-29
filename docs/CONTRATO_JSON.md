# Contrato JSON del sitio estático

`schemaVersion` actual: **1**

Los JSON de `cache/` (índices de Parquet, estructuras internas de Python) **no
se reutilizan**. Este es un esquema web explícito, versionado y estable.

## Reglas generales

- JSON estricto: sin `NaN`, `Infinity` ni `-Infinity`. Todo valor no finito se
  serializa como `null`.
- Formato columnar (arrays paralelos) en las series y en las tablas grandes.
- Series fragmentadas por **activo y año**.
- Nunca se publican rutas absolutas del sistema de archivos.
- Cada archivo lleva un hash de contenido en el nombre; `manifest.json` es el
  único recurso sin hash y se solicita con `cache: "no-cache"`.
- Solo se descarga el activo seleccionado.

## Estructura

```text
dist/
├── index.html
├── .nojekyll
├── assets/
│   ├── app.css
│   ├── app.js
│   ├── worker.js
│   ├── analytics/*.js
│   └── vendor/plotly-2.35.2.min.js
└── data/
    ├── manifest.json
    ├── BTCUSDT/
    │   ├── report.<hash>.json
    │   ├── series-2017.<hash>.json
    │   └── ...
    └── ...
```

## `manifest.json`

```jsonc
{
  "schemaVersion": 1,
  "processingVersion": "1.0.0",   // versión del generador
  "generatedAt": "2026-08-29T12:34:56Z",
  "contentHash": "…",             // hash del conjunto completo
  "sourceRowCount": 604111,
  "categories": { "crypto": "Criptomonedas", … },
  "assets": [
    {
      "symbol": "BTCUSDT",
      "nombre": "Bitcoin / USDT",
      "categoria": "crypto",
      "mercado": "Binance Spot",
      "sesion": "24/7",
      "zonaHoraria": "UTC",
      "temporalidad": "1h",
      "tipoTimestamp": "instante_utc",
      "formulaRetorno": "(close_final / open_inicial - 1) * 100",
      "archivo": "BTCUSDT_1h.csv",       // solo el nombre, nunca la ruta
      "intradia": true,
      "baseMinutes": 60,
      "sesionReconocida": "24/7",        // null si la etiqueta no se reconoce (A-3)
      "primeraFecha": "2017-08-17T04:00:00+00:00",
      "ultimaFecha": "2026-07-26T16:00:00+00:00",
      "filasTotales": 78246,
      "filasValidas": 78245,
      "porcentajeValido": 99.99,
      "cobertura": { "disponible": true, "porcentaje": 99.83, … },
      "years": [2017, 2018, …],
      "report": "BTCUSDT/report.a1b2c3d4.json",
      "series": { "2017": "BTCUSDT/series-2017.e5f6…json", … },
      "bytes": { "report": 51234, "series": 1234567 },
      "tz": {
        "name": "UTC",
        "transitions": [[epochUTC, offsetSegundos], …],
        "initialOffset": 0
      }
    }
  ]
}
```

`transitions` cubre el rango de datos del activo más un año de margen a cada
lado. Permite convertir hora local a instante absoluto sin usar la zona horaria
del navegador.

## `series-<AÑO>.<hash>.json`

Velas base del año, en hora local del mercado, formato columnar.

```jsonc
{
  "schemaVersion": 1,
  "symbol": "XAUUSD",
  "year": 2003,
  "count": 5678,
  "scale": 1000,        // null => precios en punto flotante literal
  "t0": 1052092800,     // epoch UTC de la primera vela, en segundos
  "dt": [0, 3600, …],   // deltas de epoch UTC en segundos (acumulativos)
  "off": [[0, -14400], [3542, -18000]],  // [índiceInicial, offsetSegundos] RLE
  "o": [340345, 116, …], // primer valor absoluto (entero escalado), resto deltas
  "h": [...], "l": [...], "c": [...]
}
```

- Cuando `scale` es un entero, el precio real es `valorAcumulado / scale`. La
  división de un entero exacto por una potencia de diez está correctamente
  redondeada en IEEE-754, así que reproduce **bit a bit** el doble que Python
  obtiene al parsear el CSV.
- `scale` es `null` (y los arrays contienen dobles literales sin delta) cuando
  el CSV trae más decimales de los que caben en 2^53 al escalar — el caso de
  `SP500` y `NIKKEI225`, cuyos precios de Yahoo llevan 13 decimales.
- `volume` no se publica: ninguna vista lo analiza.

## `report.<hash>.json`

Metadatos del activo y **vistas predeterminadas precalculadas** por Python
(sesión `Declarada`, IQR desactivado). El cliente las pinta de inmediato; el
Web Worker recalcula al cambiar cualquier filtro.

```jsonc
{
  "schemaVersion": 1,
  "symbol": "XAUUSD",
  "generatedAt": "…",
  "calidad": {
    "filasTotales": 140353, "filasValidas": 140352, "filasInvalidas": 1,
    "fechaInicial": "2003-05-04T20:00:00-04:00",
    "fechaFinal": "2026-07-24T16:00:00-04:00",
    "velasUtilizadas": 140352,
    "motivosInvalidez": { "duplicado; se conserva la primera aparicion": 1 },
    "advertencias": [ … ]
  },
  "sesionPorDefecto": { "modo": "Declarada", "detalle": "…", "filtrado": false },
  "observado": { "dias": [0,1,2,3,4], "horas": [0,1,…,23] },
  "defaultViews": {
    "resumen": { … }, "periodo": { … }, "mensual": { … },
    "semanal": { … }, "diaSemana": { … }, "diaria": { … },
    "horaria": { … }, "matriz": { … }, "extremos": { … }
  }
}
```

Las pruebas de paridad comparan `defaultViews` (generado por Python) contra la
salida del módulo de analítica en JavaScript sobre las mismas series, con la
tolerancia de `PARIDAD.md` §2.5.

## Presupuestos

| Presupuesto | Límite | Verificado por |
|---|---|---|
| Tamaño total del sitio | 200 MB (límite duro de Pages: 1 GB) | `tools/check_dist.py` |
| Carga inicial (shell + manifiesto, sin comprimir) | 6 MB | `tools/check_dist.py` |
| Mayor fragmento individual | 8 MB | `tools/check_dist.py` |
| Tiempo de generación | 10 min (límite de Pages) | workflow |
| Cambio de activo | < 2 s en red local | verificación manual |
