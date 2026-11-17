"""Cálculos: KPIs, rankings, heatmap, calidad de datos, outliers y pronóstico."""
import warnings
from functools import lru_cache

import numpy as np
import pandas as pd

from config import COBIJA, CORTE
from .data_loader import cargar, log_carga, serie

UMBRAL_COMPLETO = 12
ANIO_CORTE_SUCRE = 2015
CORTE_FECHA = pd.Timestamp(CORTE)


def _lista(s, dec=0):
    """Convierte una serie a lista JSON sin NaN (los nulos pasan como None)."""
    return [None if pd.isna(v) else float(round(v, dec)) for v in s]


def _matriz(df, dec=0):
    return [_lista(fila, dec) for fila in df.values]


def _sin_cobija(d):
    if COBIJA != "excluir" or d.empty:
        return d
    return d[d.categoria.str.lower() != "cobija"]


def _es_cobija(categoria):
    return COBIJA == "excluir" and str(categoria).lower() == "cobija"


def _ventana(s, categoria):
    """Recorta Sucre antes de 2015 y el tramo inicial sin dato; conserva huecos."""
    s = s.sort_index()
    s = s[~s.index.duplicated(keep="first")]
    if str(categoria).lower() == "sucre":
        s = s[s.index >= pd.Timestamp(ANIO_CORTE_SUCRE, 1, 1)]
    if not s.notna().any():
        return s, None
    primero = s.first_valid_index()
    recorte = None
    if primero > s.index[0]:
        recorte = primero.strftime("%Y-%m")
        s = s.loc[primero:]
    return s, recorte


def preparar_serie(s, categoria):
    """Serie mensual tratada: sin interpolación, con los nulos eliminados."""
    if _es_cobija(categoria):
        return pd.Series(dtype=float), None
    s, recorte = _ventana(s, categoria)
    return s.dropna(), recorte


def _racha(s):
    """Racha máxima de meses consecutivos sin dato y sus extremos."""
    s = s.sort_index().asfreq("MS")
    mejor = actual = 0
    inicio = fin = mejor_ini = mejor_fin = None
    for fecha, falta in s.isna().items():
        if falta:
            if actual == 0:
                inicio = fecha
            actual += 1
            fin = fecha
            if actual > mejor:
                mejor, mejor_ini, mejor_fin = actual, inicio, fin
        else:
            actual = 0
    return mejor, mejor_ini, mejor_fin


# --------------------------------------------------------------------------- #
# Completitud temporal
# --------------------------------------------------------------------------- #
def _anual(s):
    """Suma anual y cantidad de meses con dato por año (antes de descartar nulos)."""
    meses = s.notna().groupby(s.index.year).sum()
    total = s.groupby(s.index.year).sum(min_count=1)
    return total, meses


def meses_por_anio(dataset, categoria="Total"):
    _, meses = _anual(serie(dataset, categoria))
    return {int(a): int(m) for a, m in meses.items()}


def anios_completos(dataset, categoria="Total"):
    _, meses = _anual(serie(dataset, categoria))
    return [int(a) for a in meses[meses >= UMBRAL_COMPLETO].index]


def anios_incompletos(dataset, categoria="Total"):
    _, meses = _anual(serie(dataset, categoria))
    return [int(a) for a in meses[meses < UMBRAL_COMPLETO].index]


def meta():
    d = cargar()
    completos = anios_completos("ciudades", "Total")
    ciudades = _sin_cobija(d["ciudades"])
    return {"ciudades": [c for c in ciudades.categoria.unique() if c.lower() != "total"],
            "tipos": [c for c in d["tipos"].categoria.unique() if c.lower() != "total"],
            "anios": sorted(int(a) for a in d["ciudades"].fecha.dt.year.unique()),
            "anios_completos": completos,
            "anio_ultimo_completo": completos[-1] if completos else None,
            "anios_incompletos": anios_incompletos("ciudades", "Total")}


