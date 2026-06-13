"""
Genera una biblioteca HTML estatica para navegar los partidos.

El archivo se escribe dentro de DIRECTORIO_BASE y usa enlaces relativos para que
la carpeta completa pueda copiarse a otra computadora sin romper los links.
"""
import html
import logging
import os
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from urllib.parse import quote
from zoneinfo import ZoneInfo

import config
from idioma_utils import etiqueta_idioma

logger = logging.getLogger("mundial")

FLAG_MAP: dict[str, tuple[str, str]] = {
    "Alemania": ("🇩🇪", "DE"),
    "Arabia Saudita": ("🇸🇦", "SA"),
    "Argelia": ("🇩🇿", "DZ"),
    "Argentina": ("🇦🇷", "AR"),
    "Australia": ("🇦🇺", "AU"),
    "Austria": ("🇦🇹", "AT"),
    "Bosnia-Herzegovina": ("🇧🇦", "BA"),
    "Brasil": ("🇧🇷", "BR"),
    "Bélgica": ("🇧🇪", "BE"),
    "Cabo Verde": ("🇨🇻", "CV"),
    "Canadá": ("🇨🇦", "CA"),
    "Colombia": ("🇨🇴", "CO"),
    "Corea del Sur": ("🇰🇷", "KR"),
    "Costa de Marfil": ("🇨🇮", "CI"),
    "Croacia": ("🇭🇷", "HR"),
    "Curazao": ("🇨🇼", "CW"),
    "Ecuador": ("🇪🇨", "EC"),
    "Egipto": ("🇪🇬", "EG"),
    "Escocia": ("🏴", "SCO"),
    "España": ("🇪🇸", "ES"),
    "Estados Unidos": ("🇺🇸", "US"),
    "Francia": ("🇫🇷", "FR"),
    "Ghana": ("🇬🇭", "GH"),
    "Haití": ("🇭🇹", "HT"),
    "Inglaterra": ("🏴", "ENG"),
    "Irak": ("🇮🇶", "IQ"),
    "Irán": ("🇮🇷", "IR"),
    "Japón": ("🇯🇵", "JP"),
    "Jordania": ("🇯🇴", "JO"),
    "Marruecos": ("🇲🇦", "MA"),
    "México": ("🇲🇽", "MX"),
    "Noruega": ("🇳🇴", "NO"),
    "Nueva Zelanda": ("🇳🇿", "NZ"),
    "Panamá": ("🇵🇦", "PA"),
    "Paraguay": ("🇵🇾", "PY"),
    "Países Bajos": ("🇳🇱", "NL"),
    "Por definir": ("", "TBD"),
    "Portugal": ("🇵🇹", "PT"),
    "Qatar": ("🇶🇦", "QA"),
    "RD Congo": ("🇨🇩", "CD"),
    "Rep. Checa": ("🇨🇿", "CZ"),
    "Senegal": ("🇸🇳", "SN"),
    "Sudáfrica": ("🇿🇦", "ZA"),
    "Suecia": ("🇸🇪", "SE"),
    "Suiza": ("🇨🇭", "CH"),
    "Turquía": ("🇹🇷", "TR"),
    "Túnez": ("🇹🇳", "TN"),
    "Uruguay": ("🇺🇾", "UY"),
    "Uzbekistán": ("🇺🇿", "UZ"),
}


def _parse_utc(valor: str | None) -> datetime | None:
    if not valor:
        return None
    try:
        return datetime.fromisoformat(valor.replace("Z", "+00:00"))
    except ValueError:
        return None


def _fecha_local(partido: dict) -> datetime | None:
    fecha = _parse_utc(partido.get("fecha_hora_utc"))
    if not fecha:
        return None
    tz = ZoneInfo(getattr(config, "ZONA_HORARIA_REPORTE", "America/Argentina/Buenos_Aires"))
    return fecha.astimezone(tz)


def _nombre_partido(partido: dict) -> str:
    return f"{partido.get('equipo1', 'Por definir')} vs {partido.get('equipo2', 'Por definir')}"


