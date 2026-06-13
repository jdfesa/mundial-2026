"""
Buscador multi-fuente de torrents para partidos del Mundial 2026.
Busca en múltiples sitios torrent con prioridad en español.
"""
import json
import re
import time
import logging
import requests
from bs4 import BeautifulSoup
from urllib.parse import quote_plus

import config
from idioma_utils import detectar_idioma, normalizar_texto
from nombres_archivos import nombre_base_canonico_partido

logger = logging.getLogger("mundial")

# Intentar importar py1337x
try:
    from py1337x import Py1337x
    PY1337X_DISPONIBLE = True
except ImportError:
    PY1337X_DISPONIBLE = False
    logger.warning("py1337x no está instalado. Ejecutá: pip install 1337x")


# ─── Utilidades ──────────────────────────────────────────────────────────────

def normalizar_tamano_gb(tamano_str: str) -> float:
    """Convierte un string de tamaño a GB. Ej: '2.5 GB' -> 2.5, '800 MB' -> 0.78"""
    try:
        tamano_str = tamano_str.strip().upper()
        match = re.search(r'([\d.]+)\s*(GB|MB|TB)', tamano_str)
        if not match:
            return 0.0
        valor = float(match.group(1))
        unidad = match.group(2)
        if unidad == "GB":
            return valor
        elif unidad == "MB":
            return valor / 1024
        elif unidad == "TB":
            return valor * 1024
        return 0.0
    except Exception:
        return 0.0


def es_partido_completo(titulo: str) -> bool:
    """Verifica que el resultado sea un partido completo y no un resumen."""
    titulo_lower = titulo.lower()
    # Verificar que no tenga keywords negativas
    for kw in config.KEYWORDS_NEGATIVAS:
        if kw.lower() in titulo_lower:
            return False
    return True


def titulo_menciona_equipos(titulo: str, equipo1: str, equipo2: str) -> bool:
    """Verifica que el título mencione al menos uno de los equipos del partido."""
    titulo_lower = normalizar_texto(titulo)
    nombres = [
        normalizar_texto(equipo1),
        normalizar_texto(equipo2),
        normalizar_texto(_traducir_equipo(equipo1)),
        normalizar_texto(_traducir_equipo(equipo2)),
    ]
    return any(n and n in titulo_lower for n in nombres)


def calcular_puntuacion(titulo: str, seeders: int, tamano_gb: float) -> float:
    """
    Calcula una puntuación para un resultado de torrent.
    Mayor puntuación = mejor candidato.
    Prioriza: español > seeders > tamaño razonable
    """
    puntuacion = 0.0
    titulo_lower = titulo.lower()

    # Bonus por idioma español (mayor prioridad)
    indicadores_espanol = ["español", "espanol", "spanish", "latino", "castellano", "spa"]
    for ind in indicadores_espanol:
        if ind in titulo_lower:
            puntuacion += 100
            break

    # Bonus por partido completo
    indicadores_completo = ["full match", "completo", "full game", "partido completo"]
    for ind in indicadores_completo:
        if ind in titulo_lower:
            puntuacion += 50
            break

    # Bonus por calidad. La preferencia operativa es 720p: suficiente calidad,
    # archivos razonables y menos CPU/espacio para administrar.
    if "720p" in titulo_lower or "hdtv" in titulo_lower:
        puntuacion += 30
    elif "1080p" in titulo_lower or "full hd" in titulo_lower:
        puntuacion += 8
    elif "4k" in titulo_lower or "2160p" in titulo_lower:
        puntuacion -= 25

    # Bonus por seeders (logarítmico para no sobrevalorar)
    if seeders > 0:
        import math
        puntuacion += min(math.log2(seeders + 1) * 5, 40)

    # Penalización por tamaño extremo
    if tamano_gb < config.TAMANO_MIN_GB:
        puntuacion -= 50  # Probablemente no es un partido completo
    elif tamano_gb > config.TAMANO_MAX_GB:
        puntuacion -= 20  # Muy grande, posiblemente 4K
    elif 1.5 <= tamano_gb <= getattr(config, "TAMANO_IDEAL_MAX_GB", 5.0):
        puntuacion += 15  # Tamaño ideal para HD
    elif tamano_gb > getattr(config, "TAMANO_IDEAL_MAX_GB", 5.0):
        puntuacion -= 8

    # Bonus por keywords de mundial
    mundial_keywords = ["world cup", "mundial", "copa del mundo", "fifa", "wc2026", "wc 2026"]
    for kw in mundial_keywords:
        if kw in titulo_lower:
            puntuacion += 10
            break

    return puntuacion


