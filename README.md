# fitness_log

App-agnostic training database (running, strength, recovery/health) for Jivago's hybrid 5K/10K program.
The CSVs in `data/` are the source of truth; Strava, Hevy, the Apple Watch, Apple Health and Bevel are only
ingestion sources. Data and code are in English; the human-facing summary (`context/status.md`), the plan and
free-text notes are in Portuguese.

```
data/              tables (CSV, UTF-8, comma-separated, dot decimal)
context/
  plan.md          the program: goals, weekly structure, calibrations (edited by hand, Portuguese)
  status.md        GENERATED — last 14 days, weekly volume, races/PRs, loads, recovery, alerts (Portuguese)
  last_sync.txt    UTC timestamp of the last successful Strava/Health sync
scripts/
  build_status.py      validates the CSVs and regenerates context/status.md
  import_watch_run.py  Apple Watch run export (JSON) → runs.csv
  import_hevy_text.py  Hevy workout text (app share text or Strava description) → strength_sets.csv
  import_health.py     Apple Health samples sent by the iPhone shortcut → daily_health.csv
raw/               versioned raw layer: Apple Watch JSON, raw/hevy/ (Hevy text), raw/health/ (iPhone shortcut)
docs/              guides (health_shortcut.md: the iPhone shortcut)
```

**GitHub is the source.** Every write happens in a clone and is pushed; the Mac copy only runs `git pull`.
A scheduled Claude task syncs Strava and Apple Health twice a day (08:50 and 22:50 Lisbon).
`context/status.md` and `context/plan.md` are mirrored into the "Fitness 2026" Claude Project
(as `fitness_log/estado_atual.md` and `fitness_log/plano.md`) so every conversation starts from real data.
The operating protocol for Claude is in `CLAUDE.md`.

Flow: record/sync → `python3 scripts/build_status.py` → commit → push → update the Project copy.

## Data dictionary

Conventions: dates `YYYY-MM-DD` (Europe/Lisbon); durations `m:ss` or `h:mm:ss`; empty field = no data.
Pace and speed are never stored for whole runs: they are derived from distance and duration.

### runs.csv — one row per run
| column | description |
|---|---|
| id | `YYYY-MM-DD-n` (n = 1, 2… when there is more than one run that day) |
| date, start_time | local date and `HH:MM` start |
| type | `interval` · `tempo` · `long` · `z2` · `recovery` · `race` · `test` |
| location | `treadmill` · `road` · `track` |
| distance_km | total distance, warm-up and cool-down included (treadmill with GymKit: machine distance) |
| duration | moving time |
| hr_avg, hr_max | bpm |
| z1_s … z5_s | seconds in each heart-rate zone (Apple Watch zones, HRR method, HR max 192) |
| cadence_spm | average cadence (steps/min) |
| elevation_m | elevation gain (on the treadmill it reflects the incline) |
| power_w, gct_ms, vertical_osc_cm, stride_m | Apple Watch running dynamics (power, ground contact time, vertical oscillation, stride) — outdoor only |
| rpe | perceived effort 1–10 |
| temperature_c | relevant for races and outdoor runs |
| source | `apple_watch` · `strava` · `manual` |
| source_id | Apple Watch workout uuid (JSON) — prevents double imports |
| strava_id | Strava activity id |
| notes | free text (Portuguese): workout structure, feelings, "tipo a confirmar" |

### intervals.csv — one row per rep (links to runs.id)
| column | description |
|---|---|
| run_id | `runs.id` |
| rep | rep number (1, 2, …) |
| distance_m / duration | fill what exists; with both, speed is derived |
| speed_kmh | treadmill speed (preferred on the treadmill) |
| recovery | recovery duration after the rep |
| hr_peak | max HR in the rep |
| hr_end_recovery | HR at the end of the recovery (recovery quality) |

### strength_sets.csv — one row per set
| column | description |
|---|---|
| date | session date |
| workout | `A` (lower body/core) · `B` (push) · `C` (pull) · `D` (core + Z2 circuit) · `other` |
| exercise | canonical name = Hevy name, as logged (key of `exercises.csv`) |
| set | set number |
| set_type | `normal` · `warmup` · `drop` · `failure` (warm-ups are excluded from volume) |
| weight_kg | load as logged in Hevy. **Dumbbells: sum of both** (2 × 20 kg = 40). Bodyweight = empty |
| reps | reps. **Unilateral: sum of both sides** (10 + 10 = 20) |
| rpe | optional |
| notes | free text; the first set carries the Hevy routine name |
| source_id | Strava activity id (prevents double imports) |

### exercises.csv — exercise dimension
`exercise` (Hevy name, key) · `name_en` (English name) · `muscle_group` (`chest`, `back`, `shoulders`, `biceps`,
`triceps`, `quads`, `hamstrings`, `glutes`, `adductors`, `calves`, `core`, `cardio`) · `notes`.
Every new exercise in `strength_sets.csv` needs a row here (the status script warns).

### races.csv — one row per race (official result)
`date` · `name` · `location` · `distance_km` (official distance) · `chip_time` · `gun_time` · `overall_place` ·
`category_place` · `run_id` (links to the watch data in `runs.csv`) · `notes`.
Personal records come from here (chip time), not from the watch.

### daily_health.csv — one row per day
| column | description |
|---|---|
| bevel_recovery_pct, bevel_strain_pct, bevel_sleep_pct | Bevel scores (0–100) from the daily card: recovery and sleep refer to that morning, strain accumulates during the day |
| hrv_ms | night mean HRV (Apple Watch SDNN, 18:00 the day before → 14:00) |
| resting_hr | resting heart rate (bpm) |
| sleep_h, deep_sleep_h, rem_sleep_h | hours asleep in the night ending that day (overlapping samples counted once) |
| steps, active_kcal, basal_kcal | daily totals from Apple Health (highest total received; the next morning closes the day) |
| vo2max | Apple Watch VO2 max estimate ("Cardio Fitness", mL/kg/min), latest sample of the day |
| source | `bevel` · `health` · `bevel+health` |
| notes | free text |
