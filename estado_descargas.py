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

logger = logging.getLogger("mundial")

STATE_FIELDS = (
    "descargado",
    "intentos",
    "ultimo_intento",
    "archivo",
    "proveedor",
    "ruta",
    "idioma",
    "estado_final",
    "necesita_mejora",
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
        item["equipo1"] = partido.get("equipo1")
        item["equipo2"] = partido.get("equipo2")
        item["fecha_hora_utc"] = partido.get("fecha_hora_utc")
        item["actualizado_en"] = datetime.now(timezone.utc).isoformat()

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
        "  PENDIENTE   = todavia no hay descarga",
        "",
    ]

    for partido in sorted(calendario, key=lambda p: p.get("id", 9999)):
        _normalizar_estado_partido(partido)
        descargado = bool(partido.get("descargado"))
        estado = "PENDIENTE"
        if descargado and partido.get("estado_final"):
            estado = "FINAL"
        elif descargado:
            estado = "MEJORABLE"

        idioma = etiqueta_idioma(partido.get("idioma")) if descargado else "-"
        archivo = partido.get("archivo") or "-"
        fecha = partido.get("fecha_hora_utc", "-")
        grupo = partido.get("grupo", partido.get("fase", "-"))
        equipo1 = partido.get("equipo1", "Por definir")
        equipo2 = partido.get("equipo2", "Por definir")

        lineas.append(
            f"{partido.get('id', '?'):>3} | {estado:<9} | {idioma:<11} | "
            f"{fecha} | {grupo} | {equipo1} vs {equipo2} | {archivo}"
        )

    with open(ruta, "w", encoding="utf-8") as f:
        f.write("\n".join(lineas) + "\n")
    logger.debug(f"Estado TXT guardado en {ruta}")
