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
    "ru",
    "bg",
    "pt",
    "fr",
    "de",
    "it",
    "ar",
    "zh",
    "ja",
    "ko",
    "nl",
    "pl",
    "tr",
}

CODIGOS_IDIOMA = {
    "es": IDIOMA_ES,
    "spa": IDIOMA_ES,
    "esl": IDIOMA_ES,
    "en": IDIOMA_EN,
    "eng": IDIOMA_EN,
    "ru": "ru",
    "rus": "ru",
    "bg": "bg",
    "bul": "bg",
    "pt": "pt",
    "por": "pt",
    "fr": "fr",
    "fre": "fr",
    "fra": "fr",
    "deu": "de",
    "ger": "de",
    "it": "it",
    "ita": "it",
    "ar": "ar",
    "ara": "ar",
    "zh": "zh",
    "chi": "zh",
    "zho": "zh",
    "ja": "ja",
    "jpn": "ja",
    "ko": "ko",
    "kor": "ko",
    "nl": "nl",
    "dut": "nl",
    "nld": "nl",
    "pl": "pl",
    "pol": "pl",
    "tr": "tr",
    "tur": "tr",
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
    ("ru", ("russian", "ruso", "rusa", "русский", "rus", "ru")),
    ("bg", ("bulgarian", "bulgaro", "búlgaro", "bulgara", "búlgara", "bul", "bg")),
    ("pt", ("portuguese", "portugues", "português", "brazilian", "brasileiro", "por", "pt")),
    ("fr", ("french", "frances", "francés", "fra", "fre")),
    ("de", ("german", "aleman", "alemán", "deu", "ger")),
    ("it", ("italian", "italiano", "ita")),
    ("ar", ("arabic", "arabe", "árabe", "ara")),
    ("zh", ("chinese", "mandarin", "chino", "zho", "chi")),
    ("ja", ("japanese", "japones", "japonés", "jpn")),
    ("ko", ("korean", "coreano", "kor")),
    ("nl", ("dutch", "holandes", "holandés", "nld", "dut")),
    ("pl", ("polish", "polaco", "pol", "pl")),
    ("tr", ("turkish", "turco", "tur", "tr")),
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
        "ru": "ruso",
        "bg": "búlgaro",
        "pt": "portugués",
        "fr": "francés",
        "de": "alemán",
        "it": "italiano",
        "ar": "árabe",
        "zh": "chino",
        "ja": "japonés",
        "ko": "coreano",
        "nl": "neerlandés",
        "pl": "polaco",
        "tr": "turco",
        IDIOMA_DESCONOCIDO: "desconocido",
    }
    codigo = normalizar_codigo_idioma(idioma) or idioma or IDIOMA_DESCONOCIDO
    return etiquetas.get(codigo, codigo)
