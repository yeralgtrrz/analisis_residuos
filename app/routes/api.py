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
    crudo = request.args.get("crudo") == "1"
    if request.args.get("agg") == "anual":
        return jsonify(an.serie_anual(ds, cats, desde, hasta, crudo))
    out = []
    for c in cats:
        s = serie(ds, c)
        estimados, recorte = 0, None
        if not crudo:
            s, est, recorte = an.imputar_serie(s)
            estimados = int(est.sum())
        elif s.notna().any():
            s = s.loc[s.first_valid_index():]
        s = s[(s.index.year >= desde) & (s.index.year <= hasta)]
        out.append({"nombre": c, "x": s.index.strftime("%Y-%m").tolist(),
                    "y": an._lista(s), "estimados": estimados, "recortado_desde": recorte})
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


@api.get("/imputacion")
def imputacion():
    ciudad = request.args.get("ciudad", "Sucre")
    s, est, recorte = an.imputar_ciudad(ciudad)
    return jsonify({"x": s.index.strftime("%Y-%m").tolist(), "y": an._lista(s),
                    "estimado": est.tolist(), "recortado_desde": recorte,
                    "n_estimados": int(est.sum()), "metodo": "interpolación lineal"})


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
    return jsonify(an.ciudad_tipo(request.args.get("ciudad", "La Paz"),
                                  request.args.get("crudo") == "1"))


@api.get("/anomalias")
def anomalias():
    return jsonify(an.anomalias(request.args.get("dataset", "ciudades"), request.args.get("cat", "Total")))


@api.get("/correlacion")
def correlacion():
    return jsonify(an.correlacion())
