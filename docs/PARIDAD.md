# Contrato de paridad — Streamlit → estático

Este documento fija el comportamiento **efectivo** de la aplicación Streamlit
(`src/interfaz.py`, commit `9d1c6d9`) que la versión estática debe reproducir.

Regla rectora: **paridad antes que corrección**. Cuando el comportamiento
observado difiere de su documentación o de lo que sería semánticamente deseable,
la migración replica el comportamiento observado y lo registra aquí. Las
correcciones semánticas se abordan en commits o issues posteriores.

---

## 1. Alcance funcional

### 1.1 Activos (8)

| Símbolo | Categoría | Zona | Sesión declarada | Filas válidas |
|---|---|---|---|---|
| `BTCUSDT` | crypto | UTC | `24/7` | 78 245 |
| `SP500` | indice_oficial | America/New_York | `NYSE regular observada` | 5 081 |
| `NIKKEI225` | indice_oficial | Asia/Tokyo | `Tokyo regular observada` | 5 090 |
| `USA500IDXUSD` | cfd_indice | America/New_York | `Dukascopy 24/5 extendida` | 74 294 |
| `JPNIDXJPY` | cfd_indice | Asia/Tokyo | `Dukascopy 24/5 extendida` | 75 722 |
| `XAUUSD` | metal_spot | America/New_York | `Dukascopy 24/5 extendida` | 140 352 |
| `XAGUSD` | metal_spot | America/New_York | `Dukascopy 24/5 extendida` | 139 418 |
| `WTI_LIGHTCMDUSD` | energia_cfd | America/New_York | `Dukascopy 24/5 extendida` | 85 909 |

Total: **604 111** observaciones válidas.

### 1.2 Vistas (10)

`Resumen`, `Calidad de datos`, `Análisis por periodo`, `Análisis mensual`,
`Análisis semanal`, `Día de la semana`, `Análisis diario`, `Análisis horario`,
`Matriz día-hora`, `Eventos extremos`.

### 1.3 Controles que deben conservarse

- Tema claro / oscuro.
- Selección de categoría y de activo.
- Sesión: `Declarada`, `Observada`, `Personalizada`.
- Filtro IQR (vista semanal y matriz), con factor configurable en la matriz.
- Métrica de la matriz y mínimo de observaciones por celda.
- Eventos extremos: periodo, y o bien `n` mejores/peores o bien umbral absoluto.
- Estados de carga, error y ausencia de datos.

---

## 2. Núcleo numérico

### 2.1 Retorno

Siempre `(último_close / primer_open - 1) * 100`. **Nunca se suman retornos.**
Si `|open| <= 1e-10` el retorno es `NaN`.

### 2.2 Tolerancia neutra

`TOLERANCIA = 1e-10`. Clasificación de un retorno `r`:

- positivo si `r > 1e-10`
- negativo si `r < -1e-10`
- neutro si `|r| <= 1e-10`

### 2.3 `estadisticas_retornos`

Sobre los valores **finitos** (`NaN` e infinitos se descartan antes de contar `n`):

| Campo | Definición |
|---|---|
| `promedio` | media aritmética |
| `mediana` | mediana (promedio de los dos centrales si `n` es par) |
| `maximo` / `mejor` | máximo |
| `minimo` / `peor` | mínimo |
| `std` | desviación **muestral** `ddof=1`; `NaN` si `n < 2` |
| `positivo_pct` | `#{r > 1e-10} / n * 100` |
| `negativo_pct` | `#{r < -1e-10} / n * 100` |
| `neutro_pct` | `#{abs(r) <= 1e-10} / n * 100` |
| `n` | número de valores finitos |
| `rango` | `maximo - minimo` |

Con `n == 0` todos los campos numéricos valen `NaN` y `n = 0`.

### 2.4 Cuantiles (IQR)

Interpolación lineal de NumPy (`method="linear"`):
`pos = (n-1)*q`, `lo = floor(pos)`, `frac = pos - lo`,
`v = a[lo] + frac*(a[lo+1] - a[lo])` sobre el vector ordenado.

