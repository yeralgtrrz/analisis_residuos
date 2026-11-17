"""Lee los Excel del INE (con logos y notas) y los convierte a tablas limpias."""
import re
from functools import lru_cache

import numpy as np
import pandas as pd

from config import ARCHIVOS

RENOMBRES = {"Domiciliaria": "Domiciliarios", "Hospital": "Establecimientos de salud",
             "Otros(1)": "Otros"}

_LOG = []

MESES = {m: i + 1 for i, m in enumerate(
    ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio",
     "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"])}


def _num(v):
    return pd.to_numeric(v, errors="coerce")  # 'n.d.' -> NaN


def _limpiar(df, claves):
    """Elimina filas repetidas y valida que no queden claves ambiguas.

    Redondea las toneladas a 6 decimales para que los duplicados por diferencias
    de punto flotante (p. ej. 10563,9157615964 vs 10563,9157615965) se colapsen.
    """
    df = df.copy()
    df["ton"] = pd.to_numeric(df["ton"], errors="coerce").round(6)
    df = df.drop_duplicates().reset_index(drop=True)
    repes = df[df.duplicated(subset=claves, keep=False)]
    if not repes.empty:
        ejemplo = repes.sort_values(claves).head(5).to_dict("records")
        raise ValueError(f"Claves duplicadas con valores distintos en {claves}: {ejemplo}")
    return df


def _mensual(path):
    """Devuelve (mensual, anual) en formato largo: fecha/anio, categoria, toneladas."""
    raw = pd.read_excel(path, header=None)
    h = raw.index[raw[1].astype(str).str.upper().str.strip() == "PERÍODO"][0]
    cols = [str(c).strip() for c in raw.iloc[h, 2:] if pd.notna(c)]
    mensual, anual, anio = [], [], None
    for _, r in raw.iloc[h + 1:].iterrows():
        k = "" if pd.isna(r[1]) else str(r[1]).strip()
        m = re.match(r"^(\d{4})", k)
        for j, c in enumerate(cols):
            if m:
                anual.append((int(m[1]), c, _num(r[2 + j])))
            elif k in MESES and anio:
                mensual.append((pd.Timestamp(anio, MESES[k], 1), c, _num(r[2 + j])))
        if m:
            anio = int(m[1])
    return (pd.DataFrame(mensual, columns=["fecha", "categoria", "ton"]),
            pd.DataFrame(anual, columns=["anio", "categoria", "ton"]))


def _ciudad_tipo(path):
    raw = pd.read_excel(path, header=None)
    h = raw.index[raw[1].astype(str).str.upper().str.strip() == "TIPO DE PROCEDENCIA"][0]
    ciudades = [str(c).strip().title() for c in raw.iloc[h, 3:] if pd.notna(c)]
    rows, anio = [], None
    for _, r in raw.iloc[h + 1:].iterrows():
        k = "" if pd.isna(r[1]) else str(r[1])
        m = re.match(r"^\s*(\d{4})", k)
        if m:
            anio, tipo = int(m[1]), "Total"
        elif anio and k.startswith(" "):
            tipo = k.strip().replace("(1)", "").strip()
        else:
            continue
        for j, c in enumerate(ciudades):
            rows.append((anio, tipo, c, _num(r[3 + j])))
    return pd.DataFrame(rows, columns=["anio", "tipo", "ciudad", "ton"])


def _preparar(nombre, df, claves, nota=""):
    filas = len(df)
    limpio = _limpiar(df, claves)
    _LOG.append({"dataset": nombre, "filas_iniciales": filas,
                 "duplicados": filas - len(limpio), "filas_finales": len(limpio),
                 "nulos": int(limpio.ton.isna().sum()), "nota": nota})
    return limpio


@lru_cache(maxsize=1)
def cargar():
    global _LOG
    _LOG = []
    cm, ca = _mensual(ARCHIVOS["ciudades"])
    tm, ta = _mensual(ARCHIVOS["tipos"])
    for d in (cm, ca):
        d["categoria"] = d["categoria"].str.strip().str.title()
    for d in (tm, ta):
        d["categoria"] = d["categoria"].str.strip().str.title().replace(RENOMBRES)
    cm = _preparar("ciudades", cm, ["fecha", "categoria"])
    ca = _preparar("ciudades_anual", ca, ["anio", "categoria"])
    tm = _preparar("tipos", tm, ["fecha", "categoria"], "Nombres de tipos unificados")
    ta = _preparar("tipos_anual", ta, ["anio", "categoria"], "Nombres de tipos unificados")
    ciudad_tipo = _preparar("ciudad_tipo", _ciudad_tipo(ARCHIVOS["ciudad_tipo"]),
                            ["anio", "tipo", "ciudad"])
    return {"ciudades": cm, "ciudades_anual": ca, "tipos": tm, "tipos_anual": ta,
            "ciudad_tipo": ciudad_tipo}


def log_carga():
    cargar()
    return [dict(r) for r in _LOG]


def serie(dataset, categoria):
    """Serie mensual indexada por fecha de una ciudad o tipo (o 'Total')."""
    d = cargar()[dataset]
    d = d[d["categoria"].str.lower() == categoria.lower()]
    return d.set_index("fecha")["ton"].sort_index()