def _render_flag(equipo: str | None) -> str:
    nombre = equipo or "Por definir"
    emoji, codigo = FLAG_MAP.get(nombre, ("", ""))
    emoji = emoji or "?"
    codigo = codigo or "?"
    return (
        f"<span class=\"team-flag\" title=\"{html.escape(nombre, quote=True)}\">"
        f"<span class=\"flag-emoji\" aria-hidden=\"true\">{html.escape(emoji)}</span>"
        f"<span class=\"flag-code\">{html.escape(codigo)}</span>"
        "</span>"
    )


def _render_flag_pair(partido: dict, class_name: str = "flags") -> str:
    equipo1 = partido.get("equipo1") or "Por definir"
    equipo2 = partido.get("equipo2") or "Por definir"
    nombre = _nombre_partido(partido)
    return (
        f"<span class=\"{class_name}\" aria-label=\"{html.escape(nombre, quote=True)}\">"
        f"{_render_flag(equipo1)}"
        "<span class=\"vs\">VS</span>"
        f"{_render_flag(equipo2)}"
        "</span>"
    )


def _directorio_partido(partido: dict) -> str:
    fase = partido.get("fase", "grupo")
    carpeta_fase = config.CARPETAS_FASE.get(fase, "Otros")
    if fase == "grupo":
        grupo = partido.get("grupo", "Sin_Grupo").replace(" ", "_")
        return os.path.join(config.DIRECTORIO_BASE, carpeta_fase, grupo)
    return os.path.join(config.DIRECTORIO_BASE, carpeta_fase)


def _archivo_existe_local(partido: dict) -> str | None:
    path = partido.get("archivo_local")
    if path and os.path.exists(path):
        return path
    return None


def _archivo_portable(partido: dict) -> str | None:
    """Devuelve la ruta que debe tener el video dentro de la biblioteca copiada."""
    if not partido.get("descargado"):
        return None

    local = _archivo_existe_local(partido)
    if local:
        return local

    ultimo = partido.get("archivo_local_ultimo")
    if ultimo:
        return ultimo

    nombre = partido.get("nombre_canonico")
    if nombre and Path(nombre).suffix:
        return os.path.join(_directorio_partido(partido), nombre)

    return None


def _estado_tarjeta(partido: dict) -> tuple[str, str, str]:
    archivo = _archivo_portable(partido)
    if archivo:
        if partido.get("estado_final"):
            return "disponible", "Disponible", "Listo para reproducir"
        return "mejorable", "Disponible", "Listo para reproducir"
    if partido.get("descargado"):
        return "eliminado", "Video eliminado", "Fue descargado, pero no hay una ruta guardada"
    return "pendiente", "Aun no disponible", "Todavia no se descargo"


def _visible_por_defecto(estado_key: str) -> bool:
    return estado_key in {"disponible", "mejorable"}


def _href(path: str) -> str:
    try:
        rel = os.path.relpath(path, config.DIRECTORIO_BASE)
    except ValueError:
        rel = path
    return quote(rel.replace(os.sep, "/"))


def _playlist_path(path: str) -> str:
    try:
        return os.path.relpath(path, config.DIRECTORIO_BASE).replace(os.sep, "/")
    except ValueError:
        return path


def _texto_busqueda(partido: dict, archivo: str | None) -> str:
    partes = [
        str(partido.get("id", "")),
        partido.get("equipo1", ""),
        partido.get("equipo2", ""),
        partido.get("grupo", ""),
        partido.get("fase", ""),
        etiqueta_idioma(partido.get("idioma")),
        partido.get("nombre_canonico", ""),
        partido.get("archivo", ""),
        Path(archivo).name if archivo else "",
    ]
    return html.escape(" ".join(str(p) for p in partes if p).lower(), quote=True)


def _fmt_fecha(partido: dict) -> str:
    fecha = _fecha_local(partido)
    if not fecha:
        return "Fecha por definir"
    return fecha.strftime("%d/%m/%Y %H:%M")


def _fmt_fecha_corta(partido: dict) -> str:
    fecha = _fecha_local(partido)
    if not fecha:
        return "-"
    return fecha.strftime("%d/%m %H:%M")


def _titulo_dia(fecha: datetime | None) -> str:
    if not fecha:
        return "Por definir"
    dias = [
        "Lunes",
        "Martes",
        "Miercoles",
        "Jueves",
        "Viernes",
        "Sabado",
        "Domingo",
    ]
    return f"{dias[fecha.weekday()]} {fecha.strftime('%d/%m/%Y')}"


