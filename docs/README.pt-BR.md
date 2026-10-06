# Claude Code User Sync

**Mantenha seus chats locais do Claude Code disponíveis ao trocar de conta no mesmo computador.**

[English](../README.md) · [Español](README.es.md) · Português

O Claude Code User Sync sincroniza os catálogos de conversas da **aba Code do Claude Desktop** entre as contas detectadas no computador. Inclui um aplicativo Electron compartilhado por macOS, Windows e Linux e uma ferramenta Python, com backup automático e opção de desfazer alterações. O aplicativo oferece inglês, espanhol e português.

Se você criou uma conversa local na conta A, a sincronização permite que o registro apareça também na conta B. O histórico permanece no armazenamento local compartilhado; a ferramenta atualiza os registros usados na lista de chats de cada conta.

A ferramenta não transfere chats entre contas na nuvem ou computadores e não sincroniza as conversas comuns do site claude.ai. Este é um projeto independente, sem vínculo com a Anthropic.

## Recursos

- Detecta automaticamente as contas locais, inclusive mais de duas.
- Sincroniza chats de todos os projetos e preserva títulos, identificadores, referências de histórico, favoritos e estado de arquivamento.
- Usa a última atividade para resolver diferenças; versões diferentes empatadas permanecem pendentes.
- Respeita exclusões e deixa automações e sessões SSH, WSL e remotas fora do escopo.
- Preserva referências de artifacts, verifica imagens incorporadas e copia os arquivos locais vinculados que estiverem disponíveis.
- Recupera cópias preservadas quando o arquivo temporário original desapareceu.
- Faz backup antes de gravar e permite desfazer a sincronização sem sobrescrever alterações posteriores.
- Executa a sincronização localmente, sem chamadas ao modelo nem requisições de rede.

## Requisitos

