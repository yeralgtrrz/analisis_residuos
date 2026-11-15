"""Genera app/static/data/bolivia.json a partir del GeoJSON ADM1 de geoBoundaries.

Uso:
    python tools/generar_mapa.py

Descarga (o reutiliza) el GeoJSON simplificado de Bolivia (9 departamentos),
reduce los puntos con Douglas-Peucker y guarda un JSON liviano con los anillos
en formato [lon, lat], listo para dibujar en SVG.

Fuente: geoBoundaries BOL ADM1 (dominio publico).
"""

import json
import os
import urllib.request

URL = ("https://github.com/wmgeolab/geoBoundaries/raw/9469f09/"
       "releaseData/gbOpen/BOL/ADM1/geoBoundaries-BOL-ADM1_simplified.geojson")
CACHE = os.path.join(os.path.dirname(__file__), "_bol_adm1.geojson")
SALIDA = os.path.join(os.path.dirname(__file__), "..", "app", "static", "data", "bolivia.json")
TOLERANCIA = 0.01


def descargar():
    if os.path.exists(CACHE):
        with open(CACHE, encoding="utf-8") as f:
            return json.load(f)
    with urllib.request.urlopen(URL) as r:
        data = json.load(r)
    with open(CACHE, "w", encoding="utf-8") as f:
        json.dump(data, f)
    return data


def _dist_punto_segmento(p, a, b):
    (px, py), (ax, ay), (bx, by) = p, a, b
    dx, dy = bx - ax, by - ay
    if dx == dy == 0:
        return ((px - ax) ** 2 + (py - ay) ** 2) ** 0.5
    t = ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)
    t = max(0.0, min(1.0, t))
    cx, cy = ax + t * dx, ay + t * dy
    return ((px - cx) ** 2 + (py - cy) ** 2) ** 0.5


def simplificar(puntos, tol):
    if len(puntos) <= 2:
        return puntos
    # Douglas-Peucker iterativo para evitar recursion profunda.
    keep = [False] * len(puntos)
    keep[0] = keep[-1] = True
    pila = [(0, len(puntos) - 1)]
    while pila:
        i, j = pila.pop()
        if j <= i + 1:
            continue
        dmax, idx = 0.0, i
        for k in range(i + 1, j):
            d = _dist_punto_segmento(puntos[k], puntos[i], puntos[j])
            if d > dmax:
                dmax, idx = d, k
        if dmax > tol:
            keep[idx] = True
            pila.append((i, idx))
            pila.append((idx, j))
    return [p for p, k in zip(puntos, keep) if k]


def anillos(geom):
    tipo = geom["type"]
    if tipo == "Polygon":
        return geom["coordinates"]
    if tipo == "MultiPolygon":
        return [anillo for poly in geom["coordinates"] for anillo in poly]
    return []


def main():
    data = descargar()
    deptos = []
    xs, ys = [], []
    for feat in data["features"]:
        props = feat.get("properties", {})
        nombre = props.get("shapeName") or props.get("NAME_1") or "Departamento"
        poligonos = []
        for anillo in anillos(feat["geometry"]):
            simple = simplificar([(float(x), float(y)) for x, y in anillo], TOLERANCIA)
            if len(simple) < 3:
                continue
            poligonos.append([[round(x, 5), round(y, 5)] for x, y in simple])
            xs.extend(p[0] for p in simple)
            ys.extend(p[1] for p in simple)
        if poligonos:
            deptos.append({"nombre": nombre, "anillos": poligonos})

    deptos.sort(key=lambda d: d["nombre"])
    salida = {"bbox": [min(xs), min(ys), max(xs), max(ys)], "departamentos": deptos}
    os.makedirs(os.path.dirname(SALIDA), exist_ok=True)
    with open(SALIDA, "w", encoding="utf-8") as f:
        json.dump(salida, f, ensure_ascii=False, separators=(",", ":"))
    total = sum(len(a) for d in deptos for a in d["anillos"])
    print(f"{len(deptos)} departamentos, {total} puntos -> {os.path.normpath(SALIDA)}")


if __name__ == "__main__":
    main()
