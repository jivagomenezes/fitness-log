# fitness_log

Base de dados de treino (corrida, academia, recuperação) independente de aplicativo.
Os CSVs em `data/` são a fonte da verdade; Strava, Hevy e Bevel são apenas fontes de ingestão.

```
data/            tabelas (CSV, UTF-8, separador vírgula, decimal com ponto)
contexto/
  plano.md         o programa: objetivos, estrutura semanal, calibrações (editado à mão)
  estado_atual.md  GERADO — resumo dos últimos dias, volume, cargas, recuperação, alertas
scripts/
  gerar_estado.py  valida os CSVs e regenera contexto/estado_atual.md
raw/             exportações brutas (Hevy CSV, Strava JSON, prints) — fora do git
```

Fluxo: registrar treino → `python3 scripts/gerar_estado.py` → commit.
O `estado_atual.md` e o `plano.md` vão para o conhecimento do Projeto "Fitness 2026" no Claude,
para que toda conversa comece com o contexto real. Protocolo completo em `CLAUDE.md`.

## Dicionário de dados

Convenções gerais: datas `AAAA-MM-DD`; durações `m:ss` ou `h:mm:ss`; campos vazios = sem dado.
Nada de pace armazenado: pace e velocidade são sempre derivados de distância e duração.

### corridas.csv — 1 linha por corrida
| coluna | descrição |
|---|---|
| id | `AAAA-MM-DD-n` (n = 1, 2… se houver mais de uma no dia) |
| data | data da corrida |
| tipo | `intervalado` · `tempo` · `longao` · `z2` · `regenerativo` · `prova` · `teste` |
| local | `esteira` · `rua` · `pista` |
| distancia_km | distância total, incluindo aquecimento e desaquecimento |
| duracao | tempo em movimento |
| fc_media, fc_max | bpm |
| rpe | esforço percebido 1–10 |
| temperatura_c | relevante para provas e corridas na rua |
| fonte | `strava` · `manual` · `apple_watch` · `bevel` |
| strava_id | id da atividade no Strava (chave para a futura ingestão automática) |
| notas | texto livre: estrutura do treino, sensações |

### tiros.csv — 1 linha por tiro (liga com corridas.id)
| coluna | descrição |
|---|---|
| corrida_id | `corridas.id` |
| n | número do tiro (1, 2, …) |
| distancia_m / duracao | preencher o que existir; com os dois, a velocidade é derivada |
| velocidade_kmh | velocidade da esteira (preferir quando for esteira) |
| recuperacao | duração da recuperação depois do tiro |
| fc_pico | FC máxima no tiro |
| fc_fim_rec | FC ao fim da recuperação (mede a qualidade da recuperação) |

### academia.csv — 1 linha por série
| coluna | descrição |
|---|---|
| data | data da sessão |
| treino | `A` (inferiores/core) · `B` (push) · `C` (pull) · `D` (core + circuito Z2) · `outro` |
| exercicio | nome canônico, igual ao do Hevy (chave de `exercicios.csv`) |
| serie | número da série |
| tipo_serie | `normal` · `aquecimento` · `drop` · `falha` (aquecimento fica fora do volume) |
| carga_kg | carga como registrada no Hevy (halteres: por halter); peso corporal = vazio |
| reps | repetições |
| rpe | opcional |

### exercicios.csv — dimensão de exercícios
`exercicio` (nome Hevy) · `nome_pt` · `grupo` (`peito`, `costas`, `ombro`, `biceps`, `triceps`, `quadriceps`, `posterior`, `gluteo`, `panturrilha`, `core`, `cardio`) · `notas`.
Todo exercício novo em `academia.csv` precisa de uma linha aqui (o script avisa).

### recuperacao.csv — 1 linha por dia
`data` · `hrv_ms` · `fc_repouso` · `sono_h` · `recuperacao_pct` (score do Bevel, 0–100) · `fonte` · `notas`.
