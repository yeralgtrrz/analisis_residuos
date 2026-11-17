import secrets
import shutil
from datetime import datetime

from flask import Blueprint, render_template, request

from config import ADMIN_PASSWORD, ARCHIVOS, RAW

from ..services import analytics as an
from ..services.data_loader import cargar

pages = Blueprint("pages", __name__)

PAGINAS = [("panel", "/", "Panel"), ("comparar", "/comparar", "Comparar"),
           ("pronostico", "/pronostico", "Pronóstico"), ("mapa", "/mapa", "Mapa"), ("tipos", "/tipos", "Por tipo"),
           ("analisis", "/analisis", "Análisis"), ("simulador", "/simulador", "Simulador"),
           ("calidad", "/calidad", "Calidad"), ("aprende", "/aprende", "Aprende"),
           ("admin", "/admin", "Datos")]

COLUMNAS = {"ciudades": {"fecha", "categoria", "ton"}, "ciudades_anual": {"anio", "categoria", "ton"},
            "tipos": {"fecha", "categoria", "ton"}, "tipos_anual": {"anio", "categoria", "ton"},
            "ciudad_tipo": {"anio", "tipo", "ciudad", "ton"}}


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


@pages.get("/admin")
def admin():
    return _p("admin", habilitado=bool(ADMIN_PASSWORD), mensaje=None, error=None)


@pages.post("/admin")
def admin_subir():
    if not ADMIN_PASSWORD:
        return _p("admin", habilitado=False, mensaje=None,
                  error="Definí la variable de entorno ADMIN_PASSWORD para habilitar la subida."), 403
    if not secrets.compare_digest(request.form.get("clave", ""), ADMIN_PASSWORD):
        return _p("admin", habilitado=True, mensaje=None, error="Clave incorrecta."), 403

    activos = {k: f for k in ARCHIVOS if (f := request.files.get(k)) and f.filename}
    if not activos:
        return _p("admin", habilitado=True, mensaje=None, error="No elegiste ningún archivo."), 400
    for k, f in activos.items():
        if not f.filename.lower().endswith(".xlsx"):
            return _p("admin", habilitado=True, mensaje=None,
                      error=f"{k}: solo se aceptan archivos .xlsx"), 400

    respaldo = RAW / "backup" / datetime.now().strftime("%Y%m%d-%H%M%S")
    respaldo.mkdir(parents=True, exist_ok=True)
    copias = {}
    try:
        for k, f in activos.items():
            destino = ARCHIVOS[k]
            if destino.exists():
                shutil.copy2(destino, respaldo / destino.name)
                copias[destino] = respaldo / destino.name
            f.save(destino)
        cargar.cache_clear()
        an.pronostico.cache_clear()
        an.ciudad_tipo_tratado.cache_clear()
        datos = cargar()
        for nombre, df in datos.items():
            if df.empty or not COLUMNAS[nombre] <= set(df.columns):
                raise ValueError(f"{nombre} no tiene el formato esperado")
    except Exception as e:
        for destino, copia in copias.items():
            shutil.copy2(copia, destino)
        cargar.cache_clear()
        an.pronostico.cache_clear()
        an.ciudad_tipo_tratado.cache_clear()
        return _p("admin", habilitado=True, mensaje=None,
                  error=f"No se pudo leer el Excel; se restauraron los datos anteriores: {e}"), 400

    nombres = ", ".join(activos)
    return _p("admin", habilitado=True, error=None,
              mensaje=f"Datos actualizados ({nombres}). Respaldo en data/raw/backup/{respaldo.name}.")
