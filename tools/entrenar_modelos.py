"""Reentrena y guarda los artefactos que usa la aplicación."""
import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from app.services.modelo import entrenar_artefactos  # noqa: E402

if __name__ == "__main__":
    print(json.dumps(entrenar_artefactos(), ensure_ascii=False, indent=2))
