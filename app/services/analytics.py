"""Cálculos: KPIs, rankings, heatmap, calidad de datos, imputación y pronóstico."""
import numpy as np
import pandas as pd

from .data_loader import cargar, serie


def meta():
    d = cargar()
    return {"ciudades": [c for c in d["ciudades"].categoria.unique() if c != "Total"],
            "tipos": [c for c in d["tipos"].categoria.unique() if c != "Total"],
            "anios": sorted(d["ciudades"].fecha.dt.year.unique().tolist())}


def kpis():
    d = cargar()["ciudades"]
    t = d[d.categoria == "Total"].dropna(subset=["ton"])
    por_anio = t.groupby(t.fecha.dt.year).ton.agg(["sum", "count"])
    completos = por_anio[por_anio["count"] == 12]
    ult, prev = completos.index[-1], completos.index[-2]
    c = d[(d.categoria != "Total") & (d.fecha.dt.year == ult)].groupby("categoria").ton.sum()
    mes_pico = t[t.fecha.dt.year == ult].sort_values("ton").iloc[-1]
    return {"anio": int(ult), "total": float(completos.loc[ult, "sum"]),
            "variacion": float(completos.loc[ult, "sum"] / completos.loc[prev, "sum"] - 1),
            "ciudad_top": c.idxmax(), "ciudad_top_ton": float(c.max()),
            "mes_pico": mes_pico.fecha.strftime("%Y-%m"), "mes_pico_ton": float(mes_pico.ton)}


def ranking(anio):
    d = cargar()["ciudades"]
    d = d[(d.categoria != "Total") & (d.fecha.dt.year == anio)]
    r = d.groupby("categoria").ton.sum().sort_values(ascending=False)
    return {"labels": r.index.tolist(), "values": r.round(0).tolist()}


def heatmap(dataset, cat):
    s = serie(dataset, cat).dropna()
    p = s.groupby([s.index.year, s.index.month]).sum().unstack()
    return {"anios": p.index.tolist(), "meses": p.columns.tolist(),
            "valores": p.round(0).where(p.notna(), None).values.tolist()}


def composicion():
    d = cargar()["tipos_anual"]
    d = d[d.categoria != "Total"]
    p = d.pivot_table(index="anio", columns="categoria", values="ton")
    return {"anios": p.index.tolist(),
            "series": {c: p[c].round(0).where(p[c].notna(), None).tolist() for c in p}}


def faltantes():
    """Meses sin dato por ciudad y año (n.d. o vacío)."""
    d = cargar()["ciudades"]
    d = d[d.categoria != "Total"].copy()
    d["falta"] = d.ton.isna()
    p = d.pivot_table(index="categoria", columns=d.fecha.dt.year, values="falta", aggfunc="sum")
    return {"ciudades": p.index.tolist(), "anios": p.columns.tolist(),
            "valores": p.fillna(0).astype(int).values.tolist()}


def imputar_ciudad(ciudad="Sucre"):
    """Rellena meses faltantes: (total anual − meses conocidos) repartido con la
    estacionalidad de los años completos. Devuelve la serie y una máscara de estimados."""
    d = cargar()
    s = serie("ciudades", ciudad)
    anual = d["ciudades_anual"].query("categoria == @ciudad").set_index("anio").ton
    comp = s.groupby(s.index.year).filter(lambda x: x.notna().all() and len(x) == 12)
    pesos = (comp / comp.groupby(comp.index.year).transform("sum")).groupby(comp.index.month).mean()
    est = pd.Series(False, index=s.index)
    out = s.copy()
    for anio, g in s.groupby(s.index.year):
        falt = g[g.isna()].index
        if len(falt) == 0 or pd.isna(anual.get(anio)):
            continue
        resto = max(anual[anio] - g.sum(), 0)
        w = pesos.reindex(falt.month).values
        out[falt] = resto * w / w.sum()
        est[falt] = True
    return out, est


def pronostico(dataset, cat, meses=12):
    s = serie(dataset, cat).dropna().asfreq("MS").interpolate()
    try:
        from statsmodels.tsa.holtwinters import ExponentialSmoothing
        m = ExponentialSmoothing(s, trend="add", damped_trend=True, seasonal="add",
                                 seasonal_periods=12).fit()
        pred, resid, metodo = m.forecast(meses), m.resid, "Holt-Winters"
    except Exception:  # sin statsmodels: tendencia lineal reciente + estacionalidad
        r = s[-36:]
        x = np.arange(len(r))
        a, b = np.polyfit(x, r.values, 1)
        estac = (r - (a * x + b)).groupby(r.index.month).mean()
        idx = pd.date_range(s.index[-1] + pd.offsets.MonthBegin(), periods=meses, freq="MS")
        pred = pd.Series([a * (len(r) + i) + b + estac[d.month] for i, d in enumerate(idx)], index=idx)
        resid, metodo = r - (a * x + b) - r.index.month.map(estac).values, "Tendencia + estacionalidad"
    e = float(np.nanstd(resid))
    return {"metodo": metodo,
            "hist": {"x": s.index.strftime("%Y-%m").tolist()[-60:], "y": s.round(0).tolist()[-60:]},
            "pred": {"x": pred.index.strftime("%Y-%m").tolist(), "y": pred.round(0).tolist(),
                     "min": (pred - 1.96 * e).round(0).tolist(), "max": (pred + 1.96 * e).round(0).tolist()}}


COORDS = {"Sucre": (-65.26, -19.04), "La Paz": (-68.13, -16.50), "Cochabamba": (-66.16, -17.39),
          "Oruro": (-67.11, -17.97), "Potosí": (-65.75, -19.58), "Tarija": (-64.73, -21.53),
          "Santa Cruz": (-63.18, -17.78), "Trinidad": (-64.90, -14.83), "Cobija": (-68.77, -11.03),
          "El Alto": (-68.25, -16.52)}


def mapa(anio):
    r = ranking(anio)
    return [{"ciudad": c, "ton": t, "lon": COORDS[c][0], "lat": COORDS[c][1]}
            for c, t in zip(r["labels"], r["values"]) if c in COORDS]


def ciudad_tipo(ciudad):
    d = cargar()["ciudad_tipo"]
    d = d[(d.ciudad.str.lower() == ciudad.lower()) & (d.tipo != "Total")]
    p = d.pivot_table(index="anio", columns="tipo", values="ton", dropna=False)
    return {"anios": p.index.tolist(),
            "series": {c: p[c].round(0).where(p[c].notna(), None).tolist() for c in p}}


def anomalias(dataset, cat, umbral=2.5):
    """Descomposición simple (tendencia 12m, estacionalidad, residuo) y meses atípicos."""
    s = serie(dataset, cat).dropna().asfreq("MS").interpolate()
    tend = s.rolling(12, center=True, min_periods=6).mean()
    estac = (s - tend).groupby(s.index.month).transform("mean")
    res = s - tend - estac
    z = res / res.std()
    idx = z.abs() > umbral
    f = lambda x: x.round(0).where(x.notna(), None).tolist()
    return {"x": s.index.strftime("%Y-%m").tolist(), "y": f(s), "tendencia": f(tend), "estacional": f(estac),
            "anomalias": [{"mes": d.strftime("%Y-%m"), "ton": round(float(s[d])), "z": round(float(z[d]), 1)}
                          for d in s.index[idx]]}


def correlacion():
    d = cargar()["ciudades"]
    p = d[d.categoria != "Total"].pivot_table(index="fecha", columns="categoria", values="ton")
    c = p.diff().corr()
    return {"ciudades": c.columns.tolist(), "valores": c.round(2).where(c.notna(), None).values.tolist()}
