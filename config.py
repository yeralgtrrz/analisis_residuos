from pathlib import Path

CORTE = "2023-01-01"

BASE = Path(__file__).parent
RAW = BASE / "data" / "raw"
ARCHIVOS = {
    "ciudades": RAW / "ciudades_mensual_2005_2026.xlsx",
    "tipos": RAW / "tipo_mensual_2005_2026.xlsx",
    "ciudad_tipo": RAW / "ciudad_tipo_2010_2025.xlsx",
}
