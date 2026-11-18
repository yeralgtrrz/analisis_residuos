import io

from flask import Blueprint, jsonify, request, send_file

from ..services import analytics as an
from ..services import modelo as ml
from ..services.data_loader import serie

api = Blueprint("api", __name__)


@api.get("/meta")
def meta():
    return jsonify(an.meta())


@api.get("/kpis")
def kpis():
    return jsonify(an.kpis())


@api.get("/serie")
def get_serie():
    ds = request.args.get("dataset", "ciudades")
    cats = request.args.get("cats", "Total").split(",")
    desde, hasta = int(request.args.get("desde", 2005)), int(request.args.get("hasta", 2026))
    crudo = request.args.get("crudo") == "1"
    if request.args.get("agg") == "anual":
        return jsonify(an.serie_anual(ds, cats, desde, hasta, crudo))
    out = []
    for c in cats:
        if an._es_cobija(c) and not crudo:
            continue
        s = serie(ds, c)
        recorte = None
        if not crudo:
            s, recorte = an.preparar_serie(s, c)
        elif s.notna().any():
            s = s.loc[s.first_valid_index():]
        s = s[(s.index.year >= desde) & (s.index.year <= hasta)]
        out.append({"nombre": c, "x": s.index.strftime("%Y-%m").tolist(),
                    "y": an._lista(s), "estimados": 0, "recortado_desde": recorte})
    return jsonify(out)


@api.get("/ranking")
def ranking():
    return jsonify(an.ranking(int(request.args.get("anio", 2025))))


@api.get("/composicion")
def composicion():
    return jsonify(an.composicion())


@api.get("/heatmap")
def heatmap():
    return jsonify(an.heatmap(request.args.get("dataset", "ciudades"), request.args.get("cat", "Total"),
                              request.args.get("crudo") == "1"))


@api.get("/pronostico")
def pronostico():
    return jsonify(an.pronostico(request.args.get("dataset", "ciudades"),
                                 request.args.get("cat", "Total"), int(request.args.get("meses", 12)),
                                 request.args.get("modelo", "auto")))


@api.get("/faltantes")
def faltantes():
    return jsonify(an.faltantes())


@api.get("/cobertura")
def cobertura():
    return jsonify(an.cobertura_ciudad(request.args.get("ciudad", "Sucre")))


@api.get("/consistencia")
def consistencia():
    return jsonify(an.consistencia())


@api.get("/limpieza")
@api.get("/log-limpieza")
def limpieza():
    return jsonify(an.log_limpieza())


@api.get("/limpieza.csv")
@api.get("/log-limpieza.csv")
def limpieza_csv():
    import pandas as pd

    buf = io.BytesIO()
    pd.DataFrame(an.log_limpieza()).to_csv(buf, index=False)
    buf.seek(0)
    return send_file(buf, mimetype="text/csv", as_attachment=True,
                     download_name="limpieza.csv")


@api.get("/descargar/<dataset>.<fmt>")
def descargar(dataset, fmt):
    crudo = request.args.get("crudo") == "1"
    try:
        df = an.datos_descarga(dataset, crudo)
    except KeyError:
        return jsonify({"error": "Dataset desconocido"}), 404
    buf = io.BytesIO()
    if fmt == "xlsx":
        df.to_excel(buf, index=False)
        mime = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    else:
        buf.write(df.to_csv(index=False).encode("utf-8-sig"))
        mime = "text/csv"
    buf.seek(0)
    nombre = dataset + ("_crudo" if crudo else "") + "." + fmt
    return send_file(buf, mimetype=mime, as_attachment=True, download_name=nombre)


@api.get("/mapa")
def mapa():
    return jsonify(an.mapa(int(request.args.get("anio", 2025))))


@api.get("/ciudad-tipo")
def ciudad_tipo():
    return jsonify(an.ciudad_tipo(request.args.get("ciudad", "La Paz"),
                                  request.args.get("crudo") == "1"))


@api.get("/anomalias")
def anomalias():
    return jsonify(an.anomalias(request.args.get("dataset", "ciudades"), request.args.get("cat", "Total")))


@api.get("/correlacion")
def correlacion():
    return jsonify(an.correlacion())


@api.get("/predecir")
def predecir():
    try:
        meses = min(24, max(1, int(request.args.get("meses", 12))))
        return jsonify(ml.predecir(request.args.get("ciudad", "La Paz"), meses))
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@api.get("/modelos")
def modelos():
    datos = ml.metricas()
    if datos is None:
        return jsonify({"error": "El modelo todavía no fue entrenado."}), 503
    return jsonify(datos)


@api.get("/perfiles")
def perfiles():
    datos = ml.perfiles()
    if datos is None:
        return jsonify({"error": "Los perfiles todavía no fueron entrenados."}), 503
    return jsonify(datos)


@api.get("/alerta")
def alerta():
    ciudad = request.args.get("ciudad")
    datos = ml.alerta(ciudad) if ciudad else ml.alerta_global()
    if datos is None:
        return jsonify({"error": "El clasificador de picos no está disponible."}), 503
    return jsonify(datos)
