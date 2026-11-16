from app import create_app
from app.services import analytics as an
from app.services.data_loader import cargar


def test_datos_cargan():
    d = cargar()
    assert len(d["ciudades"]) > 1000 and "Sucre" in set(d["ciudades"].categoria)
    assert {"Domiciliarios", "Total"} <= set(d["ciudad_tipo"].tipo)


def test_sin_duplicados():
    d = cargar()
    assert not d["tipos"].duplicated(["fecha", "categoria"]).any()
    assert not d["tipos_anual"].duplicated(["anio", "categoria"]).any()


def test_composicion_limpia():
    c = an.composicion()
    assert "Total" not in c["series"]
    assert 2026 not in c["anios"] and 2026 in c["excluidos"]
    total_2025 = sum(v[c["anios"].index(2025)] for v in c["series"].values())
    assert 1_550_000 < total_2025 < 1_650_000


def test_sucre_recortado_e_imputado():
    serie, est, recorte = an.imputar_ciudad("Sucre")
    assert recorte == "2015-01"
    assert serie.index[0].year == 2015
    assert int(est.sum()) == 6
    assert not serie.isna().any()


def test_anios_incompletos():
    assert an.meta()["anio_ultimo_completo"] == 2025
    assert 2026 in an.meta()["anios_incompletos"]
    assert an.ranking(2026)["parcial"] is True
    anual = an.serie_anual("ciudades", ["Total"], 2005, 2026)[0]
    assert anual["x"][-1] == "2025" and 2026 in anual["omitidos"]


def test_pronostico_backtesting():
    p = an.pronostico("ciudades", "Total", 12)
    assert {m["modelo"] for m in p["modelos"]} == {"Holt-Winters", "SARIMA", "Regresión lineal"}
    assert p["metodo"] in {m["modelo"] for m in p["modelos"]}
    assert p["banda"] == "error de backtesting"
    assert len(p["pred"]["x"]) == 12
    assert all(m["mae"] >= 0 for m in p["modelos"])


def test_endpoints():
    c = create_app().test_client()
    for url in ["/", "/comparar", "/pronostico", "/calidad", "/admin", "/asistente",
                "/api/meta", "/api/kpis", "/api/ranking?anio=2024",
                "/api/composicion", "/api/heatmap?cat=La Paz", "/api/faltantes", "/api/imputacion",
                "/api/serie?cats=La Paz,El Alto&agg=anual", "/api/serie?cats=Sucre&agg=anual&imputado=1",
                "/api/pronostico?cat=Total", "/api/descargar/tipos.csv", "/mapa", "/tipos", "/analisis",
                "/simulador", "/aprende", "/reporte/Sucre", "/api/mapa", "/api/ciudad-tipo?ciudad=La Paz",
                "/api/ciudad-tipo?ciudad=Sucre&imputado=1", "/api/anomalias?cat=Oruro", "/api/correlacion",
                "/static/data/bolivia.json"]:
        assert c.get(url).status_code == 200, url
    assert c.post("/api/asistente", json={"pregunta": "¿ciudad con más residuos?"}).status_code == 200
