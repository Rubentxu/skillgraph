# WI-75 — La cobertura del CLI ejecutado por subproceso se mide (y era deuda documentada desde WI-57)

- **Ciclo SDDK**: `p-b7740b96d79ec013/wi-75-subprocess-coverage-instrument`
- **Fecha**: 2026-10-02
- **Alcance**: instrumentación de medición. Sin cambios de comportamiento en `src/skillgraph/`.
- **Veredicto**: cerrado. La cobertura del CLI se mide de forma reproducible y AGENTS §6.3 se cumple.

---

## 1. Qué disparó el workitem

Medición de la cobertura real del repo contra el contrato de AGENTS.md §6.3
("CLI: ≥ 70 %"), que nadie había contrastado desde que WI-63 lo dejó anotado.

Con la configuración canónica (`pytest --cov=skillgraph.cli`, es decir
`[tool.coverage.run]` de `pyproject.toml`):

```
TOTAL (solo src/skillgraph/cli)          986 stmts   298 miss   65.86 %
src/skillgraph/cli/commands/expansion.py 253        145 miss   40 %
src/skillgraph/cli/commands/runs.py       86         50 miss   37 %
src/skillgraph/cli/commands/pack.py       75         38 miss   46 %
src/skillgraph/cli/support.py            107         31 miss   69 %
```

**65,86 % < 70 %**: prima facie, incumplimiento del contrato. La lectura
natural —"faltan tests"— habría carryjado a escribir tests para código que ya
estaba probado.

## 2. Por qué era falso

La suite ejercita la frontera CLI por **subproceso**
(`sys.executable -m skillgraph ...`, con `cwd=tmp_path`). `pytest-cov` mide
solo el proceso principal: todo el código que se ejecuta en otro proceso le
resulta **invisible**. El 40 % de `expansion.py` era exactamente el perfil de
las funciones que los tests lanzan como subproceso.

La deuda ya estaba documentada. `pyproject.toml` decía, bajo
`[tool.coverage.run]`:

> la cobertura de los tests CLI por SUBPROCESO no se instrumenta de forma
> fiable: sin parallel, los subprocesos se pisan .coverage (last-writer-wins);
> con parallel=true pytest-cov NO combina los ficheros […] Queda deuda de
> setup dedicado (COVERAGE_PROCESS_START + combine explicito)

Es decir: la alarma era **consecuencia de una limitación conocida del
instrumento**, no un hallazgo sobre los tests.

## 3. Causa raíz: cuatro ingredientes, no uno

| # | Ingrediente | Qué rompía sin él | Evidencia |
|---|---|---|---|
| 1 | Hook `.pth` que llama a `coverage.process_startup()` | Nadie lee `COVERAGE_PROCESS_START`; el subproceso no instrumenta nada. **Estaba colado a mano en el venv** (`a1_coverage.pth`, 2026-09-23) y **no estaba declarado** en `pyproject.toml` ni en `uv.lock`: en una máquina nueva la receta reproducía el 0 % en silencio | Mutación A |
| 2 | `parallel = true` en `[run]` | Todos los procesos escriben el mismo fichero; el último pisa a los demás. Es el "last-writer-wins" que WI-57 midió como "knowledge 95 % vs runs 9 %" en un mismo run | Mutación B |
| 3 | `data_file` **absoluto** | Los tests lanzan la CLI con `cwd=tmp_path`, así que un path relativo resuelve dentro del tmp de pytest — y pytest lo borra. Con path relativo se recuperaban **4** ficheros de datos (solo el principal) y `expansion.py` daba **0 %** pese a 15+ invocaciones reales; con absoluto, **26** ficheros y 45 % | Mutación C |
| 4 | **pytest-cov** para el principal, hook para los subprocesos, **mismo `data_file`** | Correr `pytest` a pelo (solo el hook) perdía el perfil del proceso principal: suite completa a **60 %** — `expansion.py` 82 % pero `runtime/locks.py` 35 % | Mutación E |

El ingrediente 4 se costó más de encontrar que los otros tres juntos: A/B sobre
un subconjunto daba `locks.py` 91 % **con y sin** `--no-cov`, igual que en runs
pequeños, y solo a escala de suite completa se manifestaba. Se aisló
midiendo tamaños de los ficheros de datos: en la suite completa el perfil de
`pytest` no estaba (ningún fichero ≥ 300 KB; el mayor pesaba 274 432 B y había
8 iguales, todos de subproceso).

## 4. Resultado

`bash scripts/coverage.sh` (suite completa, 2225 tests):

