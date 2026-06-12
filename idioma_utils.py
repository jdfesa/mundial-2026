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
    "castellano",
    "relato español",
    "relato espanol",
    "audio español",
    "audio espanol",
    "spa",
)

INDICADORES_EN = (
    "english",
    "ingles",
    "inglés",
    "eng",
)


def normalizar_texto(texto: str | None) -> str:
    texto = texto or ""
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    texto = texto.lower()
    return re.sub(r"\s+", " ", texto).strip()


def detectar_idioma(texto: str | None) -> str:
    """Detecta idioma probable a partir de un titulo o metadatos."""
    normalizado = normalizar_texto(texto)

    for indicador in INDICADORES_ES:
        if normalizar_texto(indicador) in normalizado:
            return IDIOMA_ES

    for indicador in INDICADORES_EN:
        if normalizar_texto(indicador) in normalizado:
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