def _traducir_equipo(nombre: str) -> str:
    """Traduce el nombre de un equipo del español al inglés."""
    traducciones = {
        "Estados Unidos": "USA",
        "Corea del Sur": "South Korea",
        "Rep. Checa": "Czech Republic",
        "Países Bajos": "Netherlands",
        "Costa de Marfil": "Ivory Coast",
        "Cabo Verde": "Cape Verde",
        "Arabia Saudita": "Saudi Arabia",
        "RD Congo": "DR Congo",
        "Nueva Zelanda": "New Zealand",
        "Bosnia-Herzegovina": "Bosnia",
        "Turquía": "Turkey",
        "Túnez": "Tunisia",
        "Sudáfrica": "South Africa",
        "Haití": "Haiti",
        "Argelia": "Algeria",
        "Jordania": "Jordan",
        "Uzbekistán": "Uzbekistan",
        "Panamá": "Panama",
        "Bélgica": "Belgium",
        "Egipto": "Egypt",
        "Irán": "Iran",
        "Suecia": "Sweden",
        "Suiza": "Switzerland",
        "Alemania": "Germany",
        "Curazao": "Curacao",
        "Escocia": "Scotland",
        "Marruecos": "Morocco",
        "Noruega": "Norway",
        "Irak": "Iraq",
        "Francia": "France",
        "Inglaterra": "England",
        "Croacia": "Croatia",
        "México": "Mexico",
        "Canadá": "Canada",
        "Japón": "Japan",
    }
    return traducciones.get(nombre, nombre)


def _alternativas_equipo(nombre: str) -> set[str]:
    alternativas = {nombre, _traducir_equipo(nombre)}
    extras = {
        "Estados Unidos": {"United States", "USA", "USMNT"},
        "Rep. Checa": {"Czech Republic", "Czechia"},
        "Bosnia-Herzegovina": {"Bosnia", "Bosnia and Herzegovina"},
        "Corea del Sur": {"South Korea", "Korea Republic"},
    }
    alternativas.update(extras.get(nombre, set()))
    return {normalizar_texto(a) for a in alternativas if a}


def _titulo_contiene_equipo(titulo: str, equipo: str) -> bool:
    titulo_norm = normalizar_texto(titulo)
    return any(alt and alt in titulo_norm for alt in _alternativas_equipo(equipo))


def _altura_metadata(info: dict) -> int | None:
    altura = info.get("height")
    if isinstance(altura, int):
        return altura
    alturas = []
    for formato in info.get("formats") or []:
        h = formato.get("height")
        if isinstance(h, int):
            alturas.append(h)
    return max(alturas) if alturas else None


def _validar_candidato_ytdlp(info: dict, equipo1: str, equipo2: str) -> tuple[bool, str]:
    titulo = info.get("title") or ""
    titulo_norm = normalizar_texto(titulo)

    if not _titulo_contiene_equipo(titulo, equipo1) or not _titulo_contiene_equipo(titulo, equipo2):
        return False, "no_contiene_ambos_equipos"

    for keyword in getattr(config, "YTDLP_KEYWORDS_NEGATIVAS", []):
        if normalizar_texto(keyword) in titulo_norm:
            return False, f"keyword_negativa:{keyword}"

    positivos = (
        "full match",
        "partido completo",
        "completo",
        "full game",
        "match replay",
        "replay",
    )
    if not any(p in titulo_norm for p in positivos):
        return False, "sin_indicador_partido_completo"

    duracion = info.get("duration")
    if not isinstance(duracion, (int, float)):
        return False, "sin_duracion"
    if duracion < getattr(config, "YTDLP_DURACION_MINIMA", 5400):
        return False, "duracion_corta"
    if duracion > getattr(config, "YTDLP_DURACION_MAXIMA", 3 * 3600):
        return False, "duracion_larga"

    altura = _altura_metadata(info)
    if altura is None:
        return False, "sin_altura"
    if altura < getattr(config, "YTDLP_ALTURA_MINIMA", 720):
        return False, f"altura_baja:{altura}"

    return True, "ok"