- macOS 13 ou mais recente, Windows 10/11 ou Ubuntu 22.04+/Debian 12+, com Claude Desktop e conversas locais na aba Code. Consulte o [guia de instalação para macOS/Windows](https://support.claude.com/en/articles/10065433-install-claude-desktop) ou o [guia oficial do beta Linux](https://code.claude.com/docs/en/desktop-linux). O Linux oferece x64 e arm64.
- Pelo menos dois perfis de conta inicializados localmente. Entre em cada conta, abra a aba Code, selecione o ambiente Local e crie uma conversa nesse computador.
- Para executar pelo código-fonte: **Node.js 22.12 ou mais recente**, npm e **Python 3.10 ou mais recente**. O motor Python usa somente a biblioteca padrão. No macOS, use uma instalação de Python compatível com sua versão do macOS.
- Os aplicativos empacotados incluem Electron e Python. O computador de destino não precisa instalar Node.js nem Python separadamente. Uma compilação para macOS pode exigir uma versão mais recente que o macOS 13, dependendo do Python usado para compilá-la.

| Sistema | Aplicativo | Verificação |
| --- | --- | --- |
| macOS | Aplicativo Electron para a arquitetura do Mac usado na compilação | Testes automatizados e prévia locais; o fluxo autenticado depende do formato interno do Claude Desktop |
| Windows | A mesma interface Electron e instalador Windows x64 | Experimental; a sincronização autenticada no Claude Desktop ainda não foi verificada em uma máquina Windows |
| Linux | A mesma interface Electron, com instalador Debian e arquivo portátil para a arquitetura da máquina de compilação | Experimental; a sincronização autenticada no Claude Desktop ainda não foi verificada em uma máquina Linux |

No Windows, use o PowerShell normal, fora do WSL. Compile no sistema de destino para incluir o executável Python adequado.

## Obter o código-fonte

Baixe o projeto por **Code → Download ZIP** no GitHub e extraia o arquivo. Se já tiver [Git](https://git-scm.com/downloads), você também pode cloná-lo:

```sh
git clone https://github.com/ebald/claude-code-user-sync.git
cd claude-code-user-sync
```

Execute os comandos abaixo na pasta baixada ou clonada. Instale o Claude Desktop separadamente e inicialize suas conversas locais na aba Code antes de sincronizar.

## Preparação automática

Os aplicativos empacotados já incluem Electron e Python. Os scripts de preparação servem para executar este projeto pelo código-fonte: conferem as ferramentas existentes, instalam os requisitos ausentes, baixam as dependências e abrem o aplicativo. Abrir o aplicativo **não** inicia uma sincronização; você escolhe quando sincronizar na interface.

| Sistema | Iniciar a preparação automática |
| --- | --- |
| macOS | Clique duas vezes em `setup.command` no Finder, ou execute `bash ./setup.sh` no Terminal |
| Windows x64 | Clique duas vezes em `setup.bat` no Explorador de Arquivos, ou execute `.\setup.bat` no PowerShell |
| Ubuntu / Debian | Execute `bash ./setup.sh` no terminal do seu usuário normal |

A instalação precisa de conexão com a internet. As versões compatíveis de Node.js, npm e Python já instaladas são reutilizadas. O console de preparação usa inglês; o aplicativo abre no idioma compatível do sistema e oferece inglês, espanhol e português.

Se o Node.js estiver ausente ou for antigo demais, o script do macOS/Linux baixa uma distribuição oficial verificada na pasta `.sandbox/setup/`, ignorada pelo Git, e a usa para este aplicativo. No macOS, o Python ausente é instalado por um pacote oficial assinado. No Ubuntu/Debian, o `apt` instala o Python, o suporte a ambientes virtuais e as bibliotecas do Electron que estiverem faltando. A instalação de pacotes do sistema pede privilégios de administrador quando precisa; o aplicativo executa como seu usuário normal.

No Linux em que o AppArmor restringe a abertura do Electron pelo código-fonte, a preparação padrão compila e instala o pacote `.deb` e abre o aplicativo instalado. A instalação pode pedir sua senha de administrador. Depois de instalar, abra o aplicativo diretamente pelo menu de aplicativos nas próximas vezes. Isso trata as restrições usadas pelo Ubuntu 24.04 e versões mais recentes; `--check` informa quando essa forma de abertura é necessária sem fazer alterações.

No Windows, a preparação usa PowerShell e [WinGet](https://learn.microsoft.com/en-us/windows/package-manager/winget/) quando disponível. Caso contrário, verifica os downloads oficiais do Node.js e Python e os instala para este projeto em `.sandbox/setup/`; o instalador do Python usa uma instalação para o seu usuário. O Windows pode mostrar a solicitação normal de permissões do instalador. A preparação não altera a política global de execução do PowerShell. Os caminhos selecionados só se aplicam ao processo de preparação e ao aplicativo.

Para conferir os requisitos sem instalar, baixar dependências ou abrir o aplicativo:

```sh
# macOS / Linux
bash ./setup.sh --check
```

```powershell
# Windows
.\setup.bat --check
```

A verificação termina com sucesso se os requisitos estiverem prontos; se faltar algo, informa o que falta e termina com o código de saída 1. Para instalar os requisitos ausentes e preparar as dependências do código-fonte sem abrir o aplicativo:

```sh
# macOS / Linux
bash ./setup.sh --no-launch
```

```powershell
# Windows
.\setup.bat --no-launch
```

No Linux, `--no-launch` também pula a compilação e a instalação do pacote do aplicativo. Adicione `--help` a qualquer um dos lançadores para consultar as opções disponíveis. Para abrir pelo código-fonte, execute o script novamente quando quiser abrir o aplicativo. A preparação manual e o desenvolvimento continuam disponíveis abaixo.

### Preparação manual para desenvolvedores

Se a preparação automática usou um ambiente local do projeto, abra o aplicativo depois pelo script de preparação. Os comandos manuais de `npm` abaixo precisam de Node.js e npm no seu PATH normal.

Instale [Node.js](https://nodejs.org/en/download) 22.12 ou mais recente e [Python](https://www.python.org/downloads/) 3.10 ou mais recente, depois instale as dependências fixadas no arquivo de lock do projeto:

```sh
npm ci
```

No PowerShell do Windows, use `npm.cmd ci`. A preparação baixa as dependências de compilação e o Electron; a sincronização acontece localmente. Continue com as instruções do seu sistema abaixo.

## macOS

Confira os requisitos e inicie o Electron:

```sh
node --version
python3 --version
npm start
```

### Usar o aplicativo

1. Termine as tarefas em andamento no Claude.
2. O aplicativo abre no idioma compatível preferido do sistema operacional. Mantenha **Idioma do sistema** para seguir essa configuração ou escolha **English**, **Español** ou **Português**; a escolha manual será salva.
3. Clique no botão de sincronização e reabertura.
4. Aguarde o Claude fechar, os catálogos sincronizarem e o Claude reabrir.
5. Faça logout e login na outra conta dentro do Claude.

O aplicativo solicita o encerramento normal e espera até 30 segundos, sem forçar a saída. A troca de conta continua manual. Os controles de arquivos, diagnóstico e último backup permitem conferir o resultado. Um arquivo indisponível é informado de forma específica, sem tratar uma sincronização bem-sucedida como falha.

Para testar a interface com resultados de exemplo:

```sh
npm run preview
```

A prévia não sincroniza catálogos reais, não fecha o Claude nem salva preferências. Lê a quantidade de contas pelas pastas locais e identifica os demais números como dados de exemplo.

### Compilar para macOS

```sh
npm run build:mac
```

Gera um DMG e um ZIP em `release/` para a arquitetura do Mac atual. A compilação cria um ambiente Python isolado e empacota o motor com PyInstaller. Registra o requisito de macOS a partir do Electron e do Python incluído, usando a versão mínima mais recente dos dois. O aplicativo recebe uma assinatura local ad hoc e não é notarizado. Use `npm run pack` para gerar o aplicativo sem instalador.

Consulte o [guia do Electron](../desktop/README.pt-BR.md) para detalhes de compilação, armazenamento e testes.

### Terminal ou Finder

Encerre completamente o Claude com **Cmd+Q** e termine os processos ativos do Claude Code. Execute:

```sh
python3 claude_sync.py sync --live
```

Ou abra `sync.command` pelo Finder. Depois reabra o Claude e entre na conta desejada.

`sync --live` sincroniza todos os perfis e projetos locais detectados. Informa as quantidades, divergências pendentes, históricos indisponíveis, problemas com arquivos e local do backup. Pode copiar um registro de catálogo mesmo que falte o histórico, mas não pode reconstruir o conteúdo de uma conversa ausente.

## Windows

1. Instale Node.js 22.12 ou mais recente e Python 3.10 ou mais recente pelos sites oficiais, incluindo o inicializador Python. Abra um novo PowerShell depois da instalação.
2. Abra o PowerShell na pasta deste projeto e execute `npm.cmd ci` se ainda não tiver feito isso.
3. Confira os requisitos e inicie o mesmo aplicativo Electron usado no macOS:

   ```powershell
   node --version
   py -3 --version
   npm.cmd start
   ```

O aplicativo segue automaticamente o idioma do sistema operacional. Você pode alterá-lo no seletor de idioma. Termine suas tarefas no Claude e clique no botão de sincronização e reabertura. O aplicativo solicita o encerramento normal, verifica se o Claude parou, sincroniza e tenta reabri-lo. Não força o encerramento. A troca de conta permanece manual. Se o Claude não for encontrado automaticamente, é possível selecionar seu executável.

Para testar sem alterar os dados do Claude:

```powershell
npm.cmd run preview
```

### Compilar um instalador Windows

Execute em um computador Windows x64 com Node.js e Python x64:

```powershell
npm.cmd run build:win
```

A compilação cria um ambiente Python isolado, empacota o motor com PyInstaller e gera um instalador NSIS em `release/`. Inclui Electron, Python, sincronizador e traduções. O computador de destino não precisa instalar Node.js nem Python separadamente. O instalador não é assinado. A compilação não instala o aplicativo nem altera dados do Claude.

Use `npm.cmd run pack` no Windows para gerar o aplicativo sem instalador.

### PowerShell ou Explorador de Arquivos

1. Termine as tarefas e saia do Claude pelo menu ou pela bandeja do sistema. Fechar somente a janela pode deixar o aplicativo aberto. Encerre também os terminais ativos do Claude Code.
2. Execute:

   ```powershell
   py -3 claude_sync.py sync --live
   ```

3. Reabra o Claude pelo menu Iniciar e troque de conta.

Também é possível clicar duas vezes em `sync.cmd` no Explorador de Arquivos depois de encerrar o Claude. Se `py` não estiver disponível, mas `python` estiver no PATH, substitua `py -3` por `python`. A sincronização dos seus próprios dados normalmente não exige privilégios de administrador.

### Pastas de dados no Windows

A ferramenta procura o catálogo em `%APPDATA%\Claude\claude-code-sessions` e nas pastas de dados do Claude instalado por MSIX, quando existirem. Os históricos normalmente ficam em `%USERPROFILE%\.claude\projects`.

Se o catálogo não for encontrado ou houver mais de uma instalação, informe os caminhos corretos. `--app-data` recebe a pasta que **contém** `claude-code-sessions`; as opções globais vêm antes do comando:

```powershell
py -3 claude_sync.py --app-data "C:\caminho\Claude" --projects-dir "C:\caminho\.claude\projects" sync --live
```

A ferramenta não transfere conversas entre máquinas nem entre usuários diferentes do Windows.

No Windows, a verificação de arquivos aceita arquivos comuns em unidades locais. Compartilhamentos de rede, junctions, links simbólicos e arquivos de nuvem que ainda sejam reparse points são recusados. Disponibilize os arquivos necessários como arquivos locais comuns antes de sincronizar.

## Linux

Use Ubuntu 22.04 ou mais recente ou Debian 12 ou mais recente, com uma sessão gráfica x64 ou arm64. Instale o Claude Desktop pelo [guia oficial do beta Linux](https://code.claude.com/docs/en/desktop-linux) e inicialize conversas locais na aba Code de cada conta. Execute o aplicativo como seu usuário normal.

Instale Node.js 22.12 ou mais recente, npm e Python 3.10 ou mais recente. Para compilar no Ubuntu ou Debian, instale também `python3-venv`. Na pasta do projeto:

```sh
node --version
python3 --version
npm ci
npm start
```

No Ubuntu 24.04 ou mais recente, o AppArmor pode impedir que o Electron abra pelo código-fonte ou pelo arquivo portátil. Se a abertura falhar com um erro de sandbox, instale o pacote `.deb`, que inclui um perfil AppArmor para este aplicativo. É possível criá-lo com `npm run build:linux` sem abrir primeiro o aplicativo pelo código-fonte. Consulte as [notas da versão do Ubuntu](https://documentation.ubuntu.com/release-notes/24.04/).

O aplicativo segue automaticamente o idioma do sistema, com o mesmo seletor usado no macOS e Windows. Termine suas tarefas no Claude e os terminais ativos do Claude Code, depois clique no botão de sincronização e reabertura. Na instalação oficial para Linux, o aplicativo solicita o encerramento normal e espera até 30 segundos. Se não puder solicitar o encerramento com segurança ou o Claude Code continuar ativo, pede que você encerre completamente o Claude e tente novamente. Não força o encerramento dos processos. Depois que o Claude reabrir, troque de conta manualmente.

Para testar a interface sem alterar dados do Claude:

```sh
npm run preview
```

### Compilar pacotes Linux

Compile em um computador Linux com Node.js e Python para a arquitetura desse computador. Use a distribuição compatível mais antiga que pretende atender (Ubuntu 22.04 é a base); pacotes compilados em um sistema mais recente ou com um Python mais recente podem exigir bibliotecas Linux mais recentes.

```sh
npm run build:linux
```

A compilação inclui o motor Python e gera um **instalador Debian `.deb`** e um **arquivo portátil `.tar.gz`** em `release/`. Abra o `.deb` no instalador de programas da distribuição, ou extraia o arquivo portátil e execute `claude-code-user-sync` como seu usuário normal. Os pacotes incluem Electron, Python, sincronizador e traduções. Use `npm run pack` para gerar o aplicativo sem instalador.

### Terminal e pastas de dados no Linux

Encerre completamente o Claude Desktop e termine os terminais ativos do Claude Code, depois execute:

```sh
python3 claude_sync.py sync --live
```

Reabra o Claude pelo menu de aplicativos ou execute `claude-desktop`, depois troque de conta. O catálogo padrão fica em `${XDG_CONFIG_HOME:-~/.config}/Claude/claude-code-sessions`; os históricos ficam em `~/.claude/projects`. O aplicativo respeita `XDG_CONFIG_HOME` e `XDG_DATA_HOME` quando definidos como caminhos absolutos.

Se suas pastas forem diferentes, selecione-as nas configurações ou use as opções globais da ferramenta de terminal antes do comando:

```sh
python3 claude_sync.py --app-data "/caminho/Claude" --projects-dir "/caminho/.claude/projects" sync --live
```

A sincronização no Linux é experimental. Os testes automatizados e a prévia não verificam a sincronização autenticada no Claude Desktop em uma máquina Linux.

## Backups e reversão

A ferramenta de linha de comando salva cada operação em `.sandbox/sync-ID/` dentro do projeto. Para escolher outro local:

```sh
python3 claude_sync.py sync --live --storage-dir /caminho/privado/backups
```

No Windows:

```powershell
py -3 claude_sync.py sync --live --storage-dir "$env:LOCALAPPDATA\Claude Code User Sync\Backups"
```

O aplicativo Electron mantém os backups do macOS em `~/Library/Application Support/Claude Account Sync/Backups/`. O nome interno antigo foi preservado para manter a compatibilidade. No Windows, os backups ficam em `%LOCALAPPDATA%\Claude Code User Sync\Backups\`; no Linux, em `${XDG_DATA_HOME:-~/.local/share}/Claude Code User Sync/Backups/`. O Electron guarda suas preferências na pasta padrão de dados do aplicativo; consulte o [guia](../desktop/README.pt-BR.md#armazenamento).

Os backups incluem o catálogo, os arquivos originais necessários para desfazer e um manifesto dos arquivos vinculados. As cópias disponíveis ficam em `asset-snapshot/`. No macOS e Linux, as permissões são exclusivas do usuário. No Windows, os backups herdam as permissões da pasta que os contém; use uma pasta dentro do seu perfil, sem compartilhamento.

Para desfazer no macOS, feche o Claude e use o caminho de backup indicado pela operação:

```sh
python3 claude_sync.py undo \
  --root "$HOME/Library/Application Support/Claude/claude-code-sessions" \
  --backup .sandbox/sync-OPERATION_ID/backup \
  --live
```

No Windows, para o local padrão:

```powershell
py -3 claude_sync.py undo --root "$env:APPDATA\Claude\claude-code-sessions" --backup ".sandbox\sync-OPERATION_ID\backup" --live
```

No Linux, com o Claude encerrado:

```sh
python3 claude_sync.py undo \
  --root "${XDG_CONFIG_HOME:-$HOME/.config}/Claude/claude-code-sessions" \
  --backup .sandbox/sync-OPERATION_ID/backup \
  --live
```

Substitua `OPERATION_ID` pelo identificador real. Para outro local, informe o caminho completo do backup. Instalações MSIX ou personalizadas exigem o mesmo `--app-data` antes de `undo` e a pasta de catálogo correspondente em `--root`. A reversão recusa sobrescrever registros alterados depois da sincronização.

## Testar e conferir arquivos

É possível criar uma cópia privada, gerar um plano, aplicar e desfazer sem alterar os catálogos reais:

```sh
python3 claude_sync.py sandbox --dest .sandbox/demo
python3 claude_sync.py plan --root .sandbox/demo/registry --projects .sandbox/demo/config/projects --out .sandbox/demo/plan.json
python3 claude_sync.py apply --root .sandbox/demo/registry --plan .sandbox/demo/plan.json --backup .sandbox/demo/backup
python3 claude_sync.py undo --root .sandbox/demo/registry --backup .sandbox/demo/backup
```

No Windows, substitua `python3` por `py -3`. Use uma nova pasta de destino em cada teste e deixe o Claude ocioso ou fechado durante a cópia.

Por padrão, `plan` não resolve divergências nem inclui registros sem histórico legível. `--resolve-newest` usa a última atividade e `--all-chats` inclui históricos indisponíveis. Versões diferentes empatadas continuam pendentes. Alterações nos arquivos após a prévia invalidam o plano.

Para conferir referências de artifacts, imagens e arquivos sem alterar o catálogo:

```sh
python3 claude_sync.py audit --out .sandbox/asset-audit.json
```

No Windows, use `py -3` no lugar de `python3`. Links remotos são registrados, sem download ou teste de acesso. Arquivos ausentes não são recriados e as permissões dos artifacts hospedados não são transferidas.

## Desenvolvimento

```sh
npm test
python3 -m unittest discover
```

No Windows, use `npm.cmd test` e `py -3 -m unittest discover`. O GitHub Actions está configurado para executar testes Python com dados sintéticos no macOS, Windows e Linux, testar o fluxo do Electron e as traduções, e gerar um backend empacotado e um aplicativo sem instalador em cada plataforma. O [guia do aplicativo](../desktop/README.pt-BR.md#testes-e-prévia) inclui os comandos de prévia e empacotamento.

A interface compartilhada usa **i18next** e dicionários JSON em `desktop/locales/` para inglês, espanhol e português brasileiro. As mesmas chaves atendem macOS, Windows e Linux, e os testes verificam a cobertura e as variáveis de interpolação. Por padrão, **Idioma do sistema** usa o idioma compatível preferido do sistema operacional. As variantes regionais de inglês e espanhol usam as respectivas traduções; todas as variantes de português usam português brasileiro. Se nenhum idioma preferido tiver tradução, o aplicativo usa inglês. A escolha manual é salva entre aberturas; selecione **Idioma do sistema** para voltar à seleção automática.

As suítes usam catálogos e históricos sintéticos. Cobrem várias contas, perfis novos, sincronizações repetidas, conflitos, marcadores de exclusão, recuperação de artifacts, verificação de arquivos, planos desatualizados, reversão e o fluxo desktop.

Para uma verificação adicional de leitura com a versão fixa do Anthropic Agent SDK:

```sh
npm ci

node validate_sessions.mjs \
  --sandbox .sandbox/demo \
  --profile account-1/org-local \
  --out .sandbox/demo/validation.json
```

Escolha uma pasta de perfil que exista no catálogo copiado. No PowerShell do Windows, use `npm.cmd ci` e coloque o comando `node` inteiro em uma linha. O validador lê os históricos copiados, limpa variáveis de ambiente de credenciais e bloqueia operações de rede e subprocessos durante a verificação. Informa quantidades e hashes sem imprimir mensagens. Esse validador opcional usa o SDK com versão fixa; o aplicativo Electron não o usa durante a sincronização.

## Privacidade e limites

- Credenciais, estado de login e históricos originais não são transferidos entre contas nem modificados pela sincronização.
- Concessões de acesso, configuração de conectores e estado de processos não são transportados.
- Cópias, planos, diagnósticos e backups podem conter conversas, caminhos e links privados. Os locais padrão de dados gerados estão excluídos do Git; mantenha essas informações privadas.
- A ferramenta depende do formato interno do Claude Desktop. Atualizações do aplicativo podem alterar a compatibilidade; testes sintéticos não garantem todos os fluxos autenticados.
- Apenas os dados locais existentes ficam disponíveis. Históricos e arquivos ausentes não podem ser reconstruídos.

Ao informar um problema, inclua o comando, o sistema operacional, a versão do Claude Desktop e uma mensagem de erro sem dados pessoais. Não envie conversas reais, pastas de backup ou manifestos de diagnóstico sem remover informações privadas.
