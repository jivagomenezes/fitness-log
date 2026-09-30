# Atalho do iPhone: HRV, FC de repouso e sono → GitHub

O atalho lê do app Saúde as amostras da noite e grava um arquivo em `raw/saude/AAAA-MM-DD_HHMM.txt`
no repositório, pela API do GitHub. A sincronização (`scripts/importar_saude.py`) transforma isso em
`hrv_ms`, `fc_repouso`, `sono_h`, `sono_profundo_h` e `sono_rem_h` em `data/recuperacao.csv`.

Formato de cada linha: `tipo;inicio;fim;valor` com `tipo` = `hrv`, `fcr` ou `sono`.

## 1. Token do GitHub (uma vez)

1. github.com/settings/personal-access-tokens/new (token *fine-grained*).
2. **Repository access** → *Only select repositories* → `fitness-log`.
3. **Permissions** → *Contents* → **Read and write**. Nada mais.
4. Validade de 1 ano. Copie o token e guarde **só dentro do atalho**. Nunca cole em conversa.

## 2. O atalho (app Atalhos → +), nome "Saúde → fitness_log"

Os nomes das ações podem variar um pouco conforme a versão do iOS.

**HRV**
1. **Encontrar Amostras de Saúde** — Tipo: *Variabilidade da Frequência Cardíaca*; *Data de Início* está nos últimos *1 dia*.
2. **Repetir com Cada** item → dentro, **Texto**: `hrv;` + *Item de Repetição › Data de Início* + `;` + *Item de Repetição › Data de Fim* + `;` + *Item de Repetição › Valor*.
   Nas duas datas, toque na variável e escolha o formato **ISO 8601**.
3. Ainda dentro do Repetir: **Adicionar à Variável** → `linhas`.

**FC de repouso**: repita os passos 1–3 com o tipo *Frequência Cardíaca em Repouso* e o prefixo `fcr;`.

**Sono**: repita os passos 1–3 com o tipo *Análise do Sono* e o prefixo `sono;`. O *Valor* aqui é a fase (Principal, Profundo, REM, Acordado…).

**Envio**
4. **Combinar Texto** `linhas` com **Nova Linha**.
5. **Codificar em Base64** o texto combinado (quebras de linha: *Nenhuma*).
6. **Data Atual** → **Formatar Data** com formato personalizado `yyyy-MM-dd_HHmm` → variável `nome`.
7. **Obter Conteúdo do URL**:
   - URL: `https://api.github.com/repos/jivagomenezes/fitness-log/contents/raw/saude/` + `nome` + `.txt`
   - Método: **PUT**
   - Cabeçalhos: `Authorization` = `Bearer <seu token>` · `Accept` = `application/vnd.github+json`
   - Corpo da solicitação: **JSON** com `message` = `saude: ` + `nome` e `content` = o texto em Base64.

## 3. Automação (roda sozinho)

Atalhos → **Automação** → **+** → **App** → *Bevel* → **É Aberto** → **Executar Imediatamente** → escolha o atalho.

Precisa ser um momento com o iPhone **desbloqueado** (com ele bloqueado o iOS não deixa ler dados de saúde);
por isso o gatilho é abrir o Bevel de manhã, não um horário fixo. Se rodar mais de uma vez no dia, vale o arquivo mais recente.

## Conferir

Depois da primeira execução, o arquivo aparece em `raw/saude/` no GitHub. A próxima sincronização importa;
fases de sono com nome desconhecido geram aviso e não são contadas (é só acrescentar o nome em `FASES`
no `scripts/importar_saude.py`).
