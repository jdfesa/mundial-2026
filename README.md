# ⚽ Descargador Mundial 2026

## Aviso Legal

Este proyecto es una herramienta de automatización con fines educativos, técnicos y de uso
personal. El script no aloja, no vende, no publica y no distribuye contenido audiovisual.
Solo automatiza búsquedas, organización local, reintentos y descargas a partir de fuentes
configuradas por el usuario.

Los partidos, transmisiones, relatos, logos, nombres comerciales y materiales asociados al
Mundial pueden estar protegidos por derechos de autor, derechos de transmisión, marcas u
otras restricciones legales. Cada usuario es responsable de verificar que tiene permiso,
licencia o derecho de acceso para descargar, grabar, copiar o conservar cualquier contenido
que use con este proyecto.

Agregar este aviso no autoriza el uso de fuentes no permitidas ni reemplaza asesoramiento
legal. Si una fuente no permite descarga, copia, redistribución o conservación local, no
debería usarse con este script.

---

## Qué es

Scripts en Python para organizar la búsqueda, descarga y archivo automático de los 104
partidos del Mundial FIFA 2026. Funciona en macOS y Windows.

El sistema busca partidos ya finalizados en fuentes torrent configuradas por el usuario,
los descarga vía qBittorrent y los organiza automáticamente en carpetas por fase y grupo.

## Cómo funciona

```
┌─────────────────────────────────────────────────────────────────┐
│  launchd / Task Scheduler (cada 30 min)                        │
│      └── descargar_partidos.py                                 │
│              ├── Lee calendario_mundial_2026.json (104 matches) │
│              ├── ¿Partido terminó hace +3 horas? ──► buscar    │
│              ├── buscador_torrents.py                           │
│              │       ├── fuentes_torrent.json (mirrors)        │
│              │       ├── fuentes_manuales.json (URLs propias)  │
│              │       └── yt-dlp (fallback)                     │
│              ├── qbit_manager.py ──► qBittorrent               │
│              ├── organizador_descargas.py                      │
│              ├── verificador_archivos.py                       │
│              ├── reporte_diario.py                             │
│              ├── indice_biblioteca.py                          │
│              └── ~/Desktop/Mundial_Partidos/                   │
│                      ├── Fase_de_Grupos/Grupo_A/               │
│                      ├── Fase_de_Grupos/Grupo_B/               │
│                      ├── ...                                   │
│                      ├── Octavos_de_Final/                     │
│                      ├── Cuartos_de_Final/                     │
│                      ├── Semifinales/                          │
│                      └── Final/                                │
└─────────────────────────────────────────────────────────────────┘
```

### Lógica de búsqueda

1. El script revisa el calendario y solo procesa partidos que:
   - ya hayan empezado hace al menos 3 horas;
   - no estén descargados en idioma final;
   - no hayan superado el máximo de intentos normales (15);
   - respeten el tiempo entre reintentos (30 min).

2. Para cada partido genera ~15 queries de búsqueda (en inglés y español, en ambos
   órdenes: "Mexico vs South Africa" y "South Africa vs Mexico").

3. Busca en los indexadores configurados en `fuentes_torrent.json`. Si no encuentra
   nada, `yt-dlp` queda reservado como fallback tardío y validado.

4. Si `GROQ_HABILITADO=1`, Groq puede sumar queries de búsqueda y ajustar la puntuación
   de resultados ya encontrados. No agrega URLs por su cuenta ni salta las fuentes
   configuradas.

5. El mejor resultado se elige por puntuación:
   - Idioma español: **+100 puntos**
   - Partido completo: +50
   - Calidad 720p: +30
   - Seeders (logarítmico): hasta +40
   - Tamaño ideal (1.5-5 GB): +15
    - Keywords del mundial: +10

El fallback `yt-dlp` espera bastante más que los torrents antes de activarse
(`YTDLP_HORAS_ESPERA_POST_PARTIDO`, por defecto 24 horas desde el inicio del partido).
Antes de descargar, revisa metadata: ambos equipos deben aparecer en el título, debe haber
señal de partido completo/replay, no puede contener palabras de comentario/reacción, debe
durar entre 90 y 180 minutos y tener al menos 720p. Si un archivo descargado por `yt-dlp`
no pasa esa validación local, queda como `rechazado` y el partido vuelve a pendiente.

### Lógica de idioma