def _grupo_orden(partido: dict) -> tuple[str, int]:
    grupo = partido.get("grupo") or partido.get("fase") or "Otros"
    try:
        return grupo, int(partido.get("id", 9999))
    except (TypeError, ValueError):
        return grupo, 9999


def _render_card(partido: dict) -> str:
    archivo = _archivo_portable(partido)
    estado_key, estado_label, estado_detalle = _estado_tarjeta(partido)
    nombre = _nombre_partido(partido)
    idioma = etiqueta_idioma(partido.get("idioma")) if partido.get("descargado") else "-"
    grupo = partido.get("grupo") or partido.get("fase") or "Sin grupo"
    fecha = _fmt_fecha(partido)
    canonico = (
        partido.get("nombre_canonico")
        or partido.get("nombre_base_canonico")
        or partido.get("archivo")
        or "Sin archivo"
    )
    data_text = _texto_busqueda(partido, archivo)
    numero = str(partido.get("id", "?")).zfill(3) if partido.get("id") is not None else "--"
    hidden_class = "" if _visible_por_defecto(estado_key) else " hidden"

    if archivo:
        accion = (
            f"<a class=\"play-button\" href=\"{_href(archivo)}\">Abrir video</a>"
            f"<p class=\"file-name\">{html.escape(Path(archivo).name)}</p>"
        )
    elif partido.get("descargado"):
        ultimo = partido.get("archivo_local_ultimo") or canonico
        accion = (
            "<div class=\"empty-action deleted\">Video eliminado o movido</div>"
            f"<p class=\"file-name\">Ultimo visto: {html.escape(Path(str(ultimo)).name)}</p>"
        )
    else:
        accion = "<div class=\"empty-action\">Aun no disponible</div>"

    return f"""
    <article class="match-card status-{estado_key}{hidden_class}" data-status="{estado_key}" data-text="{data_text}">
      <div class="thumb">
        <span class="match-number">{html.escape(numero)}</span>
        {_render_flag_pair(partido)}
      </div>
      <div class="card-body">
        <div class="meta-row">
          <span>{html.escape(grupo)}</span>
          <span>{html.escape(fecha)}</span>
        </div>
        <h3>{html.escape(nombre)}</h3>
        <div class="badges">
          <span class="badge badge-{estado_key}">{html.escape(estado_label)}</span>
          <span class="badge">{html.escape(idioma)}</span>
        </div>
        <p class="detail">{html.escape(estado_detalle)}</p>
        <div class="card-action">{accion}</div>
      </div>
    </article>
    """


def _render_calendar_row(partido: dict) -> str:
    archivo = _archivo_portable(partido)
    estado_key, estado_label, _ = _estado_tarjeta(partido)
    data_text = _texto_busqueda(partido, archivo)
    hidden_class = "" if _visible_por_defecto(estado_key) else " hidden"
    return (
        f"<tr class=\"calendar-row status-{estado_key}{hidden_class}\" data-status=\"{estado_key}\" "
        f"data-text=\"{data_text}\">"
        f"<td>{html.escape(_fmt_fecha_corta(partido))}</td>"
        f"<td><span class=\"calendar-match\">{_render_flag_pair(partido, 'calendar-flags')}"
        f"<span>{html.escape(_nombre_partido(partido))}</span></span></td>"
        f"<td>{html.escape(partido.get('grupo') or partido.get('fase') or '-')}</td>"
        f"<td><span class=\"badge badge-{estado_key}\">{html.escape(estado_label)}</span></td>"
        "</tr>"
    )


def _render_calendar(calendario: list[dict]) -> str:
    por_dia: dict[str, list[dict]] = defaultdict(list)
    for partido in calendario:
        fecha = _fecha_local(partido)
        clave = fecha.strftime("%Y-%m-%d") if fecha else "Por definir"
        por_dia[clave].append(partido)

    partes = []
    for clave in sorted(por_dia):
        partidos = sorted(por_dia[clave], key=lambda p: p.get("fecha_hora_utc", ""))
        titulo = _titulo_dia(_fecha_local(partidos[0]))
        filas = "\n".join(_render_calendar_row(p) for p in partidos)
        partes.append(
            f"""
            <section class="day-block">
              <h3>{html.escape(titulo)}</h3>
              <table>
                <thead><tr><th>Hora</th><th>Partido</th><th>Grupo</th><th>Estado</th></tr></thead>
                <tbody>{filas}</tbody>
              </table>
            </section>
            """
        )
    return "\n".join(partes)


