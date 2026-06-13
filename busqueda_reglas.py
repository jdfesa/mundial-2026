"""
Reglas de busqueda, scoring y validacion de candidatos.
"""
import logging
import re

import config
from idioma_utils import normalizar_texto

logger = logging.getLogger("mundial")


def normalizar_tamano_gb(tamano_str: str) -> float:
    """Convierte un string de tamaño a GB. Ej: '2.5 GB' -> 2.5."""
    try:
        tamano_str = tamano_str.strip().upper()
        match = re.search(r"([\d.]+)\s*(GB|MB|TB)", tamano_str)
        if not match:
            return 0.0
        valor = float(match.group(1))
        unidad = match.group(2)
        if unidad == "GB":
            return valor
        if unidad == "MB":
            return valor / 1024
        if unidad == "TB":
            return valor * 1024
        return 0.0
    except Exception:
        return 0.0


def es_partido_completo(titulo: str) -> bool:
    """Verifica que el resultado no parezca resumen, previa o reaccion."""
    titulo_lower = titulo.lower()
    for kw in config.KEYWORDS_NEGATIVAS:
        if kw.lower() in titulo_lower:
            return False
    return True


def traducir_equipo(nombre: str) -> str:
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


def alternativas_equipo(nombre: str) -> set[str]:
    alternativas = {nombre, traducir_equipo(nombre)}
    extras = {
        "Estados Unidos": {"United States", "USA", "USMNT"},
        "Rep. Checa": {"Czech Republic", "Czechia"},
        "Bosnia-Herzegovina": {"Bosnia", "Bosnia and Herzegovina"},
        "Corea del Sur": {"South Korea", "Korea Republic"},
    }
    alternativas.update(extras.get(nombre, set()))
    return {normalizar_texto(a) for a in alternativas if a}


def titulo_contiene_equipo(titulo: str, equipo: str) -> bool:
    titulo_norm = normalizar_texto(titulo)
    return any(alt and alt in titulo_norm for alt in alternativas_equipo(equipo))


def titulo_menciona_equipos(titulo: str, equipo1: str, equipo2: str) -> bool:
    """Verifica que el titulo mencione al menos uno de los equipos del partido."""
    return titulo_contiene_equipo(titulo, equipo1) or titulo_contiene_equipo(titulo, equipo2)


def calcular_puntuacion(titulo: str, seeders: int, tamano_gb: float) -> float:
    """
    Calcula una puntuación para un resultado de torrent.
    Mayor puntuación = mejor candidato.
    """
    puntuacion = 0.0
    titulo_lower = titulo.lower()

    indicadores_espanol = ["español", "espanol", "spanish", "latino", "castellano", "spa"]
    for ind in indicadores_espanol:
        if ind in titulo_lower:
            puntuacion += 100
            break

    indicadores_completo = ["full match", "completo", "full game", "partido completo"]
    for ind in indicadores_completo:
        if ind in titulo_lower:
            puntuacion += 50
            break

    if "720p" in titulo_lower or "hdtv" in titulo_lower:
        puntuacion += 30
    elif "1080p" in titulo_lower or "full hd" in titulo_lower:
        puntuacion += 8
    elif "4k" in titulo_lower or "2160p" in titulo_lower:
        puntuacion -= 25

    if seeders > 0:
        import math

        puntuacion += min(math.log2(seeders + 1) * 5, 40)

    if tamano_gb < config.TAMANO_MIN_GB:
        puntuacion -= 50
    elif tamano_gb > config.TAMANO_MAX_GB:
        puntuacion -= 20
    elif 1.5 <= tamano_gb <= getattr(config, "TAMANO_IDEAL_MAX_GB", 5.0):
        puntuacion += 15
    elif tamano_gb > getattr(config, "TAMANO_IDEAL_MAX_GB", 5.0):
        puntuacion -= 8

    mundial_keywords = ["world cup", "mundial", "copa del mundo", "fifa", "wc2026", "wc 2026"]
    for kw in mundial_keywords:
        if kw in titulo_lower:
            puntuacion += 10
            break

    return puntuacion


def altura_metadata(info: dict) -> int | None:
    altura = info.get("height")
    if isinstance(altura, int):
        return altura
    alturas = []
    for formato in info.get("formats") or []:
        h = formato.get("height")
        if isinstance(h, int):
            alturas.append(h)
    return max(alturas) if alturas else None


def validar_candidato_ytdlp(info: dict, equipo1: str, equipo2: str) -> tuple[bool, str]:
    titulo = info.get("title") or ""
    titulo_norm = normalizar_texto(titulo)

    if not titulo_contiene_equipo(titulo, equipo1) or not titulo_contiene_equipo(titulo, equipo2):
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

    altura = altura_metadata(info)
    if altura is None:
        return False, "sin_altura"
    if altura < getattr(config, "YTDLP_ALTURA_MINIMA", 720):
        return False, f"altura_baja:{altura}"

    return True, "ok"


def generar_queries(equipo1: str, equipo2: str) -> list[str]:
    """Genera queries de búsqueda deterministicas y opcionalmente asistidas."""
    queries = []
    en1 = traducir_equipo(equipo1)
    en2 = traducir_equipo(equipo2)

    queries.append(f"{en1} vs {en2} World Cup 2026")
    queries.append(f"{en1} {en2} FIFA World Cup 2026")
    queries.append(f"FIFA World Cup 2026 {en1} {en2}")
    queries.append(f"{en1} vs {en2} World Cup 2026 full match")
    queries.append(f"{en1} {en2} World Cup 2026 spanish")
    queries.append(f"{en1} vs {en2} WC 2026")

    queries.append(f"{en2} vs {en1} World Cup 2026")
    queries.append(f"{en2} {en1} FIFA World Cup 2026")
    queries.append(f"{en2} vs {en1} World Cup 2026 full match")

    if equipo1 != en1 or equipo2 != en2:
        queries.append(f"{equipo1} vs {equipo2} mundial 2026")
        queries.append(f"{equipo1} {equipo2} mundial 2026 completo")
        queries.append(f"{equipo1} vs {equipo2} copa del mundo 2026")
        queries.append(f"{equipo2} vs {equipo1} mundial 2026")

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
