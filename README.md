# Plataforma web de residuos sólidos de Bolivia

Aplicación Flask que lee los Excel del INE (recolección de residuos 2005-2026) y los muestra con gráficas interactivas, comparativas, pronósticos y control de calidad de datos.

## Cómo ejecutarla

```bash
python -m venv .venv
 .venv/Scripts/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python run.py                    # abre http://localhost:5000
python -m pytest                 # (opcional) corre los tests
```

Las gráficas usan Chart.js desde un CDN, así que la primera carga necesita internet.

## Estructura de archivos

```
residuos-bolivia/
├── README.md               Este archivo
├── requirements.txt        Dependencias (Flask, pandas, openpyxl, statsmodels)
├── run.py                  Punto de entrada: python run.py
├── config.py               Rutas a los 3 Excel
├── data/
│   └── raw/                Excel originales del INE (no se modifican)
│       ├── ciudades_mensual_2005_2026.xlsx    Ciudad × mes
│       ├── tipo_mensual_2005_2026.xlsx        Tipo de procedencia × mes
│       └── ciudad_tipo_2010_2025.xlsx         Ciudad × tipo, anual
├── app/
│   ├── __init__.py         create_app(): registra las rutas
│   ├── routes/
│   │   ├── pages.py        Páginas HTML y reporte
│   │   └── api.py          API JSON /api/* y descarga CSV/Excel
│   ├── services/
│   │   ├── data_loader.py  Lee los Excel, normaliza y elimina duplicados
│   │   └── analytics.py    KPIs, tratamientos, Hampel, consistencia y backtesting
│   ├── templates/
│   │   ├── base.html       Cabecera, menú, tema y pie comunes
│   │   ├── panel.html      KPIs, serie de tiempo, ranking, composición por tipo
│   │   ├── comparar.html   Ciudad vs. ciudad y heatmap mes × año
│   │   ├── pronostico.html Proyección con backtesting y banda de error real
│   │   └── calidad.html    Faltantes, rachas, cobertura, consistencia y LOG
│   └── static/
│       ├── css/styles.css  Estilos (tema claro/oscuro y estilos de impresión)
│       └── js/app.js       Lógica de cada página (fetch a la API + Chart.js)
└── tests/
    └── test_app.py         Lectura, completitud, pronóstico y endpoints
```

## Criterios de datos

- **Duplicados**: se eliminan las filas repetidas al cargar. El dataset de tipos traía 72 claves `(fecha, tipo)` repetidas en 2021; sumarlas duplicaba ese año. La limpieza queda resumida en el LOG de Calidad.
- **Nombres de tipos**: se unifican `Domiciliaria → Domiciliarios`, `Hospital → Establecimientos de salud` y `Otros(1) → Otros`.
- **Años incompletos**: los agregados anuales excluyen años con menos de 12 meses de dato (2026 llega hasta junio). La vista mensual sí los muestra y la página Calidad lo explica.
- **Cobija**: se excluye de las vistas por ciudad (ranking, mapa, comparar, correlación y composición por ciudad) porque tiene hasta 43 meses seguidos sin dato. El **Total** sigue siendo el dato oficial del INE y sí la incluye, por eso la suma de ciudades no iguala al Total (~1 %). En Calidad, la racha de Cobija se muestra como referencia marcada «excluida».
- **Serie B (ciudades)**: sin interpolación. Se recorta Sucre antes de 2015 y se eliminan las filas con `ton` nulo (menos del 5 % de la serie). Los huecos se ven como cortes y la cobertura mensual se reporta en Calidad.
- **Ciudad × Tipo (A)**: mismo criterio que B (sin Cobija y Sucre desde 2015). Los tipos sin dato se marcan `no_reportado = True`, se rellenan con 0 y no se imputan. Así la suma de tipos reportados coincide con el total de B.
- **Atípicos**: Hampel local sobre el logaritmo de la serie, ventana de 13 meses y 4 MAD. Se reporta `out_local`, `ton_final`, `mediana_local` y `desvio_pct`; el dato atípico se winsoriza con los límites locales.
- **Pronóstico**: entrenamiento anterior a `2023-01-01` y prueba desde esa fecha. Se comparan Holt-Winters, SARIMA y regresión lineal estacional con MAE/MAPE, se elige el de menor MAE y la banda usa el error del backtesting. La interpolación se usa solo internamente para regularizar la serie mensual.
- **Descargas**: por defecto entregan datos tratados (sin Cobija en las vistas por ciudad); `?crudo=1` entrega los datos completos con Cobija, deduplicados y con nombres normalizados.

