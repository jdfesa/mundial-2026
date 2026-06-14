"""Bootstrap de imports para los scripts modulares del proyecto."""
from pathlib import Path
import sys


def configurar_imports() -> None:
    """Agrega la raiz y las carpetas numeradas de scripts al import path."""
    scripts_root = Path(__file__).resolve().parent
    project_root = scripts_root.parent
    rutas = [project_root, scripts_root]
    rutas.extend(
        ruta
        for ruta in sorted(scripts_root.iterdir())
        if ruta.is_dir() and ruta.name[:2].isdigit()
    )

    for ruta in reversed(rutas):
        ruta_str = str(ruta)
        if ruta_str not in sys.path:
            sys.path.insert(0, ruta_str)
