"""Cálculos: KPIs, rankings, heatmap, calidad de datos, imputación y pronóstico."""
import warnings
from functools import lru_cache

import numpy as np
import pandas as pd

from .data_loader import cargar, serie

UMBRAL_COMPLETO = 12


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
    return {"ciudades": [c for c in d["ciudades"].categoria.unique() if c.lower() != "total"],
            "tipos": [c for c in d["tipos"].categoria.unique() if c.lower() != "total"],
            "anios": sorted(int(a) for a in d["ciudades"].fecha.dt.year.unique()),
            "anios_completos": completos,
            "anio_ultimo_completo": completos[-1] if completos else None,
            "anios_incompletos": anios_incompletos("ciudades", "Total")}


# --------------------------------------------------------------------------- #
# KPIs y agregados
# --------------------------------------------------------------------------- #
def kpis():
    d = cargar()["ciudades"]
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
    d = cargar()["ciudades"]
    d = d[(d.categoria.str.lower() != "total") & (d.fecha.dt.year == anio)]
    r = d.groupby("categoria").ton.sum(min_count=1).sort_values(ascending=False)
    return {"labels": r.index.tolist(), "values": r.round(0).tolist(),
            "parcial": anio in anios_incompletos("ciudades", "Total")}


def composicion():
    d = cargar()["tipos_anual"]
    d = d[d.categoria.str.lower() != "total"]
    excluidos = anios_incompletos("tipos", "Total")
    d = d[~d.anio.isin(excluidos)]
    p = d.pivot_table(index="anio", columns="categoria", values="ton", aggfunc="sum")
    return {"anios": [int(a) for a in p.index],
            "series": {c: p[c].round(0).where(p[c].notna(), None).tolist() for c in p},
            "excluidos": excluidos}


def serie_anual(dataset, cats, desde, hasta, imputado=False):
    """Series anuales descartando años con menos de 12 meses con dato."""
    out = []
    for c in cats:
        s = serie(dataset, c)
        s = s[(s.index.year >= desde) & (s.index.year <= hasta)]
        if imputado:
            s = imputar_serie(s)[0]
        total, meses = _anual(s)
        ok = meses[meses >= UMBRAL_COMPLETO]
        filtrado = total.reindex(ok.index)
        out.append({"nombre": c, "x": [str(int(a)) for a in filtrado.index],
                    "y": filtrado.round(0).tolist(),
                    "omitidos": [int(a) for a in meses[meses < UMBRAL_COMPLETO].index]})
    return out


def heatmap(dataset, cat, imputado=False):
    s = serie(dataset, cat)
    if imputado:
        s = imputar_serie(s)[0]
    else:
        s = s.dropna()
    p = s.groupby([s.index.year, s.index.month]).sum().unstack()
    return {"anios": [int(a) for a in p.index], "meses": [int(m) for m in p.columns],
            "valores": p.round(0).where(p.notna(), None).values.tolist()}

# --------------------------------------------------------------------------- #
# Nulos: un solo criterio (Sucre se recorta antes de 2015, resto interpola)
# --------------------------------------------------------------------------- #
def imputar_serie(s):
    """Recorta el tramo inicial sin dato y rellena con interpolación lineal.

    Devuelve (serie_imputada, mascara_estimados, primer_mes_real).
    """
    s = s.sort_index()
    s = s[~s.index.duplicated(keep="first")]
    if s.notna().sum() == 0:
        return s, pd.Series(False, index=s.index), None
    primero = s.first_valid_index()
    recorte = None
    if primero is not None and primero > s.index[0]:
        recorte = primero.strftime("%Y-%m")
        s = s.loc[primero:]
    est = s.isna()
    out = s.interpolate(method="linear", limit_direction="both")
    return out, est, recorte


def imputar_ciudad(ciudad="Sucre"):
    out, est, recorte = imputar_serie(serie("ciudades", ciudad))
    return out, est, recorte


def faltantes():
    """Meses sin dato por ciudad y año (n.d. o vacío)."""
    d = cargar()["ciudades"]
    d = d[d.categoria.str.lower() != "total"].copy()
    d["falta"] = d.ton.isna()
    p = d.pivot_table(index="categoria", columns=d.fecha.dt.year, values="falta", aggfunc="sum")
    return {"ciudades": p.index.tolist(), "anios": [int(a) for a in p.columns],
            "valores": p.fillna(0).astype(int).values.tolist()}


