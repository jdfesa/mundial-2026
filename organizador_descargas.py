"""
Sincroniza descargas completas de qBittorrent con la estructura de carpetas.

Cuando qBittorrent recibe un magnet por fallback puede descargar en su ruta por
defecto. Este modulo detecta torrents completos y le pide a qBittorrent que los
mueva al destino esperado del partido.
"""
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

import config
from idioma_utils import normalizar_texto

logger = logging.getLogger("mundial")


def directorio_partido(partido: dict) -> str:
    """Calcula el directorio final esperado para un partido."""
    fase = partido.get("fase", "grupo")
    carpeta_fase = config.CARPETAS_FASE.get(fase, "Otros")

    if fase == "grupo":
        grupo = partido.get("grupo", "Sin_Grupo").replace(" ", "_")
        return os.path.join(config.DIRECTORIO_BASE, carpeta_fase, grupo)
    return os.path.join(config.DIRECTORIO_BASE, carpeta_fase)


def _score_torrent_partido(torrent: dict, partido: dict) -> int:
    texto = normalizar_texto(" ".join([
        torrent.get("nombre", ""),
        torrent.get("content_path", ""),
    ]))
    score = 0

    torrent_hash = normalizar_texto(torrent.get("hash"))
    partido_hash = normalizar_texto(partido.get("torrent_hash"))
    if torrent_hash and partido_hash and torrent_hash == partido_hash:
        score += 200

    archivo = normalizar_texto(partido.get("archivo"))
    if archivo and archivo in texto:
        score += 120

    equipo1 = normalizar_texto(partido.get("equipo1"))
    equipo2 = normalizar_texto(partido.get("equipo2"))
    if equipo1 and equipo1 in texto:
        score += 30
    if equipo2 and equipo2 in texto:
        score += 30

    grupo = normalizar_texto(partido.get("grupo"))
    if grupo and grupo in texto:
        score += 10

    return score


def _actualizar_estado_torrent(partido: dict, torrent: dict) -> None:
    ahora = datetime.now(timezone.utc).isoformat()
    if torrent.get("hash"):
        partido["torrent_hash"] = torrent.get("hash")
    partido["descarga_estado"] = "completa" if torrent.get("completado") else torrent.get("estado", "activa")
    partido["descarga_progreso"] = torrent.get("progreso")
    partido["descarga_actualizada_en"] = ahora
    if torrent.get("ruta"):
        partido["ruta"] = torrent.get("ruta")


def _mismo_directorio(actual: str | None, destino: str) -> bool:
    if not actual:
        return False
    try:
        return Path(actual).expanduser().resolve() == Path(destino).expanduser().resolve()
    except OSError:
        return False


def sincronizar_descargas_completadas(
    calendario: list[dict],
    dry_run: bool = False,
    iniciar_qbit_si_no_corre: bool = False,
) -> dict:
    """
    Mueve torrents completos al directorio esperado del partido.

    En modo automatico puede abrir qBittorrent si no esta corriendo. En --status
    se deja desactivado para no abrir aplicaciones por sorpresa.
    """
    resumen = {"candidatos": 0, "movidos": 0, "omitidos": 0, "actualizados": 0}
    if not getattr(config, "QBIT_MOVER_COMPLETADOS", True):
        return resumen

    from qbit_manager import listar_torrents, mover_torrent

    torrents = listar_torrents(
        incluir_todos=getattr(config, "QBIT_BUSCAR_TODAS_LAS_DESCARGAS", True),
        iniciar_si_no_corre=iniciar_qbit_si_no_corre,
    )
    if not torrents:
        logger.info("No hay torrents para sincronizar")
        return resumen

    for torrent in torrents:
        mejor = None
        mejor_score = 0
        for partido in calendario:
            score = _score_torrent_partido(torrent, partido)
            if score > mejor_score:
                mejor = partido
                mejor_score = score

        if not mejor or mejor_score < 60:
            resumen["omitidos"] += 1
            continue

        _actualizar_estado_torrent(mejor, torrent)
        resumen["actualizados"] += 1

        if not torrent.get("completado"):
            continue

        destino = directorio_partido(mejor)
        resumen["candidatos"] += 1

        if _mismo_directorio(torrent.get("ruta"), destino):
            mejor["ruta"] = destino
            mejor["descarga_estado"] = "completa"
            mejor["descarga_progreso"] = 100
            mejor["movido_a_destino"] = True
            resumen["omitidos"] += 1
            continue

        logger.info(
            f"Torrent completo detectado: {torrent.get('nombre')} -> {destino}"
        )
        if dry_run:
            resumen["omitidos"] += 1
            continue

        if mover_torrent(torrent.get("hash", ""), destino):
            mejor["ruta"] = destino
            mejor["descarga_estado"] = "completa"
            mejor["descarga_progreso"] = 100
            mejor["movido_a_destino"] = True
            mejor["ultimo_movimiento"] = datetime.now(timezone.utc).isoformat()
            if not mejor.get("archivo"):
                mejor["archivo"] = torrent.get("nombre")
            resumen["movidos"] += 1
        else:
            resumen["omitidos"] += 1

    if resumen["candidatos"]:
        logger.info(
            "Sincronizacion qBittorrent: "
            f"{resumen['movidos']} movidos, {resumen['omitidos']} omitidos"
        )
    return resumen
