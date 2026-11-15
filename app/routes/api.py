import io

from flask import Blueprint, jsonify, request, send_file

from ..services import analytics as an
from ..services.data_loader import cargar, serie

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
    anual = request.args.get("agg") == "anual"
    out = []
    for c in cats:
        s = serie(ds, c).dropna()
        s = s[(s.index.year >= desde) & (s.index.year <= hasta)]
        if anual:
            s = s.groupby(s.index.year).sum()
            x = [str(i) for i in s.index]
        else:
            x = s.index.strftime("%Y-%m").tolist()
        out.append({"nombre": c, "x": x, "y": s.round(0).tolist()})
    return jsonify(out)


@api.get("/ranking")
def ranking():
    return jsonify(an.ranking(int(request.args.get("anio", 2025))))


@api.get("/composicion")
def composicion():
    return jsonify(an.composicion())


@api.get("/heatmap")
def heatmap():
    return jsonify(an.heatmap(request.args.get("dataset", "ciudades"), request.args.get("cat", "Total")))


@api.get("/pronostico")
def pronostico():
    return jsonify(an.pronostico(request.args.get("dataset", "ciudades"),
                                 request.args.get("cat", "Total"), int(request.args.get("meses", 12))))


@api.get("/faltantes")
def faltantes():
    return jsonify(an.faltantes())


@api.get("/imputacion")
def imputacion():
    ciudad = request.args.get("ciudad", "Sucre")
    s, est = an.imputar_ciudad(ciudad)
    return jsonify({"x": s.index.strftime("%Y-%m").tolist(), "y": s.round(0).tolist(),
                    "estimado": est.tolist()})


@api.get("/descargar/<dataset>.<fmt>")
def descargar(dataset, fmt):
    df = cargar()[dataset]
    buf = io.BytesIO()
    if fmt == "xlsx":
        df.to_excel(buf, index=False)
        mime = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    else:
        buf.write(df.to_csv(index=False).encode("utf-8-sig"))
        mime = "text/csv"
    buf.seek(0)
    return send_file(buf, mimetype=mime, as_attachment=True, download_name=f"{dataset}.{fmt}")


@api.get("/mapa")
def mapa():
    return jsonify(an.mapa(int(request.args.get("anio", 2025))))


@api.get("/ciudad-tipo")
def ciudad_tipo():
    return jsonify(an.ciudad_tipo(request.args.get("ciudad", "La Paz")))


@api.get("/anomalias")
def anomalias():
    return jsonify(an.anomalias(request.args.get("dataset", "ciudades"), request.args.get("cat", "Total")))


@api.get("/correlacion")
def correlacion():
    return jsonify(an.correlacion())
