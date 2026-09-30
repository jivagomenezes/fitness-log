# Atalho do iPhone: HRV, FC de repouso, sono, passos e calorias → GitHub

O atalho lê do app Saúde as amostras dos últimos 2 dias e grava um arquivo em `raw/health/YYYY-MM-DD_HHMM.txt`
no repositório, pela API do GitHub. A sincronização (`scripts/import_health.py`) transforma isso em
`hrv_ms`, `resting_hr`, `sleep_h`, `deep_sleep_h`, `rem_sleep_h`, `steps`, `active_kcal`, `basal_kcal` e `vo2max`
em `data/daily_health.csv`.

Formato de cada linha: `type;start;end;value[;unit]` com `type` = `hrv`, `rhr`, `sleep`, `vo2max`, `steps`,
`active_kcal` ou `basal_kcal`. O atalho pode rodar várias vezes por dia: as amostras são juntadas sem repetir.

## 1. Token do GitHub (uma vez)

1. github.com/settings/personal-access-tokens/new (token *fine-grained*).
2. **Repository access** → *Only select repositories* → `fitness-log`.
3. **Permissions** → *Contents* → **Read and write**. Nada mais.
4. Validade de 1 ano. O token fica **só dentro do atalho** — nunca em conversa, arquivo ou print.

## 2. Gerar o atalho com a IA do app Atalhos (iOS 27)

Cole o texto abaixo no gerador. Ele está em inglês porque os nomes técnicos (ISO 8601, PUT, Base64) ficam menos
ambíguos; deixe `PASTE_TOKEN_HERE` como está e troque pelo token **depois**, direto na ação gerada.

```
Create a shortcut named "Health → fitness_log" that runs without asking anything:

1. Start with an empty list variable called Lines.
2. Find Health Samples of type Heart Rate Variability whose Start Date is in the last 2 days, sorted by Start Date.
   Repeat with each sample and add this text to Lines:
   hrv;START;END;VALUE
   where START and END are the sample's Start Date and End Date formatted as ISO 8601 (date and time, with time zone)
   and VALUE is the sample's Value as a plain number.
3. Do the same for Resting Heart Rate, using the prefix rhr instead of hrv.
4. Do the same for Sleep Analysis, using the prefix sleep; here VALUE is the sleep stage (Core, Deep, REM, Awake, In Bed).
   Do the same for Cardio Fitness (VO2 Max), using the prefix vo2max.
5. Find Health Samples of type Steps whose Start Date is in the last 2 days, grouped by Day.
   Repeat with each daily total and add: steps;START;END;VALUE
6. Do the same for Active Energy with the prefix active_kcal, and for Resting Energy with the prefix basal_kcal,
   both grouped by Day, and add ;UNIT at the end of each line with the sample's Unit.
7. Combine Lines into a single text separated by New Lines.
8. Base64 encode that text, with no line breaks.
9. Format the Current Date with the custom format yyyy-MM-dd_HHmm and save it as FileName.
10. Get Contents of URL https://api.github.com/repos/jivagomenezes/fitness-log/contents/raw/health/FileName.txt
    with method PUT, headers
      Authorization: Bearer PASTE_TOKEN_HERE
      Accept: application/vnd.github+json
      X-GitHub-Api-Version: 2022-11-28
    and a JSON request body with
      message: health: FileName
      content: the Base64 text from step 8
11. If the result contains "content", show the notification "Saúde enviada ✅". Otherwise show a notification with the result.
```

**Conferir no atalho gerado (é aqui que a IA costuma errar):**
- As datas de START e END estão em **ISO 8601** (toque na variável › formato de data). Se vierem em outro formato,
  o importador ainda entende `dd/mm/aaaa, HH:MM`, mas ISO é o mais seguro.
- Passos, Energia Ativa e Energia em Repouso estão com **Agrupar por: Dia** ligado.
- O *Valor* das amostras não carrega texto junto (ex.: "48 ms" também funciona, mas o ideal é só o número).
- A URL termina com a variável FileName seguida de `.txt`.
- O token foi colado no cabeçalho `Authorization`, depois de `Bearer ` (com espaço).

**Permissão de envio (obrigatória):** o app Atalhos bloqueia o envio de muitos itens de saúde para fora do iPhone
(erro "está tentando compartilhar N itens do app Saúde, o que não é permitido"). Libere em
**Ajustes → Apps → Atalhos → Avançado → Permitir Compartilhar Grandes Quantidades de Dados**. Na primeira execução,
quando perguntar se pode enviar para `api.github.com`, escolha **Permitir Sempre**.

**Teste:** rode o atalho uma vez à mão. Deve aparecer "Saúde enviada ✅" e um arquivo novo em `raw/health/`
no GitHub. Se aparecer um erro, mande o texto do erro (sem o token) para uma conversa do Projeto.

## 3. Automação (roda sozinho)

Atalhos → **Automação** → **+** → **App** → *Bevel* → **É Aberto** → **Executar Imediatamente** → escolha o atalho.

Precisa ser um momento com o iPhone **desbloqueado** (com ele bloqueado o iOS não deixa ler dados de saúde);
por isso o gatilho é abrir o Bevel, não um horário fixo. De manhã ele traz a noite (HRV, sono, FC de repouso);
à noite, os totais do dia (passos e calorias). Se num dia você não abrir o Bevel à noite, a manhã seguinte completa.

## Se preferir montar à mão

As ações equivalentes, em português: **Encontrar Amostras de Saúde** → **Repetir com Cada** → **Texto** →
**Adicionar à Variável** (para cada tipo) → **Combinar Texto** (Nova Linha) → **Codificar em Base64** →
**Data Atual** + **Formatar Data** → **Obter Conteúdo do URL** (PUT, cabeçalhos e corpo JSON como acima) →
**Se** / **Mostrar Notificação**.

## Nomes que o importador aceita

Fases do sono em inglês ou português (Core/Principal, Deep/Profundo, REM, Awake/Acordado, In Bed/Na Cama).
Fase desconhecida gera aviso e não é contada — é só acrescentar o nome em `STAGES` no `scripts/import_health.py`.
Tipos antigos em português (`fcr`, `sono`, `passos`, `kcal_ativas`, `kcal_repouso`) também são aceitos.