Conservación: `no_finito | (r >= Q1 - f*IQR - 1e-10 && r <= Q3 + f*IQR + 1e-10)`.
**Los valores no finitos se conservan** deliberadamente, para no ocultar
problemas de calidad ajenos al criterio IQR.

### 2.5 Tolerancia Python ↔ JavaScript

Ambas implementaciones usan IEEE-754 binario de 64 bits, pero difieren en el
orden de suma (NumPy usa suma por pares; JavaScript usa suma compensada
Kahan–Neumaier). Tolerancia aceptada y verificada por las pruebas de paridad:

- **Absoluta `1e-9`** o **relativa `1e-12`**, la que sea mayor, para todo valor
  expresado en puntos porcentuales.
- **Exactitud binaria** para precios, conteos, marcas de tiempo y banderas
  booleanas.

---

## 3. Tiempo, zonas horarias y DST

### 3.1 Reglas

1. **La zona horaria del navegador nunca interviene.** Todo campo de calendario
   (año, mes, día, hora, día de la semana, semana ISO) se deriva de la hora
   local del mercado declarada en `activos.json`.
2. El generador Python emite, por observación: epoch UTC, desplazamiento UTC en
   segundos y epoch local (`epoch_utc + offset`). El cliente extrae los campos
   de calendario del epoch local con los captadores `getUTC*`, de modo que
   reproduce la hora de pared del mercado sin consultar el sistema.
3. El manifiesto incluye la **tabla de transiciones** de cada zona (instante y
   desplazamiento), para poder convertir hora local a instante absoluto al
   calcular los límites de un periodo. Así un día con cambio de horario dura
   correctamente 23 o 25 horas.

### 3.2 Clave de agrupación por periodo

Réplica exacta de `analisis._clave_periodo`:

| Periodo | Clave | Orden |
|---|---|---|
| `hour` | `(año, mes, día, hora, offset_utc)` local | lexicográfico de la tupla |
| `day` | medianoche local | cronológico |
| `week` | `año_iso * 100 + semana_iso` local | numérico |
| `month` | `año * 100 + mes` local | numérico |
| `year` | `año` local | numérico |

> **A-1 · Orden invertido en la hora repetida de DST.** La clave horaria incluye
> el desplazamiento UTC para distinguir las dos apariciones de la hora repetida
> al terminar el horario de verano. Como la ordenación es lexicográfica y el
> desplazamiento menor (p. ej. `-18000` = EST) precede al mayor (`-14400` = EDT),
> la **segunda** ocurrencia cronológica se ordena **antes** que la primera.
> Se conserva. Ninguno de los ocho CSV actuales contiene esa hora repetida.

### 3.3 Límites y completitud de un periodo

`completo` es `true` solo si, simultáneamente:

- no hay marcas duplicadas dentro del grupo (`cantidad_registros == marcas_unicas`);
- todas las velas consecutivas del grupo distan exactamente una temporalidad
  base en tiempo **absoluto**;
- el `inicio` observado coincide con el inicio calendario local del periodo;
- el `fin` observado coincide con `fin_exclusivo - temporalidad`;
- `cantidad_registros == (fin_exclusivo - inicio) / temporalidad`, calculado en
  segundos absolutos (por eso un día con DST espera 23 o 25 velas).

### 3.4 Casos cubiertos por pruebas

Nueva York, Tokio, UTC, transición de primavera (hora inexistente), transición
de otoño (hora repetida), semanas ISO que cruzan de año, velas que empiezan en
`HH:30`, sesiones que cruzan medianoche.

> **A-2 · Velas en `HH:30`.** `SP500` produce marcas locales en el minuto 30
> (09:30, 10:30, …). La agregación horaria las agrupa por su hora local, pero
> `completo` resulta `false` porque el inicio observado no coincide con el
> inicio calendario de la hora. Se conserva.

---

## 4. Ambigüedades conservadas

