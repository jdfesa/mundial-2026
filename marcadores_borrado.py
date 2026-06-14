"""
Marcadores locales para videos ya transferidos o borrados.

El estado JSON es la fuente principal del historial. El marcador BORRADO es una
huella visible dentro de la biblioteca local para que humanos y scripts sepan
que ese ID ya fue atendido aunque el MP4 no este en esta maquina.
"""
import logging
from datetime import datetime, timezone
from pathlib import Path

from idioma_utils import detectar_idioma, idioma_es_final
from nombres_archivos import nombre_base_canonico_partido

logger = logging.getLogger("mundial")

MARCADOR_SUFFIX = "BORRADO"


def nombre_marcador_borrado(partido: dict, idioma: str | None = None) -> str:
    base = nombre_base_canonico_partido(partido, idioma or partido.get("idioma"))
    return f"{base}_{MARCADOR_SUFFIX}.txt"


def ruta_marcador_borrado(partido: dict, idioma: str | None = None) -> Path:
    from organizador_descargas import directorio_partido

    return Path(directorio_partido(partido)) / nombre_marcador_borrado(partido, idioma)


def _id_prefijo(partido: dict) -> str | None:
    try:
        return f"{int(partido.get('id')):03d}_"
    except (TypeError, ValueError):
        return None


def _detectar_idioma_marcador(path: Path, contenido: dict | None = None) -> str:
    if contenido and contenido.get("idioma"):
        return str(contenido["idioma"])
    nombre = path.stem.lower()
    if nombre.endswith("_es_borrado"):
        return "es"
    return detectar_idioma(nombre)


def leer_marcador_borrado(path: Path) -> dict:
    datos = {}
    try:
        texto = path.read_text(encoding="utf-8")
    except OSError:
        return datos
    for linea in texto.splitlines():
        if "=" not in linea:
            continue
        clave, _, valor = linea.partition("=")
        datos[clave.strip()] = valor.strip()
    return datos


def buscar_marcadores_borrado(partido: dict) -> list[Path]:
    candidatos = []
    esperado = ruta_marcador_borrado(partido)
    if esperado.exists():
        candidatos.append(esperado)

    prefijo = _id_prefijo(partido)
    if not prefijo:
        return candidatos

    from organizador_descargas import directorio_partido

    directorio = Path(directorio_partido(partido))
    if directorio.exists():
        for path in directorio.glob(f"{prefijo}*_{MARCADOR_SUFFIX}.txt"):
            if path not in candidatos:
                candidatos.append(path)
    return candidatos


def aplicar_marcador_a_partido(partido: dict, marcador: Path) -> None:
    datos = leer_marcador_borrado(marcador)
    idioma = _detectar_idioma_marcador(marcador, datos)
    actualizado = datetime.now(timezone.utc).isoformat()
    partido["descargado"] = True
    partido["idioma"] = idioma
    partido["estado_final"] = idioma_es_final(idioma)
    partido["necesita_mejora"] = False
    partido["archivo_existe"] = False
    partido["archivo_web_existe"] = False
    partido["archivo_local"] = None
    partido["archivo_web"] = None
    partido["archivo_local_estado"] = "borrado_marcador"
    partido["audio_compatible_web"] = False
    partido["compatibilidad_web"] = {
        "estado": "borrado",
        "motivo": "marcador_borrado",
        "actualizado_en": actualizado,
    }
    partido["marcador_borrado"] = str(marcador)
    partido["marcador_borrado_existe"] = True
    partido["marcador_borrado_en"] = datos.get("borrado_en") or datos.get("actualizado_en")
    partido["nombre_base_canonico"] = nombre_base_canonico_partido(partido, idioma)


def aplicar_marcadores_borrado(calendario: list[dict]) -> dict:
    resumen = {"marcados": 0}
    for partido in calendario:
        marcadores = buscar_marcadores_borrado(partido)
        if not marcadores:
            continue
        aplicar_marcador_a_partido(partido, marcadores[0])
        resumen["marcados"] += 1
    return resumen


def escribir_marcador_borrado(partido: dict, dry_run: bool = False) -> Path:
    marcador = ruta_marcador_borrado(partido)
    if dry_run:
        return marcador

    marcador.parent.mkdir(parents=True, exist_ok=True)
    idioma = partido.get("idioma") or detectar_idioma(partido.get("archivo"))
    ahora = datetime.now(timezone.utc).isoformat()
    contenido = [
        f"id={partido.get('id')}",
        f"partido={partido.get('equipo1')} vs {partido.get('equipo2')}",
        f"idioma={idioma}",
        "estado=BORRADO",
        f"borrado_en={ahora}",
        f"ultimo_archivo={Path(str(partido.get('archivo_local_ultimo') or partido.get('archivo_web_ultimo') or partido.get('nombre_canonico') or '')).name}",
        "",
    ]
    marcador.write_text("\n".join(contenido), encoding="utf-8")
    return marcador


def partido_tiene_marcador_borrado(partido: dict) -> bool:
    return bool(partido.get("marcador_borrado_existe") or buscar_marcadores_borrado(partido))


def sincronizar_marcadores_borrado(calendario: list[dict], dry_run: bool = False) -> dict:
    """
    Crea marcadores para partidos descargados cuyo archivo ya no esta localmente.
    """
    resumen = {"existentes": 0, "creados": 0}
    for partido in calendario:
        if not partido.get("descargado"):
            continue
        if partido.get("archivo_existe") or partido.get("archivo_web_existe"):
            continue
        if partido.get("archivo_local_estado") == "descarga_en_progreso":
            continue
        if partido.get("archivo_local_estado") in {"estado_inconsistente", "rechazado"}:
            continue
        if partido.get("validacion_error") or partido.get("archivo_rechazado"):
            continue

        marcadores = buscar_marcadores_borrado(partido)
        if marcadores:
            aplicar_marcador_a_partido(partido, marcadores[0])
            resumen["existentes"] += 1
            continue

        tiene_historial = any(
            partido.get(campo)
            for campo in (
                "archivo_local_ultimo",
                "archivo_web_ultimo",
                "postprocesado_web_en",
                "descargado_en",
                "nombre_canonico",
                "nombre_base_canonico",
            )
        )
        if not tiene_historial:
            continue

        marcador = escribir_marcador_borrado(partido, dry_run=dry_run)
        if not dry_run:
            aplicar_marcador_a_partido(partido, marcador)
            logger.info(f"Marcador BORRADO creado: {marcador.name}")
        resumen["creados"] += 1
    return resumen
