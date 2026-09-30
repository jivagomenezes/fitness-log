# Protocolo do fitness_log

Este repositório é a memória de treino do Jivago. Os CSVs em `data/` são a fonte da verdade;
esquemas e convenções estão no `README.md` (dicionário de dados). Responder sempre em português.

## Onde os dados vivem

- **O GitHub (`jivagomenezes/fitness-log`, privado) é a fonte.** Toda gravação é feita num clone dele:
  anexar o repositório à sessão (add_repo, acesso de push), clonar ou `git pull`, gravar, commit e `git push`.
  Isso funciona de qualquer lugar, inclusive do iPhone, sem o Mac.
- O Mac (`~/DEV/fitness_log`) é só uma cópia local, atualizada com `git pull`. Não gravar direto na pasta do Mac,
  para não divergir do GitHub.
- Antes de gravar: `git pull`. Se o push for recusado porque o remoto andou (outra sessão ou a tarefa agendada),
  `git pull --rebase` e push de novo.

## Antes de responder qualquer pergunta de treino

1. Ler `contexto/estado_atual.md` (e `contexto/plano.md` quando a pergunta envolver plano, metas ou paces).
   Conferir a data de geração; se estiver velha, sincronizar (seção abaixo) ou perguntar o que foi feito.
2. Se a pergunta depender de algo que não está no resumo, consultar os CSVs diretamente.
3. "Qual o treino de hoje?" → cruzar o dia da semana com a estrutura do plano, os últimos 14 dias
   (o que já foi feito na semana, dias duros seguidos, o que cada grupo muscular já recebeu)
   e a recuperação (score do Bevel, HRV/FC de repouso vs. linha de base, sono). Ajustar se houver alerta.

## Registrar um treino (texto colado, print, exportação)

1. **Extrair** os campos para o esquema da tabela certa:
   - corrida → `corridas.csv` (+ `tiros.csv` se for intervalado com tiros identificáveis);
     JSON do Apple Watch → salvar em `raw/` e usar `scripts/importar_corrida_json.py --tipo <tipo>`
     (o tipo do treino não vem no JSON: confirmar com o Jivago)
   - academia (texto do Hevy) → salvar em `raw/hevy/` e usar `scripts/importar_hevy_texto.py`
   - prova → além da corrida, o resultado oficial (chip, oficial, colocação) em `provas.csv`
   - recuperação: card do Bevel → `recuperacao.csv` (recuperação, esforço e sono em %), uma linha por dia
2. **Nome do exercício** = nome exato do Hevy. Se for novo, acrescentar em `exercicios.csv` com `nome_pt` e `grupo`.
   Halteres: carga = soma dos dois. Unilateral: reps = soma dos dois lados.
3. **Não inventar dados.** Campo que não veio fica vazio. Se faltar algo importante (ex.: data, tipo da corrida),
   perguntar antes de gravar. Datas relativas ("ontem") são resolvidas no fuso de Lisboa.
4. **Não duplicar:** conferir se já existe registro para a mesma data/tipo (ou mesmo `fonte_id`/`strava_id`) antes do append.
   Correção de dado errado = editar a linha existente, não criar outra.
5. Mostrar ao Jivago, em poucas linhas, o que foi gravado.
6. Rodar `python3 scripts/gerar_estado.py`. Se sair com erro, corrigir os dados e rodar de novo.
7. Commit com mensagem `registro: <tipo> <data>` (ex.: `registro: intervalado 2026-09-29`) e push.
8. Atualizar o doc `fitness_log/estado_atual.md` no conhecimento do Projeto "Fitness 2026"
   com o conteúdo novo de `contexto/estado_atual.md` (ferramenta Projects). Se `plano.md` mudou, atualizar
   `fitness_log/plano.md` também. Se a ferramenta não estiver disponível na sessão, dizer isso no resumo.
9. Comentar brevemente o que chamar atenção (alertas novos, progressão de carga, FC dos tiros).

## Sincronizar (Strava + app Saúde) — também é o que a tarefa agendada faz

1. `git pull`. Ler `contexto/ultima_sync.txt` (data/hora UTC da última sincronização bem-sucedida).
2. **Strava** (conector do Strava): listar as atividades desde 3 dias antes da última sincronização
   (`list_activities` com `range_start` em horário local). A janela sobreposta é proposital: se uma execução
   falhar, a seguinte recupera; a deduplicação é pelo `strava_id` / `fonte_id`.
   - **Run** que não esteja em `corridas.csv` (`strava_id`): gravar com os dados do Strava (data, início,
     distância, tempo, FC via `get_activity_performance`), `fonte=strava`. Na esteira com GymKit, distância e
     velocidade do resumo são as da esteira (corretas). O nome/descrição da atividade costuma dizer o treino
     (ex.: "VO2 · 5×800m…"); se não disser, inferir pelas zonas e marcar "tipo a confirmar" nas notas.
     Se depois chegar o JSON do Apple Watch, o importador completa o registro.
   - **WeightTraining** com descrição "Registrado com hevyapp.com": salvar o texto em `raw/hevy/<id>.txt` e rodar
     `scripts/importar_hevy_texto.py --data <data> --treino <A|B|C|D|outro> --fonte-id <id> --rotina "<nome>"`.
     Treino pela rotina/conteúdo: Push → B, Pull → C, Lower/pernas → A; misto → outro. Exercício novo → `exercicios.csv`.
     WeightTraining sem descrição do Hevy (treino só no relógio) não entra na tabela de séries.
   - Ignorar alongamento/mobilidade (PhysicalTherapy), caminhada e outros esportes.
3. **App Saúde**: o atalho do iPhone grava em `raw/saude/AAAA-MM-DD_HHMM.txt`. Rodar `python3 scripts/importar_saude.py`
   (idempotente: preenche HRV da noite, FC de repouso, sono, passos e calorias em `recuperacao.csv`
   sem apagar os scores do Bevel).
4. Se houve dado novo: passos 6–8 do registro (gerar estado, commit `sync: <resumo>`, push, atualizar o Projeto).
5. Gravar a hora atual (UTC, ISO 8601) em `contexto/ultima_sync.txt` e commitar junto — mesmo sem dado novo,
   para registrar que a sincronização rodou.

## Regras

- Nunca editar `contexto/estado_atual.md` à mão: ele é gerado.
- Mudanças de plano (metas, paces, estrutura) vão em `contexto/plano.md`, só quando o Jivago confirmar.
- Parâmetros do script (início do bloco, FC máx, limiares de alerta) ficam no topo de `scripts/gerar_estado.py`.
- Chaves e tokens (GitHub, Strava) nunca no repositório nem na conversa.
- Exportações brutas ficam em `raw/` (versionadas no git: são a camada bruta que permite reprocessar tudo).
