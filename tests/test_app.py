import json

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


def test_ciudad_tipo_umbrales():
    t = an.ciudad_tipo_tratado()
    assert t[t.ciudad == "Sucre"].anio.min() == 2015
    assert t[t.ciudad == "Sucre"].anio.max() == 2025
    assert t[t.faltante].ton.isna().all()
    assert t[~t.faltante].ton.notna().all()
    por = t.groupby("ciudad").agg(est=("estimado", "sum"), falt=("faltante", "sum"))
    assert por.loc["Oruro", "falt"] == 3 and por.loc["Santa Cruz", "falt"] == 3
    assert por.loc["Cobija", "est"] == 15
    assert por.loc["El Alto", "est"] == 10
    assert por.loc["Cochabamba", "est"] == 6
    assert por.loc["Trinidad", "est"] == 6
    assert por.loc["Sucre", "est"] == 3
    assert int(t.estimado.sum()) == 40 and int(t.faltante.sum()) == 6


def test_ciudad_tipo_api_tratado_y_crudo():
    c = create_app().test_client()
    d = c.get("/api/ciudad-tipo?ciudad=Sucre").get_json()
    assert d["anios"][0] == 2015 and d["anios"][-1] == 2025
    assert d["imputado"] is True and d["crudo"] is False
    assert not any(v is None for s in d["series"].values() for v in s)
    assert sum(sum(v) for v in d["estimado"].values()) == 3

    crudo = c.get("/api/ciudad-tipo?ciudad=Sucre&crudo=1").get_json()
    assert crudo["anios"][0] == 2010 and crudo["imputado"] is False
    assert sum(v is None for s in crudo["series"].values() for v in s) == 28

    oruro = c.get("/api/ciudad-tipo?ciudad=Oruro").get_json()
    assert sum(v is None for s in oruro["series"].values() for v in s) == 3
    assert sum(sum(v) for v in oruro["faltante"].values()) == 3
    assert oruro["anios_incompletos"] == [2010, 2011, 2012]
    assert oruro["totales"][0] is not None


def test_json_sin_nan():
    c = create_app().test_client()
    urls = ["/api/ciudad-tipo?ciudad=Sucre", "/api/ciudad-tipo?ciudad=Sucre&crudo=1",
            "/api/ciudad-tipo?ciudad=Cobija", "/api/serie?cats=Sucre&agg=mensual",
            "/api/serie?cats=Cobija&agg=mensual&crudo=1", "/api/heatmap?cat=Total",
            "/api/heatmap?cat=Sucre&crudo=1", "/api/ranking?anio=2026",
            "/api/pronostico?cat=Total", "/api/pronostico?cat=Total&modelo=SARIMA",
            "/api/anomalias?cat=Oruro", "/api/correlacion"]

    def falla(x):
        raise ValueError(f"JSON inválido: {x}")

    for url in urls:
        texto = c.get(url).get_data(as_text=True)
        assert "NaN" not in texto, url
        json.loads(texto, parse_constant=falla)


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
    assert len(p["residuos"]["y"]) == len(p["backtest"]["x"]) == 12
    assert set(p["backtest"]["predicciones"]) == {m["modelo"] for m in p["modelos"]}

    forzado = an.pronostico("ciudades", "Total", 12, "SARIMA")
    assert forzado["metodo"] == "SARIMA" and forzado["automatico"] is False
    assert forzado["automatico_metodo"] in set(p["backtest"]["predicciones"])
    assert an.pronostico("ciudades", "Total", 12, "No existe")["automatico"] is True


def test_endpoints():
    c = create_app().test_client()
    for url in ["/", "/comparar", "/pronostico", "/calidad",
                "/api/meta", "/api/kpis", "/api/ranking?anio=2024",
                "/api/composicion", "/api/heatmap?cat=La Paz", "/api/faltantes", "/api/imputacion",
                "/api/serie?cats=La Paz,El Alto&agg=anual", "/api/serie?cats=Sucre&agg=anual",
                "/api/serie?cats=Sucre&agg=anual&crudo=1",
                "/api/pronostico?cat=Total", "/api/pronostico?cat=Total&modelo=SARIMA",
                "/api/descargar/tipos.csv", "/mapa", "/tipos", "/analisis",
                "/simulador", "/aprende", "/reporte/Sucre", "/api/mapa", "/api/ciudad-tipo?ciudad=La Paz",
                "/api/ciudad-tipo?ciudad=Sucre", "/api/ciudad-tipo?ciudad=Sucre&crudo=1",
                "/api/anomalias?cat=Oruro", "/api/correlacion", "/static/data/bolivia.json"]:
        assert c.get(url).status_code == 200, url


def test_admin_eliminado():
    c = create_app().test_client()
    assert c.get("/admin").status_code == 404
    assert c.post("/admin").status_code == 404
