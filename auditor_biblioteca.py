"""
Auditoria y saneamiento local de rutas de biblioteca.

No decide identidad: usa el calendario y el prefijo canonico del archivo para
detectar inconsistencias como un `001_...` dentro de la carpeta de otro grupo o
dos partidos apuntando al mismo MP4.
"""
import logging
import os
from collections import defaultdict
from pathlib import Path

import config
from estado_partido import descarga_en_progreso
from nombres_archivos import nombre_canonico_partido
from organizador_descargas import directorio_partido

logger = logging.getLogger("mundial")


def _id_archivo(path: Path) -> int | None:
    nombre = path.name
    if "_" not in nombre:
        return None
    prefijo = nombre.split("_", 1)[0]
    try:
        return int(prefijo)
    except ValueError:
        return None


def _videos_locales() -> list[Path]:
    base = Path(config.DIRECTORIO_BASE)
    if not base.exists():
        return []
    extensiones = tuple(ext.lower() for ext in getattr(config, "EXTENSIONES_VIDEO", []))
    return [path for path in base.rglob("*") if path.is_file() and path.suffix.lower() in extensiones]


def _rel(path: Path) -> str:
    try:
        return os.path.relpath(path, config.DIRECTORIO_BASE)
    except ValueError:
        return str(path)


def _path_estado(partido: dict, campo: str) -> Path | None:
    valor = partido.get(campo)
    if not valor:
        return None
    return Path(valor)


def _resolver_destino(partido: dict, path: Path) -> Path:
    nombre = path.name
    if _id_archivo(path) == partido.get("id"):
        nombre = nombre_canonico_partido(partido, path.suffix, partido.get("idioma"))
    return Path(directorio_partido(partido)) / nombre


def _limpiar_metadata_local(partido: dict) -> None:
    for campo in (
        "archivo",
        "archivo_local",
        "archivo_web",
        "archivo_local_ultimo",
        "archivo_web_ultimo",
        "nombre_canonico",
        "tamano_mb",
        "duracion_min",
        "resolucion",
        "ancho",
        "alto",
        "fps",
        "bitrate_kbps",
        "codec_video",
        "codec_audio",
        "codecs_audio",
        "canales_audio",
        "layout_audio",
        "postproceso",
        "compatibilidad_web",
        "audio_compatible_web",
        "postprocesado_web_en",
    ):
        partido.pop(campo, None)
    partido["archivo_existe"] = False
    partido["archivo_web_existe"] = False


def auditar_biblioteca(calendario: list[dict]) -> dict:
    por_id = {p.get("id"): p for p in calendario if p.get("id") is not None}
    problemas = {
        "archivos_fuera_de_carpeta": [],
        "estado_id_incorrecto": [],
        "rutas_duplicadas": [],
    }

    for path in _videos_locales():
        archivo_id = _id_archivo(path)
        if archivo_id is None or archivo_id not in por_id:
            continue
        partido = por_id[archivo_id]
        esperado = Path(directorio_partido(partido))
        try:
            carpeta_actual = path.parent.resolve()
            carpeta_esperada = esperado.resolve()
        except OSError:
            continue
        if carpeta_actual != carpeta_esperada:
            problemas["archivos_fuera_de_carpeta"].append({
                "id": archivo_id,
                "partido": f"{partido.get('equipo1')} vs {partido.get('equipo2')}",
                "actual": _rel(path),
                "esperado": _rel(esperado / path.name),
            })

    rutas_por_partido = defaultdict(list)
    for partido in calendario:
        for campo in ("archivo", "archivo_local", "archivo_web", "archivo_local_ultimo", "archivo_web_ultimo"):
            path = _path_estado(partido, campo)
            if not path:
                continue
            archivo_id = _id_archivo(path)
            if archivo_id is not None and partido.get("id") is not None and archivo_id != partido.get("id"):
                problemas["estado_id_incorrecto"].append({
                    "id": partido.get("id"),
                    "campo": campo,
                    "archivo_id": archivo_id,
                    "ruta": str(path),
                })
            rutas_por_partido[str(path)].append(partido.get("id"))

    for ruta, ids in rutas_por_partido.items():
        unicos = sorted({i for i in ids if i is not None})
        if len(unicos) > 1:
            problemas["rutas_duplicadas"].append({"ruta": ruta, "ids": unicos})

    return problemas


def imprimir_auditoria(problemas: dict) -> None:
    total = sum(len(v) for v in problemas.values())
    if not total:
        print("Auditoria biblioteca: sin inconsistencias detectadas")
        return
    print(f"Auditoria biblioteca: {total} inconsistencia(s)")
    for clave, items in problemas.items():
        if not items:
            continue
        print(f"\n{clave}:")
        for item in items:
            print(f"  - {item}")


def sanear_biblioteca(calendario: list[dict], dry_run: bool = True) -> dict:
    """
    Corrige inconsistencias obvias sin tocar descargas activas.
    """
    por_id = {p.get("id"): p for p in calendario if p.get("id") is not None}
    resumen = {"movidos": 0, "estado_limpiado": 0, "omitidos": 0, "acciones": []}

    for path in _videos_locales():
        archivo_id = _id_archivo(path)
        partido = por_id.get(archivo_id)
        if not partido:
            continue
        if descarga_en_progreso(partido):
            resumen["omitidos"] += 1
            continue
        destino = _resolver_destino(partido, path)
        try:
            if path.resolve() == destino.resolve():
                continue
        except OSError:
            continue
        accion = f"mover {_rel(path)} -> {_rel(destino)}"
        resumen["acciones"].append(accion)
        if dry_run:
            continue
        if destino.exists():
            resumen["omitidos"] += 1
            continue
        destino.parent.mkdir(parents=True, exist_ok=True)
        path.rename(destino)
        partido["archivo_local"] = str(destino)
        partido["archivo_local_ultimo"] = str(destino)
        partido["archivo_web"] = str(destino)
        partido["archivo_web_ultimo"] = str(destino)
        partido["archivo"] = destino.name
        partido["nombre_canonico"] = destino.name
        partido["ruta"] = str(destino.parent)
        partido["archivo_existe"] = True
        partido["archivo_web_existe"] = True
        resumen["movidos"] += 1

    for partido in calendario:
        partido_id = partido.get("id")
        limpio_estado = False
        for campo in ("archivo", "archivo_local", "archivo_web", "archivo_local_ultimo", "archivo_web_ultimo"):
            path = _path_estado(partido, campo)
            if not path:
                continue
            archivo_id = _id_archivo(path)
            if archivo_id is None or archivo_id == partido_id:
                continue
            resumen["acciones"].append(
                f"limpiar estado id {partido_id}: {campo} apuntaba a archivo id {archivo_id}"
            )
            if dry_run:
                continue
            partido[campo] = None
            limpio_estado = True
            resumen["estado_limpiado"] += 1
        if limpio_estado and not dry_run:
            _limpiar_metadata_local(partido)
            if partido.get("validacion_error") or partido.get("archivo_rechazado"):
                partido["descargado"] = False
                partido["estado_final"] = False
                partido["necesita_mejora"] = False
                partido["descarga_estado"] = "rechazada"
                partido["archivo_local_estado"] = "rechazado"
            else:
                partido["archivo_local_estado"] = "estado_inconsistente"

    if resumen["acciones"]:
        logger.info(
            "Saneamiento biblioteca: "
            f"{resumen['movidos']} movidos, {resumen['estado_limpiado']} campos limpiados"
        )
    return resumen