def ciudad_tipo(ciudad, imputado=False):
    d = cargar()["ciudad_tipo"]
    d = d[(d.ciudad.str.lower() == ciudad.lower()) & (d.tipo.str.lower() != "total")]
    p = d.pivot_table(index="anio", columns="tipo", values="ton", dropna=False).sort_index()
    estimado = {}
    if imputado:
        if ciudad.lower() == "sucre":
            p = p[p.index >= 2015]
        for c in p.columns:
            col = p[c]
            estimado[c] = col.isna().tolist()
            p[c] = col.interpolate(method="linear", limit_direction="both")
    return {"anios": [int(a) for a in p.index],
            "series": {c: p[c].round(0).where(p[c].notna(), None).tolist() for c in p},
            "estimado": estimado, "imputado": imputado}


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


@lru_cache(maxsize=64)
def pronostico(dataset, cat, meses=12):
    s = imputar_serie(serie(dataset, cat))[0]
    raw = serie(dataset, cat)
    s = s.asfreq("MS").interpolate(limit_direction="both")
    meses = int(meses)
    if len(s) < 36:
        raise ValueError("La serie es demasiado corta para pronosticar.")

    corte = 12 if len(s) >= 48 else max(6, len(s) // 4)
    entreno, prueba = s.iloc[:-corte], s.iloc[-corte:]
    comparacion, predicciones, errores = [], {}, {}
    for nombre in NOMBRES:
        try:
            pred = _ajustar(nombre, entreno, len(prueba))
            err = np.asarray(prueba, float) - pred
            errores[nombre] = err
            predicciones[nombre] = pred
            comparacion.append({"modelo": nombre, "mae": round(_mae(prueba, pred), 1),
                                "mape": round(_mape(prueba, pred), 1)})
        except Exception:
            continue
    if not comparacion:
        raise ValueError("Ningún modelo pudo ajustarse a la serie.")

    elegido = min(comparacion, key=lambda m: m["mae"])["modelo"]
    pred = _ajustar(elegido, s, meses)
    idx = pd.date_range(s.index[-1] + pd.offsets.MonthBegin(), periods=meses, freq="MS")
    sigma = float(np.nanstd(errores[elegido]))
    if not np.isfinite(sigma) or sigma == 0:
        sigma = float(np.nanstd(s)) or 1.0

    raw = raw.reindex(s.index)
    return {"metodo": elegido,
            "banda": "error de backtesting",
            "modelos": comparacion,
            "backtest": {"x": prueba.index.strftime("%Y-%m").tolist(),
                         "real": prueba.round(0).tolist(),
                         "predicciones": {k: np.round(v, 0).tolist() for k, v in predicciones.items()}},
            "hist": {"x": s.index.strftime("%Y-%m").tolist()[-60:], "y": s.round(0).tolist()[-60:]},
            "hist_crudo": {"x": raw.index.strftime("%Y-%m").tolist()[-60:],
                           "y": raw.round(0).where(raw.notna(), None).tolist()[-60:]},
            "pred": {"x": idx.strftime("%Y-%m").tolist(), "y": pred.round(0).tolist(),
                     "min": (pred - 1.96 * sigma).round(0).tolist(),
                     "max": (pred + 1.96 * sigma).round(0).tolist()}}


def anomalias(dataset, cat, umbral=2.5):
    """Descomposición simple (tendencia 12m, estacionalidad, residuo) y meses atípicos."""
    s = imputar_serie(serie(dataset, cat))[0].asfreq("MS").interpolate(limit_direction="both")
    crudo = serie(dataset, cat).reindex(s.index)
    tend = s.rolling(12, center=True, min_periods=6).mean()
    estac = (s - tend).groupby(s.index.month).transform("mean")
    res = s - tend - estac
    z = res / res.std()
    idx = z.abs() > umbral
    f = lambda x: x.round(0).where(x.notna(), None).tolist()
    return {"x": s.index.strftime("%Y-%m").tolist(), "y": f(s), "y_crudo": f(crudo),
            "tendencia": f(tend), "estacional": f(estac),
            "anomalias": [{"mes": d.strftime("%Y-%m"), "ton": round(float(s[d])), "z": round(float(z[d]), 1)}
                          for d in s.index[idx]]}


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
            for c, t in zip(r["labels"], r["values"]) if c in COORDS]


def correlacion():
    d = cargar()["ciudades"]
    p = d[d.categoria.str.lower() != "total"].pivot_table(index="fecha", columns="categoria", values="ton")
    c = p.diff().corr()
    return {"ciudades": c.columns.tolist(), "valores": c.round(2).where(c.notna(), None).values.tolist()}
