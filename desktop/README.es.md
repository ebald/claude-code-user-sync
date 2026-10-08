# Aplicación de escritorio Claude Code User Sync

[English](README.md) · Español · [Português](README.pt-BR.md)

Una interfaz Electron compartida para macOS, Windows y Linux, con el motor Python de sincronización existente. El [README principal](../docs/README.es.md) explica el alcance de la sincronización y la herramienta de terminal.

## Ejecutar desde el código fuente

Usa macOS 13 o posterior, Windows 10/11 x64, Windows 11 ARM64 o Ubuntu 22.04+/Debian 12+ con la [beta oficial de Claude Desktop para Linux](https://code.claude.com/docs/en/desktop-linux). Linux admite x64 y arm64. Ejecuta la aplicación en Windows, fuera de WSL. En Windows 11 ARM64, Node.js, Python y Electron x64 funcionan mediante la [emulación x64](https://learn.microsoft.com/en-us/windows/arm/apps-on-arm-x86-emulation) del sistema. Windows 10 ARM64 no es compatible. El instalador empaquetado sigue siendo x64; no se ofrece una compilación nativa para Windows ARM64. Las aplicaciones empaquetadas ya incluyen Electron y Python; la preparación siguiente sirve para una copia descargada o clonada del código fuente.

La pestaña Code de Claude Desktop requiere una [suscripción Pro, Max, Team o Enterprise](https://code.claude.com/docs/en/desktop-quickstart).

En Windows, si Claude solicita Git antes de una conversación Local, instala [Git para Windows](https://git-scm.com/downloads/win), luego cierra y vuelve a abrir Claude, o actualiza Claude si no usas worktrees; consulta la [solución de problemas de Git en Claude](https://code.claude.com/docs/en/desktop#git-and-git-lfs-errors). La preparación no instala Claude Desktop ni Git, y el sincronizador no necesita Git si se descarga como ZIP.

### Preparación automática

Desde la raíz del proyecto, ejecuta `bash ./setup.sh` en macOS o Linux, o `.\setup.bat` en PowerShell de Windows 10/11 x64 o Windows 11 ARM64. En macOS también puedes abrir `setup.command` con doble clic; en Windows, abre `setup.bat` con doble clic.

En macOS, `setup.sh` prepara y abre la aplicación desde el código fuente; no instala un `.app` en Aplicaciones. Instala el `.app` empaquetado por separado siguiendo las instrucciones del DMG más abajo.

Los scripts comprueban las herramientas instaladas, instalan los requisitos que falten, ejecutan `npm ci --include=dev` y abren la aplicación Electron. La instalación requiere conexión a internet. El primer inicio puede terminar de descargar el runtime de Electron; mantén la conexión hasta que se abra la aplicación. Abrir la aplicación no sincroniza datos de Claude. Se reutilizan las instalaciones existentes y compatibles de Node.js, npm y Python. La preparación de Windows selecciona herramientas x64 en ambas arquitecturas compatibles; la preparación desde el código fuente, el inicio normal y la vista previa Electron se han verificado en una VM Windows 11 ARM64.

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

Instala Node.js 22.12 o posterior, npm y Python 3.10 o posterior. En macOS, tu instalación de Python también debe ser compatible con tu versión de macOS para abrir desde el código fuente. En Windows, instala las versiones x64 de Node.js y Python, también en Windows 11 ARM64. Desde la raíz del proyecto:

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

En Windows, Claude puede seguir ejecutándose en la bandeja del sistema después de cerrar su ventana. La aplicación solicita una salida normal de Claude para que su proceso de la bandeja también termine. Si el cierre automático no termina, completa las tareas activas, elige **Salir** (**Quit/Exit**) en el menú de Claude o de su icono en la bandeja y vuelve a intentar la sincronización.

La cantidad de cuentas procede de las carpetas locales de cuentas, en lugar del número de perfiles de organización. Una cuenta puede tener más de un perfil de organización.

Una sincronización correcta usa el estado de éxito. Los archivos o historiales no disponibles y las diferencias pendientes se indican específicamente y pueden consultarse en los diagnósticos. Los controles de archivos y copias de seguridad abren el resultado guardado en el explorador de archivos del sistema operativo. Si falla la localización automática de Claude, selecciona la aplicación o ejecutable de Claude mediante la interfaz.

La sincronización autenticada desde el código fuente se verificó en una VM Windows 11 ARM64 mediante emulación x64 y en una VM Debian 13.7 ARM64 con LXDE. La preparación desde el código fuente, la selección de idioma, una sincronización repetida sin escrituras del catálogo y las compilaciones nativas ARM64 también se verificaron en la VM Debian. Las pruebas autenticadas en un equipo Windows x64 nativo o en otras distribuciones o versiones de Linux, el instalador Windows empaquetado, la instalación nativa empaquetada en Linux y la preparación mediante AppArmor en Ubuntu siguen sin verificar.

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

Para instalar la aplicación empaquetada del Mac, abre el DMG y copia **Claude Code User Sync.app** a **Aplicaciones**; después ábrela desde allí. El paquete incluye sus runtimes y no necesita `setup.sh`.

### Windows

En Windows x64 con Node.js y Python x64, desde PowerShell. Esto crea un paquete x64; aún no se ha verificado la compilación en un equipo ARM64:

```powershell
npm.cmd run build:win
```

El comando empaqueta el backend y genera un instalador NSIS en `release/`. La aplicación instalada incluye Electron, Python y traducciones. El equipo de destino no necesita instalar Node.js ni Python aparte. El instalador no está firmado.

### Linux

En Ubuntu 22.04+/Debian 12+ nativo, usa Node.js y Python x64 o arm64 correspondientes a la arquitectura del equipo. Compila en la distribución más antigua que quieras admitir (Ubuntu 22.04 es la referencia); los paquetes compilados en un sistema o Python más reciente pueden necesitar bibliotecas Linux más recientes.

Para empaquetar en Linux se necesitan `python3-venv` y `binutils` (que incluye `objdump`); la preparación automática instala ambos.

```sh
sudo apt install python3-venv binutils
npm run build:linux
```

En Ubuntu 24.04 y posteriores, AppArmor puede bloquear el inicio de Electron desde el código fuente o el archivo portátil. Si aparece un error de sandbox, instala el paquete `.deb`, que incluye un perfil AppArmor para esta aplicación. Puedes crearlo con `npm run build:linux` sin abrir primero la aplicación desde el código fuente. Consulta las [notas de lanzamiento de Ubuntu](https://documentation.ubuntu.com/release-notes/24.04/).

La compilación incluye el backend Python y crea un instalador Debian `.deb` y archivo portátil `.tar.gz` en `release/`. El equipo de destino no necesita instalar Node.js ni Python aparte. Abre el `.deb` con el instalador de software, o extrae el archivo portátil y ejecuta `claude-code-user-sync` como usuario normal. Usa la [guía oficial de Claude Desktop Linux beta](https://code.claude.com/docs/en/desktop-linux) para instalar Claude.

Desde la carpeta del proyecto, también puedes instalar el `.deb` en un terminal si no hay un instalador de software:

```sh
sudo apt install './release/claude-code-user-sync_1.3.0_arm64.deb'
```

Este nombre de archivo es un ejemplo para la versión 1.3.0 en ARM64. Sustitúyelo por el nombre real del `.deb` para tu versión y arquitectura; después abre **Claude Code User Sync** desde el menú de aplicaciones.

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

En un Mac con Apple silicon, la compilación local Electron 1.3.0 ARM64 se instaló desde su DMG en Aplicaciones. Las comprobaciones de la aplicación instalada pasaron para inglés, español, portugués y la selección automática del idioma del sistema. Una sincronización real iniciada por el usuario terminó, creó su copia de seguridad y reabrió Claude. Esto verifica ese flujo local; otras versiones de Claude Desktop pueden cambiar el formato interno de sus catálogos.

El inicio predeterminado de `setup.sh` pasó usando las herramientas existentes en un ZIP descargado del repositorio público de GitHub sin credenciales; la aplicación real abrió en el idioma del sistema sin iniciar una sincronización. En una copia nueva del código fuente cuya carpeta tenía espacios en el nombre y con Node.js no disponible para la preparación, el script descargó y verificó Node.js 22.23.3 oficial, reutilizó Python instalado y abrió la aplicación. La descarga, el SHA-256 y la firma del instalador del paquete oficial de Python se verificaron por separado; aún no se ha probado la instalación con permisos de administrador en un Mac sin Python.

En una máquina virtual Windows 11 ARM64, `setup.bat --check` informó correctamente de los requisitos ausentes, `--no-launch` instaló Node.js y Python x64 desde descargas oficiales verificadas y las dependencias npm como usuario normal, y la comprobación final `--check` pasó. Las comprobaciones automatizadas de JavaScript y Python terminaron sin fallos. Una comprobación de la vista previa desde el código fuente pasó y terminó normalmente tras verificar inglés, español y portugués, la selección automática de inglés del sistema, la cantidad real de cuentas locales, el estado de éxito traducido y el aislamiento del renderer.

La ejecución predeterminada de `.\setup.bat` también reutilizó las herramientas, instaló las dependencias fijadas y abrió la aplicación real. Detectó perfiles locales inicializados, inició en el idioma del sistema (inglés) y cambió a portugués y de nuevo a **Idioma del sistema** (inglés). Cerrar su ventana normalmente terminó con código de salida 0. Esas comprobaciones de instalación e idioma no iniciaron una sincronización.

Una comprobación independiente en Windows 11 ARM64 usó un ZIP descargado directamente del repositorio público sin credenciales, extraído en una carpeta con espacios. `setup.bat --check` informó de Node.js/npm ausentes y Python 3.14.8 x64 disponible; la ejecución predeterminada de `setup.bat` descargó y verificó Node.js 22.23.3 x64, instaló las dependencias npm fijadas y abrió la aplicación real en el idioma del sistema (inglés). La comprobación final `--check` pasó, al igual que la prueba de vista previa desde el código fuente para los tres idiomas, la selección automática del idioma del sistema, el estado de éxito traducido y el aislamiento del renderer. No se inició una sincronización durante esa comprobación de instalación; no se registró el código de salida de la preparación predeterminada.

En la misma VM Windows 11 ARM64, la aplicación desde el código fuente sincronizó una conversación local de prueba en Code entre dos cuentas inicializadas con sesión iniciada en Claude Desktop oficial MSIX 2.26454.0.0. Cerró Claude normalmente y lo reabrió de forma automática. Después, ambos catálogos de perfiles contenían la conversación; la instantánea de la copia de seguridad y el catálogo escrito pasaron las comprobaciones de hashes, no faltaban historiales y un plan posterior no tenía cambios pendientes. Repetir la sincronización no escribió archivos del catálogo ni creó duplicados. El instalador Windows empaquetado y la compilación en un equipo ARM64 siguen sin verificar.

En una VM Debian 13.7 ARM64 recién instalada con LXDE, se descargó un ZIP público de GitHub del commit `641bac4` sin credenciales y se extrajo en una carpeta con espacios. `bash ./setup.sh --check` informó de Node.js/npm, soporte de entornos virtuales de Python y curl ausentes sin modificar el código fuente. La ejecución predeterminada de `bash ./setup.sh` instaló los requisitos, descargó y verificó Node.js 22.23.3 ARM64 oficial y abrió la aplicación desde el código fuente con Python 3.13.5 y Electron 44.5.1. El cierre normal de la aplicación y la comprobación final de requisitos terminaron con código de salida 0. La interfaz real seleccionó inglés a partir de la configuración regional `en_US` del sistema y cambió a portugués y español. La elección manual del español se mantuvo tras reiniciar la VM.

Se descargó un segundo ZIP público del commit `697bd1a` sin credenciales. La preparación predeterminada actualizada instaló `binutils`, verificó Node.js 22.23.3 ARM64 oficial y abrió la aplicación desde el código fuente como usuario habitual del escritorio. El cierre normal de la aplicación y la comprobación final de requisitos terminaron con código de salida 0.

Las comprobaciones JavaScript en Linux tuvieron 57 pruebas aprobadas y una omisión prevista; la suite Python actualizada ejecutó 204 pruebas con seis omisiones previstas y ningún fallo. La comprobación de la vista previa desde el código fuente pasó para los tres idiomas y la selección automática del idioma del sistema.

En la misma VM Debian, la aplicación desde el código fuente sincronizó una conversación local nativa de Code entre dos cuentas inicializadas con sesión iniciada en Claude Desktop oficial 2.26454.2 ARM64. Iniciar la sincronización desde la aplicación mientras Claude estaba abierto cerró Claude normalmente y lo reabrió de forma automática conservando la sesión iniciada. Después, ambos catálogos de perfiles contenían la única conversación; la instantánea de la copia de seguridad y el catálogo escrito pasaron las comprobaciones de hashes, no faltaban historiales, no había conflictos y un plan posterior no tenía cambios pendientes. La comprobación no encontró cambios inesperados en los historiales o archivos de las conversaciones nativas ni escrituras fuera del alcance permitido de la sincronización.

Una sincronización real repetida con el código fuente público corregido, mientras Claude estaba abierto, también cerró Claude normalmente y lo reabrió conservando la sesión iniciada. No escribió archivos del catálogo, las instantáneas de las copias de seguridad de ambos perfiles pasaron las comprobaciones de hashes y no se encontraron conversaciones duplicadas, historiales ausentes, conflictos, cambios pendientes ni cambios inesperados en archivos nativos.

Una compilación nativa ARM64 generó correctamente el instalador Debian y el archivo portátil de la versión 1.3.0. La instalación nativa empaquetada, la sincronización autenticada en otras distribuciones o versiones de Linux y la preparación mediante AppArmor en Ubuntu siguen sin verificar.

Los nueve [jobs de GitHub Actions](https://github.com/ebald/claude-code-user-sync/actions/runs/37709530312) del repositorio público pasaron para el commit `697bd1a`: pruebas de Python 3.10/3.14, del flujo de Electron y las traducciones, del backend incluido y de inicio de la aplicación empaquetada en macOS, Windows y Linux. También pasaron las compilaciones del instalador y el archivo portátil de Linux. Las pruebas automatizadas y de vista previa no demuestran que funcionen todos los flujos autenticados de Claude Desktop.

## Arquitectura

- El proceso principal de Electron controla la ventana, las preferencias y las acciones de escritorio aprobadas.
- Un puente limitado de preload expone operaciones específicas a la interfaz.
- El renderer compartido usa HTML, CSS, JavaScript y diccionarios i18next locales.
- El backend Python se ocupa del descubrimiento de cuentas, validación de catálogos, cierre normal de Claude, copias de seguridad, sincronización y reapertura de Claude.
- Los paquetes ejecutan el backend incluido; la ejecución desde el código fuente usa un intérprete Python instalado.

La interfaz funciona con aislamiento de contexto y sandbox activados, e integración Node desactivada. Carga recursos locales con una política restrictiva de seguridad de contenido y valida las solicitudes IPC. El motor Python trata el contenido de las conversaciones; la interfaz muestra resúmenes de operaciones y diagnósticos.
