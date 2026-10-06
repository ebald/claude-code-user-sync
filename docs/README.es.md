# Claude Code User Sync

**Mantén tus chats locales de Claude Code disponibles al cambiar de cuenta en el mismo equipo.**

[English](../README.md) · Español · [Português](README.pt-BR.md)

Claude Code User Sync sincroniza los catálogos de conversaciones de la **pestaña Code de Claude Desktop** entre las cuentas detectadas en el equipo. Incluye una aplicación Electron compartida por macOS, Windows y Linux y una herramienta Python, con copias de seguridad automáticas y una opción para deshacer cambios. La aplicación ofrece inglés, español y portugués.

Si creaste una conversación local en la cuenta A, la sincronización permite que su registro aparezca también en la cuenta B. El historial permanece en el almacenamiento local compartido; la herramienta actualiza los registros que usa la lista de chats de cada cuenta.

La herramienta no transfiere chats entre cuentas en la nube ni entre equipos, y no sincroniza las conversaciones habituales del sitio claude.ai. Es un proyecto independiente, sin vinculación con Anthropic.

## Funciones

- Detecta automáticamente las cuentas locales, incluso más de dos.
- Sincroniza chats de todos los proyectos y conserva títulos, identificadores, referencias del historial, favoritos y estado de archivo.
- Usa la última actividad para resolver diferencias; las versiones distintas con la misma fecha permanecen pendientes.
- Respeta las eliminaciones y excluye las automatizaciones y las sesiones SSH, WSL y remotas.
- Conserva referencias de artifacts, comprueba imágenes integradas y copia los archivos locales vinculados que estén disponibles.
- Recupera copias conservadas cuando desaparece el archivo temporal original.
- Crea una copia de seguridad antes de escribir y permite deshacer sin sobrescribir cambios posteriores.
- Ejecuta la sincronización localmente, sin llamadas al modelo ni solicitudes de red.

## Requisitos