def _css() -> str:
    return """
    :root {
      --bg: #f7f7f8;
      --panel: #ffffff;
      --ink: #1f2328;
      --muted: #68707d;
      --line: #dedfe3;
      --accent: #cc1f1a;
      --accent-dark: #a91612;
      --ok: #147a43;
      --warn: #936300;
      --bad: #9a3412;
      --pending: #626b76;
      --shadow: 0 6px 18px rgba(17, 24, 39, .08);
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      background: var(--bg);
      color: var(--ink);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      line-height: 1.45;
    }
    header {
      background: #181818;
      color: white;
      padding: 26px clamp(18px, 4vw, 44px);
    }
    header h1 { margin: 0 0 8px; font-size: clamp(28px, 4vw, 44px); }
    header p { margin: 0; color: #d6d6d6; font-size: 17px; }
    main { max-width: 1240px; margin: 0 auto; padding: 22px clamp(14px, 3vw, 32px) 48px; }
    .stats {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 12px;
      margin: 0 0 18px;
    }
    .stat {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 14px;
      box-shadow: var(--shadow);
    }
    .stat strong { display: block; font-size: 28px; }
    .stat span { color: var(--muted); }
    .toolbar {
      position: sticky;
      top: 0;
      z-index: 5;
      background: rgba(247,247,248,.96);
      border-bottom: 1px solid var(--line);
      padding: 12px 0;
      backdrop-filter: blur(8px);
    }
    .search {
      width: 100%;
      min-height: 48px;
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 0 14px;
      font-size: 18px;
      background: white;
    }
    .filters {
      display: flex;
      gap: 8px;
      overflow-x: auto;
      padding: 10px 0 0;
    }
    .filter {
      border: 1px solid var(--line);
      background: white;
      color: var(--ink);
      min-height: 40px;
      border-radius: 8px;
      padding: 0 13px;
      font-weight: 650;
      cursor: pointer;
      white-space: nowrap;
    }
    .filter.active {
      background: var(--accent);
      border-color: var(--accent);
      color: white;
    }
    .section-title {
      display: flex;
      align-items: end;
      justify-content: space-between;
      gap: 12px;
      margin: 24px 0 12px;
    }
    .section-title h2 { margin: 0; font-size: 24px; }
    .section-title span { color: var(--muted); }
    .grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
      gap: 14px;
    }
    .match-card {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      overflow: hidden;
      box-shadow: var(--shadow);
      min-height: 386px;
      display: flex;
      flex-direction: column;
    }
    .thumb {
      height: 132px;
      background: linear-gradient(135deg, #232323, #4b4f58);
      color: white;
      display: flex;
      align-items: center;
      justify-content: center;
      position: relative;
    }
    .match-number {
      position: absolute;
      top: 10px;
      left: 10px;
      background: rgba(0,0,0,.45);
      padding: 4px 8px;
      border-radius: 8px;
      font-weight: 700;
    }
    .flags {
      width: 100%;
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 16px;
      padding: 0 18px;
    }
    .team-flag {
      min-width: 72px;
      min-height: 78px;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      gap: 5px;
    }
    .flag-emoji {
      font-size: 48px;
      line-height: 1;
      filter: drop-shadow(0 2px 3px rgba(0,0,0,.18));
    }
    .flag-code {
      min-width: 34px;
      border-radius: 999px;
      padding: 2px 7px;
      background: rgba(0,0,0,.36);
      color: white;
      font-size: 12px;
      font-weight: 850;
      text-align: center;
    }
    .vs { font-size: 28px; font-weight: 850; letter-spacing: 0; }
    .card-body {
      padding: 14px;
      display: flex;
      flex-direction: column;
      gap: 10px;
      flex: 1;
    }
    .meta-row {
      display: flex;
      justify-content: space-between;
      gap: 8px;
      color: var(--muted);
      font-size: 13px;
    }
    h3 {
      margin: 0;
      min-height: 50px;
      font-size: 20px;
      line-height: 1.22;
    }
    .badges {
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
      min-height: 28px;
    }
    .badge {
      display: inline-flex;
      align-items: center;
      min-height: 28px;
      border-radius: 8px;
      padding: 0 8px;
      background: #eef0f3;
      color: #2f3640;
      font-size: 13px;
      font-weight: 700;
    }
    .badge-disponible, .badge-mejorable { background: #e8f5ee; color: var(--ok); }
    .badge-eliminado { background: #fff1e8; color: var(--bad); }
    .badge-pendiente { background: #eef0f3; color: var(--pending); }
    .detail { color: var(--muted); margin: 0; min-height: 42px; }
    .card-action {
      min-height: 88px;
      display: flex;
      flex-direction: column;
      gap: 8px;
      justify-content: flex-start;
      margin-top: auto;
    }
    .play-button {
      display: flex;
      align-items: center;
      justify-content: center;
      width: 100%;
      min-height: 46px;
      border-radius: 8px;
      background: var(--accent);
      color: white;
      text-decoration: none;
      font-weight: 800;
    }
    .play-button:hover { background: var(--accent-dark); }
    .empty-action {
      display: flex;
      align-items: center;
      justify-content: center;
      width: 100%;
      min-height: 46px;
      border-radius: 8px;
      background: #eceef2;
      color: var(--pending);
      font-weight: 800;
    }
    .empty-action.deleted { background: #fff1e8; color: var(--bad); }
    .file-name {
      margin: 0;
      color: var(--muted);
      font-size: 13px;
      overflow-wrap: anywhere;
      min-height: 34px;
      display: -webkit-box;
      -webkit-line-clamp: 2;
      -webkit-box-orient: vertical;
      overflow: hidden;
    }
    .calendar {
      margin-top: 28px;
    }
    .day-block {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 12px;
      margin: 12px 0;
      box-shadow: var(--shadow);
    }
    .day-block h3 { margin: 0 0 8px; }
    table { width: 100%; border-collapse: collapse; }
    th, td { text-align: left; border-bottom: 1px solid var(--line); padding: 10px 8px; }
    th { color: var(--muted); font-size: 13px; }
    tr:last-child td { border-bottom: 0; }
    .calendar-match {
      display: flex;
      align-items: center;
      gap: 8px;
    }
    .calendar-flags {
      display: inline-flex;
      align-items: center;
      gap: 3px;
      flex: 0 0 auto;
    }
    .calendar-flags .team-flag {
      min-width: 0;
      min-height: 0;
      display: inline-flex;
      flex-direction: row;
    }
    .calendar-flags .flag-emoji {
      font-size: 22px;
      filter: none;
    }
    .calendar-flags .flag-code { display: none; }
    .calendar-flags .vs {
      color: var(--muted);
      font-size: 11px;
      font-weight: 800;
    }
    .hidden { display: none !important; }
    @media (max-width: 760px) {
      .stats { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .grid { grid-template-columns: 1fr; }
      table { font-size: 14px; }
      th:nth-child(3), td:nth-child(3) { display: none; }
    }
    """


