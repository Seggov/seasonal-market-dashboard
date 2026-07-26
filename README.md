# Finance

Aplicacion local de analisis historico y estacional de mercados financieros. Lee activos configurados mediante `data/activos.json`, valida sus CSV y presenta estadisticas descriptivas en Streamlit. No descarga datos, no modifica las fuentes y no genera indicadores, senales, predicciones ni recomendaciones de inversion.

## Funcionalidad

- Catalogo dinamico por categoria y activo.
- Panel de navegacion estadistica visible dentro de la pagina y sincronizado con la barra lateral.
- Temas claro y oscuro seleccionables durante la sesion.
- Validacion de columnas, timestamps, simbolo, temporalidad, precios y estructura OHLC.
- Clasificacion de velas correctas, invalidas y faltantes.
- Retornos por hora, dia, semana ISO, mes y ano calculados desde la primera apertura hasta el ultimo cierre.
- Estacionalidad por mes, semana ISO, dia de la semana, dia del mes y hora.
- Matriz dia-hora con dias en el eje X y horas en el eje Y.
- Eventos extremos historicos por temporalidad.
- Sesion declarada, observada o personalizada cuando la temporalidad contiene horas reales.
- Cache en memoria con Streamlit y cache persistente Parquet invalidada por cambios en CSV o `activos.json`.

## Arquitectura

```text
Finance/
|-- app.py                 # Punto de entrada Streamlit
|-- data/                  # CSV originales y activos.json
|-- src/
|   |-- configuracion.py   # Metadata dinamica y zonas horarias
|   |-- datos.py           # Lectura, validacion, calidad y cobertura
|   |-- cache.py           # Firma, Parquet e invalidacion
|   |-- analisis.py        # Retornos, agregaciones y estacionalidad
|   `-- interfaz.py        # Navegacion, tablas y graficos
|-- cache/                 # Archivos regenerables; no contiene fuentes
|-- tests/                 # Pruebas unitarias pequenas y deterministas
|-- requirements.txt
`-- README.md
```

Los modulos estadisticos y de datos no dependen de Streamlit. Esto permite probar los calculos sin ejecutar la interfaz.

## Instalacion

Desde PowerShell:

