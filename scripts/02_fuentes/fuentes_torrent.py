"""
Fuentes torrent configurables para partidos del Mundial 2026.
"""
import logging
import re
import time
from urllib.parse import quote_plus

import requests
from bs4 import BeautifulSoup

import config
from busqueda_reglas import (
    calcular_puntuacion,
    es_partido_completo,
    generar_queries,
    normalizar_tamano_gb,
    titulo_menciona_equipos,
)

logger = logging.getLogger("mundial")

try:
    from py1337x import Py1337x

    PY1337X_DISPONIBLE = True
except ImportError:
    PY1337X_DISPONIBLE = False
    logger.warning("py1337x no está instalado. Ejecutá: pip install 1337x")


HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/120.0.0.0 Safari/537.36"
}

TRACKERS = [
    "udp://tracker.opentrackr.org:1337/announce",
    "udp://open.stealth.si:80/announce",
    "udp://tracker.torrent.eu.org:451/announce",
    "udp://tracker.bittor.pw:1337/announce",
    "udp://public.popcorn-tracker.org:6969/announce",
    "udp://tracker.dler.org:6969/announce",
    "udp://exodus.desync.com:6969",
    "udp://open.demonii.com:1337/announce",
]


def _hash_magnet(magnet: str) -> str | None:
    match = re.search(r"btih:([a-fA-F0-9]+)", magnet)
    return match.group(1).lower() if match else None


def _resultado(titulo: str, magnet: str, seeders: int, tamano_gb: float, fuente: str) -> dict:
    return {
        "titulo": titulo,
        "magnet": magnet,
        "torrent_hash": _hash_magnet(magnet),
        "seeders": seeders,
        "tamano_gb": round(tamano_gb, 2),
        "fuente": fuente,
        "puntuacion": calcular_puntuacion(titulo, seeders, tamano_gb),
    }


def _mirrors_indexador(nombre: str, fallback: list[str] | None = None) -> list[str]:
    datos_fuentes = config.cargar_fuentes_torrent()
    for idx in datos_fuentes.get("indexadores", []):
        if idx.get("nombre") == nombre and idx.get("habilitado"):
            return idx.get("mirrors", fallback or [])
    return fallback or []


def buscar_1337x(equipo1: str, equipo2: str) -> list[dict]:
    """Busca torrents en 1337x usando py1337x."""
    if not PY1337X_DISPONIBLE or not config.indexador_habilitado("1337x"):
        return []

    resultados = []
    queries = generar_queries(equipo1, equipo2)

    for query in queries[:5]:
        try:
            logger.debug(f"[1337x] Buscando: {query}")
            torrent = Py1337x()
            busqueda = torrent.search(query, page=1, sortBy="seeders", order="desc")

            if not busqueda or "items" not in busqueda:
                continue

            for item in busqueda["items"][:10]:
                titulo = item.get("name", "")
                if not es_partido_completo(titulo):
                    continue

                try:
                    info = torrent.info(link=item.get("link", ""))
                    magnet = info.get("magnetLink", "")
                    seeders = int(info.get("seeders", 0))
                    tamano_str = info.get("size", "0 GB")
                except Exception:
                    magnet = ""
                    seeders = int(item.get("seeders", 0))
                    tamano_str = item.get("size", "0 GB")

                if not magnet:
                    continue

                tamano_gb = normalizar_tamano_gb(tamano_str)
                if tamano_gb < config.TAMANO_MIN_GB or seeders < config.MIN_SEEDERS:
                    continue

                resultados.append(_resultado(titulo, magnet, seeders, tamano_gb, "1337x"))

            time.sleep(1)

        except Exception as e:
            logger.debug(f"[1337x] Error buscando '{query}': {e}")
            continue

    return resultados


