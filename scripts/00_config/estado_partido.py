"""
Reglas compartidas para interpretar el estado operativo de un partido.

El calendario conserva la identidad del partido. Estos helpers solo responden
preguntas de flujo: si una descarga sigue activa, si ya se puede verificar un
archivo local, o si corresponde esperar a qBittorrent.
"""

ESTADOS_COMPLETOS = {
    "completa",
    "complete",
    "completed",
    "uploading",
    "stalledup",
    "pausedup",
    "queuedup",
    "checkingup",
    "forcedup",
}

ESTADOS_EN_PROGRESO = {
    "activa",
    "downloading",
    "stalleddl",
    "pauseddl",
    "queueddl",
    "checkingdl",
    "forceddl",
    "metadl",
    "allocating",
    "checkingresume",
    "moving",
}


def _estado_descarga(partido: dict) -> str:
    return str(partido.get("descarga_estado") or "").strip().lower()


def progreso_descarga(partido: dict) -> float | None:
    """Devuelve el progreso normalizado a porcentaje 0..100 si existe."""
    progreso = partido.get("descarga_progreso")
    if progreso is None:
        return None
    try:
        valor = float(progreso)
    except (TypeError, ValueError):
        return None
    if 0 <= valor <= 1:
        return valor * 100
    return valor


def descarga_confirmada_completa(partido: dict) -> bool:
    """Indica si la descarga llego a 100% segun estado o progreso."""
    progreso = progreso_descarga(partido)
    if progreso is not None and progreso >= 100:
        return True
    return _estado_descarga(partido) in ESTADOS_COMPLETOS


def descarga_en_progreso(partido: dict) -> bool:
    """
    True cuando hay evidencia de una descarga activa/incompleta.

    Estados como missingFiles no cuentan como progreso: suelen aparecer despues
    de retirar o borrar el origen y no deben disparar una nueva descarga.
    """
    if descarga_confirmada_completa(partido):
        return False
    estado = _estado_descarga(partido)
    if estado in ESTADOS_EN_PROGRESO:
        return True
    if estado:
        return False
    progreso = progreso_descarga(partido)
    return progreso is not None and progreso < 100


def archivo_local_usable(partido: dict) -> bool:
    """Un archivo local solo se usa cuando qBittorrent ya no lo esta bajando."""
    return not descarga_en_progreso(partido)
