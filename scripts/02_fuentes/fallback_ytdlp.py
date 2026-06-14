"""
Fallback validado con yt-dlp.

Se usa tarde y con filtros estrictos para evitar comentarios, reacciones o
videos que no sean el partido completo.
"""
import json
import logging
import os
import shutil
import subprocess

import config
from busqueda_reglas import altura_metadata, traducir_equipo, validar_candidato_ytdlp
from idioma_utils import detectar_idioma
from nombres_archivos import nombre_base_canonico_partido

logger = logging.getLogger("mundial")


def _yt_dlp_path() -> str | None:
    ytdlp_path = shutil.which("yt-dlp")
    if ytdlp_path:
        return ytdlp_path

    venv_path = os.path.join(config.DIRECTORIO_PROYECTO, "venv", "bin", "yt-dlp")
    if os.path.exists(venv_path):
        return venv_path
    return None


def _queries_ytdlp(equipo1: str, equipo2: str) -> list[str]:
    cantidad = getattr(config, "YTDLP_RESULTADOS_BUSQUEDA", 5)
    return [
        f'ytsearch{cantidad}:"{equipo1} vs {equipo2} mundial 2026 partido completo 720p"',
        f'ytsearch{cantidad}:"{equipo1} vs {equipo2} world cup 2026 full match 720p"',
        (
            f'ytsearch{cantidad}:"{traducir_equipo(equipo1)} vs '
            f'{traducir_equipo(equipo2)} FIFA World Cup 2026 full match 720p"'
        ),
    ]


def _buscar_candidatos(ytdlp_path: str, equipo1: str, equipo2: str) -> list[dict]:
    candidatos = []
    for query in _queries_ytdlp(equipo1, equipo2):
        try:
            logger.debug(f"[yt-dlp] Buscando: {query}")
            comando = [
                ytdlp_path,
                "--dump-json",
                "--skip-download",
                "--no-playlist",
                "--socket-timeout",
                "30",
                query,
            ]
            resultado = subprocess.run(comando, capture_output=True, text=True, timeout=180)
            if resultado.returncode != 0:
                logger.debug(f"[yt-dlp] No encontró resultado para: {query}")
                continue

            for linea in resultado.stdout.splitlines():
                try:
                    info = json.loads(linea)
                except json.JSONDecodeError:
                    continue

                valido, razon = validar_candidato_ytdlp(info, equipo1, equipo2)
                titulo = info.get("title") or "-"
                if not valido:
                    logger.debug(f"[yt-dlp] Rechazado: {titulo} ({razon})")
                    continue
                candidatos.append(info)

        except subprocess.TimeoutExpired:
            logger.warning(f"[yt-dlp] Timeout buscando: {query}")
        except Exception as e:
            logger.debug(f"[yt-dlp] Error: {e}")

    return candidatos


def _elegir_candidato(candidatos: list[dict]) -> dict | None:
    if not candidatos:
        return None
    candidatos.sort(
        key=lambda info: (
            altura_metadata(info) or 0,
            -abs(float(info.get("duration", 0)) - 7200),
        ),
        reverse=True,
    )
    return candidatos[0]


def buscar_ytdlp(equipo1: str, equipo2: str, directorio_destino: str) -> dict | None:
    """
    Busca y descarga un candidato validado con yt-dlp.

    Retorna info del archivo descargado o None.
    """
    if not config.FUENTES_HABILITADAS.get("yt_dlp"):
        return None

    ytdlp_path = _yt_dlp_path()
    if not ytdlp_path:
        logger.warning("yt-dlp no encontrado en PATH ni en venv")
        return None

    elegido = _elegir_candidato(_buscar_candidatos(ytdlp_path, equipo1, equipo2))
    if not elegido:
        logger.info("[yt-dlp] Sin candidatos confiables; no se descarga fallback")
        return None

    url = elegido.get("webpage_url") or elegido.get("original_url") or elegido.get("url")
    if not url:
        logger.info("[yt-dlp] Candidato sin URL util; no se descarga fallback")
        return None

    idioma = detectar_idioma(elegido.get("title"))
    nombre_archivo = nombre_base_canonico_partido(
        {"equipo1": equipo1, "equipo2": equipo2},
        idioma,
    )
    ruta_salida = os.path.join(directorio_destino, f"{nombre_archivo}.%(ext)s")
    logger.info(
        f"[yt-dlp] Candidato validado: {elegido.get('title')} "
        f"({round((elegido.get('duration') or 0) / 60, 1)} min, "
        f"{altura_metadata(elegido)}p)"
    )

    comando_descarga = [
        ytdlp_path,
        "-f",
        config.YTDLP_FORMATO,
        "-o",
        ruta_salida,
        "--no-playlist",
        "--socket-timeout",
        "30",
        url,
    ]

    try:
        resultado = subprocess.run(
            comando_descarga,
            capture_output=True,
            text=True,
            timeout=getattr(config, "YTDLP_TIMEOUT_SEGUNDOS", 7200),
        )
    except subprocess.TimeoutExpired:
        logger.warning("[yt-dlp] Timeout descargando candidato validado")
        return None
    except Exception as e:
        logger.debug(f"[yt-dlp] Error descargando candidato validado: {e}")
        return None

    if resultado.returncode != 0:
        logger.debug(resultado.stderr)
        logger.info("[yt-dlp] Fallo la descarga del candidato validado")
        return None

    logger.info(f"[yt-dlp] Descarga validada exitosa: {nombre_archivo}")
    return {
        "titulo": elegido.get("title") or nombre_archivo,
        "fuente": "yt-dlp",
        "ruta": directorio_destino,
        "url": url,
        "idioma": idioma,
        "yt_dlp_validado": True,
        "yt_dlp_duracion": elegido.get("duration"),
        "yt_dlp_altura": altura_metadata(elegido),
    }