| Idioma detectado | Estado      | ¿Sigue buscando?                        |
|------------------|-------------|------------------------------------------|
| Español          | `FINAL`     | No. Ya tiene la versión preferida.       |
| Inglés           | `MEJORABLE` | Sí, pero solo si encuentra una en español. |
| Desconocido      | `MEJORABLE` | Sí, igual que inglés.                    |

Si un partido ya está en inglés y una búsqueda posterior encuentra otro resultado en
inglés, no se vuelve a descargar. Si encuentra una versión en español, se descarga y
el partido pasa a estado final.

Las búsquedas de mejora para partidos ya descargados en inglés no consumen los intentos
normales. Se registran aparte como `intentos_mejora` y `ultimo_intento_mejora`, y se
reintentan cada `MINUTOS_ENTRE_REINTENTOS_MEJORA`.

## Verificación, índice y reporte

El histórico operativo vive en `estado_descargas.json`. Ese archivo es la verdad que usa
el script para saber qué partidos ya fueron descargados, cuáles son finales y cuáles siguen
siendo mejorables. La biblioteca local solo se usa como verificación complementaria: si
movés o borrás un archivo de esta computadora después de pasarlo a otra PC, el partido no
vuelve a pendiente.

En cada `--status` y al final de una ejecución real, el script revisa la biblioteca local:

- busca archivos de video en `DIRECTORIO_BASE`;
- también revisa la ruta guardada del partido si existe;
- opcionalmente revisa rutas extra configuradas en `MUNDIAL_DIRECTORIOS_EXTRA`;
- si encuentra un video, guarda `archivo_local`, `archivo_local_ultimo`,
  `archivo_existe`, `archivo_local_estado`, `tamano_mb`, `duracion_min`, `resolucion`,
  `codec_video`, `fps`, `bitrate_kbps` e `idioma_detectado_archivo`;
- si ya no encuentra el video, conserva `archivo_local_ultimo` y marca
  `archivo_local_estado=movido_o_borrado`, sin cambiar `descargado`,
  `estado_final` ni `necesita_mejora`.

Para leer duración, resolución e idioma de pistas de audio usa `ffprobe` si está instalado.
Si no está, igual detecta existencia y tamaño.

### Nombres y postproceso

Los archivos completos se renombran a un formato estable cuando el script puede hacerlo de
forma segura:

```text
001_mexico_vs_sudafrica_en.mkv
002_corea_del_sur_vs_rep_checa_es.mp4
```

El prefijo numérico evita colisiones, los equipos salen del calendario en español y el
sufijo indica idioma/estado: `_es` es final, `_en` queda como mejorable. Si qBittorrent
está administrando el archivo, el renombrado se intenta por la Web API de qBittorrent. Para
fuentes manuales o `yt-dlp`, el renombrado puede hacerse directamente sobre el archivo.

No se recomprime por defecto. El postproceso queda como evaluación registrada en estado:
si el archivo pesa hasta 5 GB y está en 720p o menos, se marca `mantener_origen`; si supera
5 GB o viene por encima de 720p, queda `revisar` para decidir manualmente si vale la pena
remuxear o recomprimir.

Cuando una descarga se encola, el estado guarda `descarga_iniciada_en`,
`revisar_descarga_despues_de` y `torrent_hash` si está disponible. La revisión de una hora
es una referencia: cada corrida consulta qBittorrent y solo mueve/renombra/verifica cuando
el progreso real está completo.

Si qBittorrent está corriendo y la Web API responde, también sincroniza torrents completos:

- detecta torrents ya completados;
- los compara contra el calendario/estado por título y equipos;
- si están en la carpeta por defecto de qBittorrent, le pide a qBittorrent que los mueva al
  destino final por fase/grupo;
- no mueve archivos con `shutil` mientras qBittorrent los administra.

Esto se controla con:

```env
QBIT_MOVER_COMPLETADOS=1
QBIT_BUSCAR_TODAS_LAS_DESCARGAS=1
MUNDIAL_RENOMBRAR_ARCHIVOS=1
```

En una ejecución normal el script puede abrir qBittorrent si no está corriendo. En `--status`
no lo abre: solo informa el estado para que consultar no dispare aplicaciones.

También se generan:

```text
estado_partidos.txt
reporte_diario.txt
<DIRECTORIO_BASE>/index.html
<DIRECTORIO_BASE>/playlist_mundial.m3u
```

El índice HTML permite abrir los partidos descargados desde una página simple, agrupados por
grupo/fase. La playlist M3U sirve para abrir todo desde VLC u otro reproductor compatible.

La zona horaria del reporte diario se puede cambiar con:

