from pathlib import Path
import os

BASE = Path(__file__).parent
RAW = BASE / "data" / "raw"
ARCHIVOS = {
    "ciudades": RAW / "ciudades_mensual_2005_2026.xlsx",
    "tipos": RAW / "tipo_mensual_2005_2026.xlsx",
    "ciudad_tipo": RAW / "ciudad_tipo_2010_2025.xlsx",
}

ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
