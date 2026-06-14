"""
Estado persistente de descargas.

Mantiene un espejo separado de los campos operativos para que el calendario pueda
seguir siendo la fuente de fixtures y horarios.
"""
import json
import logging
import os
from datetime import datetime, timezone

import config
from idioma_utils import detectar_idioma, etiqueta_idioma, idioma_es_final
from nombres_archivos import nombre_base_canonico_partido

logger = logging.getLogger("mundial")

STATE_FIELDS = (
    "descargado",
    "descargado_en",
    "ultima_descarga_en",
    "descarga_iniciada_en",
    "revisar_descarga_despues_de",
    "descarga_estado",
    "descarga_progreso",
    "descarga_actualizada_en",
    "torrent_hash",
    "intentos",
    "ultimo_intento",
    "archivo",
    "proveedor",
    "ruta",
    "idioma",
    "estado_final",
    "necesita_mejora",
    "nombre_base_canonico",
    "nombre_canonico",
    "archivo_local",
    "archivo_local_ultimo",
    "archivo_local_estado",
    "archivo_existe",
    "archivo_valido",
    "validacion_error",
    "archivo_rechazado",
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
    "ffprobe",
    "pistas_audio",
    "idioma_detectado_archivo",
    "verificado_en",
    "postproceso",
    "compatibilidad_web",
    "audio_compatible_web",
    "archivo_web",
    "archivo_web_ultimo",
    "archivo_web_existe",
    "marcador_borrado",
    "marcador_borrado_existe",
    "marcador_borrado_en",
    "postprocesado_web_en",
    "archivo_origen_postproceso",
    "archivos_origen_postproceso",
    "postproceso_modo",
    "archivo_origen_eliminado",
    "archivo_origen_eliminado_en",
    "archivo_origen_eliminado_error",
    "archivos_origen_eliminados",
    "torrent_retirado_postproceso",
    "torrent_retirado_postproceso_en",
    "renombrado_en",
    "archivo_nombre_anterior",
    "archivo_relativo_torrent",
    "archivo_relativo_anterior",
    "metodo_renombrado",
    "renombrado",
    "renombrado_pendiente",
    "renombrado_error",
    "colision_nombre_canonico",
    "auxiliares_limpiados",
    "archivos_idioma_anterior_purgados",
    "idioma_anterior_purgado_en",
    "purga_idioma_anterior_pendiente",
    "purga_idioma_anterior_error",
    "intentos_mejora",
    "ultimo_intento_mejora",
)


def _partido_key(partido: dict) -> str:
    """Clave estable para identificar partidos entre calendario y estado."""
    if partido.get("id") is not None:
        return str(partido["id"])
    if partido.get("match_id") is not None:
        return str(partido["match_id"])
    equipo1 = partido.get("equipo1", "")
    equipo2 = partido.get("equipo2", "")
    fecha = partido.get("fecha_hora_utc", "")
    return f"{fecha}|{equipo1}|{equipo2}"


def cargar_estado() -> dict:
    """Carga estado desde disco; si no existe, devuelve estructura vacia."""
    ruta = getattr(config, "ARCHIVO_ESTADO", None)
    if not ruta or not os.path.exists(ruta):
        return {"partidos": {}}

    try:
        with open(ruta, "r", encoding="utf-8") as f:
            datos = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        logger.warning(f"No se pudo cargar estado separado: {e}")
        return {"partidos": {}}

    if not isinstance(datos, dict):
        return {"partidos": {}}
    datos.setdefault("partidos", {})
    return datos


def aplicar_estado(calendario: list[dict], estado: dict) -> None:
    """
    Aplica el estado separado sobre el calendario en memoria.

    Si no hay estado separado para un partido, se conservan los campos que ya
    estaban en el JSON de calendario.
    """
    partidos_estado = estado.get("partidos", {})
    for partido in calendario:
        datos = partidos_estado.get(_partido_key(partido))
        if not datos:
            continue
        for campo in STATE_FIELDS:
            if campo in datos:
                if campo == "descargado" and partido.get("descargado") and not datos[campo]:
                    continue
                partido[campo] = datos[campo]

        _normalizar_estado_partido(partido)


def normalizar_calendario(calendario: list[dict]) -> None:
    """Normaliza todos los partidos aunque aun no exista estado separado."""
    for partido in calendario:
        _normalizar_estado_partido(partido)


def _normalizar_estado_partido(partido: dict) -> None:
    """Completa campos nuevos para calendarios viejos."""
    if partido.get("descargado"):
        if not partido.get("idioma"):
            partido["idioma"] = detectar_idioma(partido.get("archivo"))
        partido["estado_final"] = idioma_es_final(partido.get("idioma"))
        partido["necesita_mejora"] = not partido["estado_final"]
        partido["nombre_base_canonico"] = nombre_base_canonico_partido(partido)
        if partido.get("archivo_local") and not partido.get("archivo_local_ultimo"):
            partido["archivo_local_ultimo"] = partido.get("archivo_local")
        if not partido.get("archivo_local_estado"):
            partido["archivo_local_estado"] = (
                "presente" if partido.get("archivo_existe") else "no_verificado"
            )
    else:
        partido.setdefault("idioma", None)
        partido.setdefault("estado_final", False)
        partido.setdefault("necesita_mejora", False)