```env
MUNDIAL_ZONA_HORARIA=America/Argentina/Buenos_Aires
```

## Instalación

### Requisitos

- Python 3.10+
- [qBittorrent](https://www.qbittorrent.org/) instalado
- Git (para clonar el repo)

### Paso a paso

```bash
# 1. Clonar el repositorio
git clone https://github.com/jdfesa/mundial-2026.git
cd mundial-2026

# 2. Crear entorno virtual e instalar dependencias
python3 -m venv venv
source venv/bin/activate        # En Windows: venv\Scripts\activate
pip install -r requirements.txt

# 3. Configurar datos locales
cp .env.example .env
cp fuentes_torrent.example.json fuentes_torrent.json
cp fuentes_manuales.example.json fuentes_manuales.json

# 4. Editar .env con tu ruta de descarga y credenciales de qBittorrent
# 5. Editar fuentes_torrent.json con mirrors funcionales
```

### Setup automático (macOS)

```bash
chmod +x setup.sh
bash setup.sh
```

Esto crea el entorno, instala dependencias, genera las carpetas de destino e instala
la tarea de launchd para ejecución automática cada 30 minutos.

### Setup automático (Windows)

```bat
run_windows.bat --dry-run
install_windows_task.bat
```

## Configuración

### `.env`

Archivo con datos locales (no se sube al repo):

```env
MUNDIAL_DIRECTORIO_BASE=~/Desktop/Mundial_Partidos
QBIT_HOST=127.0.0.1
QBIT_PORT=8080
QBIT_USER=admin
QBIT_PASS=adminadmin
GROQ_API_KEY=tu_api_key_local
GROQ_HABILITADO=1
GROQ_MODEL=openai/gpt-oss-20b
```

### `fuentes_torrent.json`

Archivo con los indexadores y sus mirrors (no se sube al repo):

```json
{
  "indexadores": [
    {
      "nombre": "1337x",
      "habilitado": true,
      "tipo": "scraper"
    },
    {
      "nombre": "piratebay",
      "habilitado": true,
      "tipo": "api",
      "mirrors": [
        "https://tu-mirror-1.com",
        "https://tu-mirror-2.com/api"
      ]
    }
  ]
}
```

Podés agregar más indexadores siguiendo el mismo formato. Si uno no responde, pasa al
siguiente automáticamente.

### `fuentes_manuales.json`

Para agregar URLs específicas de partidos (replays oficiales, grabaciones propias, etc.):

```json
{
  "fuentes": [
    {
      "id": 3,
      "equipo1": "Canada",
      "equipo2": "Bosnia-Herzegovina",
      "url": "https://example.com/replay.mp4",
      "titulo": "Canada_vs_Bosnia_2026_1080p_es",
      "idioma": "es"
    }
  ]
}
```

Las fuentes manuales se intentan primero. Si no hay una para el partido, el flujo normal
sigue funcionando.

## Uso

### macOS

Uso recomendado con menu interactivo:

```bash
./menu_macos.sh
```

El menu permite ver estado, ejecutar, simular, forzar un partido, marcar descargas,
probar qBittorrent y reinstalar la tarea automatica.

```bash
./run_macos.sh                   # Ejecutar
./run_macos.sh --dry-run         # Simular sin descargar
./run_macos.sh --status          # Ver estado de descargas
./run_macos.sh --forzar 3        # Forzar descarga del partido #3
./run_macos.sh --solo-manuales   # Solo fuentes manuales
./run_macos.sh --marcar-descargado 1 --idioma en --archivo "Titulo visto en qBittorrent"
```

### Windows

```bat
run_windows.bat --dry-run
run_windows.bat --status
run_windows.bat --forzar 3
run_windows.bat --marcar-descargado 1 --idioma en --archivo "Titulo visto en qBittorrent"
```

### Directo con Python

```bash
python descargar_partidos.py --status
python descargar_partidos.py --dry-run
python descargar_partidos.py --forzar 1
python descargar_partidos.py --marcar-descargado 1 --idioma es --archivo "Mexico vs Sudafrica español"
```

`--marcar-descargado` sirve para rectificar el estado cuando ya viste que un partido está
descargado o en cola. Si lo marcás con `--idioma en`, queda como `MEJORABLE`; si lo marcás
con `--idioma es`, queda como `FINAL`.

## Estructura de carpetas

```
~/Desktop/Mundial_Partidos/
├── Fase_de_Grupos/
│   ├── Grupo_A/   (México, Sudáfrica, Corea del Sur, Rep. Checa)
│   ├── Grupo_B/   (Canadá, Bosnia, Qatar, Suiza)
│   ├── ...
│   ├── Grupo_J/   (Argentina ⭐, Argelia, Austria, Jordania)
│   └── Grupo_L/
├── Octavos_de_Final/
├── Cuartos_de_Final/
├── Semifinales/
├── Tercer_Puesto/
└── Final/
```

## Archivos del proyecto

| Archivo | En el repo | Descripción |
|---------|:----------:|-------------|
| `descargar_partidos.py` | ✅ | Script principal, coordinador |
| `buscador_torrents.py` | ✅ | Motor de búsqueda multi-fuente |
| `qbit_manager.py` | ✅ | Integración con qBittorrent (macOS/Windows/Linux) |
| `notificador.py` | ✅ | Notificaciones del sistema |
| `config.py` | ✅ | Configuración centralizada (lee de `.env`) |
| `estado_descargas.py` | ✅ | Estado persistente separado del calendario |
| `idioma_utils.py` | ✅ | Detección y clasificación de idioma |
| `fuentes_manuales.py` | ✅ | Lógica para fuentes declaradas por el usuario |
| `organizador_descargas.py` | ✅ | Mueve torrents completos a la carpeta final |
| `verificador_archivos.py` | ✅ | Verifica archivos locales y metadata con ffprobe |
| `indice_biblioteca.py` | ✅ | Genera índice HTML y playlist M3U |
| `reporte_diario.py` | ✅ | Genera resumen diario de partidos y mejoras |
| `calendario_mundial_2026.json` | ✅ | 104 partidos con fechas UTC |
| `requirements.txt` | ✅ | Dependencias Python |
| `.env.example` | ✅ | Template para configuración local |
| `fuentes_torrent.example.json` | ✅ | Template para indexadores |
| `fuentes_manuales.example.json` | ✅ | Template para fuentes manuales |
| `setup.sh` | ✅ | Setup automático macOS |
| `menu_macos.sh` | ✅ | Menú interactivo para macOS |
| `run_macos.sh` | ✅ | Ejecutor portable macOS |
| `run_windows.bat` | ✅ | Ejecutor portable Windows |
| `install_macos_launchd.sh` | ✅ | Instala tarea launchd |
| `install_windows_task.bat` | ✅ | Instala tarea programada Windows |
| `.env` | ❌ | Rutas y credenciales locales |
| `fuentes_torrent.json` | ❌ | Mirrors reales de indexadores |
| `fuentes_manuales.json` | ❌ | URLs de partidos del usuario |
| `estado_descargas.json` | ❌ | Estado local de descargas |
| `estado_partidos.txt` | ❌ | Resumen legible de estado, idioma y archivo |
| `reporte_diario.txt` | ❌ | Reporte diario generado |
| `mundial.log` | ❌ | Logs de ejecución |

## qBittorrent

La descarga vía qBittorrent intenta primero la Web API (`host:puerto`). Si la Web API
no responde, se usa un fallback que abre el magnet link directamente con la aplicación
asociada del sistema (`open` en macOS, `cmd /c start` en Windows, `xdg-open` en Linux).

Para usar la Web API:

1. Abrir qBittorrent.
2. Ir a Preferencias > Web UI > Habilitar la interfaz de usuario web.
3. Configurar:
   - IP address: `127.0.0.1`
   - Port: `8080`
   - Username: `admin`
   - Password: `adminadmin`
4. Dejar desactivado HTTPS para uso local.
5. Tocar Apply/OK y reiniciar qBittorrent si el puerto no responde.
6. Verificar que `.env` tenga los mismos valores.

Prueba rápida:

```bash
curl -I http://127.0.0.1:8080
```

Si responde `401`, `403` o `200`, la Web UI está levantada. Si responde `000` o
connection refused, qBittorrent no está escuchando en ese puerto o falta aplicar la
configuración.

## Repos útiles

- [debatepro/world-cup-2026-calendar](https://github.com/debatepro/world-cup-2026-calendar) — JSON/CSV/ICS con `kickoff_utc`, estadio, ciudad. CC0/MIT.
- [openfootball/worldcup.json](https://github.com/openfootball/worldcup.json) — Fixtures, equipos, grupos, resultados. CC0.
- [mjwebmaster/world-cup-2026-schedule-data](https://github.com/mjwebmaster/world-cup-2026-schedule-data) — JSON/CSV/ICS alternativo.