def _js() -> str:
    return """
    const search = document.querySelector('[data-search]');
    const filters = Array.from(document.querySelectorAll('[data-filter]'));
    const cards = Array.from(document.querySelectorAll('.match-card'));
    const rows = Array.from(document.querySelectorAll('.calendar-row'));
    const counter = document.querySelector('[data-counter]');
    let activeFilter = 'disponibles';

    function normalizeText(value) {
      return (value || '').normalize('NFD').replace(/[\\u0300-\\u036f]/g, '').toLowerCase();
    }

    function matchesFilter(item) {
      if (activeFilter === 'disponibles') {
        return item.dataset.status === 'disponible' || item.dataset.status === 'mejorable';
      }
      return activeFilter === 'todos' || item.dataset.status === activeFilter;
    }

    function matchesSearch(item, query) {
      return !query || normalizeText(item.dataset.text).includes(query);
    }

    function applyFilters() {
      const query = normalizeText(search.value).trim();
      let visibleCards = 0;
      cards.forEach(card => {
        const visible = matchesFilter(card) && matchesSearch(card, query);
        card.classList.toggle('hidden', !visible);
        if (visible) visibleCards += 1;
      });
      rows.forEach(row => {
        row.classList.toggle('hidden', !(matchesFilter(row) && matchesSearch(row, query)));
      });
      counter.textContent = `${visibleCards} partidos visibles`;
    }

    filters.forEach(button => {
      button.addEventListener('click', () => {
        activeFilter = button.dataset.filter;
        filters.forEach(btn => btn.classList.toggle('active', btn === button));
        applyFilters();
      });
    });

    search.addEventListener('input', applyFilters);
    applyFilters();
    """