def generar_queries(equipo1: str, equipo2: str) -> list[str]:
    """
    Genera múltiples queries de búsqueda para un partido.
    Los torrents se suben mayoritariamente con nombres en inglés,
    así que las queries en inglés van primero.
    Incluye búsqueda invertida (Team2 vs Team1) por si el uploader
    puso primero al ganador.
    """
    queries = []
    en1 = _traducir_equipo(equipo1)
    en2 = _traducir_equipo(equipo2)

    # === Queries en INGLÉS — orden original ===
    queries.append(f"{en1} vs {en2} World Cup 2026")
    queries.append(f"{en1} {en2} FIFA World Cup 2026")
    queries.append(f"FIFA World Cup 2026 {en1} {en2}")
    queries.append(f"{en1} vs {en2} World Cup 2026 full match")
    queries.append(f"{en1} {en2} World Cup 2026 spanish")
    queries.append(f"{en1} vs {en2} WC 2026")

    # === Queries en INGLÉS — orden INVERTIDO ===
    queries.append(f"{en2} vs {en1} World Cup 2026")
    queries.append(f"{en2} {en1} FIFA World Cup 2026")
    queries.append(f"{en2} vs {en1} World Cup 2026 full match")

    # === Queries en ESPAÑOL (para fuentes en español) ===
    if equipo1 != en1 or equipo2 != en2:
        queries.append(f"{equipo1} vs {equipo2} mundial 2026")
        queries.append(f"{equipo1} {equipo2} mundial 2026 completo")
        queries.append(f"{equipo1} vs {equipo2} copa del mundo 2026")
        # Invertido en español
        queries.append(f"{equipo2} vs {equipo1} mundial 2026")

    # === Queries simples (catch-all, último recurso) ===
    queries.append(f"{en1} {en2} 2026")
    queries.append(f"{en2} {en1} 2026")

    if getattr(config, "GROQ_HABILITADO", False) and getattr(config, "GROQ_GENERAR_QUERIES", True):
        try:
            from groq_asistente import generar_queries as generar_queries_groq

            extras = list(generar_queries_groq(equipo1, equipo2))
            if extras:
                logger.info(f"  [Groq] {len(extras)} queries extra")
                queries.extend(extras)
        except Exception as e:
            logger.debug(f"[Groq] No se pudieron generar queries extra: {e}")

    deduplicadas = []
    vistas = set()
    for query in queries:
        clave = query.lower()
        if clave in vistas:
            continue
        vistas.add(clave)
        deduplicadas.append(query)

    return deduplicadas


# ─── Fuente: 1337x ──────────────────────────────────────────────────────────

def buscar_1337x(equipo1: str, equipo2: str) -> list[dict]:
    """Busca torrents en 1337x usando py1337x."""
    if not PY1337X_DISPONIBLE or not config.indexador_habilitado("1337x"):
        return []

    resultados = []
    queries = generar_queries(equipo1, equipo2)

    for query in queries[:5]:  # Limitar a 5 queries por fuente
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

                # Obtener info detallada (incluyendo magnet)
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

                if tamano_gb < config.TAMANO_MIN_GB:
                    continue

                if seeders < config.MIN_SEEDERS:
                    continue

                puntuacion = calcular_puntuacion(titulo, seeders, tamano_gb)
                hash_match = re.search(r'btih:([a-fA-F0-9]+)', magnet)

                resultados.append({
                    "titulo": titulo,
                    "magnet": magnet,
                    "torrent_hash": hash_match.group(1).lower() if hash_match else None,
                    "seeders": seeders,
                    "tamano_gb": tamano_gb,
                    "fuente": "1337x",
                    "puntuacion": puntuacion,
                })

            time.sleep(1)  # Rate limiting

        except Exception as e:
            logger.debug(f"[1337x] Error buscando '{query}': {e}")
            continue

    return resultados


