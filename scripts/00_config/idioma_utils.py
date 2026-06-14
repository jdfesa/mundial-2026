"""
Utilidades para clasificar idioma y calidad de resultados.
"""
import re
import unicodedata

import config

IDIOMA_ES = "es"
IDIOMA_EN = "en"
IDIOMA_DESCONOCIDO = "desconocido"

INDICADORES_ES = (
    "español",
    "espanol",
    "spanish",
    "latino",
    "latam",
    "castellano",
    "relato español",
    "relato espanol",
    "audio español",
    "audio espanol",
    "comentarios español",
    "comentarios espanol",
    "telemundo",
    "universo",
    "tudn",
    "televisa",
    "azteca",
    "tyc",
    "tyc sports",
    "tv publica",
    "tv pública",
    "deportes",
    "fox deportes",
    "espn deportes",
    "vix",
    "dgo",
    "directv sports",
    "spa",
    "es",
)

INDICADORES_EN = (
    "english",
    "ingles",
    "inglés",
    "bbc",
    "itv",
    "fox",
    "fs1",
    "tsn",
    "eng",
    "en",
)


def normalizar_texto(texto: str | None) -> str:
    texto = texto or ""
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    texto = texto.lower()
    return re.sub(r"\s+", " ", texto).strip()


def _contiene_indicador(texto: str, indicador: str) -> bool:
    indicador = normalizar_texto(indicador)
    if len(indicador) <= 3:
        return re.search(rf"\b{re.escape(indicador)}\b", texto) is not None
    return indicador in texto


def detectar_idioma(texto: str | None) -> str:
    """Detecta idioma probable a partir de un titulo o metadatos."""
    normalizado = normalizar_texto(texto)

    for indicador in INDICADORES_ES:
        if _contiene_indicador(normalizado, indicador):
            return IDIOMA_ES

    for indicador in INDICADORES_EN:
        if _contiene_indicador(normalizado, indicador):
            return IDIOMA_EN

    return getattr(config, "IDIOMA_DEFAULT_SIN_INDICADOR", IDIOMA_DESCONOCIDO)


def idioma_es_final(idioma: str | None) -> bool:
    """Indica si el idioma cumple la preferencia final configurada."""
    preferidos = getattr(config, "IDIOMAS_FINALES", ["es"])
    return (idioma or IDIOMA_DESCONOCIDO) in preferidos


def etiqueta_idioma(idioma: str | None) -> str:
    etiquetas = {
        IDIOMA_ES: "español",
        IDIOMA_EN: "inglés",
        IDIOMA_DESCONOCIDO: "desconocido",
    }
    return etiquetas.get(idioma or IDIOMA_DESCONOCIDO, idioma or IDIOMA_DESCONOCIDO)
