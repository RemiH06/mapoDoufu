"""Ejecuta `estado.ipynb` para cada estado y deja la copia ejecutada en
`estados/NN.ipynb` y las cifras en `resultados/NN.json`.

    uv run python por_estado.py              # los 32, saltando los ya hechos
    uv run python por_estado.py 03 14        # solo esos
    uv run python por_estado.py --todo       # rehacer aunque ya estén

Un estado que falla no detiene a los demás: queda en `estados/NN.error.txt`.
"""

from __future__ import annotations

import os
import sys
import time
import traceback
from pathlib import Path

import nbformat
from nbconvert.preprocessors import ExecutePreprocessor

AQUI = Path(__file__).parent
PLANTILLA = AQUI / "estado.ipynb"
ESTADOS = [f"{n:02d}" for n in range(1, 33)]


def correr(estado: str) -> None:
    nb = nbformat.read(PLANTILLA, as_version=4)
    os.environ["ESTADO"] = estado
    ExecutePreprocessor(timeout=7200, kernel_name="python3").preprocess(nb, {"metadata": {"path": str(AQUI)}})
    nbformat.write(nb, AQUI / "estados" / f"{estado}.ipynb")


def main() -> int:
    argumentos = [a for a in sys.argv[1:] if a != "--todo"]
    rehacer = "--todo" in sys.argv
    (AQUI / "estados").mkdir(exist_ok=True)
    fallas = []
    for estado in argumentos or ESTADOS:
        if not rehacer and (AQUI / "resultados" / f"{estado}.json").exists():
            continue
        inicio = time.time()
        try:
            correr(estado)
            (AQUI / "estados" / f"{estado}.error.txt").unlink(missing_ok=True)
            print(f"{estado} listo en {time.time() - inicio:.0f} s", flush=True)
        except Exception:
            fallas.append(estado)
            (AQUI / "estados" / f"{estado}.error.txt").write_text(traceback.format_exc(), encoding="utf-8")
            print(f"{estado} FALLÓ en {time.time() - inicio:.0f} s", flush=True)
    print("Fallas:", ", ".join(fallas) or "ninguna")
    return 1 if fallas else 0


if __name__ == "__main__":
    raise SystemExit(main())