# --------------------------------------------------------------------------- #
# KPIs y agregados
# --------------------------------------------------------------------------- #
def kpis():
    d = _sin_cobija(cargar()["ciudades"])
    t = d[d.categoria.str.lower() == "total"].dropna(subset=["ton"])
    por_anio = t.groupby(t.fecha.dt.year).ton.agg(["sum", "count"])
    completos = por_anio[por_anio["count"] == UMBRAL_COMPLETO]
    ult, prev = completos.index[-1], completos.index[-2]
    c = d[(d.categoria.str.lower() != "total") & (d.fecha.dt.year == ult)].groupby("categoria").ton.sum()
    mes_pico = t[t.fecha.dt.year == ult].sort_values("ton").iloc[-1]
    return {"anio": int(ult), "total": float(completos.loc[ult, "sum"]),
            "variacion": float(completos.loc[ult, "sum"] / completos.loc[prev, "sum"] - 1),
            "ciudad_top": c.idxmax(), "ciudad_top_ton": float(c.max()),
            "mes_pico": mes_pico.fecha.strftime("%Y-%m"), "mes_pico_ton": float(mes_pico.ton)}


def ranking(anio):
    anio = int(anio)
    d = _sin_cobija(cargar()["ciudades"])
    d = d[(d.categoria.str.lower() != "total") & (d.fecha.dt.year == anio)]
    r = d.groupby("categoria").ton.sum(min_count=1).sort_values(ascending=False)
    return {"labels": r.index.tolist(), "values": _lista(r),
            "parcial": anio in anios_incompletos("ciudades", "Total")}


def composicion():
    d = cargar()["tipos_anual"]
    d = d[d.categoria.str.lower() != "total"]
    excluidos = anios_incompletos("tipos", "Total")
    d = d[~d.anio.isin(excluidos)]
    p = d.pivot_table(index="anio", columns="categoria", values="ton", aggfunc="sum")
    return {"anios": [int(a) for a in p.index],
            "series": {c: _lista(p[c]) for c in p},
            "excluidos": excluidos}


def serie_anual(dataset, cats, desde, hasta, crudo=False):
    """Series anuales sin interpolar; se omiten años con menos de 12 meses con dato."""
    out = []
    for c in cats:
        if _es_cobija(c):
            continue
        s = serie(dataset, c)
        recorte = None
        if not crudo:
            s, recorte = preparar_serie(s, c)
        s = s[(s.index.year >= desde) & (s.index.year <= hasta)]
        total, meses = _anual(s)
        ok = meses[meses >= UMBRAL_COMPLETO]
        filtrado = total.reindex(ok.index)
        out.append({"nombre": c, "x": [str(int(a)) for a in filtrado.index],
                    "y": _lista(filtrado),
                    "omitidos": [int(a) for a in meses[meses < UMBRAL_COMPLETO].index],
                    "estimados": 0, "recortado_desde": recorte})
    return out


def heatmap(dataset, cat, crudo=False):
    if _es_cobija(cat):
        return {"anios": [], "meses": list(range(1, 13)), "valores": []}
    s = serie(dataset, cat)
    if not crudo:
        s = preparar_serie(s, cat)[0]
    p = s.groupby([s.index.year, s.index.month]).sum(min_count=1).unstack()
    p = p.reindex(columns=range(1, 13))
    return {"anios": [int(a) for a in p.index], "meses": [int(m) for m in p.columns],
            "valores": _matriz(p)}

# --------------------------------------------------------------------------- #
# Nulos: series mensuales sin imputación y tratamiento de Ciudad x Tipo
# --------------------------------------------------------------------------- #
@lru_cache(maxsize=1)
def ciudades_tratado():
    """B tratado: sin Cobija, Sucre desde 2015 y sin filas nulas."""
    d = cargar()["ciudades"].copy()
    if COBIJA == "excluir":
        d = d[d.categoria.str.lower() != "cobija"]
    d = d[~((d.categoria == "Sucre") & (d.fecha < pd.Timestamp(ANIO_CORTE_SUCRE, 1, 1)))]
    return d.dropna(subset=["ton"]).reset_index(drop=True)


