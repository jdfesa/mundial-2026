"""
Nombres canonicos para archivos de partidos.

El nombre fisico del release puede variar mucho entre fuentes. Este modulo
construye una forma estable, legible y ordenable para el archivo final.
"""
import re
import unicodedata

from idioma_utils import IDIOMA_EN, detectar_idioma, idioma_es_final, normalizar_codigo_idioma


def slug_archivo(texto: str | None) -> str:
    """Convierte texto en snake_case ASCII apto para nombres de archivo."""
    texto = texto or ""
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    texto = texto.lower().replace("&", " y ")
    texto = re.sub(r"[^a-z0-9]+", "_", texto)
    texto = re.sub(r"_+", "_", texto).strip("_")
    return texto or "equipo"


def sufijo_idioma_archivo(idioma: str | None) -> str:
    """Devuelve el sufijo corto usado en el nombre canonico."""
    if idioma_es_final(idioma):
        return "es"
    return normalizar_codigo_idioma(idioma) or IDIOMA_EN


def idioma_nombre_partido(partido: dict, idioma: str | None = None) -> str:
    """Elige el idioma que debe reflejar el nombre del archivo."""
    idioma_detectado = idioma or partido.get("idioma") or detectar_idioma(partido.get("archivo"))
    return sufijo_idioma_archivo(idioma_detectado)


def nombre_base_canonico_partido(partido: dict, idioma: str | None = None) -> str:
    """Construye un nombre sin extension: 001_mexico_vs_argentina_en."""
    partido_id = partido.get("id")
    prefijo = ""
    try:
        if partido_id is not None:
            prefijo = f"{int(partido_id):03d}_"
    except (TypeError, ValueError):
        if partido_id:
            prefijo = f"{slug_archivo(str(partido_id))}_"

    equipo1 = slug_archivo(partido.get("equipo1") or "equipo_1")
    equipo2 = slug_archivo(partido.get("equipo2") or "equipo_2")
    idioma_suffix = idioma_nombre_partido(partido, idioma)
    return f"{prefijo}{equipo1}_vs_{equipo2}_{idioma_suffix}"


def nombre_canonico_partido(
    partido: dict,
    extension: str | None = None,
    idioma: str | None = None,
) -> str:
    """Construye el nombre canonico con extension opcional."""
    base = nombre_base_canonico_partido(partido, idioma)
    extension = extension or ""
    if extension and not extension.startswith("."):
        extension = f".{extension}"
    return f"{base}{extension.lower()}"
