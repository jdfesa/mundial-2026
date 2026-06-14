"""
Fachada del buscador multi-fuente de partidos.

Las reglas viven en busqueda_reglas.py, los scrapers torrent en
fuentes_torrent.py y el fallback con yt-dlp en fallback_ytdlp.py.
"""
import logging
import re
import signal
from contextlib import contextmanager

import config
from busqueda_reglas import (
    altura_metadata as _altura_metadata,
    calcular_puntuacion,
    es_partido_completo,
    generar_queries,
    normalizar_tamano_gb,
    titulo_menciona_equipos,
    traducir_equipo as _traducir_equipo,
    validar_candidato_ytdlp as _validar_candidato_ytdlp,
)
from fallback_ytdlp import buscar_ytdlp
from fuentes_torrent import (
    buscar_1337x,
    buscar_btdig,
    buscar_limetorrents,
    buscar_piratebay,
    buscar_torrentgalaxy,
)

logger = logging.getLogger("mundial")


FUENTES_TORRENT = (
    ("1337x", buscar_1337x),
    ("TPB", buscar_piratebay),
    ("TGx", buscar_torrentgalaxy),
    ("Lime", buscar_limetorrents),
    ("BTDIG", buscar_btdig),
)


class TimeoutFuenteTorrent(TimeoutError):
    pass


@contextmanager
def _timeout_fuente(segundos: int):
    """Limita una fuente completa en Unix/macOS; en otros sistemas no hace nada."""
    if segundos <= 0 or not hasattr(signal, "SIGALRM"):
        yield
        return

    def _handler(_signum, _frame):
        raise TimeoutFuenteTorrent(f"timeout global de fuente tras {segundos}s")

    anterior = signal.getsignal(signal.SIGALRM)
    signal.signal(signal.SIGALRM, _handler)
    signal.setitimer(signal.ITIMER_REAL, segundos)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, anterior)


def _deduplicar_y_filtrar(resultados: list[dict], equipo1: str, equipo2: str) -> list[dict]:
    vistos = set()
    unicos = []

    for resultado in resultados:
        titulo = resultado.get("titulo", "")
        if not titulo_menciona_equipos(titulo, equipo1, equipo2):
            continue

        hash_match = re.search(r"btih:([a-fA-F0-9]+)", resultado.get("magnet", ""))
        if hash_match:
            info_hash = hash_match.group(1).lower()
            if info_hash in vistos:
                continue
            vistos.add(info_hash)

        unicos.append(resultado)

    return unicos


def _clasificar_con_groq(equipo1: str, equipo2: str, resultados: list[dict]) -> None:
    if not resultados or not getattr(config, "GROQ_HABILITADO", False):
        return

    try:
        from groq_asistente import clasificar_resultados

        clasificar_resultados(equipo1, equipo2, resultados)
        for resultado in resultados:
            groq_idioma = resultado.get("groq_idioma")
            if groq_idioma in {"es", "en", "desconocido"}:
                resultado.setdefault("idioma", groq_idioma)
    except Exception as e:
        logger.debug(f"[Groq] No se pudieron clasificar resultados: {e}")


def buscar_partido(equipo1: str, equipo2: str) -> list[dict]:
    """
    Busca un partido en todas las fuentes torrent habilitadas.

    Retorna una lista de resultados ordenados por puntuación (mejor primero).
    """
    logger.info(f"Buscando partido: {equipo1} vs {equipo2}")
    todos_resultados = []

    for etiqueta, buscador in FUENTES_TORRENT:
        try:
            with _timeout_fuente(int(getattr(config, "SCRAPER_TIMEOUT_SEGUNDOS", 45))):
                resultados = buscador(equipo1, equipo2)
            todos_resultados.extend(resultados)
            logger.info(f"  [{etiqueta}] {len(resultados)} resultados")
        except TimeoutFuenteTorrent as e:
            logger.warning(f"  [{etiqueta}] Timeout: {e}")
        except Exception as e:
            logger.error(f"  [{etiqueta}] Error: {e}")

    unicos = _deduplicar_y_filtrar(todos_resultados, equipo1, equipo2)
    _clasificar_con_groq(equipo1, equipo2, unicos)
    unicos.sort(key=lambda x: x.get("puntuacion", 0), reverse=True)

    logger.info(f"  Total: {len(unicos)} resultados únicos")
    if unicos:
        mejor = unicos[0]
        logger.info(
            f"  Mejor resultado: '{mejor['titulo']}' "
            f"(punt: {mejor['puntuacion']:.0f}, "
            f"seeders: {mejor['seeders']}, "
            f"tamaño: {mejor['tamano_gb']}GB, "
            f"fuente: {mejor['fuente']})"
        )

    return unicos


def obtener_mejor_resultado(equipo1: str, equipo2: str) -> dict | None:
    """Busca un partido y retorna el mejor resultado, o None si no encuentra nada."""
    resultados = buscar_partido(equipo1, equipo2)
    if not resultados:
        logger.warning(f"No se encontraron torrents para {equipo1} vs {equipo2}")
        return None
    return resultados[0]