def cobertura_ciudad(ciudad="Sucre"):
    """Serie mensual tratada con sus huecos, sin interpolar."""
    if _es_cobija(ciudad):
        return {"x": [], "y": [], "n_huecos": 0, "racha_max": None,
                "inicio_racha": None, "fin_racha": None, "recortado_desde": None,
                "excluida": True}
    s, recorte = _ventana(serie("ciudades", ciudad), ciudad)
    s = s.asfreq("MS")
    racha, ini, fin = _racha(s)
    return {"x": s.index.strftime("%Y-%m").tolist(), "y": _lista(s),
            "n_huecos": int(s.isna().sum()), "racha_max": racha,
            "inicio_racha": ini.strftime("%Y-%m") if ini is not None else None,
            "fin_racha": fin.strftime("%Y-%m") if fin is not None else None,
            "recortado_desde": recorte, "excluida": False}


def faltantes():
    """Meses sin dato por ciudad/año y rachas tratadas y crudas."""
    raw = cargar()["ciudades"]
    raw = raw[raw.categoria.str.lower() != "total"].copy()
    d = _sin_cobija(raw)
    d["falta"] = d.ton.isna()
    p = d.pivot_table(index="categoria", columns=d.fecha.dt.year, values="falta", aggfunc="sum")

    rachas = []
    for ciudad in sorted(raw.categoria.unique()):
        s_raw = raw[raw.categoria == ciudad].set_index("fecha").ton
        crudo, crudo_ini, crudo_fin = _racha(s_raw)
        if _es_cobija(ciudad):
            tratada = trat_ini = trat_fin = None
            anios = []
            excluida = True
        else:
            s_trat, _ = _ventana(s_raw, ciudad)
            s_trat = s_trat.asfreq("MS")
            tratada, trat_ini, trat_fin = _racha(s_trat)
            anios = sorted(int(a) for a in s_trat.index[s_trat.isna()].year.unique())
            excluida = False
        rachas.append({
            "ciudad": ciudad, "tratada": tratada,
            "inicio_tratada": trat_ini.strftime("%Y-%m") if trat_ini is not None else None,
            "fin_tratada": trat_fin.strftime("%Y-%m") if trat_fin is not None else None,
            "cruda": crudo,
            "inicio_cruda": crudo_ini.strftime("%Y-%m") if crudo_ini is not None else None,
            "fin_cruda": crudo_fin.strftime("%Y-%m") if crudo_fin is not None else None,
            "anios_afectados": anios, "excluida": excluida})

    return {"ciudades": p.index.tolist(), "anios": [int(a) for a in p.columns],
            "valores": p.fillna(0).astype(int).values.tolist(), "rachas": rachas}


@lru_cache(maxsize=1)
def ciudad_tipo_tratado():
    """A tratado como en el notebook: no reportado = 0, sin imputar."""
    d = cargar()["ciudad_tipo"].copy()
    d = d[d.tipo.str.lower() != "total"].copy()
    if COBIJA == "excluir":
        d = d[d.ciudad.str.lower() != "cobija"]
    d = d[~((d.ciudad == "Sucre") & (d.anio < ANIO_CORTE_SUCRE))].copy()
    d["no_reportado"] = d.ton.isna()
    d["ton"] = d.ton.fillna(0)
    d["estimado"] = False
    d["faltante"] = False
    return d.reset_index(drop=True)