def buscar_piratebay(equipo1: str, equipo2: str) -> list[dict]:
    """Busca torrents en The Pirate Bay usando APIs de fuentes_torrent.json."""
    if not config.indexador_habilitado("piratebay"):
        return []

    mirrors = config.obtener_mirrors_tpb()
    if not mirrors:
        logger.warning("[TPB] No hay mirrors configurados en fuentes_torrent.json")
        return []

    resultados = []
    queries = generar_queries(equipo1, equipo2)

    for query in queries[:6]:
        for mirror in mirrors:
            try:
                url = f"{mirror}/q.php?q={quote_plus(query)}&cat=200"
                logger.debug(f"[TPB] Buscando: {url}")

                resp = requests.get(url, headers=HEADERS, timeout=15)
                if resp.status_code != 200:
                    continue

                datos = resp.json()
                if not datos or (len(datos) == 1 and datos[0].get("name") == "No results returned"):
                    continue

                for item in datos[:10]:
                    titulo = item.get("name", "")
                    if not es_partido_completo(titulo):
                        continue

                    seeders = int(item.get("seeders", 0))
                    tamano_bytes = int(item.get("size", 0))
                    tamano_gb = tamano_bytes / (1024**3)
                    info_hash = item.get("info_hash", "")

                    if not info_hash or seeders < config.MIN_SEEDERS:
                        continue
                    if tamano_gb < config.TAMANO_MIN_GB:
                        continue

                    tracker_str = "&".join([f"tr={quote_plus(t)}" for t in TRACKERS])
                    magnet = f"magnet:?xt=urn:btih:{info_hash}&dn={quote_plus(titulo)}&{tracker_str}"
                    item_resultado = _resultado(titulo, magnet, seeders, tamano_gb, "piratebay")
                    item_resultado["torrent_hash"] = info_hash.lower()
                    resultados.append(item_resultado)

                time.sleep(1)
                break

            except Exception as e:
                logger.debug(f"[TPB] Error en mirror {mirror}: {e}")
                continue

    return resultados


def buscar_torrentgalaxy(equipo1: str, equipo2: str) -> list[dict]:
    """Busca torrents en TorrentGalaxy via scraping HTML."""
    if not config.indexador_habilitado("torrentgalaxy"):
        return []

    mirrors = _mirrors_indexador("torrentgalaxy", ["https://torrentgalaxy.to"])
    resultados = []
    queries = generar_queries(equipo1, equipo2)

    for query in queries[:5]:
        for mirror in mirrors:
            try:
                url = f"{mirror}/torrents.php?search={quote_plus(query)}&cat=41&sort=seeders&order=desc"
                logger.debug(f"[TGx] Buscando: {url}")

                resp = requests.get(url, headers=HEADERS, timeout=15)
                if resp.status_code != 200:
                    continue

                soup = BeautifulSoup(resp.text, "html.parser")
                filas = soup.select("div.tgxtablerow")

                for fila in filas[:10]:
                    link_titulo = fila.select_one("a.txlight")
                    if not link_titulo:
                        continue
                    titulo = link_titulo.get_text(strip=True)
                    if not es_partido_completo(titulo):
                        continue

                    link_magnet = fila.select_one('a[href^="magnet:"]')
                    if not link_magnet:
                        continue
                    magnet = link_magnet["href"]

                    span_seed = fila.select_one('span[title="Seeders/Leechers"] b')
                    if not span_seed:
                        font_seed = fila.select_one('font[color="green"]')
                        seeders = int(font_seed.get_text(strip=True)) if font_seed else 0
                    else:
                        seeders = int(span_seed.get_text(strip=True))

                    if seeders < config.MIN_SEEDERS:
                        continue

                    span_size = fila.select_one("span.badge-secondary")
                    tamano_str = span_size.get_text(strip=True) if span_size else "0 GB"
                    tamano_gb = normalizar_tamano_gb(tamano_str)
                    if tamano_gb < config.TAMANO_MIN_GB:
                        continue

                    resultados.append(_resultado(titulo, magnet, seeders, tamano_gb, "torrentgalaxy"))

                time.sleep(1)
                break

            except Exception as e:
                logger.debug(f"[TGx] Error en mirror {mirror}: {e}")
                continue

    return resultados


