"""Modelo de predicción, métricas, perfiles y alerta de picos."""
import json
from datetime import datetime, timezone
from functools import lru_cache

import numpy as np
import pandas as pd

from config import BASE, CORTE

from .analytics import preparar_serie
from .data_loader import cargar, serie

FEATURES = ["lag1", "lag12", "mm3", "mm12", "t"]
FEATURES_PICO = FEATURES + ["mes_sin", "mes_cos"]
DIR = BASE / "app" / "models"
LINEAL = DIR / "regresion_lineal.joblib"
METRICAS = DIR / "metricas.json"
PERFILES = DIR / "perfiles.json"
PICOS = DIR / "clasificador_picos.joblib"
PICOS_JSON = DIR / "picos.json"
CORTE_FECHA = pd.Timestamp(CORTE)


def _ciudades():
    d = cargar()["ciudades"]
    return sorted(c for c in d.categoria.unique() if str(c).lower() != "total")


def _serie_ciudad(ciudad):
    s = preparar_serie(serie("ciudades", ciudad), ciudad)[0]
    return s.asfreq("MS")


def _tabla(s, ciudad):
    df = pd.DataFrame({"y": s.astype(float)})
    df["t"] = np.arange(len(df))
    df["lag1"] = df.y.shift(1)
    df["lag12"] = df.y.shift(12)
    df["mm3"] = df.y.shift(1).rolling(3).mean()
    df["mm12"] = df.y.shift(1).rolling(12).mean()
    mes = 2 * np.pi * df.index.month.values / 12
    df["mes_sin"] = np.sin(mes)
    df["mes_cos"] = np.cos(mes)
    df["fecha"] = df.index
    df["ciudad"] = ciudad
    return df


@lru_cache(maxsize=1)
def datos():
    tablas = [_tabla(_serie_ciudad(c), c) for c in _ciudades()]
    d = pd.concat(tablas, ignore_index=True)
    return d.dropna(subset=["y", *FEATURES]).reset_index(drop=True)


def _metricas(y, p):
    y, p = np.asarray(y, float), np.asarray(p, float)
    return {"mae": float(np.mean(np.abs(y - p))),
            "rmse": float(np.sqrt(np.mean((y - p) ** 2))),
            "r2": float(1 - np.sum((y - p) ** 2) / np.sum((y - y.mean()) ** 2))}


def _ajustar_modelos(Xtr, ytr, Xte):
    from sklearn.ensemble import (BaggingRegressor, GradientBoostingRegressor,
                                  RandomForestRegressor, StackingRegressor)
    from sklearn.linear_model import LinearRegression
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    from sklearn.svm import SVR
    from sklearn.tree import DecisionTreeRegressor

    rf = RandomForestRegressor(300, random_state=42, n_jobs=-1)
    bag = BaggingRegressor(DecisionTreeRegressor(max_depth=12, random_state=42),
                           n_estimators=150, random_state=42, n_jobs=-1)
    gb = GradientBoostingRegressor(n_estimators=200, max_depth=2, learning_rate=.05,
                                   random_state=42)
    stack = StackingRegressor(
        estimators=[("rf", RandomForestRegressor(200, random_state=42, n_jobs=-1)),
                    ("gb", GradientBoostingRegressor(n_estimators=150, max_depth=2,
                                                     learning_rate=.05, random_state=42))],
        final_estimator=LinearRegression(), cv=3, n_jobs=-1)
    svr = make_pipeline(StandardScaler(), SVR(C=1.0, epsilon=.05))
    modelos = [("Random Forest", rf), ("Bagging", bag), ("Boosting", gb),
               ("Stacking", stack), ("SVR", svr)]
    salida = []
    for nombre, modelo in modelos:
        modelo.fit(Xtr, ytr)
        p = modelo.predict(Xte)
        salida.append((nombre, modelo, p))
    return salida


