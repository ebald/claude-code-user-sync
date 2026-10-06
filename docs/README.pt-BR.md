# Claude Code User Sync

**Mantenha seus chats locais do Claude Code disponíveis ao trocar de conta no mesmo computador.**

[English](../README.md) · [Español](README.es.md) · Português

O Claude Code User Sync sincroniza os catálogos de conversas da **aba Code do Claude Desktop** entre as contas detectadas no computador. Inclui um aplicativo Electron compartilhado por macOS e Windows e uma ferramenta Python, com backup automático e opção de desfazer alterações. O aplicativo oferece inglês, espanhol e português.

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

- macOS 13 ou mais recente, ou Windows 10/11, com Claude Desktop e conversas locais na aba Code.
- Pelo menos dois perfis de conta inicializados localmente. Entre em cada conta, abra a aba Code, selecione o ambiente Local e crie uma conversa nesse computador.
- Para executar pelo código-fonte: **Node.js 22.12 ou mais recente**, npm e **Python 3.10 ou mais recente**. O motor Python usa somente a biblioteca padrão. No macOS, use uma instalação de Python compatível com sua versão do macOS.
- Os aplicativos empacotados incluem Electron e Python. O computador de destino não precisa instalar Node.js nem Python separadamente. Uma compilação para macOS pode exigir uma versão mais recente que o macOS 13, dependendo do Python usado para compilá-la.

| Sistema | Aplicativo | Verificação |
| --- | --- | --- |
| macOS | Aplicativo Electron para a arquitetura do Mac usado na compilação | Testes automatizados e prévia locais; o fluxo autenticado depende do formato interno do Claude Desktop |
| Windows | A mesma interface Electron e instalador Windows x64 | Experimental; a sincronização autenticada no Claude Desktop ainda não foi verificada em uma máquina Windows |

No Windows, use o PowerShell normal, fora do WSL. Compile no sistema de destino para incluir o executável Python adequado.

## Obter o código-fonte

Instale [Git](https://git-scm.com/downloads), [Node.js](https://nodejs.org/en/download) e [Python](https://www.python.org/downloads/) se necessário. No Terminal do macOS ou no PowerShell do Windows:

```sh
git clone https://github.com/ebald/claude-code-user-sync.git
cd claude-code-user-sync
npm ci
```

No PowerShell do Windows, use `npm.cmd ci` para a instalação acima. Também é possível usar **Code → Download ZIP** no GitHub, extrair o arquivo e abrir um terminal na pasta extraída. Execute os comandos a partir dessa pasta. A instalação baixa as dependências de compilação e o Electron; a sincronização acontece localmente.

## macOS

Confira os requisitos e inicie o Electron:

```sh
node --version
python3 --version
npm start
```

### Usar o aplicativo

1. Termine as tarefas em andamento no Claude.
2. Escolha **Português** no seletor de idioma; a escolha será salva.
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

Consulte o [guia do Electron](../desktop/README.md) para detalhes de compilação, armazenamento e testes.

### Terminal ou Finder

Encerre completamente o Claude com **Cmd+Q** e termine os processos ativos do Claude Code. Execute:

```sh
python3 claude_sync.py sync --live
```

Ou abra `sync.command` pelo Finder. Depois reabra o Claude e entre na conta desejada.

## Windows

1. Instale Node.js 22.12 ou mais recente e Python 3.10 ou mais recente pelos sites oficiais, incluindo o inicializador Python. Abra um novo PowerShell depois da instalação.
2. Abra o PowerShell na pasta deste projeto e execute `npm.cmd ci` se ainda não tiver feito isso.
3. Confira os requisitos e inicie o mesmo aplicativo Electron usado no macOS:

   ```powershell
   node --version
   py -3 --version
   npm.cmd start
   ```

Escolha o idioma, termine suas tarefas no Claude e clique no botão de sincronização e reabertura. O aplicativo solicita o encerramento normal, verifica se o Claude parou, sincroniza e tenta reabri-lo. Não força o encerramento. A troca de conta permanece manual. Se o Claude não for encontrado automaticamente, é possível selecionar seu executável.

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

A ferramenta procura o catálogo em `%APPDATA%\Claude\claude-code-sessions` e nas pastas de dados do Claude instalado por MSIX, quando existirem. Os históricos normalmente ficam em `%USERPROFILE%\.claude\projects`.

Se o catálogo não for encontrado ou houver mais de uma instalação, informe os caminhos corretos. `--app-data` recebe a pasta que **contém** `claude-code-sessions`; as opções globais vêm antes do comando:

```powershell
py -3 claude_sync.py --app-data "C:\caminho\Claude" --projects-dir "C:\caminho\.claude\projects" sync --live
```

A ferramenta não transfere conversas entre máquinas nem entre usuários diferentes do Windows.

No Windows, a verificação de arquivos aceita arquivos comuns em unidades locais. Compartilhamentos de rede, junctions, links simbólicos e arquivos de nuvem que ainda sejam reparse points são recusados. Disponibilize os arquivos necessários como arquivos locais comuns antes de sincronizar.

## Backups e reversão

A ferramenta de linha de comando salva cada operação em `.sandbox/sync-ID/` dentro do projeto. Para escolher outro local:

```sh
python3 claude_sync.py sync --live --storage-dir /caminho/privado/backups
```

No Windows:

```powershell
py -3 claude_sync.py sync --live --storage-dir "$env:LOCALAPPDATA\Claude Code User Sync\Backups"
```

O aplicativo Electron mantém os backups do macOS em `~/Library/Application Support/Claude Account Sync/Backups/`. O nome interno antigo foi preservado para manter a compatibilidade. No Windows, os backups ficam em `%LOCALAPPDATA%\Claude Code User Sync\Backups\`. O Electron guarda suas preferências na pasta padrão de dados do aplicativo; consulte o [guia](../desktop/README.md#storage).

Os backups incluem o catálogo, os arquivos originais necessários para desfazer e um manifesto dos arquivos vinculados. As cópias disponíveis ficam em `asset-snapshot/`. No macOS, as permissões são exclusivas do usuário. No Windows, os backups herdam as permissões da pasta que os contém; use uma pasta dentro do seu perfil, sem compartilhamento.

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

No Windows: `py -3 -m unittest discover` para os testes Python. Os testes usam dados sintéticos. O [guia do aplicativo](../desktop/README.md#tests-and-preview) inclui os comandos de prévia e empacotamento. O [README em inglês](../README.md#development-and-tests) explica a validação opcional com o SDK da Anthropic.

A interface compartilhada usa **i18next** e dicionários JSON em `desktop/locales/` para inglês, espanhol e português brasileiro. As mesmas chaves atendem macOS e Windows, os testes verificam a cobertura e a seleção do idioma é salva entre aberturas.

## Privacidade e limites

- Credenciais, estado de login e históricos originais não são transferidos entre contas nem modificados pela sincronização.
- Concessões de acesso, configuração de conectores e estado de processos não são transportados.
- Cópias, planos, diagnósticos e backups podem conter conversas, caminhos e links privados. Os locais padrão de dados gerados estão excluídos do Git; mantenha essas informações privadas.
- A ferramenta depende do formato interno do Claude Desktop. Atualizações do aplicativo podem alterar a compatibilidade; testes sintéticos não garantem todos os fluxos autenticados.
- Apenas os dados locais existentes ficam disponíveis. Históricos e arquivos ausentes não podem ser reconstruídos.

Ao informar um problema, inclua o comando, o sistema operacional, a versão do Claude Desktop e uma mensagem de erro sem dados pessoais. Não envie conversas reais, pastas de backup ou manifestos de diagnóstico sem remover informações privadas.
