# Contrato JSON del sitio estático

`schemaVersion` actual: **2**

El sitio **solo dibuja**. Cada vista viaja ya calculada desde Python, así que el
contrato publica resultados agregados y no series de velas.

## Reglas generales

- JSON estricto: sin `NaN`, `Infinity` ni `-Infinity`. Todo valor no finito se
  serializa como `null`.
- Cada campo publicado se dibuja. No se exporta nada «por si acaso».
- Nunca se publican rutas absolutas del sistema de archivos.
- `report.json` lleva un hash de contenido en el nombre; `manifest.json` es el
  único recurso sin hash y se solicita con `cache: "no-cache"`.
- Solo se descarga el informe del instrumento seleccionado.

## Estructura

```text
dist/
├── index.html
├── .nojekyll
├── assets/
│   ├── app.css
│   ├── app.js          arranque, rutas y cabecera
│   ├── ui.js           formato y calendario del mercado
│   ├── graficos.js     envoltorio de Plotly
│   ├── vistas.js       una función por vista
│   └── vendor/plotly-2.35.2.min.js
└── data/
    ├── manifest.json
    ├── BTCUSDT/report.<hash>.json
    └── ...
```

## `manifest.json`

Catálogo mínimo: lo que necesitan las pestañas y la cabecera.

```jsonc
{
  "schemaVersion": 2,
  "processingVersion": "2.0.0",
  "generatedAt": "2026-08-29T19:31:22+00:00",
  "contentHash": "…",
  "sourceRowCount": 604111,
  "categories": { "crypto": "Criptomonedas", … },
  "assets": [
    {
      "symbol": "BTCUSDT",
      "nombre": "Bitcoin / USDT",
      "categoria": "crypto",
      "mercado": "Binance Spot",
      "zonaHoraria": "UTC",
      "temporalidad": "1h",
      "intradia": true,
      "baseMinutes": 60,
      "primeraFecha": "2017-08-17T04:00:00+00:00",
      "ultimaFecha": "2026-07-26T16:00:00+00:00",
      "filasValidas": 78245,
      "report": "BTCUSDT/report.a1b2c3d4.json",
      "bytes": 162880
    }
  ]
}
```

## `report.<hash>.json`

```jsonc
{
  "schemaVersion": 2,
  "processingVersion": "2.0.0",
  "symbol": "XAUUSD",
  "vistas": {
    "resumen":   { "metricas": {…}, "velas": {…} },
    "periodo":   { "anual": […], "pivote": { "años": […], "meses": [[…12]] } },
    "mensual":   { "estacional": […], "curvas": […] },
    "semanal":   { "estacional": […], "promedioGeneral": 0.12 },
    "diaSemana": { "estacional": […], "trayectorias": […] },
    "diaria":    { "estacional": […] },
    "horaria":   { "disponible": true, "estacional": […], "curvas": […] },
    "matriz":    { "disponible": true, "dias": […], "horas": […], "valores": [[…]] },
    "extremos":  { "periodo": "Día", "filas": […] }
  }
}
```

### Filas estacionales

Cada fila lleva solo la clave del eje, el promedio y el tamaño de muestra:

```jsonc
{ "numero_mes": 1, "promedio": 1.774, "n": 3 }
```

Las claves de eje son `numero_mes`, `semana_iso`, `numero_dia`, `dia_mes` u
`hora`, según la vista. Se conservan los nombres de campo de Python para que la
correspondencia con `exportador.vista_*` sea literal.

### Curvas

```jsonc
{ "clave": 3, "dia_mes": [1, 2, 3, …], "retorno": [0.1, null, 0.4, …] }
```

`clave` es el mes (1-12) o el día de la semana (0 = lunes). El eje es `dia_mes`
o `hora`. Un hueco se publica como `null` y el gráfico no lo interpola.

### Tiempo

Las vistas nunca publican fechas con formato. Cada marca viaja como **epoch
local del mercado** (`instante absoluto + desplazamiento UTC`), en segundos:

- `resumen.velas.lt` para el eje del gráfico de precio.
- `extremos.filas[].inicioLocal` para las etiquetas del ranking.

El cliente deriva año, mes, día, hora y minuto con aritmética civil exacta, sin
construir un solo `Date`. **La zona horaria del navegador nunca interviene.**

### Velas del gráfico de precio

`resumen.velas` trae la serie ya reducida a un máximo de **3 000** bloques OHLC
(`open` primero, `high` máximo, `low` mínimo, `close` último), que es todo lo
que el gráfico puede dibujar con sentido. `resumido` indica si hubo reducción.

## Presupuestos

| Presupuesto | Límite | Medido |
|---|---|---|
| Tamaño del artefacto | 200 MB (Pages: 1 GB) | **5,7 MB** en 18 archivos |
| Carga inicial | 6 MB | **4,4 MB**, de los que 4,35 MB son Plotly |
| Mayor informe | 1 MB | **204 KB** (`SP500`) |
| Tiempo de generación | 10 min (Pages) | **99 s** |

El artefacto está dominado por la biblioteca de gráficos, no por los datos: los
ocho informes suman 1,3 MB.