```powershell
cd C:\Users\PC\Desktop\Finance
python -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## Ejecucion

```powershell
cd C:\Users\PC\Desktop\Finance
.venv\Scripts\activate
streamlit run app.py
```

La aplicacion abre una pantalla de seleccion. La categoria y el activo se eligen exclusivamente desde el panel lateral izquierdo y se confirma con **Analizar activo**. En el panel del activo, las diez vistas disponibles permanecen visibles y agrupadas por finalidad. El control **Modo oscuro** cambia tablas, metricas, fondos y graficos sin alterar los datos.

Para ejecutar las pruebas:

```powershell
pytest -q
```

## Formato de activos.json

El JSON es la fuente oficial de metadata. No existe una lista de activos codificada en Python.

```json
{
  "SIMBOLO": {
    "nombre": "Nombre visible",
    "categoria": "categoria_dinamica",
    "mercado": "Mercado",
    "sesion": "24/5",
    "zona_horaria": "Area/Ciudad",
    "temporalidad": "15m",
    "archivo": "SIMBOLO_15m.csv",
    "tipo_timestamp": "instante_utc",
    "formula_retorno": "(close_final / open_inicial - 1) * 100"
  }
}
```

Campos obligatorios: `nombre`, `categoria`, `mercado`, `sesion`, `zona_horaria`, `temporalidad`, `archivo`, `tipo_timestamp` y `formula_retorno`. La zona debe ser un identificador IANA valido y el archivo debe existir dentro de `data`.

## Formato de los CSV

Cada archivo individual debe incluir:

```text
symbol,timestamp,timeframe,open,high,low,close,volume,
change_percent,return_percent,source_file,ohlc_valid
```

`open`, `high`, `low` y `close` son obligatorios, numericos, finitos y no negativos. `volume` y `change_percent` pueden estar vacios. `symbol` y `timeframe` deben coincidir con el JSON.

`change_percent` conserva el porcentaje publicado por la fuente. No se usa para agregar periodos. `return_percent` representa el retorno apertura-cierre de una vela y se recalcula para cada periodo analizado.

## Formula de retornos

```text
retorno_porcentual = (cierre_final / apertura_inicial - 1) * 100
```

La apertura inicial es la primera apertura valida del periodo y el cierre final es el ultimo cierre valido. Los retornos simples nunca se suman para formar retornos mayores.

## Timestamps y zonas horarias

- `instante_utc`: se interpreta como un instante real UTC y se convierte a `zona_horaria` mediante `zoneinfo`, incluyendo cambios de horario de verano.
- `fecha_sesion`: se conserva como fecha de mercado `YYYY-MM-DD`, sin inventar una hora ni localizarla artificialmente.

Los analisis horarios solo se habilitan para temporalidades intradia. Una vela diaria nunca se distribuye entre horas.

## Calidad y datos faltantes

Una fila es valida cuando su timestamp, metadata y OHLC son coherentes. Las repeticiones posteriores de una misma clave temporal se clasifican como invalidas; la primera aparicion se usa deterministicamente para analizar, sin alterar el CSV.

La tolerancia para clasificar una vela como neutra es `1e-10` sobre el retorno porcentual. La aplicacion informa cantidades y porcentajes positivos, negativos y neutros.

La cobertura se calcula solo con una sesion suficientemente definida:

- `24/7`: todos los intervalos entre la primera y ultima observacion.
- `24/5`: intervalos de lunes a viernes; no se inventan horas adicionales.
- Sesiones como `USA` o `Japon`: se muestra **No disponible** si falta un calendario exacto con festivos y horarios.

Los intervalos faltantes no se rellenan. Los periodos incompletos se conservan identificados como tales. Las celdas sin muestra suficiente en la matriz aparecen vacias, no como cero.

## Sesiones y outliers

Para Forex, indices y materias primas se puede usar la sesion declarada, la observada o una sesion personalizada. En datos diarios las opciones intradia se deshabilitan porque no existe una hora observable.

El filtro de outliers de la matriz esta desactivado inicialmente. Al activarlo aplica IQR (`Q1 - 1.5 * IQR`, `Q3 + 1.5 * IQR`) sobre retornos horarios ya agregados. La interfaz muestra cuantos valores fueron excluidos y nunca modifica precios ni CSV.

## Cache

La firma de cada entrada combina:

- Ruta del CSV.
- Tamano del CSV.
- Fecha de modificacion en nanosegundos.
- SHA-256 del CSV.
- Los mismos atributos de `activos.json`.
- Version del procesamiento.

Los datos validos se almacenan como Parquet en `cache/`; el indice pequeno se almacena como JSON. `st.cache_resource` comparte el dataset validado como recurso inmutable sin copiar cientos de miles de filas en cada rerun, y `st.cache_data` conserva resumenes derivados pequenos. Si el archivo cambia o el cache esta corrupto, se regenera automaticamente.

El boton **Actualizar datos y cache** limpia ambas capas y vuelve a leer exclusivamente los archivos locales.

## Agregar un activo

1. Copiar el CSV compatible dentro de `data`.
2. Agregar su entrada a `data/activos.json`.
3. Usar un simbolo y temporalidad coherentes en todas las filas.
4. Declarar una zona IANA y el tipo de timestamp correcto.
5. Pulsar **Actualizar datos y cache**.

La nueva categoria y el activo apareceran automaticamente. Un error en ese activo se mostrara de forma aislada y no impedira analizar los demas.

## Limitaciones conocidas

- No se incluyen calendarios bursatiles externos ni festivos por mercado.
- La completitud de periodos es conservadora cuando la metadata no define el calendario exacto.
- No se descargan precios ni se consumen APIs.
- No se imputan velas, precios o volumenes.
- No se implementan indicadores tecnicos, backtesting ni modelos predictivos.
- Los resultados describen la historia disponible y no constituyen asesoramiento financiero.

## Ejemplo de uso

1. Seleccionar `crypto` y `BTCUSDT`.
2. Pulsar **Analizar**.
3. Abrir **Analisis horario** para comparar retornos por hora UTC.
4. Abrir **Matriz dia-hora**, seleccionar una metrica y mantener inicialmente desactivado el filtro IQR.
5. Cambiar a un activo diario para comprobar que las vistas horarias se muestran como no disponibles.
