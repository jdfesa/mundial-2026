"""
Limpieza de variantes de idioma una vez que existe la version final.

El ID identifica al partido y el sufijo identifica la variante. Si aparece
`005_..._es.mp4`, cualquier variante canonica no final (`_en`, `_bul`, `_rus`,
etc.) deja de aportar valor y se puede purgar para recuperar espacio.
"""
import logging
import re
from datetime import datetime, timezone
from pathlib import Path

import config
from idioma_utils import idioma_es_final

logger = logging.getLogger("mundial")


def _path_en_base(path: Path) -> bool:
    try:
        return path.expanduser().resolve().is_relative_to(Path(config.DIRECTORIO_BASE).resolve())
    except AttributeError:
        try:
            return str(path.expanduser().resolve()).startswith(str(Path(config.DIRECTORIO_BASE).resolve()))
        except OSError:
            return False
    except OSError:
        return False


def _directorios_busqueda(partido: dict) -> list[Path]:
    candidatos = [Path(config.DIRECTORIO_BASE)]
    if partido.get("ruta"):
        candidatos.append(Path(partido["ruta"]))
    for campo in ("archivo_local_ultimo", "archivo_web_ultimo", "archivo_local", "archivo_web"):
        valor = partido.get(campo)
        if valor:
            candidatos.append(Path(valor).parent)

    unicos = []
    vistos = set()
    for candidato in candidatos:
        try:
            path = candidato.expanduser().resolve()
        except OSError:
            continue
        if path in vistos or not path.exists() or not _path_en_base(path):
            continue
        vistos.add(path)
        unicos.append(path)
    return unicos


def _patron_no_final(partido: dict) -> re.Pattern | None:
    partido_id = partido.get("id")
    try:
        prefijo = f"{int(partido_id):03d}_"
    except (TypeError, ValueError):
        return None
    extensiones = [re.escape(ext.lstrip(".").lower()) for ext in getattr(config, "EXTENSIONES_VIDEO", [])]
    return re.compile(rf"^{re.escape(prefijo)}.+_(?!es\.)[a-z]{{2,3}}\.({'|'.join(extensiones)})$")


def purgar_ingles_si_es_final(partido: dict, dry_run: bool = False) -> dict:
    """Elimina variantes canonicas no finales cuando ya existe `_es` final."""
    resumen = {"purgados": 0, "omitidos": 0, "candidatos": []}
    if not getattr(config, "PURGAR_INGLES_AL_FINAL_ES", True):
        return resumen
    if not idioma_es_final(partido.get("idioma")):
        return resumen
    if not (partido.get("archivo_web_existe") or partido.get("archivo_existe")):
        return resumen

    patron = _patron_no_final(partido)
    if not patron:
        return resumen

    actuales = {
        str(Path(valor).expanduser().resolve())
        for valor in (
            partido.get("archivo_local"),
            partido.get("archivo_web"),
            partido.get("archivo_local_ultimo"),
            partido.get("archivo_web_ultimo"),
        )
        if valor
    }

    candidatos = []
    vistos = set()
    for directorio in _directorios_busqueda(partido):
        for path in directorio.rglob("*"):
            if not path.is_file():
                continue
            try:
                resuelto = str(path.expanduser().resolve())
            except OSError:
                resumen["omitidos"] += 1
                continue
            if resuelto in vistos or resuelto in actuales:
                continue
            if not patron.match(path.name.lower()):
                continue
            vistos.add(resuelto)
            candidatos.append(path)

    if not candidatos:
        return resumen

    resumen["candidatos"] = [str(path) for path in candidatos]
    if dry_run:
        partido["purga_idioma_anterior_pendiente"] = resumen["candidatos"]
        return resumen

    purgados = []
    errores = []
    for path in candidatos:
        if not _path_en_base(path):
            resumen["omitidos"] += 1
            continue
        try:
            path.unlink()
            purgados.append(str(path))
        except OSError as e:
            errores.append(f"{path}:{e}")

    if purgados:
        partido["archivos_idioma_anterior_purgados"] = purgados
        partido["idioma_anterior_purgado_en"] = datetime.now(timezone.utc).isoformat()
        resumen["purgados"] = len(purgados)
        logger.info(
            "Version no final purgada tras version final en espanol: "
            f"{partido.get('id')} ({len(purgados)} archivo/s)"
        )
    if errores:
        partido["purga_idioma_anterior_error"] = " | ".join(errores)
        resumen["omitidos"] += len(errores)
        logger.warning(f"No se pudo purgar idioma anterior: {partido['purga_idioma_anterior_error']}")

    return resumen