def generar_indice(calendario: list[dict]) -> None:
    try:
        os.makedirs(config.DIRECTORIO_BASE, exist_ok=True)
    except OSError as e:
        logger.warning(f"No se pudo crear directorio base para indice: {e}")
        return

    html_path = Path(config.ARCHIVO_INDICE_HTML)
    playlist_path = Path(config.ARCHIVO_PLAYLIST_M3U)

    partidos = sorted(calendario, key=_grupo_orden)
    disponibles = [p for p in partidos if _archivo_portable(p)]
    descargados = [p for p in partidos if p.get("descargado")]
    eliminados = [p for p in partidos if p.get("descargado") and not _archivo_portable(p)]
    pendientes = [p for p in partidos if not p.get("descargado")]

    cards = "\n".join(_render_card(partido) for partido in partidos)
    calendario_html = _render_calendar(calendario)

    playlist = ["#EXTM3U"]
    for partido in partidos:
        archivo = _archivo_portable(partido)
        if not archivo:
            continue
        playlist.append(f"#EXTINF:-1,{_nombre_partido(partido)}")
        playlist.append(_playlist_path(archivo))

    partes = [
        "<!doctype html>",
        "<html lang=\"es\">",
        "<head>",
        "<meta charset=\"utf-8\">",
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">",
        "<title>Mundial 2026 - Biblioteca</title>",
        f"<style>{_css()}</style>",
        "</head>",
        "<body>",
        "<header>",
        "<h1>Mundial 2026</h1>",
        "<p>Biblioteca local de partidos. Hace click en Abrir video para reproducir.</p>",
        "</header>",
        "<main>",
        "<section class=\"stats\" aria-label=\"Resumen\">",
        f"<div class=\"stat\"><strong>{len(disponibles)}</strong><span>Videos disponibles</span></div>",
        f"<div class=\"stat\"><strong>{len(descargados)}</strong><span>Registrados</span></div>",
        f"<div class=\"stat\"><strong>{len(eliminados)}</strong><span>Videos eliminados</span></div>",
        f"<div class=\"stat\"><strong>{len(pendientes)}</strong><span>Aun no disponibles</span></div>",
        "</section>",
        "<section class=\"toolbar\" aria-label=\"Filtros\">",
        "<input class=\"search\" data-search type=\"search\" placeholder=\"Buscar equipo, grupo o numero de partido\">",
        "<div class=\"filters\">",
        "<button class=\"filter\" data-filter=\"todos\">Todos</button>",
        "<button class=\"filter active\" data-filter=\"disponibles\">Disponibles</button>",
        "<button class=\"filter\" data-filter=\"mejorable\">Mejorables</button>",
        "<button class=\"filter\" data-filter=\"pendiente\">Aun no disponibles</button>",
        "<button class=\"filter\" data-filter=\"eliminado\">Videos eliminados</button>",
        "</div>",
        "</section>",
        "<section class=\"section-title\">",
        "<h2>Partidos</h2>",
        "<span data-counter></span>",
        "</section>",
        f"<section class=\"grid\">{cards}</section>",
        "<section class=\"calendar\">",
        "<div class=\"section-title\"><h2>Calendario</h2><span>Se actualiza al finalizar cada corrida</span></div>",
        calendario_html,
        "</section>",
        "</main>",
        f"<script>{_js()}</script>",
        "</body>",
        "</html>",
    ]

    try:
        html_path.write_text("\n".join(partes), encoding="utf-8")
        playlist_path.write_text("\n".join(playlist) + "\n", encoding="utf-8")
    except OSError as e:
        logger.warning(f"No se pudo escribir indice de biblioteca: {e}")
