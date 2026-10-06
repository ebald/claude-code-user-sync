# Aplicación de escritorio Claude Code User Sync

[English](README.md) · Español · [Português](README.pt-BR.md)

Una interfaz Electron compartida para macOS, Windows y Linux, con el motor Python de sincronización existente. El [README principal](../docs/README.es.md) explica el alcance de la sincronización y la herramienta de terminal.

## Ejecutar desde el código fuente

Usa macOS 13 o posterior, Windows 10/11 o Ubuntu 22.04+/Debian 12+ con la [beta oficial de Claude Desktop para Linux](https://code.claude.com/docs/en/desktop-linux). Linux admite x64 y arm64. Ejecuta la aplicación en Windows nativo, fuera de WSL. Las aplicaciones empaquetadas ya incluyen Electron y Python; la preparación siguiente sirve para una copia descargada o clonada del código fuente.

### Preparación automática

Desde la raíz del proyecto, ejecuta `bash ./setup.sh` en macOS o Linux, o `.\setup.bat` en PowerShell de Windows x64 nativo. En macOS también puedes abrir `setup.command` con doble clic; en Windows, abre `setup.bat` con doble clic.

Los scripts comprueban las herramientas instaladas, instalan los requisitos que falten, ejecutan `npm ci --include=dev` y abren la aplicación Electron. La instalación requiere conexión a internet. Abrir la aplicación no sincroniza datos de Claude. Se reutilizan las instalaciones existentes y compatibles de Node.js, npm y Python.

En Linux, cuando AppArmor restringe el inicio de Electron desde el código fuente, la preparación predeterminada compila e instala el paquete `.deb` y abre la aplicación instalada como tu usuario normal. La instalación puede solicitar tu contraseña de administrador. Después, ábrela directamente desde el menú de aplicaciones. Esto cubre las restricciones de Ubuntu 24.04 y posteriores. `--no-launch` prepara las dependencias del código fuente sin compilar ni instalar el paquete de la aplicación; `--check` informa del modo de inicio necesario sin cambiar nada.

```sh
# macOS / Linux: comprobar requisitos sin cambios
bash ./setup.sh --check
# Preparar sin abrir la aplicación
bash ./setup.sh --no-launch
```

```powershell
# Windows
.\setup.bat --check
.\setup.bat --no-launch
```

`--check` termina correctamente si los requisitos están listos, o indica los requisitos que falten y termina con el código de salida 1. Añade `--help` a cualquiera de los lanzadores para consultar sus opciones.

Los mensajes de consola están en inglés; la aplicación sigue la preferencia de idioma del sistema operativo. Para abrir desde el código fuente en otra ocasión, ejecuta de nuevo el script de preparación. Consulta la [guía de preparación automática](../docs/README.es.md#preparación-automática) para los detalles de instalación de cada plataforma.

### Preparación manual para desarrolladores

Si la preparación automática usó un runtime local del proyecto, abre la aplicación mediante el script de preparación en las siguientes ocasiones. Los comandos manuales `npm` requieren Node.js y npm en tu PATH normal.

Instala Node.js 22.12 o posterior, npm y Python 3.10 o posterior. En macOS, tu instalación de Python también debe ser compatible con tu versión de macOS para abrir desde el código fuente. Desde la raíz del proyecto:

```sh
npm ci
npm start
```

En PowerShell de Windows, usa `npm.cmd` en lugar de `npm` en los comandos de esta guía. En macOS y Linux, la aplicación localiza `python3`. En Windows, instala el lanzador de Python y confirma `py -3 --version` en una ventana nueva de PowerShell.

La preparación descarga Electron y las dependencias de compilación. La aplicación carga localmente su interfaz, traducciones y motor de sincronización; la sincronización no llama a modelos ni sube tus chats.

## Sincronizar tus chats

1. Inicializa ambas cuentas en Claude Desktop: inicia sesión en cada una, abre Code, selecciona el entorno Local y crea una conversación local en este equipo.
2. Termina el trabajo activo en Claude antes de sincronizar.
3. Mantén **Idioma del sistema** seleccionado para seguir el sistema operativo, o elige **English**, **Español** o **Português**.
4. Haz clic en **Sincronizar y reabrir Claude**.
5. Cuando Claude se abra de nuevo, cierra sesión e inicia sesión en la cuenta que quieras usar.

La aplicación solicita un cierre normal, espera hasta 30 segundos y comprueba que Claude se haya cerrado antes de escribir los catálogos. En Linux, el cierre automático está disponible para la instalación oficial verificada de Claude Desktop; termina también los terminales activos de Claude Code. Si no se puede solicitar el cierre de forma segura o quedan procesos activos, cierra Claude por completo e inténtalo de nuevo. La aplicación no fuerza el cierre. El cambio de cuenta sigue siendo manual. Las tres plataformas usan la misma interfaz y flujo; el backend de cada plataforma se ocupa de localizar y cerrar Claude.

La cantidad de cuentas procede de las carpetas locales de cuentas, en lugar del número de perfiles de organización. Una cuenta puede tener más de un perfil de organización.

Una sincronización correcta usa el estado de éxito. Los archivos o historiales no disponibles y las diferencias pendientes se indican específicamente y pueden consultarse en los diagnósticos. Los controles de archivos y copias de seguridad abren el resultado guardado en el explorador de archivos del sistema operativo. Si falla la localización automática de Claude, selecciona la aplicación o ejecutable de Claude mediante la interfaz.

La sincronización en Windows y Linux sigue siendo experimental hasta verificar el flujo autenticado de Claude Desktop en equipos reales con esos sistemas.

## Idiomas

**i18next** gestiona las traducciones de la interfaz mediante diccionarios JSON en `desktop/locales/`:

- `en`: inglés.
- `es`: español.
- `pt-BR`: portugués brasileño.

La aplicación empieza con **Idioma del sistema** seleccionado y usa el idioma compatible preferido del sistema operativo. Las variantes regionales de inglés y español usan la traducción correspondiente; todas las variantes de portugués usan portugués brasileño. Si ningún idioma preferido es compatible, la aplicación usa inglés. La elección manual actualiza la interfaz y guarda la preferencia para los siguientes inicios. Selecciona **Idioma del sistema** para volver a seguir el sistema operativo.

Usa las mismas claves y variables de interpolación en todos los diccionarios. Las pruebas JavaScript comprueban la cobertura de las traducciones. Los nombres de archivos, detalles de diagnóstico y rutas permanecen como los registra el backend.

## Almacenamiento

La aplicación guarda el idioma y las rutas seleccionadas en `settings.json`, dentro de su carpeta de datos del usuario. El motor de sincronización de cada plataforma conserva las ubicaciones existentes de copias de seguridad e historiales por compatibilidad:

| Datos | macOS | Windows | Predeterminado en Linux |
| --- | --- | --- | --- |
| Preferencias de la aplicación | `~/Library/Application Support/Claude Code User Sync/settings.json` | `%APPDATA%\Claude Code User Sync\settings.json` | `~/.config/Claude Code User Sync/settings.json` |
| Copias de seguridad de sincronización | `~/Library/Application Support/Claude Account Sync/Backups/` | `%LOCALAPPDATA%\Claude Code User Sync\Backups\` | `~/.local/share/Claude Code User Sync/Backups/` |
| Resultado guardado de sincronización | `~/Library/Application Support/Claude Account Sync/last-sync.json` | `%LOCALAPPDATA%\Claude Code User Sync\last-sync.json` | `~/.local/share/Claude Code User Sync/last-sync.json` |
| Catálogo de Claude, instalación estándar | `~/Library/Application Support/Claude/claude-code-sessions/` | `%APPDATA%\Claude\claude-code-sessions\` | `~/.config/Claude/claude-code-sessions/` |
| Historiales de conversaciones locales | `~/.claude/projects/` | `%USERPROFILE%\.claude\projects\` | `~/.claude/projects/` |

Linux respeta `XDG_CONFIG_HOME` y `XDG_DATA_HOME` cuando se definen como rutas absolutas; la tabla muestra los valores predeterminados. El comando oficial `claude-desktop` resuelve al ejecutable de `/usr/lib/claude-desktop/`.

Las instalaciones MSIX de Windows pueden usar otra carpeta de datos de Claude, que el backend comprueba cuando existe. Si hay ambigüedad entre instalaciones, selecciona la carpeta de datos de Claude y la de historiales en los ajustes. Las [opciones de datos de la herramienta de terminal](../docs/README.es.md#carpetas-de-datos-en-windows) permiten indicar una carpeta explícitamente.

Las copias de seguridad y los diagnósticos pueden contener datos privados de conversaciones, rutas y enlaces. En macOS y Linux usan permisos exclusivos del usuario; en Windows heredan los permisos de acceso de la carpeta que los contiene. Mantenlos dentro de tu perfil de usuario. El nombre antiguo del almacenamiento en macOS es intencionado para mantener disponibles las copias existentes.

## Compilar aplicaciones empaquetadas

Compila en el sistema operativo y la arquitectura de destino. Cada paquete incluye un ejecutable Python compilado para esa plataforma.

```sh
npm run build:backend
```

Esto ejecuta `desktop/scripts/build_backend.py`, crea un entorno virtual aislado en `.sandbox/electron-backend/<platform>-<arch>/venv/`, instala una versión fija de PyInstaller y crea un backend independiente en `desktop/backend-dist/claude-sync-backend/`. Estas carpetas generadas están excluidas de Git.

### macOS

En un Mac:

```sh
npm run build:mac
```

El comando empaqueta el backend y genera un DMG y ZIP en `release/` para la arquitectura del Mac actual. La aplicación incluye Electron y Python, por lo que el Mac de destino no necesita instalar Node.js ni Python aparte. El requisito de macOS es la versión más reciente entre el mínimo de Electron y el mínimo del Python incluido. La compilación registra ese requisito en la aplicación, por lo que un paquete puede necesitar una versión posterior a macOS 13. La compilación local recibe una firma ad hoc y no está notarizada.

### Windows

En Windows x64 con Node.js y Python x64, desde PowerShell:

```powershell
npm.cmd run build:win
```

El comando empaqueta el backend y genera un instalador NSIS en `release/`. La aplicación instalada incluye Electron, Python y traducciones. El equipo de destino no necesita instalar Node.js ni Python aparte. El instalador no está firmado.

### Linux

En Ubuntu 22.04+/Debian 12+ nativo, usa Node.js y Python x64 o arm64 correspondientes a la arquitectura del equipo. Compila en la distribución más antigua que quieras admitir (Ubuntu 22.04 es la referencia); los paquetes compilados en un sistema o Python más reciente pueden necesitar bibliotecas Linux más recientes.

```sh
npm run build:linux
```

En Ubuntu 24.04 y posteriores, AppArmor puede bloquear el inicio de Electron desde el código fuente o el archivo portátil. Si aparece un error de sandbox, instala el paquete `.deb`, que incluye un perfil AppArmor para esta aplicación. Puedes crearlo con `npm run build:linux` sin abrir primero la aplicación desde el código fuente. Consulta las [notas de lanzamiento de Ubuntu](https://documentation.ubuntu.com/release-notes/24.04/).

Instala `python3-venv` si tu distribución no ofrece soporte de entornos virtuales de Python de forma predeterminada. La compilación incluye el backend Python y crea un instalador Debian `.deb` y archivo portátil `.tar.gz` en `release/`. El equipo de destino no necesita instalar Node.js ni Python aparte. Abre el `.deb` con el instalador de software, o extrae el archivo portátil y ejecuta `claude-code-user-sync` como usuario normal. Usa la [guía oficial de Claude Desktop Linux beta](https://code.claude.com/docs/en/desktop-linux) para instalar Claude.

### Aplicación sin instalador

En cualquier plataforma de destino:

```sh
npm run pack
```

Esto compila el backend incluido y genera una carpeta de aplicación sin instalador en `release/` para validación local. Compilar no instala la aplicación ni sincroniza datos de Claude.

## Pruebas y vista previa

Desde la raíz del proyecto:

```sh
npm test
python3 -m unittest discover
npm run preview
```

En Windows, usa `py -3 -m unittest discover` para la suite Python y `npm.cmd` para los comandos npm.

La vista previa usa resultados de sincronización de ejemplo. La cantidad de cuentas se lee de las carpetas locales; las demás cifras se identifican claramente como datos de ejemplo. No cierra Claude, escribe catálogos, crea copias de seguridad de sincronización ni guarda preferencias.

```sh
npm run smoke
# Después de npm run pack:
npm run smoke:packaged
```

Estas comprobaciones abren la aplicación Electron desde el código fuente o empaquetada en modo de vista previa, ejercitan los tres idiomas y el flujo de sincronización simulado, y comprueban el estado de éxito.

GitHub Actions está configurado para ejecutar pruebas Python con datos sintéticos en macOS, Windows y Linux, ejecutar las pruebas de Electron, compilar un backend independiente y generar una aplicación sin instalador en cada sistema operativo. Las pruebas automatizadas y de vista previa no demuestran que funcionen todos los flujos autenticados de Claude Desktop.

## Arquitectura

- El proceso principal de Electron controla la ventana, las preferencias y las acciones de escritorio aprobadas.
- Un puente limitado de preload expone operaciones específicas a la interfaz.
- El renderer compartido usa HTML, CSS, JavaScript y diccionarios i18next locales.
- El backend Python se ocupa del descubrimiento de cuentas, validación de catálogos, cierre normal de Claude, copias de seguridad, sincronización y reapertura de Claude.
- Los paquetes ejecutan el backend incluido; la ejecución desde el código fuente usa un intérprete Python instalado.

La interfaz funciona con aislamiento de contexto y sandbox activados, e integración Node desactivada. Carga recursos locales con una política restrictiva de seguridad de contenido y valida las solicitudes IPC. El motor Python trata el contenido de las conversaciones; la interfaz muestra resúmenes de operaciones y diagnósticos.