# ─── Fuente: The Pirate Bay (via API proxy) ──────────────────────────────────

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
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/120.0.0.0 Safari/537.36"
    }

    for query in queries[:6]:  # Más queries ahora que tenemos invertidas
        for mirror in mirrors:
            try:
                url = f"{mirror}/q.php?q={quote_plus(query)}&cat=200"  # cat 200 = video
                logger.debug(f"[TPB] Buscando: {url}")

                resp = requests.get(url, headers=headers, timeout=15)
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

                    # Construir magnet link
                    trackers = [
                        "udp://tracker.opentrackr.org:1337/announce",
                        "udp://open.stealth.si:80/announce",
                        "udp://tracker.torrent.eu.org:451/announce",
                        "udp://tracker.bittor.pw:1337/announce",
                        "udp://public.popcorn-tracker.org:6969/announce",
                        "udp://tracker.dler.org:6969/announce",
                        "udp://exodus.desync.com:6969",
                        "udp://open.demonii.com:1337/announce",
                    ]
                    tracker_str = "&".join([f"tr={quote_plus(t)}" for t in trackers])
                    magnet = f"magnet:?xt=urn:btih:{info_hash}&dn={quote_plus(titulo)}&{tracker_str}"

                    puntuacion = calcular_puntuacion(titulo, seeders, tamano_gb)

                    resultados.append({
                        "titulo": titulo,
                        "magnet": magnet,
                        "torrent_hash": info_hash.lower(),
                        "seeders": seeders,
                        "tamano_gb": round(tamano_gb, 2),
                        "fuente": "piratebay",
                        "puntuacion": puntuacion,
                    })

                time.sleep(1)
                break  # Si un mirror funcionó, no probar los demás

            except Exception as e:
                logger.debug(f"[TPB] Error en mirror {mirror}: {e}")
                continue

    return resultados


# ─── Fuente: TorrentGalaxy (scraper) ─────────────────────────────────────────

def buscar_torrentgalaxy(equipo1: str, equipo2: str) -> list[dict]:
    """Busca torrents en TorrentGalaxy via scraping HTML."""
    if not config.indexador_habilitado("torrentgalaxy"):
        return []

    datos_fuentes = config.cargar_fuentes_torrent()
    mirrors = []
    for idx in datos_fuentes.get("indexadores", []):
        if idx.get("nombre") == "torrentgalaxy" and idx.get("habilitado"):
            mirrors = idx.get("mirrors", ["https://torrentgalaxy.to"])
            break
    if not mirrors:
        mirrors = ["https://torrentgalaxy.to"]

    resultados = []
    queries = generar_queries(equipo1, equipo2)
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/120.0.0.0 Safari/537.36"
    }

    for query in queries[:5]:
        for mirror in mirrors:
            try:
                url = f"{mirror}/torrents.php?search={quote_plus(query)}&cat=41&sort=seeders&order=desc"
                logger.debug(f"[TGx] Buscando: {url}")

                resp = requests.get(url, headers=headers, timeout=15)
                if resp.status_code != 200:
                    continue

                soup = BeautifulSoup(resp.text, "html.parser")
                filas = soup.select("div.tgxtablerow")

                for fila in filas[:10]:
                    # Titulo
                    link_titulo = fila.select_one("a.txlight")
                    if not link_titulo:
                        continue
                    titulo = link_titulo.get_text(strip=True)

                    if not es_partido_completo(titulo):
                        continue

                    # Magnet
                    link_magnet = fila.select_one('a[href^="magnet:"]')
                    if not link_magnet:
                        continue
                    magnet = link_magnet["href"]

                    # Seeders
                    span_seed = fila.select_one('span[title="Seeders/Leechers"] b')
                    if not span_seed:
                        # Alternativa: buscar en fonts con color verde
                        font_seed = fila.select_one('font[color="green"]')
                        seeders = int(font_seed.get_text(strip=True)) if font_seed else 0
                    else:
                        seeders = int(span_seed.get_text(strip=True))

                    if seeders < config.MIN_SEEDERS:
                        continue

                    # Tamaño
                    span_size = fila.select_one('span.badge-secondary')
                    tamano_str = span_size.get_text(strip=True) if span_size else "0 GB"
                    tamano_gb = normalizar_tamano_gb(tamano_str)

                    if tamano_gb < config.TAMANO_MIN_GB:
                        continue

                    puntuacion = calcular_puntuacion(titulo, seeders, tamano_gb)
                    hash_match = re.search(r'btih:([a-fA-F0-9]+)', magnet)

                    resultados.append({
                        "titulo": titulo,
                        "magnet": magnet,
                        "torrent_hash": hash_match.group(1).lower() if hash_match else None,
                        "seeders": seeders,
                        "tamano_gb": round(tamano_gb, 2),
                        "fuente": "torrentgalaxy",
                        "puntuacion": puntuacion,
                    })

                time.sleep(1)
                break  # Si un mirror funcionó, no probar los demás

            except Exception as e:
                logger.debug(f"[TGx] Error en mirror {mirror}: {e}")
                continue

    return resultados


# ─── Fuente: LimeTorrents (scraper) ──────────────────────────────────────────