## Qué incluye

| Página | Contenido |
|---|---|
| Panel | KPIs del último año completo, serie mensual/anual filtrable por ciudad y años, ranking de ciudades, composición por tipo de procedencia |
| Comparar | Varias ciudades a la vez y heatmap de estacionalidad (mes × año) |
| Pronóstico | Backtesting con prueba desde 2023 de Holt-Winters, SARIMA y regresión lineal; gráficos de real vs. cada modelo, barras MAE/MAPE, residuos y selector de modelo (automático o forzado); banda de confianza fuera de muestra |
| Mapa | Mapa de Bolivia con departamentos y burbujas por ciudad, con selector de año |
| Por tipo | Evolución y composición por tipo de procedencia de cada ciudad, con `no_reportado = 0` |
| Análisis | Serie tratada, mediana local, atípicos Hampel y correlación entre ciudades |
| Simulador | Ahorro en toneladas y camiones según el % de reducción por tipo |
| Aprende | Guía de separación de residuos |
| Reporte | `/reporte/<ciudad>` con KPIs, series y pronóstico; botón «Descargar PDF» (usá Guardar como PDF del navegador) |
| Calidad de datos | Meses sin dato por ciudad/año, rachas tratadas y crudas, cobertura mensual, consistencia B/C y B/A, y LOG de limpieza descargable |
| Modo oscuro | Botón ◐ en la cabecera; respeta `prefers-color-scheme` y recuerda la elección |

## Endpoints de la API

| Ruta | Para qué |
|---|---|
| `/api/meta` | Ciudades, tipos, años y años completos |
| `/api/kpis` | Indicadores del último año completo |
| `/api/serie?cats=La Paz,El Alto&desde=2010&hasta=2025&agg=anual` | Series de tiempo tratadas (agregar `crudo=1` para las originales) |
| `/api/ranking?anio=2024` | Toneladas por ciudad (incluye si el año es parcial) |
| `/api/composicion` | Toneladas por tipo de procedencia y año (excluye años incompletos) |
| `/api/heatmap?cat=La Paz` | Matriz mes × año tratada (`crudo=1` para la original) |
| `/api/pronostico?cat=Total&meses=12&modelo=auto` | Backtesting, métricas, residuos y proyección; `modelo` puede ser `auto`, `Holt-Winters`, `SARIMA` o `Regresión lineal` |
| `/api/mapa?anio=2025` | Departamento y burbujas del mapa |
| `/api/ciudad-tipo?ciudad=La Paz` | Ciudad × tipo anual tratado, con `no_reportado`, `anios_incompletos` y `totales` (`crudo=1` para el original) |
| `/api/anomalias?cat=Total` | Hampel local, `ton_final`, mediana, desvíos y serie cruda |
| `/api/correlacion` | Matriz de correlación entre ciudades |
| `/api/faltantes` | Meses sin dato por ciudad/año y rachas tratadas/crudas |
| `/api/cobertura?ciudad=Sucre` | Serie mensual tratada con sus huecos, racha máxima y recorte |
| `/api/consistencia` | Comparaciones B/C, B sin Cobija/C y B/A |
| `/api/limpieza` | LOG de duplicados, exclusiones, recortes y no reportados |
| `/api/limpieza.csv` | LOG descargable en CSV |
| `/api/descargar/<ciudades\|tipos\|ciudad_tipo>.<csv\|xlsx>` | Descarga tratada por defecto; `?crudo=1` para los datos completos con Cobija |

## Para ampliarla (ideas pendientes)

- Autenticación de usuarios y roles
- Comparar contra población o generación per cápita
- Despliegue con Docker y actualización programada de los datos
