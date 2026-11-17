# Plataforma web de residuos sólidos de Bolivia

Aplicación Flask que lee los Excel del INE (recolección de residuos 2005-2026) y los muestra con gráficas interactivas, comparativas, pronósticos y control de calidad de datos.

## Cómo ejecutarla

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
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
│   │   ├── pages.py        Páginas HTML, subida de Excel y reporte
│   │   └── api.py          API JSON /api/* y descarga CSV/Excel
│   ├── services/
│   │   ├── data_loader.py  Lee los Excel, normaliza y elimina duplicados
│   │   └── analytics.py    KPIs, completitud, imputación, backtesting y anomalías
│   ├── templates/
│   │   ├── base.html       Cabecera, menú, tema y pie comunes
│   │   ├── panel.html      KPIs, serie de tiempo, ranking, composición por tipo
│   │   ├── comparar.html   Ciudad vs. ciudad y heatmap mes × año
│   │   ├── pronostico.html Proyección con backtesting y banda de error real
│   │   ├── calidad.html    Mapa de faltantes y datos estimados por ciudad
│   │   └── admin.html      Subida y validación de nuevos Excel
│   └── static/
│       ├── css/styles.css  Estilos (tema claro/oscuro y estilos de impresión)
│       └── js/app.js       Lógica de cada página (fetch a la API + Chart.js)
└── tests/
    └── test_app.py         Lectura, completitud, pronóstico y endpoints
```

## Criterios de datos

- **Duplicados**: se eliminan las filas repetidas al cargar. El dataset de tipos traía 72 claves `(fecha, tipo)` repetidas en 2021; sumarlas duplicaba ese año.
- **Años incompletos**: los agregados anuales excluyen años con menos de 12 meses de dato (2026 llega hasta junio). La vista mensual sí los muestra y la página Calidad lo explica.
- **Nulos**: por defecto se muestra el dataset tratado; el toggle «Ver datos originales (INE)» permite ver los crudos. En las series mensuales/anuales el tramo inicial sin registro se recorta (Sucre empieza en 2015) y los vacíos interiores se interpolan. En Ciudad × Tipo se aplica la regla de umbrales del notebook: menos de 5% de nulos no se imputa (queda `null` y `faltante: true`), 5%-30% se interpola por ciudad/tipo y Sucre (>30%) se recorta antes de 2015. Las sumas ignoran los `null` y marcan el año como incompleto.
- **Pronóstico**: se reservan los últimos 12 meses y se comparan Holt-Winters, SARIMA y regresión lineal estacional con MAE/MAPE. Se elige el de menor MAE y la banda se calcula con el error del backtesting, no con los residuos del ajuste.

## Qué incluye

| Página | Contenido |
|---|---|
| Panel | KPIs del último año completo, serie mensual/anual filtrable por ciudad y años, ranking de ciudades, composición por tipo de procedencia |
| Comparar | Varias ciudades a la vez y heatmap de estacionalidad (mes × año) |
| Pronóstico | Backtesting de Holt-Winters, SARIMA y regresión lineal; gráficos de real vs. cada modelo, barras MAE/MAPE, residuos y selector de modelo (automático o forzado); banda de confianza fuera de muestra |
| Mapa | Mapa de Bolivia con departamentos y burbujas por ciudad, con selector de año |
| Por tipo | Evolución y composición por tipo de procedencia de cada ciudad |
| Análisis | Descomposición tendencia/estacionalidad, meses atípicos y correlación entre ciudades |
| Simulador | Ahorro en toneladas y camiones según el % de reducción por tipo |
| Aprende | Guía de separación de residuos |
| Reporte | `/reporte/<ciudad>` con KPIs, series y pronóstico; botón «Descargar PDF» (usá Guardar como PDF del navegador) |
| Calidad de datos | Meses sin dato por ciudad/año y datos estimados por ciudad; en Por tipo se explican los umbrales y las celdas sin imputar |
| Datos | Subida de nuevos Excel con clave de administración, validación y respaldo automático |
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
| `/api/ciudad-tipo?ciudad=La Paz` | Ciudad × tipo anual tratado, con `estimado`, `faltante`, `anios_incompletos` y `totales` (`crudo=1` para el original) |
| `/api/anomalias?cat=Total` | Descomposición, meses atípicos y serie cruda |
| `/api/correlacion` | Matriz de correlación entre ciudades |
| `/api/faltantes` | Meses sin dato por ciudad/año |
| `/api/imputacion?ciudad=Sucre` | Serie estimada, recorte y cantidad de meses imputados |
| `/api/descargar/<ciudades\|tipos\|ciudad_tipo>.<csv\|xlsx>` | Descarga de datos limpios |

## Variables de entorno

| Variable | Para qué |
|---|---|
| `ADMIN_PASSWORD` | Habilita la subida de Excel en `/admin`. Sin ella, la subida queda deshabilitada. |

```powershell
$env:ADMIN_PASSWORD = "una-clave-larga"
python run.py
```

## Para ampliarla (ideas pendientes)

- Autenticación de usuarios y roles
- Comparar contra población o generación per cápita
- Despliegue con Docker y actualización programada de los datos
