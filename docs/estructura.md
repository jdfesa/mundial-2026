# Estructura

Este documento lista las carpetas generadas y los archivos principales del proyecto. El
README mantiene el mapa visual corto; aca queda el inventario mas completo.

## Carpeta De Biblioteca

```text
~/Desktop/Mundial_Partidos/
├── Fase_de_Grupos/
│   ├── Grupo_A/   (Mexico, Sudafrica, Corea del Sur, Rep. Checa)
│   ├── Grupo_B/   (Canada, Bosnia, Qatar, Suiza)
│   ├── ...
│   ├── Grupo_J/   (Argentina, Argelia, Austria, Jordania)
│   └── Grupo_L/
├── Octavos_de_Final/
├── Cuartos_de_Final/
├── Semifinales/
├── Tercer_Puesto/
└── Final/
```

La ruta exacta depende de `MUNDIAL_DIRECTORIO_BASE` en `.env`.

## Archivos Versionados

| Archivo | Descripcion |
|---------|-------------|
| `descargar_partidos.py` | Script principal, coordinador. |
| `buscador_torrents.py` | Fachada del buscador y ranking final. |
| `busqueda_reglas.py` | Queries, scoring y validaciones compartidas. |
| `fuentes_torrent.py` | Scrapers/APIs de indexadores torrent. |
| `fallback_ytdlp.py` | Fallback tardio y validado con yt-dlp. |
| `groq_asistente.py` | Asistente opcional para queries y clasificacion. |
| `qbit_manager.py` | Integracion con qBittorrent. |
| `notificador.py` | Notificaciones del sistema cuando aplica. |
| `config.py` | Configuracion centralizada; lee `.env`. |
| `estado_descargas.py` | Estado persistente separado del calendario. |
| `idioma_utils.py` | Deteccion y clasificacion de idioma. |
| `nombres_archivos.py` | Nombres canonicos de archivos descargados. |
| `fuentes_manuales.py` | Logica para fuentes declaradas por el usuario. |
| `organizador_descargas.py` | Mueve torrents completos a la carpeta final. |
| `verificador_archivos.py` | Verifica archivos locales y metadata con ffprobe. |
| `indice_biblioteca.py` | Genera indice HTML y playlist M3U. |
| `reporte_diario.py` | Genera resumen diario de partidos y mejoras. |
| `calendario_mundial_2026.json` | Calendario base de 104 partidos con fechas UTC. |
| `requirements.txt` | Dependencias Python. |
| `.env.example` | Template para configuracion local. |
| `fuentes_torrent.example.json` | Template para indexadores. |
| `fuentes_manuales.example.json` | Template para fuentes manuales. |
| `run.sh` | Ejecutor portable Unix, macOS/Linux manual. |
| `menu.sh` | Menu interactivo Unix, macOS/Linux manual. |
| `run_windows.bat` | Ejecutor portable Windows. |
| `setup.sh` | Setup automatico macOS. |
| `install_macos_launchd.sh` | Instala tarea launchd. |
| `install_windows_task.bat` | Instala tarea programada Windows. |

## Documentacion

| Documento | Uso |
|-----------|-----|
| `docs/funcionamiento.md` | Reglas de busqueda, idioma, historial, postproceso y reportes. |
| `docs/archivos-locales.md` | Archivos ignorados, generados y configuracion local. |
| `docs/plataformas.md` | Estado de soporte por sistema operativo. |
| `docs/qbittorrent.md` | Configuracion y diagnostico de qBittorrent Web API. |
| `docs/estructura.md` | Este inventario de estructura y archivos. |

## Archivos Locales Ignorados

Detalle completo: `docs/archivos-locales.md`.

Resumen:

- `.env`
- `fuentes_torrent.json`
- `fuentes_manuales.json`
- `estado_descargas.json`
- `estado_partidos.txt`
- `reporte_diario.txt`
- `mundial.log`
- `Mundial_Partidos/`