def buscar_limetorrents(equipo1: str, equipo2: str) -> list[dict]:
    """Busca torrents en LimeTorrents via scraping HTML."""
    if not config.indexador_habilitado("limetorrents"):
        return []

    datos_fuentes = config.cargar_fuentes_torrent()
    mirrors = []
    for idx in datos_fuentes.get("indexadores", []):
        if idx.get("nombre") == "limetorrents" and idx.get("habilitado"):
            mirrors = idx.get("mirrors", ["https://www.limetorrents.lol"])
            break
    if not mirrors:
        mirrors = ["https://www.limetorrents.lol"]

    resultados = []
    queries = generar_queries(equipo1, equipo2)
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/120.0.0.0 Safari/537.36"
    }

    for query in queries[:5]:
        for mirror in mirrors:
            try:
                search_term = query.replace(" ", "-")
                url = f"{mirror}/search/all/{quote_plus(search_term)}/seeds/1/"
                logger.debug(f"[Lime] Buscando: {url}")

                resp = requests.get(url, headers=headers, timeout=15)
                if resp.status_code != 200:
                    continue

                soup = BeautifulSoup(resp.text, "html.parser")
                tabla = soup.select_one("table.table2")
                if not tabla:
                    continue

                filas = tabla.select("tr")[1:]  # Saltar header

                for fila in filas[:10]:
                    celdas = fila.select("td")
                    if len(celdas) < 5:
                        continue

                    # Titulo y link al detalle
                    link_titulo = celdas[0].select_one("a")
                    if not link_titulo:
                        continue
                    titulo = link_titulo.get_text(strip=True)

                    if not es_partido_completo(titulo):
                        continue

                    # Link a la pagina de detalle para obtener magnet
                    href = link_titulo.get("href", "")
                    if not href:
                        continue

                    # Seeders (columna 3)
                    try:
                        seeders = int(celdas[3].get_text(strip=True).replace(",", ""))
                    except (ValueError, IndexError):
                        seeders = 0

                    if seeders < config.MIN_SEEDERS:
                        continue

                    # Tamaño (columna 2)
                    tamano_str = celdas[2].get_text(strip=True)
                    tamano_gb = normalizar_tamano_gb(tamano_str)

                    if tamano_gb < config.TAMANO_MIN_GB:
                        continue

                    # Obtener magnet desde la pagina de detalle
                    try:
                        detail_url = href if href.startswith("http") else f"{mirror}{href}"
                        resp_detail = requests.get(detail_url, headers=headers, timeout=10)
                        soup_detail = BeautifulSoup(resp_detail.text, "html.parser")
                        magnet_link = soup_detail.select_one('a[href^="magnet:"]')
                        if not magnet_link:
                            continue
                        magnet = magnet_link["href"]
                    except Exception:
                        continue

                    puntuacion = calcular_puntuacion(titulo, seeders, tamano_gb)
                    hash_match = re.search(r'btih:([a-fA-F0-9]+)', magnet)

                    resultados.append({
                        "titulo": titulo,
                        "magnet": magnet,
                        "torrent_hash": hash_match.group(1).lower() if hash_match else None,
                        "seeders": seeders,
                        "tamano_gb": round(tamano_gb, 2),
                        "fuente": "limetorrents",
                        "puntuacion": puntuacion,
                    })

                time.sleep(1)
                break

            except Exception as e:
                logger.debug(f"[Lime] Error en mirror {mirror}: {e}")
                continue

    return resultados