```
src/skillgraph/cli/__init__.py                     100 %
src/skillgraph/cli/parser.py                       100 %
src/skillgraph/cli/commands/knowledge.py            95 %
src/skillgraph/cli/commands/run.py                  96 %
src/skillgraph/cli/commands/runs.py                 86 %
src/skillgraph/cli/commands/promotion.py            85 %
src/skillgraph/cli/support.py                       85 %
src/skillgraph/cli/commands/expansion.py            82 %
src/skillgraph/cli/commands/pack.py                 78 %
src/skillgraph/cli/runner.py                        77 %
TOTAL repo                                           94 %
```

Comparación con la medición ciega:

| módulo CLI | antes (ciego) | real | §6.3 ≥70 % |
|---|---|---|---|
| expansion.py | 40 % | **82 %** | ✓ |
| runs.py | 37 % | **86 %** | ✓ |
| pack.py | 46 % | **78 %** | ✓ |
| run.py | 81 % | **96 %** | ✓ |
| support.py | 69 % | **85 %** | ✓ |
| runner.py | *excluido por `omit`* | **77 %** | ✓ |
| **CLI total** | **65,86 %** | **94 %** | ✓ |

**El contrato de §6.3 se cumple.** El "incumplimiento" era ceguera.

### Efecto secundario relevante

`cmd_expansion_apply` (266-339), la función que **WI-72 partió** de 92 a 73 LoC,
marcaba `268-338` — su rango entero — como no cubierto. Con el instrumento
correcto sale con cobertura real y solo le quedan ramas de error
(`270, 276-277, 279->286, 288-289`). El refactor de WI-72 **sí tenía red
end-to-end**; la medición no la veía.

## 5. Reproducibilidad (el punto que faltaba en WI-57/WI-63)

El hook `.pth` se verificó **ocultando el colado a mano** (`a1_coverage.pth`
renombrado a `.bak`) y ejecutando el script:

- El script detectó que faltaba y creó `coverage.pth` él mismo.
- Con el hook **generado**, `tests/test_h4_expansion_cli.py` dio
  `expansion.py = 45 %` — idéntico al del hook colado.
- El hook original se restauró después.

Una receta que solo funciona en la máquina de quien la escribió es una receta
que mide 0 % en silencio en la de los demás. Esta se auto-instala.

## 6. Verificación en ambos sentidos

`tests/test_wi75_subprocess_coverage.py`, 2 tests:

1. `test_subprocess_cli_coverage_is_recorded` — end-to-end, sin mocks:
   subproceso real de la CLI, `data_file` absoluto en `tmp_path`, `combine`
   explícito, y aserción sobre `analysis2` de `expansion.py`.
2. `test_coverage_script_pins_the_three_ingredients` — fija los 4 ingredientes
   **sobre el código del script**, no sobre el fichero entero (la cabecera
   comentada los menciona y una aserción sobre el cuerpo se satisfacía con el
   comentario mientras la config decía `parallel = false` — mutación no
   cazada el primer intento).

Mutaciones, todas cazadas:

| mutación | cambio | resultado |
|---|---|---|
| A | hook `.pth` ausente | FAILED (`assert []`, sin ficheros de datos) |
| B | `parallel = true` → `false` | FAILED (solo tras asentar sobre el código) |
| C | `data_file` → relativo | FAILED |
| D | sin comprobación previa del hook | FAILED |
| E | sin `--cov`/`--cov-config` | FAILED |

## 7. Salvedades honestas

- **El TOTAL no es comparable con la cifra canónica.** La config que genera
  el script NO aplica el `omit` de `pyproject.toml`
  (`__init__.py`, `__main__.py`, `cli/runner.py`), a propósito: así
  `cli/runner.py` queda visible en vez de desaparecer del informe. El 94 %
  cubre 5823 sentencias frente a las 5601 de la medición canónica. Comparar
  las dos cifras sin tener esto en cuenta sería engañoso.
- **La instrumentación multiplica el tiempo de suite**: 2225 tests en 172 s
  instrumentados frente a ~116 s sin instrumentar. Por eso `.pipeline.kts`
  **no** se toca: la CI canónica sigue corriendo pytest sin coverage, que es
  lo correcto. El script es una herramienta de medición, no un gate.
- **`coverage combine` deduplica por SHA-256** (`classify()` en
  `coverage/data.py`), así que "skipped N" cuenta ficheros idénticos: es
  pérdida nula, no un fallo. Descartado como causa tras medirlo.
- **Deuda lateral observada, NO resuelta aquí**: la suite reescribe
  `tests/uat-evidence/UAT-08.json` y `UAT-09.json` con el SHA de HEAD, así
  que `git status` queda sucio tras cualquier corrida y el campo `revision`
  queda siempre un commit por detrás. Es un ciclo auto-referencial. Se
  reporta al operador; no se toca en este workitem porque es una decisión de
  producto sobre qué significa la evidencia, no un bug de instrumentación.
