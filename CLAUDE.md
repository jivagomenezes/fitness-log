# Protocolo do fitness_log

Este repositório é a memória de treino do Jivago. Os CSVs em `data/` são a fonte da verdade;
esquemas e convenções estão no `README.md` (dicionário de dados). Responder sempre em português.

## Antes de responder qualquer pergunta de treino

1. Ler `contexto/estado_atual.md` (e `contexto/plano.md` quando a pergunta envolver plano, metas ou paces).
2. Se a pergunta depender de algo que não está no resumo, consultar os CSVs diretamente.
3. "Qual o treino de hoje?" → cruzar o dia da semana com a estrutura do plano, os últimos 14 dias
   (o que já foi feito na semana, dias duros seguidos, o que cada grupo muscular já recebeu)
   e a recuperação (HRV/FC de repouso vs. linha de base). Ajustar se houver alerta.

## Registrar um treino (texto colado, print, exportação)

1. **Extrair** os campos para o esquema da tabela certa:
   - corrida → `corridas.csv` (+ `tiros.csv` se for intervalado com tiros identificáveis);
     JSON do Apple Watch → copiar para `raw/` e usar `scripts/importar_corrida_json.py --tipo <tipo>`
     (o tipo do treino não vem no JSON: confirmar com o Jivago)
   - academia (texto do Hevy) → `academia.csv`, uma linha por série; aquecimento com `tipo_serie=aquecimento`
   - prova → além da corrida, o resultado oficial (chip, oficial, colocação) em `provas.csv`
   - recuperação (Bevel / app Saúde) → `recuperacao.csv`, uma linha por dia
2. **Nome do exercício** = nome exato do Hevy. Se for novo, acrescentar em `exercicios.csv` com `nome_pt` e `grupo`.
   Halteres: carga = soma dos dois. Unilateral: reps = soma dos dois lados.
3. **Não inventar dados.** Campo que não veio fica vazio. Se faltar algo importante (ex.: data, tipo da corrida),
   perguntar antes de gravar. Datas relativas ("ontem") são resolvidas no fuso de Lisboa.
4. **Não duplicar:** conferir se já existe registro para a mesma data/tipo (ou mesmo `fonte_id`) antes do append.
   Correção de dado errado = editar a linha existente, não criar outra.
5. Mostrar ao Jivago, em poucas linhas, o que foi gravado.
6. Rodar `python3 scripts/gerar_estado.py`. Se sair com erro, corrigir os dados e rodar de novo.
7. Commit com mensagem `registro: <tipo> <data>` (ex.: `registro: intervalado 2026-09-29`) e push.
8. Atualizar o doc `fitness_log/estado_atual.md` no conhecimento do Projeto "Fitness 2026"
   com o conteúdo novo de `contexto/estado_atual.md`. Se `plano.md` mudou, atualizar `fitness_log/plano.md` também.
9. Comentar brevemente o que chamar atenção (alertas novos, progressão de carga, FC dos tiros).

## Regras

- Nunca editar `contexto/estado_atual.md` à mão: ele é gerado.
- Mudanças de plano (metas, paces, estrutura) vão em `contexto/plano.md`, só quando o Jivago confirmar.
- Parâmetros do script (início do bloco, FC máx, limiares de alerta) ficam no topo de `scripts/gerar_estado.py`.
- Chaves de API (Strava, Hevy) nunca no repositório nem na conversa: segredos do GitHub ou `.env` (ignorado pelo git).
- Exportações brutas ficam em `raw/` (fora do git).
