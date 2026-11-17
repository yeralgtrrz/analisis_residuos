"""Cálculos: KPIs, rankings, heatmap, calidad de datos, imputación y pronóstico."""
import warnings
from functools import lru_cache

import numpy as np
import pandas as pd

from .data_loader import cargar, serie

UMBRAL_COMPLETO = 12
UMBRAL_BAJO = 5
UMBRAL_ALTO = 30
ANIO_CORTE_SUCRE = 2015


def _lista(s, dec=0):
    """Convierte una serie a lista JSON sin NaN (los nulos pasan como None)."""
    return [None if pd.isna(v) else float(round(v, dec)) for v in s]


def _matriz(df, dec=0):
    return [_lista(fila, dec) for fila in df.values]


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
    """Series anuales descartando años con menos de 12 meses con dato."""
    out = []
    for c in cats:
        s = serie(dataset, c)
        s = s[(s.index.year >= desde) & (s.index.year <= hasta)]
        estimados, recorte = 0, None
        if not crudo:
            s, est, recorte = imputar_serie(s)
            estimados = int(est.sum())
        total, meses = _anual(s)
        ok = meses[meses >= UMBRAL_COMPLETO]
        filtrado = total.reindex(ok.index)
        out.append({"nombre": c, "x": [str(int(a)) for a in filtrado.index],
                    "y": _lista(filtrado),
                    "omitidos": [int(a) for a in meses[meses < UMBRAL_COMPLETO].index],
                    "estimados": estimados, "recortado_desde": recorte})
    return out


def heatmap(dataset, cat, crudo=False):
    s = serie(dataset, cat)
    if not crudo:
        s = imputar_serie(s)[0]
    p = s.groupby([s.index.year, s.index.month]).sum(min_count=1).unstack()
    p = p.reindex(columns=range(1, 13))
    return {"anios": [int(a) for a in p.index], "meses": [int(m) for m in p.columns],
            "valores": _matriz(p)}

# --------------------------------------------------------------------------- #
# Nulos: series mensuales (recorte inicial + interpolación) y umbrales Ciudad x Tipo
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


@lru_cache(maxsize=1)
def ciudad_tipo_tratado():
    """Aplica la regla de umbrales del notebook al dataset Ciudad x Tipo.

    <5% de nulos: no se imputa, la celda queda nula y marcada como faltante.
    5%-30%: interpolación lineal por (ciudad, tipo).
    >30%: Sucre se recorta antes de 2015 y luego se interpola por tipo.
    """
    d = cargar()["ciudad_tipo"].copy()
    d = d[d.tipo.str.lower() != "total"].copy()
    d["pct"] = d.groupby("ciudad")["ton"].transform(lambda s: s.isna().mean() * 100)
    d["estimado"] = False
    d["faltante"] = False

    bajo = d.pct < UMBRAL_BAJO
    d.loc[bajo & d.ton.isna(), "faltante"] = True

    media = (d.pct >= UMBRAL_BAJO) & (d.pct <= UMBRAL_ALTO)
    if media.any():
        bloque = d[media]
        est = bloque.ton.isna()
        imp = bloque.groupby(["ciudad", "tipo"], group_keys=False)["ton"].transform(
            lambda s: s.interpolate(method="linear", limit_direction="both"))
        d.loc[media, "estimado"] = est
        d.loc[media, "ton"] = imp

    alto = d.pct > UMBRAL_ALTO
    if alto.any():
        d = d[~(alto & (d.anio < ANIO_CORTE_SUCRE))].copy()
        alto = d.pct > UMBRAL_ALTO
        bloque = d[alto]
        est = bloque.ton.isna()
        imp = bloque.groupby(["ciudad", "tipo"], group_keys=False)["ton"].transform(
            lambda s: s.interpolate(method="linear", limit_direction="both"))
        d.loc[alto, "estimado"] = est
        d.loc[alto, "ton"] = imp

    quedan = d.ton.isna() & ~d.faltante
    d.loc[quedan, "faltante"] = True
    return d.reset_index(drop=True)


def ciudad_tipo(ciudad, crudo=False):
    d = cargar()["ciudad_tipo"] if crudo else ciudad_tipo_tratado()
    d = d[(d.ciudad.str.lower() == ciudad.lower()) & (d.tipo.str.lower() != "total")]
    p = d.pivot_table(index="anio", columns="tipo", values="ton", dropna=False).sort_index()
    p = p.reindex(columns=sorted(p.columns))

    if crudo:
        estimado = {c: [False] * len(p) for c in p.columns}
        faltante = {c: p[c].isna().tolist() for c in p.columns}
    else:
        pe = d.pivot_table(index="anio", columns="tipo", values="estimado",
                           aggfunc="first", dropna=False).reindex(p.index)
        pf = d.pivot_table(index="anio", columns="tipo", values="faltante",
                           aggfunc="first", dropna=False).reindex(p.index)
        pe = pe.reindex(columns=p.columns).fillna(False).astype(bool)
        pf = pf.reindex(columns=p.columns).fillna(True).astype(bool)
        estimado = {c: pe[c].tolist() for c in p.columns}
        faltante = {c: pf[c].tolist() for c in p.columns}

    incompletos = [int(a) for i, a in enumerate(p.index)
                   if any(faltante[c][i] for c in p.columns)]
    totales = []
    for a in p.index:
        valores = p.loc[a].dropna()
        totales.append(float(round(valores.sum())) if len(valores) else None)

    return {"anios": [int(a) for a in p.index],
            "series": {c: _lista(p[c]) for c in p.columns},
            "estimado": estimado,
            "faltante": faltante,
            "anios_incompletos": incompletos,
            "totales": totales,
            "imputado": not crudo,
            "crudo": crudo}


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


def anomalias(dataset, cat, umbral=2.5):
    """Descomposición simple (tendencia 12m, estacionalidad, residuo) y meses atípicos."""
    s = imputar_serie(serie(dataset, cat))[0].asfreq("MS").interpolate(limit_direction="both")
    crudo = serie(dataset, cat).reindex(s.index)
    tend = s.rolling(12, center=True, min_periods=6).mean()
    estac = (s - tend).groupby(s.index.month).transform("mean")
    res = s - tend - estac
    z = res / res.std()
    idx = z.abs() > umbral
    f = _lista
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
            for c, t in zip(r["labels"], r["values"]) if c in COORDS and t is not None]


def correlacion():
    d = cargar()["ciudades"]
    p = d[d.categoria.str.lower() != "total"].pivot_table(index="fecha", columns="categoria", values="ton")
    c = p.diff().corr()
    return {"ciudades": c.columns.tolist(), "valores": _matriz(c, 2)}
