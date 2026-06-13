"""
Fuentes manuales o autorizadas para descargar con yt-dlp.

Este modulo no busca copias por la web: lee URLs declaradas por vos en un JSON.
Sirve para replays oficiales, grabaciones propias subidas a una URL accesible,
o cualquier fuente que tengas permiso de descargar.
"""
import json
import logging
import os
import re
import shutil
import subprocess
import unicodedata

import config
from nombres_archivos import nombre_base_canonico_partido

logger = logging.getLogger("mundial")


def _normalizar(texto: str | None) -> str:
    texto = texto or ""
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    texto = texto.lower()
    return re.sub(r"[^a-z0-9]+", " ", texto).strip()


def _yt_dlp_path() -> str | None:
    ytdlp_path = shutil.which("yt-dlp")
    if ytdlp_path:
        return ytdlp_path

    candidatos = [
        os.path.join(config.DIRECTORIO_PROYECTO, "venv", "bin", "yt-dlp"),
        os.path.join(config.DIRECTORIO_PROYECTO, "venv", "Scripts", "yt-dlp.exe"),
    ]
    for candidato in candidatos:
        if os.path.exists(candidato):
            return candidato
    return None


def cargar_fuentes() -> list[dict]:
    """Carga fuentes manuales desde config.ARCHIVO_FUENTES_MANUALES."""
    ruta = getattr(config, "ARCHIVO_FUENTES_MANUALES", None)
    if not ruta or not os.path.exists(ruta):
        return []

    try:
        with open(ruta, "r", encoding="utf-8") as f:
            datos = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        logger.warning(f"No se pudieron cargar fuentes manuales: {e}")
        return []

    if isinstance(datos, list):
        return datos
    if isinstance(datos, dict):
        return datos.get("fuentes", [])
    return []


def buscar_fuente_manual(partido: dict) -> dict | None:
    """
    Busca una fuente manual para el partido.

    Prioridad: id exacto, luego equipos sin importar local/visitante.
    """
    fuentes = cargar_fuentes()
    if not fuentes:
        return None

    partido_id = partido.get("id")
    equipo1 = _normalizar(partido.get("equipo1"))
    equipo2 = _normalizar(partido.get("equipo2"))
    equipos = {equipo1, equipo2}

    for fuente in fuentes:
        if partido_id is not None and fuente.get("id") == partido_id:
            return fuente

    for fuente in fuentes:
        f_equipo1 = _normalizar(fuente.get("equipo1"))
        f_equipo2 = _normalizar(fuente.get("equipo2"))
        if {f_equipo1, f_equipo2} == equipos:
            return fuente

    return None


def descargar_fuente_manual(
    fuente: dict,
    partido: dict,
    directorio_destino: str,
    dry_run: bool = False,
) -> dict | None:
    """Descarga una URL declarada manualmente usando yt-dlp."""
    url = fuente.get("url")
    if not url:
        logger.warning("Fuente manual sin URL; se ignora")
        return None

    equipo1 = partido.get("equipo1", "Equipo1")
    equipo2 = partido.get("equipo2", "Equipo2")
    titulo = fuente.get("titulo") or f"{equipo1}_vs_{equipo2}"
    nombre_base = nombre_base_canonico_partido(partido, fuente.get("idioma"))
    ruta_salida = os.path.join(directorio_destino, f"{nombre_base}.%(ext)s")

    logger.info(f"  Fuente manual: {fuente.get('nombre', url)}")
    logger.info(f"  Idioma: {fuente.get('idioma', 'sin declarar')} | Calidad: {fuente.get('calidad', 'auto')}")

    if dry_run:
        logger.info("  [DRY RUN] Se descargaria la fuente manual con yt-dlp")
        return {
            "titulo": titulo,
            "fuente": "manual",
            "ruta": directorio_destino,
            "url": url,
        }

    os.makedirs(directorio_destino, exist_ok=True)
    ytdlp_path = _yt_dlp_path()
    if not ytdlp_path:
        logger.warning("yt-dlp no encontrado en PATH ni en el entorno virtual")
        return None

    comando = [
        ytdlp_path,
        "-f",
        getattr(config, "YTDLP_FORMATO", "best[height<=1080]/best"),
        "--merge-output-format",
        "mp4",
        "-o",
        ruta_salida,
        "--no-playlist",
        "--socket-timeout",
        "30",
        url,
    ]

    extra_args = getattr(config, "YTDLP_EXTRA_ARGS", [])
    if extra_args:
        comando[1:1] = list(extra_args)

    try:
        resultado = subprocess.run(
            comando,
            capture_output=True,
            text=True,
            timeout=getattr(config, "YTDLP_TIMEOUT_SEGUNDOS", 7200),
        )
    except subprocess.TimeoutExpired:
        logger.warning("Timeout descargando fuente manual con yt-dlp")
        return None
    except Exception as e:
        logger.warning(f"Error descargando fuente manual: {e}")
        return None

    if resultado.returncode != 0:
        logger.debug(resultado.stderr)
        logger.warning("yt-dlp no pudo descargar la fuente manual")
        return None

    return {
        "titulo": titulo,
        "fuente": "manual",
        "ruta": directorio_destino,
        "url": url,
    }
