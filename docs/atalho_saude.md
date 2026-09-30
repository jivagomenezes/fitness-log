# Atalho do iPhone: HRV, FC de repouso, sono, passos e calorias → GitHub

O atalho lê do app Saúde as amostras da noite e grava um arquivo em `raw/saude/AAAA-MM-DD_HHMM.txt`
no repositório, pela API do GitHub. A sincronização (`scripts/importar_saude.py`) transforma isso em
`hrv_ms`, `fc_repouso`, `sono_h`, `sono_profundo_h`, `sono_rem_h`, `passos`, `kcal_ativas` e `kcal_repouso`
em `data/recuperacao.csv`.

Formato de cada linha: `tipo;inicio;fim;valor[;unidade]` com `tipo` = `hrv`, `fcr`, `sono`, `passos`,
`kcal_ativas` ou `kcal_repouso`. O atalho pode rodar várias vezes por dia: as amostras são juntadas sem repetir.

## 1. Token do GitHub (uma vez)

1. github.com/settings/personal-access-tokens/new (token *fine-grained*).
2. **Repository access** → *Only select repositories* → `fitness-log`.
3. **Permissions** → *Contents* → **Read and write**. Nada mais.
4. Validade de 1 ano. Copie o token e guarde **só dentro do atalho**. Nunca cole em conversa.

## 2. O atalho (app Atalhos → +), nome "Saúde → fitness_log"

Os nomes das ações podem variar um pouco conforme a versão do iOS.

**HRV**
1. **Encontrar Amostras de Saúde** — Tipo: *Variabilidade da Frequência Cardíaca*; *Data de Início* está nos últimos *2 dias*.
2. **Repetir com Cada** item → dentro, **Texto**: `hrv;` + *Item de Repetição › Data de Início* + `;` + *Item de Repetição › Data de Fim* + `;` + *Item de Repetição › Valor*.
   Nas duas datas, toque na variável e escolha o formato **ISO 8601**.
3. Ainda dentro do Repetir: **Adicionar à Variável** → `linhas`.

**FC de repouso**: repita os passos 1–3 com o tipo *Frequência Cardíaca em Repouso* e o prefixo `fcr;`.

**Sono**: repita os passos 1–3 com o tipo *Análise do Sono* e o prefixo `sono;`. O *Valor* aqui é a fase (Principal, Profundo, REM, Acordado…).

**Totais do dia** (passos e calorias): repita os passos 1–3 com **Agrupar por: Dia** ligado na ação
*Encontrar Amostras de Saúde* (assim o Saúde já devolve a soma de cada dia, e não milhares de amostras):
- *Passos* → prefixo `passos;`
- *Energia Ativa* → prefixo `kcal_ativas;` e, no fim do texto, `;` + *Item de Repetição › Unidade*
- *Energia em Repouso* → prefixo `kcal_repouso;` e, no fim, `;` + *Unidade* (se vier em kJ, o importador converte)

Com os últimos 2 dias, a execução da manhã fecha o total de ontem e a da noite traz o de hoje;
para cada dia vale o maior total recebido.

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
por isso o gatilho é abrir o Bevel, não um horário fixo. De manhã ele traz a noite (HRV, sono, FC de repouso);
à noite, os totais do dia (passos e calorias). Se num dia você não abrir o Bevel à noite, a manhã seguinte completa.

## Conferir

Depois da primeira execução, o arquivo aparece em `raw/saude/` no GitHub. A próxima sincronização importa;
fases de sono com nome desconhecido geram aviso e não são contadas (é só acrescentar o nome em `FASES`
no `scripts/importar_saude.py`).
