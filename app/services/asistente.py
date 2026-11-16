"""Asistente de datos: respuestas locales y, si hay clave, refuerzo con un LLM."""
import json
import unicodedata
import urllib.request

from config import OPENAI_API_KEY, OPENAI_MODEL

from . import analytics as an


def _sin_acentos(t):
    return "".join(c for c in unicodedata.normalize("NFD", t)
                   if unicodedata.category(c) != "Mn").lower()


def _num(x):
    return f"{x:,.0f}".replace(",", ".")


def _contexto():
    k = an.kpis()
    m = an.meta()
    filas = [f"- Año completo más reciente: {k['anio']} con {_num(k['total'])} t.",
             f"- Variación vs año anterior: {k['variacion'] * 100:.1f} %.",
             f"- Ciudad con más residuos: {k['ciudad_top']} ({_num(k['ciudad_top_ton'])} t).",
             f"- Años incompletos excluidos de agregados anuales: {m['anios_incompletos']}.",
             f"- Ciudades: {', '.join(m['ciudades'])}."]
    return "\n".join(filas), k, m


def _ciudad(q, m):
    for c in sorted(m["ciudades"], key=len, reverse=True):
        if _sin_acentos(c) in q:
            return c
    return None


def _con_ia(pregunta, contexto):
    datos = {"model": OPENAI_MODEL, "temperature": 0.2, "messages": [
        {"role": "system", "content": "Sos un asistente de datos de residuos sólidos de Bolivia. "
                                      "Respondé en español, breve y con cifras cuando aporten. Contexto:\n" + contexto},
        {"role": "user", "content": pregunta}]}
    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=json.dumps(datos).encode(),
        headers={"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.load(r)["choices"][0]["message"]["content"].strip()
    except Exception:
        return None


def responder(pregunta):
    pregunta = (pregunta or "").strip()
    if not pregunta:
        return {"respuesta": "Escribí una pregunta sobre los datos, por ejemplo: "
                             "«¿cuál es la ciudad con más residuos?» o «¿cuánto se proyecta para 2027?»."}
    q = _sin_acentos(pregunta)
    contexto, k, m = _contexto()
    ciudad = _ciudad(q, m)
    partes = []

    if any(w in q for w in ("pronost", "proyect", "futuro", "proxim")):
        cat = ciudad or "Total"
        try:
            p = an.pronostico("ciudades", cat, 12)
            total = sum(x for x in p["pred"]["y"] if x is not None)
            partes.append(f"Pronóstico de {cat} para los próximos 12 meses: {_num(total)} t en total. "
                          f"Modelo elegido por backtesting: {p['metodo']}.")
        except Exception:
            partes.append(f"No pude calcular el pronóstico de {cat}.")

    if any(w in q for w in ("tipo", "composic", "procedencia")):
        c = an.composicion()
        ult = c["anios"][-1]
        vals = {n: v[-1] for n, v in c["series"].items() if v[-1] is not None}
        if vals:
            top = max(vals, key=vals.get)
            partes.append(f"En {ult} el tipo con más toneladas fue «{top}» ({_num(vals[top])} t).")

    if any(w in q for w in ("nulo", "faltante", "vacio", "calidad", "imputa", "estim")):
        f = an.faltantes()
        totales = {c: sum(v) for c, v in zip(f["ciudades"], f["valores"])}
        top = sorted(totales.items(), key=lambda kv: kv[1], reverse=True)[:3]
        detalle = ", ".join(f"{c} ({n} meses)" for c, n in top if n)
        partes.append(f"Meses sin dato: {detalle}. Sucre se recorta antes de 2015 y los "
                      f"vacíos interiores se interpolan linealmente.")

    if any(w in q for w in ("mas", "top", "mayor", "ranking")) or "ciudad" in q:
        partes.append(f"En {k['anio']} la ciudad con más residuos fue {k['ciudad_top']} "
                      f"con {_num(k['ciudad_top_ton'])} t.")

    if ciudad and not any(w in q for w in ("pronost", "proyect", "futuro", "proxim")):
        try:
            s = an.serie_anual("ciudades", [ciudad], 2005, 2026)[0]
            if s["y"]:
                partes.append(f"{ciudad}: último año completo {s['x'][-1]} con {_num(s['y'][-1])} t.")
        except Exception:
            pass

    if not partes:
        partes.append(f"En {k['anio']} se recolectaron {_num(k['total'])} t en Bolivia "
                      f"({k['variacion'] * 100:.1f} % respecto a {k['anio'] - 1}).")

    respuesta = " ".join(partes)
    if OPENAI_API_KEY:
        respuesta = _con_ia(pregunta, contexto) or respuesta
    return {"respuesta": respuesta}
