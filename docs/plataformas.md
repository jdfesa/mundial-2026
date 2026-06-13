# Plataformas

Este proyecto se desarrollo y se probo principalmente en macOS. El nucleo Python esta
pensado para ser portable, pero los instaladores automaticos no tienen el mismo nivel de
soporte en todos los sistemas.

Como es un proyecto personal atado al Mundial 2026, la prioridad es que el flujo probado
funcione bien durante el torneo. No hay intencion de mantener una capa completa de
instaladores por sistema operativo. Groq es opcional y la API key local puede expirar; si
no esta configurado, el script sigue usando las reglas deterministicas.

## macOS

Estado: probado en esta maquina.

Funciona con:

- `./run.sh` para ejecutar el script principal.
- `./menu.sh` como menu interactivo.
- `setup.sh` para setup automatico con `launchd`.
- `install_macos_launchd.sh` para instalar o actualizar la tarea cada 30 minutos.
- qBittorrent Web UI en `127.0.0.1:8080`.

Puntos a revisar:

- `.env` con rutas y credenciales locales.
- Web UI de qBittorrent habilitada.
- `ffmpeg`/`ffprobe` disponibles si se quiere validar metadata de video.
- LaunchAgent reinstalado si cambia la ruta del repo.

## Linux

Estado: no probado end-to-end en este repo, pero el nucleo deberia correr manualmente.

Deberia funcionar:

- `python descargar_partidos.py --status`
- `./run.sh --status`
- `./menu.sh` para acciones manuales.
- qBittorrent por Web API.
- Apertura de magnet links con `xdg-open`, si el sistema lo tiene configurado.

No esta incluido:

- Instalador `systemd`.
- Instalador `cron`.
- Setup automatico equivalente a `setup.sh`.
- Notificaciones nativas.

Checklist para usarlo en Linux:

1. Crear `venv` e instalar `requirements.txt`.
2. Copiar `.env.example` a `.env`.
3. Configurar `MUNDIAL_DIRECTORIO_BASE` con una ruta valida de Linux.
4. Habilitar qBittorrent Web UI y revisar `QBIT_HOST`, `QBIT_PORT`, `QBIT_USER`, `QBIT_PASS`.
5. Instalar `ffmpeg`/`ffprobe` si se van a validar archivos.
6. Configurar `xdg-open` para magnet links si se quiere usar fallback sin Web API.
7. Crear manualmente un cron o `systemd timer` que ejecute `./run.sh`.

Ejemplo orientativo con cron:

```cron
*/30 * * * * cd /ruta/al/repo && ./run.sh >> run_stdout.log 2>> run_stderr.log
```

## Windows

Estado: hay wrappers `.bat`, pero el flujo principal se viene probando desde macOS.

Incluido:

- `run_windows.bat`
- `install_windows_task.bat`

Checklist para usarlo en Windows:

1. Crear entorno virtual o tener Python disponible en `PATH`.
2. Instalar `requirements.txt`.
3. Copiar `.env.example` a `.env`.
4. Usar rutas compatibles con Windows en `MUNDIAL_DIRECTORIO_BASE`.
5. Habilitar qBittorrent Web UI y revisar credenciales.
6. Instalar `ffmpeg`/`ffprobe` si se quiere validar metadata.
7. Probar `run_windows.bat --status` antes de instalar la tarea programada.
8. Revisar permisos del Task Scheduler si la tarea no ve las mismas rutas que el usuario.

## Regla Practica

- Para uso probado hoy: macOS.
- Para Linux: usar `run.sh`/`menu.sh` manualmente y agregar cron/systemd si hace falta.
- Para Windows: usar los `.bat` y revisar rutas/Task Scheduler.
- Para cualquier sistema: qBittorrent Web UI es el punto de integracion mas importante.