def _perfiles_kmeans(d):
    from sklearn.cluster import KMeans
    from sklearn.preprocessing import StandardScaler

    ann = d.groupby(["ciudad", d.fecha.dt.year.rename("anio")]).agg(
        media=("y", "mean"), sd=("y", "std"), n=("y", "size")).reset_index()
    ann = ann[ann.n == 12].sort_values(["ciudad", "anio"]).copy()
    ann["lmedia"] = np.log(ann.media)
    ann["cv"] = ann.sd / ann.media
    ann["crec"] = ann.groupby("ciudad").media.pct_change()
    ann = ann.dropna(subset=["lmedia", "cv", "crec"]).reset_index(drop=True)
    train = ann[ann.anio <= 2022]
    scaler = StandardScaler().fit(train[["lmedia", "cv", "crec"]])
    km = KMeans(3, n_init=20, random_state=42).fit(
        scaler.transform(train[["lmedia", "cv", "crec"]]))
    ann["cluster"] = km.predict(scaler.transform(ann[["lmedia", "cv", "crec"]]))
    perfil = ann[ann.anio <= 2022].groupby("cluster").agg(
        media=("media", "mean"), cv=("cv", "mean"), crec=("crec", "mean"))
    nombres, estables = {}, []
    for c, r in perfil.iterrows():
        if r.crec > .15:
            nombres[int(c)] = "En expansión"
        else:
            estables.append(int(c))
    estables.sort(key=lambda c: perfil.loc[c, "media"])
    for c, nombre in zip(estables, ["Volumen bajo estable", "Volumen alto estable"]):
        nombres[c] = nombre
    ann["perfil"] = ann.cluster.map(nombres)
    return {
        "grupos": [{"id": int(c), "nombre": nombres[int(c)],
                    "toneladas_medias": round(float(r.media), 1),
                    "cv": round(float(r.cv), 3),
                    "crecimiento": round(float(r.crec), 3)}
                   for c, r in perfil.sort_values("media").iterrows()],
        "anios": sorted(int(a) for a in ann.anio.unique()),
        "ciudades": sorted(ann.ciudad.unique()),
        "filas": [{"ciudad": r.ciudad, "anio": int(r.anio), "perfil": r.perfil,
                   "toneladas": round(float(r.media), 1), "cv": round(float(r.cv), 3),
                   "crecimiento": round(float(r.crec), 3)}
                  for r in ann.itertuples()],
    }


def _clasificador_picos(d):
    from sklearn.ensemble import RandomForestClassifier

    tr = d.fecha < CORTE_FECHA
    ratio = d.y / d.mm12
    umbral = float(ratio[tr].quantile(.90))
    y = (ratio > umbral).astype(int)
    X = d[FEATURES_PICO]
    rng = np.random.default_rng(42)
    pos = np.flatnonzero(tr.values & (y.values == 1))
    neg = np.flatnonzero(tr.values & (y.values == 0))
    neg = rng.choice(neg, size=len(pos), replace=False)
    idx = np.concatenate([pos, neg])
    clf = RandomForestClassifier(300, random_state=42, n_jobs=-1)
    clf.fit(X.iloc[idx], y.iloc[idx])
    return clf, umbral, y


