from app import create_app
from app.services.data_loader import cargar


def test_datos_cargan():
    d = cargar()
    assert len(d["ciudades"]) > 1000 and "Sucre" in set(d["ciudades"].categoria)
    assert {"Domiciliarios", "Total"} <= set(d["ciudad_tipo"].tipo)


def test_endpoints():
    c = create_app().test_client()
    for url in ["/", "/comparar", "/pronostico", "/calidad", "/api/meta", "/api/kpis", "/api/ranking?anio=2024",
                "/api/composicion", "/api/heatmap?cat=La Paz", "/api/faltantes", "/api/imputacion",
                "/api/serie?cats=La Paz,El Alto&agg=anual", "/api/pronostico?cat=Total", "/api/descargar/tipos.csv", "/mapa", "/tipos", "/analisis", "/simulador", "/aprende",
                "/reporte/Sucre", "/api/mapa", "/api/ciudad-tipo?ciudad=La Paz", "/api/anomalias?cat=Oruro", "/api/correlacion", "/static/data/bolivia.json"]:
        assert c.get(url).status_code == 200, url