def ciudad_tipo(ciudad, crudo=False):
    if _es_cobija(ciudad):
        return {"anios": [], "series": {}, "estimado": {}, "faltante": {},
                "no_reportado": {}, "anios_incompletos": [], "totales": [],
                "imputado": False, "crudo": crudo, "tratado": not crudo}
    d = cargar()["ciudad_tipo"] if crudo else ciudad_tipo_tratado()
    d = d[(d.ciudad.str.lower() == ciudad.lower()) & (d.tipo.str.lower() != "total")]
    p = d.pivot_table(index="anio", columns="tipo", values="ton", dropna=False).sort_index()
    p = p.reindex(columns=sorted(p.columns))

    if crudo:
        estimado = {c: [False] * len(p) for c in p.columns}
        no_reportado = {c: p[c].isna().tolist() for c in p.columns}
        faltante = {c: p[c].isna().tolist() for c in p.columns}
        incompletos = [int(a) for a in p.index if p.loc[a].isna().any()]
    else:
        nr = d.pivot_table(index="anio", columns="tipo", values="no_reportado",
                           aggfunc="first", dropna=False).reindex(p.index)
        nr = nr.reindex(columns=p.columns).fillna(False).astype(bool)
        no_reportado = {c: nr[c].tolist() for c in p.columns}
        estimado = {c: [False] * len(p) for c in p.columns}
        faltante = {c: [False] * len(p) for c in p.columns}
        incompletos = []

    totales = []
    for a in p.index:
        valores = p.loc[a].dropna()
        totales.append(float(round(valores.sum())) if len(valores) else None)

    return {"anios": [int(a) for a in p.index],
            "series": {c: _lista(p[c]) for c in p.columns},
            "estimado": estimado,
            "faltante": faltante,
            "no_reportado": no_reportado,
            "anios_incompletos": incompletos,
            "totales": totales,
            "imputado": False,
            "crudo": crudo,
            "tratado": not crudo}


# --------------------------------------------------------------------------- #
# Pronóstico con backtesting (Holt-Winters, SARIMA y regresión estacional)
# --------------------------------------------------------------------------- #
def _regresion(s, pasos, t0=0):
    m = 2 * np.pi * s.index.month.values / 12
    X = np.column_stack([np.ones(len(s)), np.arange(len(s)) + t0,
                         np.sin(m), np.cos(m), np.sin(2 * m), np.cos(2 * m)])
    coef, *_ = np.linalg.lstsq(X, s.values.astype(float), rcond=None)
    futuro = pd.date_range(s.index[-1] + pd.offsets.MonthBegin(), periods=pasos, freq="MS")
    mf = 2 * np.pi * futuro.month.values / 12
    Xf = np.column_stack([np.ones(len(futuro)), np.arange(len(futuro)) + t0 + len(s),
                          np.sin(mf), np.cos(mf), np.sin(2 * mf), np.cos(2 * mf)])
    return Xf @ coef


def _ajustar(nombre, s, pasos):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        if nombre == "Holt-Winters":
            from statsmodels.tsa.holtwinters import ExponentialSmoothing
            m = ExponentialSmoothing(s, trend="add", damped_trend=True, seasonal="add",
                                     seasonal_periods=12, initialization_method="estimated").fit()
            return np.asarray(m.forecast(pasos), float)
        if nombre == "SARIMA":
            from statsmodels.tsa.statespace.sarimax import SARIMAX
            m = SARIMAX(s, order=(1, 1, 1), seasonal_order=(1, 1, 0, 12),
                        enforce_stationarity=False, enforce_invertibility=False).fit(disp=False)
            return np.asarray(m.forecast(pasos), float)
        return np.asarray(_regresion(s, pasos), float)


def _mae(real, pred):
    return float(np.nanmean(np.abs(np.asarray(real, float) - np.asarray(pred, float))))


def _mape(real, pred):
    real, pred = np.asarray(real, float), np.asarray(pred, float)
    ok = real != 0
    return float(np.nanmean(np.abs((real[ok] - pred[ok]) / real[ok])) * 100) if ok.any() else float("nan")


NOMBRES = ("Holt-Winters", "SARIMA", "Regresión lineal")


