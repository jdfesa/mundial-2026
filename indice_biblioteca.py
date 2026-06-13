"""
Genera un indice simple para navegar los partidos descargados.
"""
import html
import logging
import os
from pathlib import Path
from urllib.parse import quote

import config
from idioma_utils import etiqueta_idioma

logger = logging.getLogger("mundial")


def _estado(partido: dict) -> str:
    if not partido.get("descargado"):
        return "Pendiente"
    if partido.get("estado_final"):
        return "Final"
    return "Mejorable"


def _estado_local(partido: dict) -> str:
    if not partido.get("descargado"):
        return "-"
    if partido.get("archivo_existe"):
        return "Local"
    if partido.get("archivo_local_ultimo"):
        return "Movido"
    return "Sin local"


def _href(path: str) -> str:
    try:
        rel = os.path.relpath(path, config.DIRECTORIO_BASE)
    except ValueError:
        rel = path
    return quote(rel.replace(os.sep, "/"))


def generar_indice(calendario: list[dict]) -> None:
    try:
        os.makedirs(config.DIRECTORIO_BASE, exist_ok=True)
    except OSError as e:
        logger.warning(f"No se pudo crear directorio base para indice: {e}")
        return

    html_path = Path(config.ARCHIVO_INDICE_HTML)
    playlist_path = Path(config.ARCHIVO_PLAYLIST_M3U)

    descargados = [p for p in calendario if p.get("descargado")]
    grupos = {}
    for partido in descargados:
        grupo = partido.get("grupo") or partido.get("fase") or "Otros"
        grupos.setdefault(grupo, []).append(partido)

    partes = [
        "<!doctype html>",
        "<html lang=\"es\">",
        "<head>",
        "<meta charset=\"utf-8\">",
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">",
        "<title>Mundial 2026 - Partidos</title>",
        "<style>",
        "body{font-family:system-ui,-apple-system,Segoe UI,sans-serif;margin:24px;line-height:1.35}",
        "table{border-collapse:collapse;width:100%;margin:12px 0 28px}",
        "th,td{border-bottom:1px solid #ddd;padding:8px;text-align:left}",
        ".final{color:#137333}.mejorable{color:#b06000}.pendiente{color:#777}",
        "</style>",
        "</head><body>",
        "<h1>Mundial 2026 - Partidos</h1>",
        f"<p>Total descargados: {len(descargados)}</p>",
    ]

    playlist = ["#EXTM3U"]

    for grupo in sorted(grupos):
        partes.append(f"<h2>{html.escape(grupo)}</h2>")
        partes.append("<table><thead><tr><th>Partido</th><th>Idioma</th><th>Estado</th><th>Local</th><th>Archivo</th></tr></thead><tbody>")
        for partido in sorted(grupos[grupo], key=lambda p: p.get("id", 9999)):
            nombre = f"{partido.get('equipo1')} vs {partido.get('equipo2')}"
            idioma = etiqueta_idioma(partido.get("idioma"))
            estado = _estado(partido)
            clase = estado.lower()
            archivo_local = partido.get("archivo_local")
            archivo = (
                partido.get("nombre_canonico")
                or partido.get("nombre_base_canonico")
                or partido.get("archivo")
                or "-"
            )
            if archivo_local and os.path.exists(archivo_local):
                link = f"<a href=\"{_href(archivo_local)}\">{html.escape(Path(archivo_local).name)}</a>"
                playlist.append(f"#EXTINF:-1,{nombre}")
                playlist.append(archivo_local)
            else:
                link = html.escape(archivo)
            partes.append(
                "<tr>"
                f"<td>{html.escape(nombre)}</td>"
                f"<td>{html.escape(idioma)}</td>"
                f"<td class=\"{clase}\">{html.escape(estado)}</td>"
                f"<td>{html.escape(_estado_local(partido))}</td>"
                f"<td>{link}</td>"
                "</tr>"
            )
        partes.append("</tbody></table>")

    partes.append("</body></html>")
    try:
        html_path.write_text("\n".join(partes), encoding="utf-8")
        playlist_path.write_text("\n".join(playlist) + "\n", encoding="utf-8")
    except OSError as e:
        logger.warning(f"No se pudo escribir indice de biblioteca: {e}")
