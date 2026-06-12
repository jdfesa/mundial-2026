"""
Genera un reporte diario de partidos, pendientes y mejoras.
"""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import config
from idioma_utils import etiqueta_idioma


def _parse_utc(valor: str):
    return datetime.fromisoformat(valor.replace("Z", "+00:00"))


def _estado(partido: dict) -> str:
    if not partido.get("descargado"):
        return "pendiente"
    if partido.get("estado_final"):
        return "final"
    return "mejorable"


def generar_reporte_diario(calendario: list[dict]) -> None:
    tz = ZoneInfo(getattr(config, "ZONA_HORARIA_REPORTE", "America/Argentina/Buenos_Aires"))
    ahora = datetime.now(tz)
    hoy = ahora.date()

    partidos_con_fecha = []
    for partido in calendario:
        try:
            fecha = _parse_utc(partido["fecha_hora_utc"]).astimezone(tz)
        except (KeyError, ValueError):
            continue
        partidos_con_fecha.append((fecha, partido))

    hoy_partidos = [(f, p) for f, p in partidos_con_fecha if f.date() == hoy]
    proximos = [(f, p) for f, p in partidos_con_fecha if f > ahora and p.get("equipo1") != "Por definir"]
    mejorables = [p for _, p in partidos_con_fecha if p.get("descargado") and not p.get("estado_final")]

    lineas = [
        "MUNDIAL 2026 - REPORTE DIARIO",
        f"Fecha local: {hoy.isoformat()} ({tz.key})",
        f"Generado: {ahora.strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "Partidos de hoy:",
    ]

    if hoy_partidos:
        for fecha, partido in sorted(hoy_partidos, key=lambda item: item[0]):
            lineas.append(
                f"  {fecha.strftime('%H:%M')} | {_estado(partido):<9} | "
                f"{partido.get('equipo1')} vs {partido.get('equipo2')} | "
                f"{partido.get('grupo', partido.get('fase', '-'))}"
            )
    else:
        lineas.append("  Sin partidos programados para hoy.")

    lineas.extend(["", "Versiones mejorables:"])
    if mejorables:
        for partido in sorted(mejorables, key=lambda p: p.get("id", 9999)):
            lineas.append(
                f"  {partido.get('id', '?'):>3} | {etiqueta_idioma(partido.get('idioma')):<11} | "
                f"{partido.get('equipo1')} vs {partido.get('equipo2')} | "
                f"{partido.get('archivo') or '-'}"
            )
    else:
        lineas.append("  No hay versiones mejorables.")

    lineas.extend(["", "Proximos partidos:"])
    for fecha, partido in sorted(proximos, key=lambda item: item[0])[:8]:
        lineas.append(
            f"  {fecha.strftime('%d/%m %H:%M')} | {_estado(partido):<9} | "
            f"{partido.get('equipo1')} vs {partido.get('equipo2')}"
        )

    with open(config.ARCHIVO_REPORTE_DIARIO, "w", encoding="utf-8") as f:
        f.write("\n".join(lineas) + "\n")