# ─── Fuente: BTDIG (DHT search engine) ───────────────────────────────────────

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
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/120.0.0.0 Safari/537.36"
    }

    trackers = [
        "udp://tracker.opentrackr.org:1337/announce",
        "udp://open.stealth.si:80/announce",
        "udp://tracker.torrent.eu.org:451/announce",
        "udp://tracker.dler.org:6969/announce",
        "udp://exodus.desync.com:6969",
        "udp://open.demonii.com:1337/announce",
    ]
    tracker_str = "&".join([f"tr={quote_plus(t)}" for t in trackers])

    for query in queries[:4]:
        try:
            url = f"{base_url}/search?q={quote_plus(query)}&order=0"
            logger.debug(f"[BTDIG] Buscando: {url}")

            resp = requests.get(url, headers=headers, timeout=15)
            if resp.status_code != 200:
                continue

            soup = BeautifulSoup(resp.text, "html.parser")
            items = soup.select("div.one_result")

            for item in items[:10]:
                # Titulo
                link_titulo = item.select_one("div.torrent_name a")
                if not link_titulo:
                    continue
                titulo = link_titulo.get_text(strip=True)

                if not es_partido_completo(titulo):
                    continue

                if not titulo_menciona_equipos(titulo, equipo1, equipo2):
                    continue

                # Hash (desde el href)
                href = link_titulo.get("href", "")
                hash_match = re.search(r'/([a-fA-F0-9]{40})/', href)
                if not hash_match:
                    continue
                info_hash = hash_match.group(1).lower()

                # Tamaño
                span_size = item.select_one("span.torrent_size")
                tamano_str = span_size.get_text(strip=True) if span_size else "0 GB"
                tamano_gb = normalizar_tamano_gb(tamano_str)

                if tamano_gb < config.TAMANO_MIN_GB:
                    continue

                # BTDIG no muestra seeders; usar 1 como estimación conservadora
                # para que no se descarte pero tampoco gane por seeders
                seeders = 1

                magnet = f"magnet:?xt=urn:btih:{info_hash}&dn={quote_plus(titulo)}&{tracker_str}"
                puntuacion = calcular_puntuacion(titulo, seeders, tamano_gb)

                resultados.append({
                    "titulo": titulo,
                    "magnet": magnet,
                    "torrent_hash": info_hash,
                    "seeders": seeders,
                    "tamano_gb": round(tamano_gb, 2),
                    "fuente": "btdig",
                    "puntuacion": puntuacion,
                })

            time.sleep(1)

        except Exception as e:
            logger.debug(f"[BTDIG] Error buscando '{query}': {e}")
            continue

    return resultados


# ─── Fuente: yt-dlp (fallback) ───────────────────────────────────────────────

