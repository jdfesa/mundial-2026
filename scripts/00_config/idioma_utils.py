"""
Utilidades para clasificar idioma y calidad de resultados.
"""
import re
import unicodedata

import config

IDIOMA_ES = "es"
IDIOMA_EN = "en"
IDIOMA_DESCONOCIDO = "desconocido"

IDIOMAS_CONOCIDOS = {
    IDIOMA_ES,
    IDIOMA_EN,
    "rus",
    "bul",
    "por",
    "fra",
    "deu",
    "ita",
    "ara",
    "zho",
    "jpn",
    "kor",
    "nld",
    "pol",
    "tur",
}

CODIGOS_IDIOMA = {
    "es": IDIOMA_ES,
    "spa": IDIOMA_ES,
    "esl": IDIOMA_ES,
    "en": IDIOMA_EN,
    "eng": IDIOMA_EN,
    "ru": "rus",
    "rus": "rus",
    "bg": "bul",
    "bul": "bul",
    "pt": "por",
    "por": "por",
    "fr": "fra",
    "fre": "fra",
    "fra": "fra",
    "de": "deu",
    "deu": "deu",
    "ger": "deu",
    "it": "ita",
    "ita": "ita",
    "ar": "ara",
    "ara": "ara",
    "zh": "zho",
    "chi": "zho",
    "zho": "zho",
    "ja": "jpn",
    "jpn": "jpn",
    "ko": "kor",
    "kor": "kor",
    "nl": "nld",
    "dut": "nld",
    "nld": "nld",
    "pl": "pol",
    "pol": "pol",
    "tr": "tur",
    "tur": "tur",
}

INDICADORES_IDIOMA = (
    (
        IDIOMA_ES,
        (
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
        ),
    ),
    (
        IDIOMA_EN,
        (
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
        ),
    ),
    ("rus", ("russian", "ruso", "rusa", "русский", "rus", "ru")),
    ("bul", ("bulgarian", "bulgaro", "búlgaro", "bulgara", "búlgara", "bul", "bg")),
    ("por", ("portuguese", "portugues", "português", "brazilian", "brasileiro", "por", "pt")),
    ("fra", ("french", "frances", "francés", "fra", "fre", "fr")),
    ("deu", ("german", "aleman", "alemán", "deu", "ger", "de")),
    ("ita", ("italian", "italiano", "ita", "it")),
    ("ara", ("arabic", "arabe", "árabe", "ara", "ar")),
    ("zho", ("chinese", "mandarin", "chino", "zho", "chi", "zh")),
    ("jpn", ("japanese", "japones", "japonés", "jpn", "ja")),
    ("kor", ("korean", "coreano", "kor", "ko")),
    ("nld", ("dutch", "holandes", "holandés", "nld", "dut", "nl")),
    ("pol", ("polish", "polaco", "pol", "pl")),
    ("tur", ("turkish", "turco", "tur", "tr")),
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


def normalizar_codigo_idioma(idioma: str | None) -> str | None:
    """Normaliza etiquetas ISO 639-1/639-2 a sufijos cortos conocidos."""
    normalizado = normalizar_texto(idioma)
    if not normalizado or normalizado == IDIOMA_DESCONOCIDO:
        return None
    if normalizado in CODIGOS_IDIOMA:
        return CODIGOS_IDIOMA[normalizado]
    if normalizado in IDIOMAS_CONOCIDOS:
        return normalizado
    return None


def detectar_idioma(texto: str | None) -> str:
    """Detecta idioma probable a partir de un titulo o metadatos."""
    normalizado = normalizar_texto(texto)

    codigo_exacto = normalizar_codigo_idioma(normalizado)
    if codigo_exacto:
        return codigo_exacto

    for codigo, indicadores in INDICADORES_IDIOMA:
        for indicador in indicadores:
            if _contiene_indicador(normalizado, indicador):
                return codigo

    return getattr(config, "IDIOMA_DEFAULT_SIN_INDICADOR", IDIOMA_DESCONOCIDO)


def idioma_es_final(idioma: str | None) -> bool:
    """Indica si el idioma cumple la preferencia final configurada."""
    preferidos = getattr(config, "IDIOMAS_FINALES", ["es"])
    return (idioma or IDIOMA_DESCONOCIDO) in preferidos


def etiqueta_idioma(idioma: str | None) -> str:
    etiquetas = {
        IDIOMA_ES: "español",
        IDIOMA_EN: "inglés",
        "rus": "ruso",
        "bul": "búlgaro",
        "por": "portugués",
        "fra": "francés",
        "deu": "alemán",
        "ita": "italiano",
        "ara": "árabe",
        "zho": "chino",
        "jpn": "japonés",
        "kor": "coreano",
        "nld": "neerlandés",
        "pol": "polaco",
        "tur": "turco",
        IDIOMA_DESCONOCIDO: "desconocido",
    }
    codigo = normalizar_codigo_idioma(idioma) or idioma or IDIOMA_DESCONOCIDO
    return etiquetas.get(codigo, codigo)