@lru_cache(maxsize=128)
def pronostico(dataset, cat, meses=12, modelo="auto"):
    if _es_cobija(cat):
        raise ValueError("Cobija se excluye del pronóstico.")
    raw = serie(dataset, cat)
    s = preparar_serie(raw, cat)[0]
    s = s.asfreq("MS").interpolate(limit_direction="both")
    meses = int(meses)
    if len(s) < 36:
        raise ValueError("La serie es demasiado corta para pronosticar.")

    entreno, prueba = s[s.index < CORTE_FECHA], s[s.index >= CORTE_FECHA]
    if len(entreno) < 36 or prueba.empty:
        raise ValueError("No hay suficientes datos antes y después del corte 2023.")
    comparacion, predicciones, errores = [], {}, {}
    for nombre in NOMBRES:
        try:
            pred = _ajustar(nombre, entreno, len(prueba))
            err = np.asarray(prueba, float) - pred
            errores[nombre] = err
            predicciones[nombre] = pred
            mape = _mape(prueba, pred)
            comparacion.append({"modelo": nombre, "mae": round(_mae(prueba, pred), 1),
                                "mape": round(mape, 1) if np.isfinite(mape) else None})
        except Exception:
            continue
    if not comparacion:
        raise ValueError("Ningún modelo pudo ajustarse a la serie.")

    automatico = min(comparacion, key=lambda m: m["mae"])["modelo"]
    pedido = modelo if modelo in predicciones else "auto"
    elegido = automatico if pedido == "auto" else pedido
    pred = _ajustar(elegido, s, meses)
    idx = pd.date_range(s.index[-1] + pd.offsets.MonthBegin(), periods=meses, freq="MS")
    sigma = float(np.nanstd(errores[elegido]))
    if not np.isfinite(sigma) or sigma == 0:
        sigma = float(np.nanstd(s)) or 1.0

    residuos = np.asarray(prueba, float) - np.asarray(predicciones[elegido], float)
    raw = raw.reindex(s.index)
    return {"metodo": elegido,
            "automatico": pedido == "auto",
            "modelo_solicitado": modelo,
            "automatico_metodo": automatico,
            "corte": CORTE_FECHA.strftime("%Y-%m"),
            "banda": "error de backtesting",
            "modelos": comparacion,
            "backtest": {"x": prueba.index.strftime("%Y-%m").tolist(),
                         "real": _lista(prueba),
                         "predicciones": {k: _lista(v) for k, v in predicciones.items()}},
            "residuos": {"x": prueba.index.strftime("%Y-%m").tolist(), "y": _lista(residuos)},
            "hist": {"x": s.index.strftime("%Y-%m").tolist()[-60:], "y": _lista(s)[-60:]},
            "hist_crudo": {"x": raw.index.strftime("%Y-%m").tolist()[-60:],
                           "y": _lista(raw)[-60:]},
            "pred": {"x": idx.strftime("%Y-%m").tolist(), "y": _lista(pred),
                     "min": _lista(pred - 1.96 * sigma),
                     "max": _lista(pred + 1.96 * sigma)}}


def detectar_local(s, ventana=13, k=4.0):
    """Hampel local en log: mediana móvil y MAD de 13 observaciones."""
    s = s.sort_index().astype(float)
    ls = np.log(s.where(s > 0))
    med = ls.rolling(ventana, center=True, min_periods=5).median()
    mad = ((ls - med).abs().rolling(ventana, center=True, min_periods=5)
           .median() * 1.4826).clip(lower=1e-9)
    out = (ls - med).abs() > k * mad
    final = s.where(~out, s.clip(lower=np.exp(med - k * mad), upper=np.exp(med + k * mad)))
    mediana = np.exp(med)
    desvio = (s / mediana - 1) * 100
    return out.fillna(False), final, mediana, desvio


