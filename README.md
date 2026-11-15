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
│   │   ├── pages.py        Páginas HTML (Panel, Comparar, Pronóstico, Mapa, Por tipo, Análisis, Simulador, Calidad, Aprende, Reporte)
│   │   └── api.py          API JSON /api/* y descarga CSV/Excel
│   ├── services/
│   │   ├── data_loader.py  Lee los Excel (salta logos y notas, "n.d." → NaN) y los pasa a formato largo
│   │   └── analytics.py    KPIs, ranking, heatmap, faltantes, imputación de Sucre y pronóstico
│   ├── templates/
│   │   ├── base.html       Cabecera, menú y pie comunes
│   │   ├── panel.html      KPIs, serie de tiempo, ranking, composición por tipo
│   │   ├── comparar.html   Ciudad vs. ciudad y heatmap mes × año
│   │   ├── pronostico.html Proyección con banda de confianza
│   │   └── calidad.html    Mapa de faltantes y Sucre con datos estimados
│   └── static/
│       ├── css/styles.css  Estilos
│       └── js/app.js       Lógica de cada página (fetch a la API + Chart.js)
└── tests/
    └── test_app.py         Verifica la lectura de datos y que cada endpoint responda
```

## Qué incluye

| Página | Contenido |
|---|---|
| Panel | KPIs del último año completo, serie mensual/anual filtrable por ciudad y años, ranking de ciudades, composición por tipo de procedencia |
| Comparar | Varias ciudades a la vez y heatmap de estacionalidad (mes × año) |
| Pronóstico | Holt-Winters (o tendencia + estacionalidad si no hay statsmodels) a 6, 12 o 24 meses |
| Mapa | Mapa de Bolivia con departamentos y burbujas por ciudad, con selector de año |
| Por tipo | Evolución y composición por tipo de procedencia de cada ciudad |
| Análisis | Descomposición tendencia/estacionalidad, meses atípicos y correlación entre ciudades |
| Simulador | Ahorro en toneladas y camiones según el % de reducción por tipo |
| Aprende | Guía de separación de residuos |
| Reporte | `/reporte/<ciudad>` con KPIs, series y pronóstico, listo para imprimir o guardar en PDF |
| Calidad de datos | Meses sin dato por ciudad/año e imputación de Sucre: total anual restante repartido con la estacionalidad de los años completos |

## Endpoints de la API

| Ruta | Para qué |
|---|---|
| `/api/meta` | Ciudades, tipos y años disponibles |
| `/api/kpis` | Indicadores del último año completo |
| `/api/serie?cats=La Paz,El Alto&desde=2010&hasta=2025&agg=anual` | Series de tiempo |
| `/api/ranking?anio=2024` | Toneladas por ciudad |
| `/api/composicion` | Toneladas por tipo de procedencia y año |
| `/api/heatmap?cat=La Paz` | Matriz mes × año |
| `/api/pronostico?cat=Total&meses=12` | Proyección |
| `/api/mapa?anio=2025` | Departamento y burbujas del mapa |
| `/api/ciudad-tipo?ciudad=La Paz` | Ciudad × tipo, anual |
| `/api/anomalias?cat=Total` | Descomposición y meses atípicos |
| `/api/correlacion` | Matriz de correlación entre ciudades |
| `/api/faltantes` | Meses sin dato por ciudad/año |
| `/api/imputacion?ciudad=Sucre` | Serie de Sucre con datos estimados |
| `/api/descargar/<ciudades\|tipos\|ciudad_tipo>.<csv\|xlsx>` | Descarga de datos limpios |

## Para ampliarla (ideas pendientes)

- Subida de nuevos Excel desde un panel de administración
- Asistente con IA que responda preguntas sobre los datos
- Modo oscuro
