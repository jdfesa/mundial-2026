"""
Verificador local de archivos descargados.

Busca archivos de video en las carpetas configuradas, intenta asociarlos con
partidos del calendario y, si ffprobe esta disponible, extrae duracion,
resolucion e idioma de pistas de audio.
"""
import json
import logging
import os
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import config
from idioma_utils import detectar_idioma, idioma_es_final, normalizar_texto

logger = logging.getLogger("mundial")


def _directorios_busqueda(partido: dict | None = None) -> list[Path]:
    rutas = [Path(config.DIRECTORIO_BASE)]
    if partido and partido.get("ruta"):
        rutas.insert(0, Path(partido["ruta"]))
    for extra in getattr(config, "DIRECTORIOS_VERIFICACION_EXTRA", []):
        rutas.append(Path(extra).expanduser())

    unicas = []
    vistos = set()
    for ruta in rutas:
        try:
            resuelta = ruta.expanduser().resolve()
        except OSError:
            continue
        if resuelta in vistos or not resuelta.exists():
            continue
        vistos.add(resuelta)
        unicas.append(resuelta)
    return unicas


def _iter_videos(directorios: list[Path]) -> list[Path]:
    extensiones = tuple(e.lower() for e in getattr(config, "EXTENSIONES_VIDEO", []))
    videos = []
    for directorio in directorios:
        for path in directorio.rglob("*"):
            if path.is_file() and path.suffix.lower() in extensiones:
                videos.append(path)
    return videos


def _score_candidato(partido: dict, path: Path) -> int:
    texto = normalizar_texto(str(path))
    score = 0

    archivo = normalizar_texto(partido.get("archivo"))
    if archivo and archivo in texto:
        score += 100

    equipo1 = normalizar_texto(partido.get("equipo1"))
    equipo2 = normalizar_texto(partido.get("equipo2"))
    if equipo1 and equipo1 in texto:
        score += 30
    if equipo2 and equipo2 in texto:
        score += 30

    partido_id = partido.get("id")
    if partido_id is not None and re.search(rf"\b{partido_id}\b", texto):
        score += 5

    return score


def _ffprobe(path: Path) -> dict:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return {"ffprobe": "no_disponible"}

    comando = [
        ffprobe,
        "-v",
        "quiet",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        str(path),
    ]
    try:
        resultado = subprocess.run(comando, capture_output=True, text=True, timeout=30)
    except Exception as e:
        return {"ffprobe": f"error: {e}"}

    if resultado.returncode != 0:
        return {"ffprobe": "error"}

    try:
        datos = json.loads(resultado.stdout)
    except json.JSONDecodeError:
        return {"ffprobe": "json_invalido"}

    return _extraer_metadata_ffprobe(datos)


def _extraer_metadata_ffprobe(datos: dict) -> dict:
    formato = datos.get("format", {})
    streams = datos.get("streams", [])
    meta = {"ffprobe": "ok"}

    try:
        duracion = float(formato.get("duration", 0))
        if duracion > 0:
            meta["duracion_min"] = round(duracion / 60, 1)
    except (TypeError, ValueError):
        pass

    for stream in streams:
        if stream.get("codec_type") == "video" and "resolucion" not in meta:
            width = stream.get("width")
            height = stream.get("height")
            if width and height:
                meta["resolucion"] = f"{width}x{height}"
        if stream.get("codec_type") == "audio":
            tags = stream.get("tags", {})
            idioma = tags.get("language")
            title = tags.get("title")
            texto = " ".join(str(v) for v in (idioma, title) if v)
            detectado = detectar_idioma(texto)
            if texto:
                meta.setdefault("pistas_audio", []).append(texto)
            if idioma_es_final(detectado):
                meta["idioma_audio"] = detectado

    return meta


def verificar_partido(partido: dict, videos_cache: list[Path] | None = None) -> dict | None:
    """Busca el mejor archivo local para un partido y devuelve metadata."""
    directorios = _directorios_busqueda(partido)
    videos = videos_cache if videos_cache is not None else _iter_videos(directorios)
    candidatos = []

    for video in videos:
        try:
            if not any(video.is_relative_to(d) for d in directorios):
                continue
        except AttributeError:
            if not any(str(video).startswith(str(d)) for d in directorios):
                continue
        score = _score_candidato(partido, video)
        if score > 0:
            candidatos.append((score, video))

    if not candidatos:
        return None

    candidatos.sort(key=lambda item: (item[0], item[1].stat().st_size), reverse=True)
    _, path = candidatos[0]
    stat = path.stat()
    meta = {
        "archivo_local": str(path),
        "archivo_existe": True,
        "tamano_mb": round(stat.st_size / (1024 * 1024), 1),
        "verificado_en": datetime.now(timezone.utc).isoformat(),
    }
    meta.update(_ffprobe(path))

    texto_idioma = " ".join(
        [
            path.name,
            " ".join(meta.get("pistas_audio", [])),
            meta.get("idioma_audio", ""),
        ]
    )
    idioma = meta.get("idioma_audio") or detectar_idioma(texto_idioma)
    meta["idioma_detectado_archivo"] = idioma
    return meta


def verificar_archivos(calendario: list[dict]) -> dict:
    """Actualiza los partidos con metadata local y retorna resumen."""
    videos_cache = _iter_videos(_directorios_busqueda())
    resumen = {"verificados": 0, "encontrados": 0, "sin_archivo": 0}

    for partido in calendario:
        if not partido.get("descargado"):
            continue
        resumen["verificados"] += 1
        meta = verificar_partido(partido, videos_cache)
        if not meta:
            partido["archivo_existe"] = False
            partido["verificado_en"] = datetime.now(timezone.utc).isoformat()
            resumen["sin_archivo"] += 1
            continue

        resumen["encontrados"] += 1
        partido.update(meta)
        idioma_archivo = meta.get("idioma_detectado_archivo")
        if idioma_archivo and idioma_es_final(idioma_archivo):
            partido["idioma"] = idioma_archivo
            partido["estado_final"] = True
            partido["necesita_mejora"] = False

    logger.info(
        "Verificacion local: "
        f"{resumen['encontrados']}/{resumen['verificados']} archivos encontrados"
    )
    return resumen