def entrenar_artefactos():
    from joblib import dump
    from sklearn.ensemble import RandomForestRegressor
    from sklearn.linear_model import LinearRegression

    d = datos()
    tr = d.fecha < CORTE_FECHA
    te = ~tr
    Xtr, Xte = d.loc[tr, FEATURES], d.loc[te, FEATURES]
    ytr, yte = d.loc[tr, "y"], d.loc[te, "y"]

    lineal = LinearRegression().fit(Xtr, ytr)
    met = _metricas(yte, lineal.predict(Xte))
    metricas = [{"nombre": "Regresión lineal", "mae": round(met["mae"], 1),
                 "rmse": round(met["rmse"], 1), "r2": round(met["r2"], 4),
                 "objetivo": "nivel"}]
    ratio_tr = ytr / d.loc[tr, "mm12"]
    for nombre, _, p_ratio in _ajustar_modelos(Xtr, ratio_tr, Xte):
        p = p_ratio * d.loc[te, "mm12"].values
        m = _metricas(yte, p)
        metricas.append({"nombre": nombre, "mae": round(m["mae"], 1),
                         "rmse": round(m["rmse"], 1), "r2": round(m["r2"], 4),
                         "objetivo": "razón y/mm12"})

    rf = RandomForestRegressor(300, random_state=42, n_jobs=-1).fit(Xtr, ratio_tr)
    importancia = [{"variable": v, "valor": round(float(x), 4)}
                   for v, x in zip(FEATURES, rf.feature_importances_)]

    final = LinearRegression().fit(d[FEATURES], d.y)
    config = {
        "modelo": "Regresión lineal",
        "features": FEATURES,
        "objetivo": "toneladas",
        "corte": CORTE_FECHA.strftime("%Y-%m"),
        "entrenamiento": {"desde": d.fecha.min().strftime("%Y-%m"),
                          "hasta": d.fecha.max().strftime("%Y-%m"),
                          "filas": int(len(d))},
        "prueba": {"desde": d.loc[te, "fecha"].min().strftime("%Y-%m"),
                   "filas": int(te.sum()),
                   "media_mensual": round(float(yte.mean()), 4)},
        "metricas": {k: round(v, 4) for k, v in met.items()},
        "coeficientes": [{"variable": v, "coeficiente": round(float(c), 6)}
                         for v, c in zip(FEATURES, final.coef_)],
        "intercepto": round(float(final.intercept_), 6),
        "actualizado": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    DIR.mkdir(parents=True, exist_ok=True)
    dump({"modelo": final, "features": FEATURES, "ciudades": _ciudades()}, LINEAL)
    METRICAS.write_text(json.dumps(
        {**config, "modelos": metricas, "importancia": importancia},
        ensure_ascii=False, indent=2), encoding="utf-8")

    perfil = _perfiles_kmeans(d)
    PERFILES.write_text(json.dumps(perfil, ensure_ascii=False, indent=2), encoding="utf-8")

    clf, umbral, y = _clasificador_picos(d)
    dump({"modelo": clf, "features": FEATURES_PICO, "umbral": umbral}, PICOS)
    train = d.fecha < CORTE_FECHA
    PICOS_JSON.write_text(json.dumps({
        "umbral_ratio": round(umbral, 4),
        "filas": int(len(d)),
        "picos_entrenamiento": int(y[train].sum()),
        "filas_entrenamiento": int(train.sum()),
        "features": FEATURES_PICO,
        "actualizado": config["actualizado"],
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    return config


@lru_cache(maxsize=1)
def cargar_lineal():
    if not LINEAL.exists():
        return None
    from joblib import load
    return load(LINEAL)


@lru_cache(maxsize=1)
def cargar_picos():
    if not PICOS.exists():
        return None
    from joblib import load
    return load(PICOS)


def metricas():
    if not METRICAS.exists():
        return None
    return json.loads(METRICAS.read_text(encoding="utf-8"))


def perfiles():
    if not PERFILES.exists():
        return None
    return json.loads(PERFILES.read_text(encoding="utf-8"))


def info_picos():
    if not PICOS_JSON.exists():
        return None
    return json.loads(PICOS_JSON.read_text(encoding="utf-8"))


def _siguiente(valores, t, fecha):
    mes = 2 * np.pi * fecha.month / 12
    return {
        "lag1": float(valores[-1]),
        "lag12": float(valores[-12]),
        "mm3": float(np.mean(valores[-3:])),
        "mm12": float(np.mean(valores[-12:])),
        "t": float(t),
        "mes_sin": float(np.sin(mes)),
        "mes_cos": float(np.cos(mes)),
    }


def _probabilidad(clf, s, valores):
    fecha = s.index[-1] + pd.offsets.MonthBegin()
    x = _siguiente(valores, len(s), fecha)
    p = clf["modelo"].predict_proba(pd.DataFrame([x])[clf["features"]])[0, 1]
    return float(p), x


def _nivel(p):
    return "alto" if p >= .35 else ("medio" if p >= .15 else "bajo")


def alerta(ciudad):
    clf = cargar_picos()
    if clf is None:
        return None
    s = _serie_ciudad(ciudad)
    values = s.astype(float).tolist()
    if len(values) < 13 or s.tail(12).isna().any():
        return None
    p, _ = _probabilidad(clf, s, values)
    return {"ciudad": ciudad, "probabilidad": round(p * 100, 1),
            "nivel": _nivel(p),
            "umbral_ratio": round(float(clf["umbral"]), 4),
            "fecha": (s.index[-1] + pd.offsets.MonthBegin()).strftime("%Y-%m")}


@lru_cache(maxsize=1)
def alerta_global():
    alertas = [a for a in (alerta(c) for c in _ciudades()) if a]
    if not alertas:
        return None
    peor = max(alertas, key=lambda a: a["probabilidad"])
    return {**peor, "ciudades": len(alertas)}


def _banda(mae, p):
    return [max(0, v) for v in p], [max(0, v - 1.96 * mae) for v in p], [v + 1.96 * mae for v in p]


def predecir(ciudad, meses=12):
    modelo = cargar_lineal()
    if modelo is None:
        raise ValueError("El modelo no está entrenado.")
    if ciudad not in modelo["ciudades"]:
        raise ValueError("Ciudad no válida para el modelo.")
    s = _serie_ciudad(ciudad)
    values = s.astype(float).tolist()
    if len(values) < 13 or s.tail(12).isna().any():
        raise ValueError("Se necesitan 12 meses recientes consecutivos para predecir.")
    fechas = pd.date_range(s.index[-1] + pd.offsets.MonthBegin(), periods=int(meses), freq="MS")
    pred = []
    for h, fecha in enumerate(fechas):
        x = _siguiente(values, len(s) + h, fecha)
        y = float(modelo["modelo"].predict(pd.DataFrame([x])[modelo["features"]])[0])
        y = max(0.0, y)
        pred.append(y)
        values.append(y)
    cfg = metricas()
    mae = float(cfg["metricas"]["mae"]) if cfg else 0.0
    y, low, high = _banda(mae, pred)
    alert = alerta(ciudad)
    hist = s.tail(36)
    return {"ciudad": ciudad, "fecha_ultima": s.index[-1].strftime("%Y-%m"),
            "meses": int(meses), "mae": round(mae, 1),
            "rmse": round(float(cfg["metricas"]["rmse"]), 1) if cfg else None,
            "r2": cfg["metricas"]["r2"] if cfg else None,
            "historico": {"x": hist.index.strftime("%Y-%m").tolist(),
                          "y": [round(float(v), 1) if pd.notna(v) else None for v in hist]},
            "pred": {"x": fechas.strftime("%Y-%m").tolist(), "y": [round(v, 1) for v in y],
                     "min": [round(v, 1) for v in low], "max": [round(v, 1) for v in high]},
            "alerta": alert,
            "promedio": round(float(np.mean(y)), 1),
            "total": round(float(np.sum(y)), 1)}


def pronosticar_serie(s, pasos):
    from sklearn.linear_model import LinearRegression

    s = s.asfreq("MS").interpolate(limit_direction="both")
    df = _tabla(s, "serie").dropna(subset=["y", *FEATURES])
    if len(df) < 15:
        raise ValueError("La serie es demasiado corta para el modelo.")
    modelo = LinearRegression().fit(df[FEATURES], df.y)
    values = s.dropna().astype(float).tolist()
    out = []
    for h in range(int(pasos)):
        fecha = s.index[-1] + pd.DateOffset(months=h + 1)
        x = _siguiente(values, len(s) + h, fecha)
        y = max(0.0, float(modelo.predict(pd.DataFrame([x])[FEATURES])[0]))
        out.append(y)
        values.append(y)
    return np.asarray(out, float)