def buscar_limetorrents(equipo1: str, equipo2: str) -> list[dict]:
    """Busca torrents en LimeTorrents via scraping HTML."""
    if not config.indexador_habilitado("limetorrents"):
        return []

    mirrors = _mirrors_indexador("limetorrents", ["https://www.limetorrents.lol"])
    resultados = []
    queries = generar_queries(equipo1, equipo2)

    for query in queries[:5]:
        for mirror in mirrors:
            try:
                search_term = query.replace(" ", "-")
                url = f"{mirror}/search/all/{quote_plus(search_term)}/seeds/1/"
                logger.debug(f"[Lime] Buscando: {url}")

                resp = requests.get(url, headers=HEADERS, timeout=15)
                if resp.status_code != 200:
                    continue

                soup = BeautifulSoup(resp.text, "html.parser")
                tabla = soup.select_one("table.table2")
                if not tabla:
                    continue

                filas = tabla.select("tr")[1:]
                for fila in filas[:10]:
                    celdas = fila.select("td")
                    if len(celdas) < 5:
                        continue

                    link_titulo = celdas[0].select_one("a")
                    if not link_titulo:
                        continue
                    titulo = link_titulo.get_text(strip=True)
                    if not es_partido_completo(titulo):
                        continue

                    href = link_titulo.get("href", "")
                    if not href:
                        continue

                    try:
                        seeders = int(celdas[3].get_text(strip=True).replace(",", ""))
                    except (ValueError, IndexError):
                        seeders = 0

                    if seeders < config.MIN_SEEDERS:
                        continue

                    tamano_str = celdas[2].get_text(strip=True)
                    tamano_gb = normalizar_tamano_gb(tamano_str)
                    if tamano_gb < config.TAMANO_MIN_GB:
                        continue

                    try:
                        detail_url = href if href.startswith("http") else f"{mirror}{href}"
                        resp_detail = requests.get(detail_url, headers=HEADERS, timeout=10)
                        soup_detail = BeautifulSoup(resp_detail.text, "html.parser")
                        magnet_link = soup_detail.select_one('a[href^="magnet:"]')
                        if not magnet_link:
                            continue
                        magnet = magnet_link["href"]
                    except Exception:
                        continue

                    resultados.append(_resultado(titulo, magnet, seeders, tamano_gb, "limetorrents"))

                time.sleep(1)
                break

            except Exception as e:
                logger.debug(f"[Lime] Error en mirror {mirror}: {e}")
                continue

    return resultados


def buscar_btdig(equipo1: str, equipo2: str) -> list[dict]:
    """Busca torrents en BTDIG (motor de búsqueda DHT, no requiere tracker)."""
    if not config.indexador_habilitado("btdig"):
        return []

    datos_fuentes = config.cargar_fuentes_torrent()
    base_url = "https://btdig.com"
    for idx in datos_fuentes.get("indexadores", []):
        if idx.get("nombre") == "btdig" and idx.get("habilitado"):
            base_url = idx.get("url", base_url)
            break

    resultados = []
    queries = generar_queries(equipo1, equipo2)
    tracker_str = "&".join([f"tr={quote_plus(t)}" for t in TRACKERS])

    for query in queries[:4]:
        try:
            url = f"{base_url}/search?q={quote_plus(query)}&order=0"
            logger.debug(f"[BTDIG] Buscando: {url}")

            resp = requests.get(url, headers=HEADERS, timeout=15)
            if resp.status_code != 200:
                continue

            soup = BeautifulSoup(resp.text, "html.parser")
            items = soup.select("div.one_result")

            for item in items[:10]:
                link_titulo = item.select_one("div.torrent_name a")
                if not link_titulo:
                    continue
                titulo = link_titulo.get_text(strip=True)

                if not es_partido_completo(titulo):
                    continue
                if not titulo_menciona_equipos(titulo, equipo1, equipo2):
                    continue

                href = link_titulo.get("href", "")
                hash_match = re.search(r"/([a-fA-F0-9]{40})/", href)
                if not hash_match:
                    continue
                info_hash = hash_match.group(1).lower()

                span_size = item.select_one("span.torrent_size")
                tamano_str = span_size.get_text(strip=True) if span_size else "0 GB"
                tamano_gb = normalizar_tamano_gb(tamano_str)
                if tamano_gb < config.TAMANO_MIN_GB:
                    continue

                seeders = 1
                magnet = f"magnet:?xt=urn:btih:{info_hash}&dn={quote_plus(titulo)}&{tracker_str}"
                item_resultado = _resultado(titulo, magnet, seeders, tamano_gb, "btdig")
                item_resultado["torrent_hash"] = info_hash
                resultados.append(item_resultado)

            time.sleep(1)

        except Exception as e:
            logger.debug(f"[BTDIG] Error buscando '{query}': {e}")
            continue

    return resultados