> **A-3 · `"Dukascopy 24/5 extendida"` no equivale a `"24/5"`.**
> Las comparaciones de sesión son de igualdad exacta sobre
> `sesion.strip().lower()` contra `"24/7"` y `"24/5"`.
> `"dukascopy 24/5 extendida"` no coincide con ninguna, de modo que en modo
> `Declarada` **no se aplica ningún filtro** y se conserva la serie completa
> (sábados y domingos incluidos, si los hubiera). Afecta a 5 de los 8 activos.
> Lo mismo ocurre con `"NYSE regular observada"` y `"Tokyo regular observada"`.
> Solo `BTCUSDT` (`24/7`) tiene una etiqueta reconocida.

> **A-4 · Cobertura no disponible salvo `24/7` y `24/5`.**
> `datos.calcular_cobertura` solo calcula intervalos esperados para esas dos
> etiquetas exactas. Para las otras siete emite `disponible: false` con su razón.
> En la práctica solo `BTCUSDT` muestra un porcentaje de cobertura.

> **A-5 · Etiquetas "ponderada" que en realidad son media simple.**
> Los siguientes textos dicen "ponderad*" pero el cálculo es una media
> aritmética sin pesos:
> - "Curva histórica ponderada de cada mes" usa `mean` del retorno acumulado.
> - Columna `retorno_ponderado` de `_curvas_mensuales` usa `mean`.
> - "Retorno histórico ponderado por semana ISO" usa `promedio` (media simple).
> - "Trayectoria histórica ponderada por día" usa `mean`.
>
> Se conservan tanto las etiquetas como el cálculo.

> **A-6 · Orden real de eventos extremos.**
> El docstring dice "de mayor a menor magnitud absoluta", pero el código ordena
> por `["return_percent", "inicio"]` con `ascending=[False, True]`: retorno
> **con signo** descendente y, a igualdad, fecha ascendente. El resultado son
> los positivos de mayor a menor seguidos de los negativos de menor magnitud a
> mayor magnitud. Se conserva el orden del código.

> **A-7 · Los periodos incompletos se incluyen en todos los agregados.**
> Ninguna vista filtra por `completo`. Meses, años y semanas parciales (incluido
> el periodo en curso al final de la serie) entran en las medias estacionales.
> `completo` solo se muestra como columna en la tabla de eventos extremos.

> **A-8 · La sesión se filtra ANTES de agregar periodos.**
> El filtro de sesión se aplica a las velas base; la agregación posterior opera
> sobre la serie ya recortada. Consecuencias conservadas:
> - El `open` de un día/mes/año es la primera vela **de la sesión**, no la
>   primera del calendario.
> - `completo` pasa a ser casi siempre `false`, porque la agregación sigue
>   esperando el periodo calendario completo (24 velas por día) y no el número
>   de velas de la sesión.

> **A-9 · Una sesión que cruza medianoche se reparte entre dos días.**
> `filtrar_sesion_personalizada` con `inicio > fin` conserva las velas de ambos
> lados de la medianoche, pero la agregación diaria asigna cada vela a su propio
> día calendario local. La sesión nocturna del día *D* queda dividida entre el
> final de *D* y el principio de *D+1*. No se reasigna a una "fecha de sesión".

> **A-10 · Modos `Observada` y `Personalizada` con datos diarios.**
> Si la temporalidad no es intradía, ambos modos devuelven la serie completa sin
> filtrar y muestran un aviso. Con los CSV actuales (todos `1h`) no se activa.

> **A-11 · El intervalo personalizado es `[inicio, fin)`.**
> `inicio == fin` significa 24 horas (sin filtro horario).

> **A-12 · Duplicados: se conserva la primera aparición.**
> La clave de deduplicación es `(symbol, timestamp, timeframe)`.

---

## 5. Definición vista por vista

### 5.1 Resumen
- `Último cierre`: `close` de la última vela de la serie filtrada, 4 decimales.
- `Retorno del último mes`: `return_percent` del **último** grupo mensual.
- `Retorno del último año`: `return_percent` del **último** grupo anual.
- `Velas positivas` / `Velas negativas`: `positivo_pct` / `negativo_pct` sobre
  las velas base filtradas.