def buscar_ytdlp(equipo1: str, equipo2: str, directorio_destino: str) -> dict | None:
    """
    Fallback: busca y descarga directamente con yt-dlp.
    Busca en YouTube, Dailymotion, etc.
    Retorna info del archivo descargado o None.
    """
    if not config.FUENTES_HABILITADAS.get("yt_dlp"):
        return None

    import os
    import subprocess
    import shutil

    # Buscar yt-dlp
    ytdlp_path = shutil.which("yt-dlp")
    if not ytdlp_path:
        # Intentar en el venv
        venv_path = os.path.join(config.DIRECTORIO_PROYECTO, "venv", "bin", "yt-dlp")
        if os.path.exists(venv_path):
            ytdlp_path = venv_path
        else:
            logger.warning("yt-dlp no encontrado en PATH ni en venv")
            return None

    cantidad = getattr(config, "YTDLP_RESULTADOS_BUSQUEDA", 5)
    queries_yt = [
        f'ytsearch{cantidad}:"{equipo1} vs {equipo2} mundial 2026 partido completo 720p"',
        f'ytsearch{cantidad}:"{equipo1} vs {equipo2} world cup 2026 full match 720p"',
        f'ytsearch{cantidad}:"{_traducir_equipo(equipo1)} vs {_traducir_equipo(equipo2)} FIFA World Cup 2026 full match 720p"',
    ]

    candidatos = []

    for query in queries_yt:
        try:
            logger.debug(f"[yt-dlp] Buscando: {query}")

            comando = [
                ytdlp_path,
                "--dump-json",
                "--skip-download",
                "--no-playlist",
                "--socket-timeout", "30",
                query
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

                valido, razon = _validar_candidato_ytdlp(info, equipo1, equipo2)
                titulo = info.get("title") or "-"
                if not valido:
                    logger.debug(f"[yt-dlp] Rechazado: {titulo} ({razon})")
                    continue
                candidatos.append(info)

        except subprocess.TimeoutExpired:
            logger.warning(f"[yt-dlp] Timeout buscando: {query}")
        except Exception as e:
            logger.debug(f"[yt-dlp] Error: {e}")

    if not candidatos:
        logger.info("[yt-dlp] Sin candidatos confiables; no se descarga fallback")
        return None

    candidatos.sort(
        key=lambda info: (
            _altura_metadata(info) or 0,
            -abs(float(info.get("duration", 0)) - 7200),
        ),
        reverse=True,
    )
    elegido = candidatos[0]
    url = elegido.get("webpage_url") or elegido.get("original_url") or elegido.get("url")
    if not url:
        logger.info("[yt-dlp] Candidato sin URL util; no se descarga fallback")
        return None

    idioma = detectar_idioma(elegido.get("title"))
    nombre_archivo = nombre_base_canonico_partido({
        "equipo1": equipo1,
        "equipo2": equipo2,
    }, idioma)
    ruta_salida = os.path.join(directorio_destino, f"{nombre_archivo}.%(ext)s")
    logger.info(
        f"[yt-dlp] Candidato validado: {elegido.get('title')} "
        f"({round((elegido.get('duration') or 0) / 60, 1)} min, "
        f"{_altura_metadata(elegido)}p)"
    )

    comando_descarga = [
        ytdlp_path,
        "-f", config.YTDLP_FORMATO,
        "-o", ruta_salida,
        "--no-playlist",
        "--socket-timeout", "30",
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
        "yt_dlp_altura": _altura_metadata(elegido),
    }

    return None


# ─── Buscador Principal ─────────────────────────────────────────────────────

def buscar_partido(equipo1: str, equipo2: str) -> list[dict]:
    """
    Busca un partido en todas las fuentes habilitadas.
    Retorna una lista de resultados ordenados por puntuación (mejor primero).
    """
    logger.info(f"Buscando partido: {equipo1} vs {equipo2}")
    todos_resultados = []

    # Buscar en 1337x
    try:
        resultados_1337x = buscar_1337x(equipo1, equipo2)
        todos_resultados.extend(resultados_1337x)
        logger.info(f"  [1337x] {len(resultados_1337x)} resultados")
    except Exception as e:
        logger.error(f"  [1337x] Error: {e}")

    # Buscar en PirateBay
    try:
        resultados_tpb = buscar_piratebay(equipo1, equipo2)
        todos_resultados.extend(resultados_tpb)
        logger.info(f"  [TPB] {len(resultados_tpb)} resultados")
    except Exception as e:
        logger.error(f"  [TPB] Error: {e}")

    # Buscar en TorrentGalaxy
    try:
        resultados_tgx = buscar_torrentgalaxy(equipo1, equipo2)
        todos_resultados.extend(resultados_tgx)
        logger.info(f"  [TGx] {len(resultados_tgx)} resultados")
    except Exception as e:
        logger.error(f"  [TGx] Error: {e}")

    # Buscar en LimeTorrents
    try:
        resultados_lime = buscar_limetorrents(equipo1, equipo2)
        todos_resultados.extend(resultados_lime)
        logger.info(f"  [Lime] {len(resultados_lime)} resultados")
    except Exception as e:
        logger.error(f"  [Lime] Error: {e}")

    # Buscar en BTDIG (DHT)
    try:
        resultados_btdig = buscar_btdig(equipo1, equipo2)
        todos_resultados.extend(resultados_btdig)
        logger.info(f"  [BTDIG] {len(resultados_btdig)} resultados")
    except Exception as e:
        logger.error(f"  [BTDIG] Error: {e}")

    # Eliminar duplicados por magnet hash y filtrar irrelevantes
    vistos = set()
    unicos = []
    for r in todos_resultados:
        # Filtrar resultados que no mencionan a ninguno de los equipos
        if not titulo_menciona_equipos(r.get("titulo", ""), equipo1, equipo2):
            continue
        # Extraer hash del magnet para deduplicar
        hash_match = re.search(r'btih:([a-fA-F0-9]+)', r.get("magnet", ""))
        if hash_match:
            info_hash = hash_match.group(1).lower()
            if info_hash not in vistos:
                vistos.add(info_hash)
                unicos.append(r)
        else:
            unicos.append(r)

    if unicos and getattr(config, "GROQ_HABILITADO", False):
        try:
            from groq_asistente import clasificar_resultados

            clasificar_resultados(equipo1, equipo2, unicos)
            for resultado in unicos:
                groq_idioma = resultado.get("groq_idioma")
                if groq_idioma in {"es", "en", "desconocido"}:
                    resultado.setdefault("idioma", groq_idioma)
        except Exception as e:
            logger.debug(f"[Groq] No se pudieron clasificar resultados: {e}")

    # Ordenar por puntuación (mejor primero)
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
    """
    Busca un partido y retorna el mejor resultado, o None si no encuentra nada.
    """
    resultados = buscar_partido(equipo1, equipo2)

    if not resultados:
        logger.warning(f"No se encontraron torrents para {equipo1} vs {equipo2}")
        return None

    return resultados[0]