def actualizar_estado_desde_calendario(calendario: list[dict], estado: dict | None = None) -> dict:
    """Construye/actualiza el estado usando los campos operativos del calendario."""
    estado = estado or {"partidos": {}}
    partidos_estado = estado.setdefault("partidos", {})

    for partido in calendario:
        _normalizar_estado_partido(partido)
        key = _partido_key(partido)
        item = partidos_estado.setdefault(key, {})
        for campo in STATE_FIELDS:
            if campo in partido:
                item[campo] = partido.get(campo)
            else:
                item.pop(campo, None)
        item["equipo1"] = partido.get("equipo1")
        item["equipo2"] = partido.get("equipo2")
        item["fecha_hora_utc"] = partido.get("fecha_hora_utc")
        item["actualizado_en"] = datetime.now(timezone.utc).isoformat()

    vacios = []
    for key, item in partidos_estado.items():
        tiene_estado_real = any(
            item.get(campo) not in (None, False, "", [], {})
            for campo in STATE_FIELDS
        )
        if not tiene_estado_real:
            vacios.append(key)
    for key in vacios:
        partidos_estado.pop(key, None)

    return estado


def guardar_estado(calendario: list[dict], estado: dict | None = None) -> None:
    """Guarda el estado separado en disco."""
    ruta = getattr(config, "ARCHIVO_ESTADO", None)
    if not ruta:
        return

    estado = actualizar_estado_desde_calendario(calendario, estado)
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump(estado, f, indent=2, ensure_ascii=False)
    logger.debug(f"Estado separado guardado en {ruta}")
    guardar_estado_txt(calendario)


def guardar_estado_txt(calendario: list[dict]) -> None:
    """Escribe un resumen legible para revisar descargas e idiomas."""
    ruta = getattr(config, "ARCHIVO_ESTADO_TXT", None)
    if not ruta:
        return

    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    ahora = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    lineas = [
        "MUNDIAL 2026 - ESTADO DE PARTIDOS",
        f"Actualizado: {ahora}",
        "",
        "Estados:",
        "  FINAL       = ya hay version en idioma preferido",
        "  MEJORABLE   = hay descarga, pero falta idioma preferido",
        "  BORRADO     = ya fue descargado/transferido, pero no esta localmente",
        "  PENDIENTE   = todavia no hay descarga",
        "",
    ]

    for partido in sorted(calendario, key=lambda p: p.get("id", 9999)):
        _normalizar_estado_partido(partido)
        descargado = bool(partido.get("descargado"))
        estado = "PENDIENTE"
        if descargado and partido.get("marcador_borrado_existe"):
            estado = "BORRADO"
        elif descargado and partido.get("estado_final"):
            estado = "FINAL"
        elif descargado:
            estado = "MEJORABLE"

        idioma = etiqueta_idioma(partido.get("idioma")) if descargado else "-"
        archivo = partido.get("archivo") or "-"
        archivo_local = partido.get("archivo_local")
        archivo_ultimo = partido.get("archivo_local_ultimo")
        nombre_canonico = partido.get("nombre_canonico") or partido.get("nombre_base_canonico")
        if archivo_local:
            archivo = f"{nombre_canonico or archivo} | local: {os.path.basename(archivo_local)}"
        elif archivo_ultimo:
            archivo = f"{nombre_canonico or archivo} | ultimo local: {os.path.basename(archivo_ultimo)}"
        elif nombre_canonico:
            archivo = nombre_canonico
        datos_archivo = []
        if partido.get("tamano_mb"):
            datos_archivo.append(f"{partido['tamano_mb']} MB")
        if partido.get("duracion_min"):
            datos_archivo.append(f"{partido['duracion_min']} min")
        if partido.get("resolucion"):
            datos_archivo.append(str(partido["resolucion"]))
        estado_local = partido.get("archivo_local_estado")
        if descargado and estado_local:
            datos_archivo.append(f"local: {estado_local}")
        if partido.get("validacion_error"):
            datos_archivo.append(f"rechazado: {partido['validacion_error']}")
        descarga_estado = partido.get("descarga_estado")
        if descargado and descarga_estado and descarga_estado != "completa":
            progreso = partido.get("descarga_progreso")
            if progreso is not None:
                datos_archivo.append(f"descarga: {descarga_estado} {progreso}%")
            else:
                datos_archivo.append(f"descarga: {descarga_estado}")
        postproceso = partido.get("postproceso") or {}
        if postproceso.get("estado") and not partido.get("validacion_error"):
            datos_archivo.append(f"post: {postproceso['estado']} ({postproceso.get('motivo', '-')})")
        compatibilidad_web = partido.get("compatibilidad_web") or {}
        if compatibilidad_web.get("estado"):
            datos_archivo.append(
                f"web: {compatibilidad_web['estado']} "
                f"({compatibilidad_web.get('motivo', '-')})"
            )
        extra = f" | {' / '.join(datos_archivo)}" if datos_archivo else ""
        fecha = partido.get("fecha_hora_utc", "-")
        grupo = partido.get("grupo", partido.get("fase", "-"))
        equipo1 = partido.get("equipo1", "Por definir")
        equipo2 = partido.get("equipo2", "Por definir")

        lineas.append(
            f"{partido.get('id', '?'):>3} | {estado:<9} | {idioma:<11} | "
            f"{fecha} | {grupo} | {equipo1} vs {equipo2} | {archivo}{extra}"
        )

    with open(ruta, "w", encoding="utf-8") as f:
        f.write("\n".join(lineas) + "\n")
    logger.debug(f"Estado TXT guardado en {ruta}")
