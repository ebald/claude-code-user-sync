# Aplicativo desktop Claude Code User Sync

[English](README.md) · [Español](README.es.md) · Português

Uma interface Electron compartilhada para macOS, Windows e Linux, com o motor Python de sincronização existente. O [README principal](../docs/README.pt-BR.md) explica o alcance da sincronização e a ferramenta de terminal.

## Executar pelo código-fonte

Use macOS 13 ou mais recente, Windows 10/11 ou Ubuntu 22.04+/Debian 12+ com o [Claude Desktop Linux beta oficial](https://code.claude.com/docs/en/desktop-linux). O Linux oferece x64 e arm64. Execute no Windows nativo, fora do WSL. Os aplicativos empacotados já incluem Electron e Python; a preparação abaixo serve para uma cópia baixada ou clonada do código-fonte.

### Preparação automática

Na raiz do projeto, execute `bash ./setup.sh` no macOS ou Linux, ou `.\setup.bat` no PowerShell do Windows x64 nativo. No macOS, também é possível abrir `setup.command` com dois cliques; no Windows, abra `setup.bat` com dois cliques.

Os scripts verificam as ferramentas instaladas, instalam os requisitos ausentes, executam `npm ci --include=dev` e abrem o aplicativo Electron. A instalação exige conexão à internet. Abrir o aplicativo não sincroniza dados do Claude. Instalações existentes e compatíveis de Node.js, npm e Python são reutilizadas.

No Linux, quando o AppArmor restringe a abertura do Electron pelo código-fonte, a preparação padrão compila e instala o pacote `.deb` e abre o aplicativo instalado como seu usuário normal. A instalação pode solicitar sua senha de administrador. Depois, abra diretamente pelo menu de aplicativos. Isso atende às restrições do Ubuntu 24.04 e mais recente. `--no-launch` prepara as dependências do código-fonte sem compilar ou instalar o pacote do aplicativo; `--check` informa o modo de abertura necessário sem alterar nada.

```sh
# macOS / Linux: verificar requisitos sem alterações
bash ./setup.sh --check
# Preparar sem abrir o aplicativo
bash ./setup.sh --no-launch
```

```powershell
# Windows
.\setup.bat --check
.\setup.bat --no-launch
```

`--check` termina com sucesso se os requisitos estiverem prontos, ou informa os requisitos ausentes e termina com o código de saída 1. Adicione `--help` a qualquer um dos lançadores para consultar suas opções.

As mensagens do console estão em inglês; o aplicativo segue a preferência de idioma do sistema operacional. Para abrir pelo código-fonte em outra ocasião, execute o script de preparação novamente. Consulte o [guia de preparação automática](../docs/README.pt-BR.md#preparação-automática) para os detalhes de instalação de cada plataforma.

### Preparação manual para desenvolvedores

Se a preparação automática usou um runtime local do projeto, abra o aplicativo pelo script de preparação nas próximas vezes. Os comandos manuais `npm` exigem Node.js e npm no PATH normal.

Instale Node.js 22.12 ou mais recente, npm e Python 3.10 ou mais recente. No macOS, seu Python também precisa ser compatível com a versão do macOS para abrir pelo código-fonte. Na raiz do projeto:

```sh
npm ci
npm start
```

No PowerShell do Windows, use `npm.cmd` no lugar de `npm` nos comandos deste guia. No macOS e Linux, o aplicativo localiza `python3`. No Windows, instale o inicializador Python e confirme `py -3 --version` em uma janela nova do PowerShell.

A preparação baixa o Electron e as dependências de compilação. O aplicativo carrega localmente sua interface, traduções e motor de sincronização; a sincronização não chama modelos nem envia seus chats.

## Sincronizar seus chats

1. Inicialize as duas contas no Claude Desktop: entre em cada uma, abra Code, selecione o ambiente Local e crie uma conversa local nesse computador.
2. Termine o trabalho ativo no Claude antes de sincronizar.
3. Mantenha **Idioma do sistema** selecionado para seguir o sistema operacional, ou escolha **English**, **Español** ou **Português**.
4. Clique em **Sincronizar e reabrir Claude**.
5. Depois que o Claude reabrir, saia e entre na conta que deseja usar.

O aplicativo solicita um encerramento normal, aguarda até 30 segundos e confirma que o Claude encerrou antes de gravar os catálogos. No Linux, o encerramento automático está disponível para a instalação oficial verificada do Claude Desktop; termine também os terminais ativos do Claude Code. Se não for possível solicitar o encerramento com segurança ou restarem processos ativos, encerre completamente o Claude e tente novamente. O aplicativo não força o encerramento. A troca de contas continua manual. As três plataformas usam a mesma interface e fluxo; o backend de cada plataforma cuida da localização e do encerramento do Claude.

A quantidade de contas vem das pastas locais de contas, em vez da quantidade de perfis de organização. Uma conta pode ter mais de um perfil de organização.

Uma sincronização bem-sucedida usa o estado de sucesso. Arquivos ou históricos indisponíveis e divergências pendentes são informados especificamente e podem ser consultados nos diagnósticos. Os controles de arquivos e backups abrem o resultado salvo no gerenciador de arquivos do sistema operacional. Se a localização automática do Claude falhar, selecione o aplicativo ou executável do Claude pela interface.

A sincronização no Windows e Linux continua experimental até a verificação do fluxo autenticado do Claude Desktop em computadores reais com esses sistemas.

## Idiomas

O **i18next** gerencia as traduções da interface usando dicionários JSON em `desktop/locales/`:

- `en`: inglês.
- `es`: espanhol.
- `pt-BR`: português brasileiro.

O aplicativo inicia com **Idioma do sistema** selecionado e usa o idioma compatível preferido do sistema operacional. As variantes regionais de inglês e espanhol usam a tradução correspondente; todas as variantes de português usam português brasileiro. Se nenhum idioma preferido for compatível, o aplicativo usa inglês. A escolha manual atualiza a interface e salva a preferência para as próximas aberturas. Selecione **Idioma do sistema** para voltar a seguir o sistema operacional.

Use as mesmas chaves e variáveis de interpolação em todos os dicionários. Os testes JavaScript verificam a cobertura das traduções. Nomes de arquivos, detalhes de diagnóstico e caminhos permanecem como registrados pelo backend.

## Armazenamento

O aplicativo salva o idioma e os caminhos selecionados em `settings.json`, dentro de sua pasta de dados do usuário. O motor de sincronização de cada plataforma preserva os locais existentes de backups e históricos por compatibilidade:

| Dados | macOS | Windows | Padrão Linux |
| --- | --- | --- | --- |
| Preferências do aplicativo | `~/Library/Application Support/Claude Code User Sync/settings.json` | `%APPDATA%\Claude Code User Sync\settings.json` | `~/.config/Claude Code User Sync/settings.json` |
| Backups de sincronização | `~/Library/Application Support/Claude Account Sync/Backups/` | `%LOCALAPPDATA%\Claude Code User Sync\Backups\` | `~/.local/share/Claude Code User Sync/Backups/` |
| Resultado de sincronização salvo | `~/Library/Application Support/Claude Account Sync/last-sync.json` | `%LOCALAPPDATA%\Claude Code User Sync\last-sync.json` | `~/.local/share/Claude Code User Sync/last-sync.json` |
| Catálogo do Claude, instalação padrão | `~/Library/Application Support/Claude/claude-code-sessions/` | `%APPDATA%\Claude\claude-code-sessions\` | `~/.config/Claude/claude-code-sessions/` |
| Históricos de conversas locais | `~/.claude/projects/` | `%USERPROFILE%\.claude\projects\` | `~/.claude/projects/` |

O Linux respeita `XDG_CONFIG_HOME` e `XDG_DATA_HOME` quando definidos como caminhos absolutos; a tabela mostra os padrões. O comando oficial `claude-desktop` resolve para o executável em `/usr/lib/claude-desktop/`.

Instalações MSIX do Windows podem usar outra pasta de dados do Claude, que o backend verifica quando existe. Se houver ambiguidade entre instalações, selecione a pasta de dados do Claude e a pasta de históricos nas configurações. As [opções de dados da ferramenta de terminal](../docs/README.pt-BR.md#pastas-de-dados-no-windows) permitem indicar uma pasta explicitamente.

Backups e diagnósticos podem conter dados privados de conversas, caminhos e links. No macOS e Linux, usam permissões exclusivas do usuário; no Windows, herdam as permissões de acesso da pasta que os contém. Mantenha-os dentro do seu perfil de usuário. O nome antigo do armazenamento no macOS é intencional, para manter os backups existentes disponíveis.

## Compilar aplicativos empacotados

Compile no sistema operacional e na arquitetura de destino. Cada pacote inclui um executável Python compilado para aquela plataforma.

```sh
npm run build:backend
```

Isso executa `desktop/scripts/build_backend.py`, cria um ambiente virtual isolado em `.sandbox/electron-backend/<platform>-<arch>/venv/`, instala uma versão fixa do PyInstaller e cria um backend independente em `desktop/backend-dist/claude-sync-backend/`. Essas pastas geradas estão excluídas do Git.

### macOS

Em um Mac:

```sh
npm run build:mac
```

O comando empacota o backend e gera um DMG e ZIP em `release/` para a arquitetura do Mac atual. O aplicativo inclui Electron e Python, portanto o Mac de destino não precisa instalar Node.js ou Python separadamente. O requisito de macOS é a versão mais recente entre o mínimo do Electron e o mínimo do Python incluído. A compilação registra esse requisito no aplicativo, então um pacote pode exigir uma versão posterior ao macOS 13. A compilação local recebe uma assinatura ad hoc e não é notarizada.

### Windows

No Windows x64, com Node.js e Python x64, pelo PowerShell:

```powershell
npm.cmd run build:win
```

O comando empacota o backend e gera um instalador NSIS em `release/`. O aplicativo instalado inclui Electron, Python e traduções. O computador de destino não precisa instalar Node.js ou Python separadamente. O instalador não é assinado.

### Linux

No Ubuntu 22.04+/Debian 12+ nativo, use Node.js e Python x64 ou arm64 correspondentes à arquitetura do computador. Compile na distribuição mais antiga que pretende atender (Ubuntu 22.04 é a referência); pacotes compilados em um sistema ou Python mais recente podem exigir bibliotecas Linux mais recentes.

```sh
npm run build:linux
```

No Ubuntu 24.04 e mais recente, o AppArmor pode bloquear a abertura do Electron pelo código-fonte ou arquivo portátil. Se ocorrer um erro de sandbox, instale o pacote `.deb`, que inclui um perfil AppArmor para este aplicativo. É possível criá-lo com `npm run build:linux` sem abrir o aplicativo pelo código-fonte primeiro. Consulte as [notas de lançamento do Ubuntu](https://documentation.ubuntu.com/release-notes/24.04/).

Instale `python3-venv` se sua distribuição não fornecer suporte a ambientes virtuais do Python por padrão. A compilação inclui o backend Python e cria um instalador Debian `.deb` e arquivo portátil `.tar.gz` em `release/`. O computador de destino não precisa instalar Node.js ou Python separadamente. Abra o `.deb` no instalador de software, ou extraia o arquivo portátil e execute `claude-code-user-sync` como usuário normal. Use o [guia oficial do Claude Desktop Linux beta](https://code.claude.com/docs/en/desktop-linux) para instalar o Claude.

### Aplicativo sem instalador

Em qualquer plataforma de destino:

```sh
npm run pack
```

Isso compila o backend incluído e gera uma pasta de aplicativo sem instalador em `release/` para validação local. Compilar não instala o aplicativo nem sincroniza dados do Claude.

## Testes e prévia

Na raiz do projeto:

```sh
npm test
python3 -m unittest discover
npm run preview
```

No Windows, use `py -3 -m unittest discover` para a suíte Python e `npm.cmd` para os comandos npm.

A prévia usa resultados de sincronização de exemplo. A quantidade de contas é lida das pastas locais; os demais números são identificados claramente como dados de exemplo. Ela não encerra o Claude, grava catálogos, cria backups de sincronização ou salva preferências.

```sh
npm run smoke
# Depois de npm run pack:
npm run smoke:packaged
```

Essas verificações abrem o aplicativo Electron pelo código-fonte ou empacotado em modo de prévia, exercitam os três idiomas e o fluxo de sincronização simulado, e verificam o estado de sucesso.

O GitHub Actions está configurado para executar testes Python com dados sintéticos no macOS, Windows e Linux, executar os testes do Electron, compilar um backend independente e gerar um aplicativo sem instalador em cada sistema operacional. Testes automatizados e de prévia não comprovam o funcionamento de todos os fluxos autenticados do Claude Desktop.

## Arquitetura

- O processo principal do Electron controla a janela, as preferências e as ações desktop aprovadas.
- Uma ponte limitada de preload expõe operações específicas à interface.
- O renderer compartilhado usa HTML, CSS, JavaScript e dicionários i18next locais.
- O backend Python cuida da descoberta de contas, validação de catálogos, encerramento normal do Claude, backups, sincronização e reabertura do Claude.
- Os pacotes executam o backend incluído; a execução pelo código-fonte usa um interpretador Python instalado.

A interface funciona com isolamento de contexto e sandbox ativados, e integração Node desativada. Carrega recursos locais com uma política restritiva de segurança de conteúdo e valida as solicitações IPC. O motor Python trata o conteúdo das conversas; a interface exibe resumos das operações e diagnósticos.