def anomalias(dataset, cat):
    """Outliers locales (Hampel) y winsorización local sobre la serie tratada."""
    if _es_cobija(cat):
        return {"x": [], "y": [], "y_crudo": [], "ton_final": [], "mediana_local": [],
                "out_local": [], "desvio_pct": [], "anomalias": []}
    s, _ = preparar_serie(serie(dataset, cat), cat)
    crudo = serie(dataset, cat).reindex(s.index)
    out, final, mediana, desvio = detectar_local(s)
    anomalias = [{"mes": d.strftime("%Y-%m"),
                  "ton": round(float(s[d])),
                  "ton_final": round(float(final[d])),
                  "mediana": round(float(mediana[d])),
                  "desvio_pct": round(float(desvio[d]), 1)}
                 for d in s.index[out]]
    f = _lista
    return {"x": s.index.strftime("%Y-%m").tolist(), "y": f(s), "y_crudo": f(crudo),
            "ton_final": f(final), "mediana_local": f(mediana),
            "out_local": out.tolist(), "desvio_pct": _lista(desvio, 1),
            "anomalias": anomalias}


# --------------------------------------------------------------------------- #
# Mapa y correlación
# --------------------------------------------------------------------------- #
COORDS = {"Sucre": (-65.26, -19.04), "La Paz": (-68.13, -16.50), "Cochabamba": (-66.16, -17.39),
          "Oruro": (-67.11, -17.97), "Potosí": (-65.75, -19.58), "Tarija": (-64.73, -21.53),
          "Santa Cruz": (-63.18, -17.78), "Trinidad": (-64.90, -14.83), "Cobija": (-68.77, -11.03),
          "El Alto": (-68.25, -16.52)}


def mapa(anio):
    r = ranking(anio)
    return [{"ciudad": c, "ton": t, "lon": COORDS[c][0], "lat": COORDS[c][1]}
            for c, t in zip(r["labels"], r["values"]) if c in COORDS and t is not None]


def correlacion():
    d = _sin_cobija(cargar()["ciudades"])
    p = d[d.categoria.str.lower() != "total"].pivot_table(index="fecha", columns="categoria", values="ton")
    c = p.diff().corr()
    return {"ciudades": c.columns.tolist(), "valores": _matriz(c, 2)}


def consistencia():
    """Comprueba B vs C (nacional) y B vs A (ciudad-año) como en el notebook."""
    d = cargar()
    b, c = d["ciudades"], d["tipos"]
    b = b[b.categoria.str.lower() != "total"]
    c = c[c.categoria.str.lower() != "total"]
    tb = b.groupby("fecha").ton.sum(min_count=1)
    tc = c.groupby("fecha").ton.sum(min_count=1)
    q = pd.concat([tb.rename("b"), tc.rename("c")], axis=1).dropna()
    dif = ((q.b / q.c - 1) * 100).abs()

    bsc = b[b.categoria.str.lower() != "cobija"]
    bs = bsc.groupby("fecha").ton.sum(min_count=1)
    cs = c.groupby("fecha").ton.sum(min_count=1)
    qsc = pd.concat([bs.rename("b"), cs.rename("c")], axis=1).dropna()
    difsc = ((qsc.b / qsc.c - 1) * 100).abs()

    bt = ciudades_tratado()
    bt = bt[bt.categoria.str.lower() != "total"]
    bt = bt.groupby([bt.fecha.dt.year, "categoria"]).ton.sum(min_count=1)
    at = ciudad_tipo_tratado().groupby(["anio", "ciudad"]).ton.sum(min_count=1)
    qa = pd.concat([bt.rename("b"), at.rename("a")], axis=1).dropna()
    difa = ((qa.b / qa.a - 1) * 100).abs()

    return {"b_c": {"periodo": "2005-2026", "meses": int(len(dif)),
                     "dif_max": round(float(dif.max()), 6)},
            "b_sin_cobija_c": {"periodo": "2005-2026", "meses": int(len(difsc)),
                                "dif_media": round(float(difsc.mean()), 2),
                                "dif_max": round(float(difsc.max()), 2)},
            "b_a": {"periodo": "2010-2025", "pares": int(len(difa)),
                     "dif_max": round(float(difa.max()), 6)}}