- macOS 13 o posterior, Windows 10/11 o Ubuntu 22.04+/Debian 12+, con Claude Desktop y conversaciones locales en la pestaña Code. Consulta la [guía oficial de la beta Linux](https://code.claude.com/docs/en/desktop-linux); admite x64 y arm64.
- Al menos dos perfiles de cuenta inicializados localmente. Inicia sesión en cada cuenta, abre Code, selecciona el entorno Local y crea una conversación en ese equipo.
- Para ejecutar desde el código fuente: **Node.js 22.12 o posterior**, npm y **Python 3.10 o posterior**. El motor Python solo usa la biblioteca estándar. En macOS, usa una instalación de Python compatible con tu versión de macOS.
- Las compilaciones empaquetadas incluyen Electron y Python. El equipo de destino no necesita instalar Node.js ni Python aparte. Una compilación para macOS puede necesitar una versión posterior a macOS 13, según el Python usado para compilarla.

| Sistema | Aplicación | Verificación |
| --- | --- | --- |
| macOS | Aplicación Electron para la arquitectura del Mac usado para compilar | Pruebas automatizadas y vista previa locales; el flujo autenticado depende del formato interno de Claude Desktop |
| Windows | La misma interfaz Electron e instalador Windows x64 | Experimental; aún no se ha verificado la sincronización autenticada de Claude Desktop en un equipo Windows |
| Linux | La misma interfaz Electron, con instalador Debian y archivo portátil para la arquitectura del equipo de compilación | Experimental; aún no se ha verificado la sincronización autenticada de Claude Desktop en un equipo Linux |

En Windows, usa PowerShell de Windows, fuera de WSL. Compila en el sistema de destino para incluir el ejecutable Python adecuado.

## Obtener el código fuente

Descarga el proyecto mediante **Code → Download ZIP** en GitHub y extrae el archivo. Si ya tienes [Git](https://git-scm.com/downloads), puedes clonarlo:

```sh
git clone https://github.com/ebald/claude-code-user-sync.git
cd claude-code-user-sync
```

Ejecuta los comandos siguientes desde la carpeta descargada o clonada. Instala Claude Desktop por separado e inicializa tus conversaciones locales en Code antes de sincronizar.

## Preparación automática

Las aplicaciones empaquetadas ya incluyen Electron y Python. Los scripts de preparación sirven para ejecutar este proyecto desde su código fuente: comprueban las herramientas existentes, instalan los requisitos que faltan, descargan las dependencias y abren la aplicación. Abrirla **no** inicia una sincronización; tú eliges cuándo sincronizar en la interfaz.

| Sistema | Iniciar la preparación automática |
| --- | --- |
| macOS | Haz doble clic en `setup.command` en Finder, o ejecuta `bash ./setup.sh` en Terminal |
| Windows x64 | Haz doble clic en `setup.bat` en el Explorador de archivos, o ejecuta `.\setup.bat` en PowerShell |
| Ubuntu / Debian | Ejecuta `bash ./setup.sh` en el terminal de tu usuario habitual |

La instalación necesita conexión a Internet. Se reutilizan las versiones compatibles de Node.js, npm y Python que ya estén instaladas. La consola de preparación usa inglés; la aplicación abre en el idioma compatible de tu sistema y ofrece inglés, español y portugués.

Si Node.js falta o es demasiado antiguo, el script de macOS/Linux descarga una distribución oficial verificada en `.sandbox/setup/`, una carpeta excluida de Git, y la usa para esta aplicación. En macOS, Python se instala mediante un paquete oficial firmado cuando hace falta. En Ubuntu/Debian, `apt` instala Python, soporte para entornos virtuales y bibliotecas de Electron que falten. La instalación de paquetes del sistema solicita permisos de administrador cuando los necesita; la aplicación se ejecuta como tu usuario habitual.

En Linux, cuando AppArmor restringe el inicio de Electron desde el código fuente, la preparación predeterminada compila e instala el paquete `.deb` y abre la aplicación instalada. La instalación puede pedir tu contraseña de administrador. Después de instalarla, puedes abrir la aplicación directamente desde el menú de aplicaciones en las siguientes ocasiones. Esto resuelve las restricciones usadas por Ubuntu 24.04 y versiones posteriores; `--check` indica cuándo hace falta esta forma de inicio sin hacer cambios.

En Windows, la preparación usa PowerShell y [WinGet](https://learn.microsoft.com/en-us/windows/package-manager/winget/) cuando está disponible. En caso contrario, verifica las descargas oficiales de Node.js y Python y los instala para este proyecto en `.sandbox/setup/`; el instalador de Python usa una instalación para tu usuario. Windows puede mostrar la solicitud de permisos habitual del instalador. La preparación no cambia la directiva global de ejecución de PowerShell. Las rutas seleccionadas solo se aplican al proceso de preparación y a la aplicación.

Para comprobar los requisitos sin instalar, descargar dependencias ni abrir la aplicación:

```sh
# macOS / Linux
bash ./setup.sh --check
```

```powershell
# Windows
.\setup.bat --check
```

Para instalar los requisitos que falten y preparar las dependencias del código fuente sin abrir la aplicación, sustituye `--check` por `--no-launch`. En Linux, esto también omite la compilación e instalación del paquete de la aplicación. Para iniciar desde el código fuente, vuelve a ejecutar el script cuando quieras abrir la aplicación. La preparación manual y el desarrollo siguen disponibles a continuación.

### Preparación manual para desarrolladores

Si la preparación automática usó un entorno local del proyecto, vuelve a abrir la aplicación con el script de preparación. Los comandos manuales de `npm` siguientes necesitan Node.js y npm en tu PATH habitual.

Instala [Node.js](https://nodejs.org/en/download) 22.12 o posterior y [Python](https://www.python.org/downloads/) 3.10 o posterior, después instala las dependencias del proyecto fijadas por el archivo de bloqueo:

```sh
npm ci
```

En PowerShell de Windows, usa `npm.cmd ci`. La preparación descarga las dependencias de compilación y Electron; la sincronización se ejecuta localmente. Continúa con las instrucciones de tu sistema a continuación.

## macOS

Comprueba los requisitos e inicia Electron:

```sh
node --version
python3 --version
npm start
```

### Usar la aplicación

1. Termina las tareas activas en Claude.
2. La aplicación abre en el idioma compatible preferido del sistema operativo. Mantén **Idioma del sistema** para seguir esa configuración o elige **English**, **Español** o **Português**; se guardará la elección manual.
3. Pulsa el botón de sincronización y reapertura.
4. Espera a que Claude se cierre, se sincronicen los catálogos y se vuelva a abrir.
5. Cierra sesión e inicia sesión en tu otra cuenta dentro de Claude.

La aplicación solicita un cierre normal y espera hasta 30 segundos, sin forzar la salida. El cambio de cuenta sigue siendo manual. Los controles de archivos, diagnóstico y última copia de seguridad permiten revisar el resultado. Un archivo no disponible se informa de forma concreta, sin tratar una sincronización correcta como un error.

Para probar la interfaz con resultados de ejemplo:

```sh
npm run preview
```

La vista previa no sincroniza catálogos reales, no cierra Claude ni guarda preferencias. Lee la cantidad de cuentas de las carpetas locales y marca las demás cifras como datos de ejemplo.

### Compilar para macOS

```sh
npm run build:mac
```

Genera un DMG y un ZIP en `release/` para la arquitectura del Mac actual. La compilación crea un entorno Python aislado y empaqueta el motor con PyInstaller. Registra el requisito de macOS a partir de Electron y del Python incluido, usando la versión mínima más reciente de los dos. La aplicación recibe una firma local ad hoc y no está notarizada. Usa `npm run pack` para generar una aplicación sin instalador.

Consulta la [guía de Electron](../desktop/README.md) para más detalles de compilación, almacenamiento y pruebas.

### Terminal o Finder

Sal completamente de Claude con **Cmd+Q** y termina los procesos activos de Claude Code. Ejecuta:

```sh
python3 claude_sync.py sync --live
```

O abre `sync.command` desde Finder. Después vuelve a abrir Claude e inicia sesión en la cuenta deseada.

## Windows

1. Instala Node.js 22.12 o posterior y Python 3.10 o posterior desde sus sitios oficiales, incluido el lanzador de Python. Abre una ventana nueva de PowerShell después de instalarlos.
2. Abre PowerShell en la carpeta del proyecto y ejecuta `npm.cmd ci` si todavía no lo has hecho.
3. Comprueba los requisitos e inicia la misma aplicación Electron que se usa en macOS:

   ```powershell
   node --version
   py -3 --version
   npm.cmd start
   ```

La aplicación sigue automáticamente el idioma del sistema operativo. Puedes cambiarlo en el selector de idioma. Termina tus tareas en Claude y pulsa el botón de sincronización y reapertura. La aplicación solicita un cierre normal, comprueba que Claude se haya detenido, sincroniza e intenta volver a abrirlo. No fuerza el cierre. El cambio de cuenta sigue siendo manual. Si no detecta Claude automáticamente, puedes seleccionar su ejecutable.

Para probar sin modificar datos de Claude:

```powershell
npm.cmd run preview
```

### Compilar un instalador Windows

Ejecuta en un equipo Windows x64 con Node.js y Python x64:

```powershell
npm.cmd run build:win
```

La compilación crea un entorno Python aislado, empaqueta el motor con PyInstaller y genera un instalador NSIS en `release/`. Incluye Electron, Python, el sincronizador y las traducciones. El equipo de destino no necesita instalar Node.js ni Python aparte. El instalador no está firmado. La compilación no instala la aplicación ni modifica datos de Claude.

Usa `npm.cmd run pack` en Windows para generar una aplicación sin instalador.

### PowerShell o Explorador de archivos

1. Termina las tareas y sal de Claude desde su menú o la bandeja del sistema. Cerrar solo la ventana puede dejar la aplicación en ejecución. Cierra también los terminales activos de Claude Code.
2. Ejecuta:

   ```powershell
   py -3 claude_sync.py sync --live
   ```

3. Vuelve a abrir Claude desde el menú Inicio y cambia de cuenta.

También puedes hacer doble clic en `sync.cmd` en el Explorador de archivos después de salir de Claude. Si `py` no está disponible, pero `python` está en el PATH, sustituye `py -3` por `python`. La sincronización de tus propios datos normalmente no necesita permisos de administrador.

La herramienta busca el catálogo en `%APPDATA%\Claude\claude-code-sessions` y en las carpetas de datos del Claude instalado por MSIX, cuando existan. Los historiales suelen estar en `%USERPROFILE%\.claude\projects`.

Si no se encuentra el catálogo o hay varias instalaciones, indica las rutas correctas. `--app-data` recibe la carpeta que **contiene** `claude-code-sessions`; las opciones globales van antes del comando:

```powershell
py -3 claude_sync.py --app-data "C:\ruta\Claude" --projects-dir "C:\ruta\.claude\projects" sync --live
```

La herramienta no transfiere conversaciones entre equipos ni entre usuarios distintos de Windows.

En Windows, la comprobación de archivos admite archivos normales en unidades locales. Se rechazan recursos de red, junctions, enlaces simbólicos y archivos de nube que sigan siendo reparse points. Guarda los archivos necesarios como archivos locales normales antes de sincronizar.

## Linux

Usa Ubuntu 22.04 o posterior o Debian 12 o posterior, con una sesión gráfica x64 o arm64. Instala Claude Desktop siguiendo la [guía oficial de la beta Linux](https://code.claude.com/docs/en/desktop-linux) e inicializa conversaciones locales en Code para cada cuenta. Ejecuta la aplicación como tu usuario habitual.

Instala Node.js 22.12 o posterior, npm y Python 3.10 o posterior. Para compilar en Ubuntu o Debian, instala también `python3-venv`. Desde la carpeta del proyecto:

```sh
node --version
python3 --version
npm ci
npm start
```

En Ubuntu 24.04 o posterior, AppArmor puede impedir que Electron se abra desde el código fuente o el archivo portátil. Si el inicio falla con un error de sandbox, instala el paquete `.deb`, que incluye un perfil AppArmor para esta aplicación. Puedes crearlo con `npm run build:linux` sin abrir primero la aplicación desde el código fuente. Consulta las [notas de la versión de Ubuntu](https://documentation.ubuntu.com/release-notes/24.04/).

La aplicación sigue automáticamente el idioma del sistema, con el mismo selector usado en macOS y Windows. Termina tus tareas en Claude y los terminales activos de Claude Code, luego pulsa el botón de sincronización y reapertura. En la instalación oficial para Linux, la aplicación solicita un cierre normal y espera hasta 30 segundos. Si no puede solicitar el cierre con seguridad o Claude Code sigue activo, te pide que cierres Claude por completo y vuelvas a intentarlo. No fuerza el cierre de los procesos. Cuando Claude se abra, cambia de cuenta manualmente.

Para probar la interfaz sin cambiar los datos de Claude:

```sh
npm run preview
```

### Compilar paquetes Linux

Compila en un equipo Linux con Node.js y Python para la arquitectura de ese equipo. Usa la distribución compatible más antigua que quieras admitir (Ubuntu 22.04 es la base); los paquetes compilados en un sistema más reciente o con un Python más reciente pueden necesitar bibliotecas Linux más recientes.

```sh
npm run build:linux
```

La compilación incluye el motor Python y genera un **instalador Debian `.deb`** y un **archivo portátil `.tar.gz`** en `release/`. Abre el `.deb` con el instalador de programas de tu distribución, o extrae el archivo portátil y ejecuta `claude-code-user-sync` como tu usuario habitual. Los paquetes incluyen Electron, Python, sincronizador y traducciones. Usa `npm run pack` para generar la aplicación sin instalador.

### Terminal y carpetas de datos en Linux

Cierra Claude Desktop por completo y termina los terminales activos de Claude Code, después ejecuta:

```sh
python3 claude_sync.py sync --live
```

Abre Claude desde el menú de aplicaciones o ejecuta `claude-desktop`, luego cambia de cuenta. El catálogo estándar está en `${XDG_CONFIG_HOME:-~/.config}/Claude/claude-code-sessions`; los historiales están en `~/.claude/projects`. La aplicación respeta `XDG_CONFIG_HOME` y `XDG_DATA_HOME` cuando se definen como rutas absolutas. Si tus carpetas son distintas, selecciónalas en los ajustes o usa `--app-data` y `--projects-dir` antes del comando en la herramienta de terminal.

La sincronización en Linux es experimental. Las pruebas automatizadas y la vista previa no verifican la sincronización autenticada de Claude Desktop en un equipo Linux.

## Copias de seguridad y restauración

La herramienta de línea de comandos guarda cada operación en `.sandbox/sync-ID/` dentro del proyecto. Para elegir otra ubicación:

```sh
python3 claude_sync.py sync --live --storage-dir /ruta/privada/copias
```

En Windows:

```powershell
py -3 claude_sync.py sync --live --storage-dir "$env:LOCALAPPDATA\Claude Code User Sync\Backups"
```

La aplicación Electron mantiene las copias de macOS en `~/Library/Application Support/Claude Account Sync/Backups/`. Se conserva el nombre interno anterior por compatibilidad. En Windows, las copias están en `%LOCALAPPDATA%\Claude Code User Sync\Backups\`; en Linux, están en `${XDG_DATA_HOME:-~/.local/share}/Claude Code User Sync/Backups/`. Electron guarda sus preferencias en su carpeta estándar de datos; consulta la [guía](../desktop/README.md#storage).

Las copias incluyen el catálogo, los archivos originales necesarios para deshacer y un manifiesto de los archivos vinculados. Las copias de archivos disponibles están en `asset-snapshot/`. En macOS y Linux, los permisos son exclusivos del usuario. En Windows, las copias heredan los permisos de su carpeta; usa una ubicación dentro de tu perfil, sin compartir.

Para deshacer en macOS, cierra Claude y usa la ruta de copia de seguridad indicada por la operación:

```sh
python3 claude_sync.py undo \
  --root "$HOME/Library/Application Support/Claude/claude-code-sessions" \
  --backup .sandbox/sync-OPERATION_ID/backup \
  --live
```

En Windows, para la ubicación estándar:

```powershell
py -3 claude_sync.py undo --root "$env:APPDATA\Claude\claude-code-sessions" --backup ".sandbox\sync-OPERATION_ID\backup" --live
```

En Linux, con Claude cerrado:

```sh
python3 claude_sync.py undo \
  --root "${XDG_CONFIG_HOME:-$HOME/.config}/Claude/claude-code-sessions" \
  --backup .sandbox/sync-OPERATION_ID/backup \
  --live
```

Sustituye `OPERATION_ID` por el identificador real. Para otras ubicaciones, indica la ruta completa de la copia. Las instalaciones MSIX o personalizadas requieren el mismo `--app-data` antes de `undo` y su carpeta de catálogo en `--root`. La restauración rechaza sobrescribir registros modificados después de sincronizar.

## Probar e inspeccionar archivos

Puedes crear una copia privada, generar un plan, aplicarlo y deshacerlo sin cambiar los catálogos reales:

```sh
python3 claude_sync.py sandbox --dest .sandbox/demo
python3 claude_sync.py plan --root .sandbox/demo/registry --projects .sandbox/demo/config/projects --out .sandbox/demo/plan.json
python3 claude_sync.py apply --root .sandbox/demo/registry --plan .sandbox/demo/plan.json --backup .sandbox/demo/backup
python3 claude_sync.py undo --root .sandbox/demo/registry --backup .sandbox/demo/backup
```

En Windows, sustituye `python3` por `py -3`. Usa una carpeta de destino nueva en cada prueba y deja Claude inactivo o cerrado durante la copia.

Por defecto, `plan` no resuelve diferencias ni incluye registros sin historial legible. `--resolve-newest` usa la última actividad y `--all-chats` incluye historiales no disponibles. Las versiones distintas con la misma fecha siguen pendientes. Los cambios posteriores a la vista previa invalidan el plan.

Para inspeccionar referencias de artifacts, imágenes y archivos sin modificar el catálogo:

```sh
python3 claude_sync.py audit --out .sandbox/asset-audit.json
```

En Windows, usa `py -3` en lugar de `python3`. Los enlaces remotos se registran sin descargarlos ni comprobar el acceso. No se recrean archivos ausentes ni se transfieren permisos de los artifacts alojados.

## Desarrollo

```sh
npm test
python3 -m unittest discover
```

En Windows: `py -3 -m unittest discover` para las pruebas Python. Las pruebas usan datos sintéticos. La [guía de la aplicación](../desktop/README.md#tests-and-preview) incluye los comandos de vista previa y empaquetado. El [README en inglés](../README.md#development-and-tests) explica la validación opcional con el SDK de Anthropic.

La interfaz compartida usa **i18next** y diccionarios JSON en `desktop/locales/` para inglés, español y portugués brasileño. Las claves son iguales en macOS, Windows y Linux, y las pruebas comprueban su cobertura. Por defecto, **Idioma del sistema** usa el idioma compatible preferido del sistema operativo. Las variantes regionales de inglés y español usan las traducciones correspondientes; todas las variantes de portugués usan portugués brasileño. Si ninguno de los idiomas preferidos tiene traducción, la aplicación usa inglés. Se guarda la elección manual entre aperturas; selecciona **Idioma del sistema** para volver a la selección automática.

## Privacidad y límites

- Las credenciales, el estado de inicio de sesión y los historiales originales no se transfieren entre cuentas ni se modifican al sincronizar.
- No se trasladan permisos de acceso, configuración de conectores ni estado de procesos.
- Las copias, planes, diagnósticos y respaldos pueden contener conversaciones, rutas y enlaces privados. Las ubicaciones estándar de datos generados están excluidas de Git; mantén privada esta información.
- La herramienta depende del formato interno de Claude Desktop. Las actualizaciones pueden cambiar la compatibilidad; las pruebas sintéticas no garantizan todos los flujos autenticados.
- Solo se dispone de datos locales existentes. No se pueden reconstruir historiales ni archivos ausentes.

Al informar de un problema, incluye el comando, el sistema operativo, la versión de Claude Desktop y un error sin datos personales. No envíes conversaciones reales, carpetas de respaldo ni manifiestos de diagnóstico sin eliminar la información privada.
