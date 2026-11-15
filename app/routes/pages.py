from flask import Blueprint, render_template

pages = Blueprint("pages", __name__)

PAGINAS = [("panel", "/", "Panel"), ("comparar", "/comparar", "Comparar"),
           ("pronostico", "/pronostico", "Pronóstico"), ("mapa", "/mapa", "Mapa"), ("tipos", "/tipos", "Por tipo"),
           ("analisis", "/analisis", "Análisis"), ("simulador", "/simulador", "Simulador"),
           ("calidad", "/calidad", "Calidad"), ("aprende", "/aprende", "Aprende")]


def _p(nombre, **kw):
    return render_template(f"{nombre}.html", paginas=PAGINAS, actual=nombre, **kw)


@pages.get("/")
def panel():
    return _p("panel")


@pages.get("/comparar")
def comparar():
    return _p("comparar")


@pages.get("/pronostico")
def pronostico():
    return _p("pronostico")


@pages.get("/calidad")
def calidad():
    return _p("calidad")


for _id in ("mapa", "tipos", "analisis", "simulador", "aprende"):
    pages.add_url_rule(f"/{_id}", _id, (lambda i: lambda: _p(i))(_id))


@pages.get("/reporte/<ciudad>")
def reporte(ciudad):
    return _p("reporte", ciudad=ciudad)