def log_limpieza():
    """Resumen de limpieza inspirado en el LOG del notebook."""
    rows = []
    for r in log_carga():
        if r["duplicados"]:
            rows.append({"paso": "L1", "dataset": r["dataset"],
                         "problema": "Filas duplicadas",
                         "cantidad": r["duplicados"],
                         "metodo": "drop_duplicates",
                         "porque": "La misma clave repetida duplicaba los totales."})
    b = cargar()["ciudades"]
    b_ciudades = b[b.categoria.str.lower() != "total"]
    cobija = b_ciudades[b_ciudades.categoria.str.lower() == "cobija"]
    sucre = b_ciudades[(b_ciudades.categoria == "Sucre") &
                       (b_ciudades.fecha < pd.Timestamp(ANIO_CORTE_SUCRE, 1, 1))]
    b_filtrada = b_ciudades[b_ciudades.categoria.str.lower() != "cobija"]
    b_filtrada = b_filtrada[~((b_filtrada.categoria == "Sucre") &
                              (b_filtrada.fecha < pd.Timestamp(ANIO_CORTE_SUCRE, 1, 1)))]
    nulos_b = int(b_filtrada.ton.isna().sum())

    a = cargar()["ciudad_tipo"]
    a = a[a.tipo.str.lower() != "total"]
    a_filtrada = a[a.ciudad.str.lower() != "cobija"]
    a_filtrada = a_filtrada[~((a_filtrada.ciudad == "Sucre") & (a_filtrada.anio < ANIO_CORTE_SUCRE))]
    nulos_a = int(a_filtrada.ton.isna().sum())

    rows.extend([
        {"paso": "L8", "dataset": "B", "problema": "Cobija: nulos en bloques de años completos",
         "cantidad": int(len(cobija)), "metodo": "Excluir la ciudad de B, A y vistas por ciudad",
         "porque": "Tiene hasta 43 meses seguidos sin dato; interpolar inventaría una serie."},
        {"paso": "L8", "dataset": "B", "problema": "Sucre: serie inexistente antes de 2015",
         "cantidad": int(len(sucre)), "metodo": "Recortar 2005-2014",
         "porque": "Los nulos son estructurales, no aleatorios."},
        {"paso": "L8", "dataset": "B", "problema": "Nulos sueltos (menos de 5 %)",
         "cantidad": nulos_b, "metodo": "Eliminar las filas",
         "porque": "Pérdida despreciable y no se inventan datos."},
        {"paso": "L9", "dataset": "A", "problema": "Cobija y Sucre anteriores a 2015",
         "cantidad": int(len(a) - len(a_filtrada)),
         "metodo": "Mismo criterio que en B",
         "porque": "Cada ciudad debe tratarse igual en A y B."},
        {"paso": "L9", "dataset": "A", "problema": "Tipos sin dato",
         "cantidad": nulos_a, "metodo": "Marcar no_reportado y poner 0",
         "porque": "La suma de tipos reportados coincide con el total de B."},
    ])
    return rows


def datos_descarga(dataset, crudo=False):
    """DataFrame para descarga: tratado por defecto o completo con crudo=1."""
    if dataset not in cargar():
        raise KeyError(dataset)
    if crudo:
        return cargar()[dataset].copy()
    if dataset == "ciudades":
        return ciudades_tratado().copy()
    if dataset == "ciudades_anual":
        d = cargar()["ciudades_anual"].copy()
        d = d[d.categoria.str.lower() != "cobija"]
        d = d[~((d.categoria == "Sucre") & (d.anio < ANIO_CORTE_SUCRE))]
        return d.dropna(subset=["ton"]).reset_index(drop=True)
    if dataset == "ciudad_tipo":
        return ciudad_tipo_tratado().copy()
    return cargar()[dataset].copy()