- Gráfico de velas. Si hay más de **3 000** velas se agrupan en bloques
  consecutivos de `ceil(n / 3000)` velas (`open` primero, `high` máximo,
  `low` mínimo, `close` último) y se avisa del resumen. Las estadísticas siguen
  usando todas las observaciones.

### 5.2 Calidad de datos
Seis métricas de la **validación completa** (serie sin filtrar): filas totales
del archivo, fecha inicial, fecha final, filas válidas, velas utilizadas, filas
eliminadas. No depende de la sesión ni de ningún filtro.

### 5.3 Análisis por periodo
- Barras de `return_percent` por año.
- Tabla pivote año × mes reindexada al rango completo de años y a los 12 meses,
  más la columna `Retorno acumulado del año` tomada del agregado anual.
  Las celdas ausentes se muestran como `-`; el resto con dos decimales y `%`.

### 5.4 Análisis mensual
- Barras del `promedio` de `estacionalidad_mes` sobre los **agregados
  mensuales** (no sobre las velas base).
- Doce curvas: para cada mes calendario, media (ver A-5) del retorno acumulado
  diario `(close_día / open_del_mes - 1) * 100` por día del mes, sobre todos los
  años. Se omite un mes con menos de 2 puntos.

### 5.5 Análisis semanal
- Agregados por semana ISO; filtro IQR global opcional (factor 1.5) aplicado a
  esos agregados, informando cuántas semanas se excluyeron.
- Barras y curva del `promedio` por número de semana ISO (1–53).
- La línea de promedio de la curva es la media de `return_percent` de los
  agregados semanales filtrados (no la media de los promedios por semana).

### 5.6 Día de la semana
- Barras del `promedio` por día sobre los **agregados diarios**.
- Siete curvas de trayectoria: media del retorno acumulado horario respecto a la
  primera apertura del día local, por hora y día de la semana.

### 5.7 Análisis diario
- Barras y curva del `promedio` por día del mes (1–31) sobre agregados diarios.
- La línea de promedio es la **media de los promedios** por día del mes.
- Mapa de calor de una fila reindexado a 1–31.

### 5.8 Análisis horario
- Barras del `promedio` por hora sobre los agregados horarios.
- Siete curvas del retorno horario medio por día de la semana.
- No disponible si la temporalidad no es intradía.

### 5.9 Matriz día-hora
- Métricas: `mean`, `median`, `positive_pct`, `std`, `count`.
- IQR opcional con factor configurable sobre los agregados horarios.
- Se enmascaran las celdas cuyo `count` sea menor que el mínimo indicado.
- Ejes: solo los días y horas **observados**, en orden ascendente.
- Detalle por día en pestañas.

### 5.10 Eventos extremos
- Periodo: `Vela base`, `Hora` (si intradía), `Día`, `Semana ISO`, `Mes`, `Año`.
  Valor por defecto `Día`.
- Sin umbral: `n` mayores positivos y `n` menores negativos (por defecto 5),
  descartando neutros; luego se eliminan duplicados.
- Con umbral: todos los eventos con `abs(r) >= umbral - 1e-10`.
- Orden: ver A-6.
- Columnas: inicio, fin, open, close, retorno, conteo, completo, tipo.

---

## 6. Diferencias deliberadas respecto a Streamlit

Estas son las **únicas** desviaciones permitidas en esta migración, porque
GitHub Pages no ejecuta Python en tiempo real:

1. **Sin "Actualizar datos y cache".** Se sustituye por `Recargar versión
   publicada` (revalida el manifiesto) y `Limpiar caché local`. Nunca se
   descargan datos y nunca se muestra la hora del navegador como hora de
   actualización del mercado: se muestra `generatedAt` del manifiesto.
2. **Las filas inválidas no viajan al cliente.** El detalle fila a fila de
   `invalidos` se resume en `report.json` (conteos y motivos agregados); la
   vista Calidad de datos muestra exactamente las mismas seis métricas.
3. **El catálogo se sirve precalculado** desde `manifest.json` en lugar de
   validar los ocho CSV en cada carga.
