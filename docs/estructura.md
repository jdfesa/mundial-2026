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

## Raiz Del Repo

`run.sh` es el unico comando normal de operacion desde la raiz. Carga el entorno Python,
prepara el `PYTHONPATH` modular y delega en `scripts/00_orquestador/descargar_partidos.py`.

Tambien viven en la raiz los archivos de configuracion versionados, templates y datos base:

| Archivo | Descripcion |
|---------|-------------|
| `run.sh` | Orquestador normal del flujo completo. |
| `calendario_mundial_2026.json` | Calendario base de 104 partidos con fechas UTC. |
| `requirements.txt` | Dependencias Python. |
| `.env.example` | Template para configuracion local. |
| `fuentes_torrent.example.json` | Template para indexadores. |
| `fuentes_manuales.example.json` | Template para fuentes manuales. |

## Scripts Modulares

Las carpetas estan numeradas segun el orden mental del flujo. El usuario no deberia tener
que entrar aca para operar: `run.sh` orquesta todo.

| Carpeta | Responsabilidad |
|---------|-----------------|
| `scripts/00_orquestador/` | Script principal `descargar_partidos.py`, CLI y orden del flujo. |
| `scripts/00_config/` | Configuracion, nombres canonicos, idioma y helpers de estado puntual. |
| `scripts/01_estado/` | Estado persistente y marcadores `*_BORRADO.txt`. |
| `scripts/02_fuentes/` | Fuentes manuales, torrents, fallback yt-dlp, scoring y Groq opcional. |
| `scripts/03_qbittorrent/` | Integracion con qBittorrent y organizacion de descargas completas. |
| `scripts/04_verificacion/` | Auditoria, saneamiento, verificacion local y limpieza de idiomas. |
| `scripts/05_postproceso/` | MP4 web, remux/transcode y limpieza de origenes pesados. |
| `scripts/06_biblioteca/` | Indice HTML, assets web, playlist y reporte diario. |
| `scripts/07_notificaciones/` | Notificaciones del sistema cuando aplica. |
| `scripts/90_utilidades/` | Menus, instaladores y wrappers por plataforma. |
| `scripts/bootstrap.py` | Registra las carpetas numeradas para imports internos. |

## Utilidades Manuales

| Archivo | Descripcion |
|---------|-------------|
| `scripts/90_utilidades/menu.sh` | Menu interactivo Unix, macOS/Linux manual. |
| `scripts/90_utilidades/setup.sh` | Setup automatico macOS. |
| `scripts/90_utilidades/install_macos_launchd.sh` | Instala tarea launchd apuntando a `run.sh`. |
| `scripts/90_utilidades/run_windows.bat` | Ejecutor portable Windows. |
| `scripts/90_utilidades/install_windows_task.bat` | Instala tarea programada Windows. |
| `scripts/90_utilidades/setup_windows_smb.bat` | Prepara una carpeta SMB en Windows para copiar partidos. |

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
