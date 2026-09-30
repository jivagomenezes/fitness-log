# Protocolo do fitness_log

Este repositório é a memória de treino do Jivago. Os CSVs em `data/` são a fonte da verdade;
esquemas e convenções estão no `README.md` (dicionário de dados, em inglês).
**Conversar sempre em português. Dados, colunas, valores, scripts e código ficam em inglês**; o resumo
`context/status.md`, o plano e as notas livres ficam em português.

## Onde os dados vivem

- **O GitHub (`jivagomenezes/fitness-log`, privado) é a fonte.** Toda gravação é feita num clone dele:
  anexar o repositório à sessão (add_repo, acesso de push), clonar ou `git pull`, gravar, commit e `git push`.
  Isso funciona de qualquer lugar, inclusive do iPhone, sem o Mac.
- O Mac (`~/DEV/fitness_log`) é só uma cópia local, atualizada com `git pull`. Não gravar direto na pasta do Mac.
- Antes de gravar: `git pull`. Se o push for recusado porque o remoto andou (outra sessão ou a tarefa agendada),
  `git pull --rebase` e push de novo.
- Espelho no Projeto "Fitness 2026": `context/status.md` → doc `fitness_log/estado_atual.md`;
  `context/plan.md` → doc `fitness_log/plano.md`; este arquivo → doc `fitness_log/protocolo.md`.

## Antes de responder qualquer pergunta de treino

1. Ler `context/status.md` (e `context/plan.md` quando a pergunta envolver plano, metas ou paces).
   Conferir a data de geração; se estiver velha, sincronizar (seção abaixo) ou perguntar o que foi feito.
2. Se a pergunta depender de algo que não está no resumo, consultar os CSVs diretamente.
3. "Qual o treino de hoje?" → cruzar o dia da semana com a estrutura do plano, os últimos 14 dias
   (o que já foi feito na semana, dias duros seguidos, o que cada grupo muscular já recebeu)
   e a recuperação (score do Bevel, HRV/FC de repouso vs. linha de base, sono, passos). Ajustar se houver alerta.

## Registrar um treino (texto colado, print, exportação)

1. **Extrair** os campos para a tabela certa:
   - corrida → `data/runs.csv` (+ `data/intervals.csv` se for intervalado com tiros identificáveis);
     JSON do Apple Watch → salvar em `raw/` e usar `scripts/import_watch_run.py FILE --type <type>`
     (o tipo não vem no JSON: confirmar com o Jivago). Tipos: `interval`, `tempo`, `long`, `z2`, `recovery`, `race`, `test`.
   - academia (texto do Hevy) → salvar em `raw/hevy/` e usar
     `scripts/import_hevy_text.py --date <date> --workout <A|B|C|D|other> [--source-id <strava id>] [--routine "<nome>"]`
   - prova → além da corrida, o resultado oficial (chip, oficial, colocação) em `data/races.csv`
   - card do Bevel → `data/daily_health.csv` (`bevel_recovery_pct`, `bevel_strain_pct`, `bevel_sleep_pct`), uma linha por dia
2. **Nome do exercício** = nome exato do Hevy. Se for novo, acrescentar em `data/exercises.csv` com `name_en` e `muscle_group`.
   Halteres: carga = soma dos dois. Unilateral: reps = soma dos dois lados.
3. **Não inventar dados.** Campo que não veio fica vazio. Se faltar algo importante (ex.: data, tipo da corrida),
   perguntar antes de gravar. Datas relativas ("ontem") são resolvidas no fuso de Lisboa.
4. **Não duplicar:** conferir se já existe registro para a mesma data/tipo (ou mesmo `source_id`/`strava_id`) antes do append.
   Correção de dado errado = editar a linha existente, não criar outra.
5. Mostrar ao Jivago, em poucas linhas, o que foi gravado.
6. Rodar `python3 scripts/build_status.py`. Se sair com erro, corrigir os dados e rodar de novo.
7. Commit com mensagem `log: <type> <date>` (ex.: `log: interval 2026-09-29`) e push.
8. Atualizar o doc `fitness_log/estado_atual.md` do Projeto "Fitness 2026" com o conteúdo novo de
   `context/status.md` (ferramenta Projects). Se `context/plan.md` mudou, atualizar `fitness_log/plano.md` também.
   Se a ferramenta não estiver disponível na sessão, dizer isso no resumo.
9. Comentar brevemente o que chamar atenção (alertas novos, progressão de carga, FC dos tiros).

## Sincronizar (Strava + app Saúde) — também é o que a tarefa agendada faz

1. `git pull`. Ler `context/last_sync.txt` (data/hora UTC da última sincronização bem-sucedida).
2. **Strava** (conector do Strava): listar as atividades desde 3 dias antes da última sincronização
   (`list_activities` com `range_start` em horário local). A janela sobreposta é proposital: se uma execução
   falhar, a seguinte recupera; a deduplicação é pelo `strava_id` / `source_id`.
   - **Run** que não esteja em `runs.csv` (`strava_id`): gravar com os dados do Strava (date, start_time,
     distance_km, duration, hr_avg/hr_max via `get_activity_performance`), `source=strava`. Na esteira com GymKit,
     distância e velocidade do resumo são as da esteira (corretas). O nome/descrição da atividade costuma dizer o
     treino (ex.: "VO2 · 5×800m…"); se não disser, inferir pelas zonas e escrever "tipo a confirmar" nas notas.
     Se depois chegar o JSON do Apple Watch, o importador completa o registro.
   - **WeightTraining** com descrição "Registrado com hevyapp.com": salvar o texto em `raw/hevy/<id>.txt` e rodar
     `scripts/import_hevy_text.py --date <date> --workout <A|B|C|D|other> --source-id <id> --routine "<nome>"`.
     Workout pela rotina/conteúdo: Push → B, Pull → C, Lower/pernas → A; misto → other.
     Exercício novo → `exercises.csv` (com `name_en` e `muscle_group`).
     WeightTraining sem descrição do Hevy (treino só no relógio) não entra na tabela de séries.
   - Ignorar alongamento/mobilidade (PhysicalTherapy), caminhada e outros esportes.
3. **App Saúde**: o atalho do iPhone grava em `raw/health/YYYY-MM-DD_HHMM.txt`. Rodar `python3 scripts/import_health.py`
   (idempotente: preenche HRV da noite, FC de repouso, sono, passos e calorias em `daily_health.csv`
   sem apagar os scores do Bevel).
4. Se houve dado novo: passos 6–8 do registro (build_status, commit `sync: <resumo>`, push, atualizar o Projeto).
5. Gravar a hora atual (UTC, ISO 8601) em `context/last_sync.txt` e commitar junto — mesmo sem dado novo,
   para registrar que a sincronização rodou.

## Regras

- Nunca editar `context/status.md` à mão: ele é gerado.
- Mudanças de plano (metas, paces, estrutura) vão em `context/plan.md`, só quando o Jivago confirmar.
- Parâmetros do script (início do bloco, FC máx, limiares de alerta) ficam no topo de `scripts/build_status.py`.
- Chaves e tokens (GitHub, Strava) nunca no repositório nem na conversa.
- Exportações brutas ficam em `raw/` (versionadas no git: são a camada bruta que permite reprocessar tudo).
