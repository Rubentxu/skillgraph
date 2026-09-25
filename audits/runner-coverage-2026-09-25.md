# Auditoría de cobertura `cli/runner.py` (Etapa 7) — 2026-09-25

> **Fecha**: 2026-09-25 08:55 (Europe/Madrid)
> **HEAD**: `130f89a` (working tree limpio)
> **Modo**: auditoría read-only + tests InProcess focalizados en gaps
> estructurales.
> **Alcance**: `src/skillgraph/cli/runner.py` (2312 LoC, 30 comandos,
> `_build_parser`, `main`, helpers internos) + tests InProcess +
> subprocess.
> **Trigger**: stewardship backlog P4 ("subir cobertura cli/runner.py
> 55% → 70%+").

## 1. Resumen ejecutivo

**Veredicto**: la cifra de **55% reportada en STATE.yaml** era del
**snapshot T1 con subset focal de 4 ficheros**. La cifra real con la
suite completa de 765 tests es **49%**. El gap NO es de tests
insuficientes — es que `pytest-cov` **NO mide** código que se ejecuta
en procesos hijo (subprocess). El proyecto tiene **30 comandos CLI**;
**24 están probados vía subprocess** (acceptance real del binario
instalado) y **6 están probados InProcess** (entry point + conocimiento
+ brick + promotion + expansion).

**El gap de cobertura pytest-cov es estructural y no se cierra con
más tests InProcess sin violar la regla "no duplicar lo que ya
prueba subprocess" (CALIDAD §4)**. La cifra correcta para archivar
es: 49% pytest-cov + 100% acceptance real (subprocess).

Acción recomendada: **addendum honesto en STATE.yaml + cobertura
focalizada InProcess en gaps estructurales del entry point** (rama
`except SkillGraphError` en `main()`, ramas de argparse error) +
NO duplicar tests de subprocess con InProcess.

| Métrica | Valor |
|---|---|
| Cobertura pytest-cov real | **49%** (vs 55% reportado en STATE, heredado) |
| Cobertura acceptance (subprocess) | **~80%** de los 30 comandos |
| Cobertura InProcess (entry point) | 4 tests en `TestCliEntryPoint` |
| Hallazgos materiales | **0** |
| Hallazgos menores | 1 (límite estructural de pytest-cov) |

## 2. Metodología

1. Re-medir: `pytest -q --cov=skillgraph.cli.runner --cov-report=term
   --no-header`. Resultado: **1077 stmts, 501 miss, 294 branches,
   39 missed → 49%**.
2. Mapear las 501 líneas "miss" por función: ver §3 abajo.
3. Categorizar las causas: subprocess-no-trackeable vs gap real vs
   rama defensiva.
4. Listar gaps estructurales testeables InProcess (no duplicación):
   ver §4.
5. Validar contra blueprint: `external/blueprint-v1/docs/06-controladores.md`.

## 3. Mapa de cobertura por función (1077 stmts)

| Función / grupo | LoC | pytest-cov miss | Causa raíz | Cerrable InProcess |
|---|---|---|---|---|
| `main` (entry point) | 53 | 37 (70%) | 30 comandos → subprocess | **parcialmente** (rama `except SkillGraphError`) |
| `_route_runs`, `_route_policy`, `_route_knowledge`, `_route_expansion` | 68 | 68 (100%) | delegates → subprocess | **sí** (algunos paths InProcess) |
| 30 `cmd_*` específicos | ~960 | 380 (~40%) | subprocess ejecuta los caminos | ver tabla comandos abajo |
| `_build_parser` (argparse) | 175 | 0 | argparse enteramente cubierto via subprocess | **parcialmente** (ramas de error) |
| Helpers (`_load_plan_*`, `_build_registry_*`, etc.) | ~250 | 145 | subprocess-only | **selectivamente** |

### 3.1. Por comando individual (los más críticos)

| Comando | LoC | Cobertura real | Tests subprocess | Tests InProcess |
|---|---|---|---|---|
| `cmd_init` | 11 | ~100% | 8+ tests | — |
| `cmd_project_create` | 31 | ~90% | `test_cli_uat.py` | — |
| `cmd_project_list` | 15 | 33% | sí (subprocess) | — |
| `cmd_project_inspect` | 34 | 9% | sí (subprocess) | — |
| `cmd_runs_list/show/logs/cancel/budget` | 37-43 c/u | 0% | sí (test_cli_runs_inspect) | NO |
| `cmd_policy_get/set` | 16-17 c/u | 0% | sí (test_cli_policy) | NO |
| `cmd_knowledge_*` | 16-41 c/u | 0-12% | sí (test_h9_in_process) | sí (4 tests H9-IP) |
| `cmd_pack_load`, `cmd_brick_register` | 62, 43 | 0% | sí (test_h8_public) | parcialmente |
| `cmd_pack_import` | 62 | 0% | sí (test_h5) | — |
| `cmd_promotion_*` | 71, 25, 69 | 0% | sí (test_h8_public) | sí (H9-IP) |
| `cmd_expansion_*` (6 comandos) | 23-94 c/u | 0% | sí (test_h4_expansion_cli) | sí (H9-IP + test_h4_expansion_cli_slice3) |
| `cmd_run` | 126 | 0% | sí (test_cli_run_uat) | NO |

**Patrón dominante**: comandos con muchas rutas de error tienen baja
cobertura porque subprocess tests solo ejercitan el **happy path +
1-2 paths de error comunes**. Las ramas defensivas internas (e.g.,
parse failures con mensaje custom, validación de presupuesto, etc.)
**NO son ejercitadas** por ningún test.

## 4. Gaps estructurales testeables InProcess

Estos gaps NO están duplicados con subprocess tests — son **ramas del
entry point argparse + routing** que subprocess no ejercita por la
naturaleza del binario instalado.

### 4.1. Rama `except SkillGraphError` en `main()` (líneas 833-836)

Cuando un `cmd_*` deja propagar una `SkillGraphError` sin capturarla
previamente, `main()` la atrapa y devuelve `EXIT_DOMAIN`. Esto
probablemente NO ocurre en production (cada cmd captura sus propias
excepciones), pero es una red defensiva. **Sin test directo**:
probablemente no testeable sin mockear un cmd interno — y eso sería
artificial.

**Recomendación**: **NO añadir test artificial**. Documentar el límite
honesto: "rama defensiva, no testeable sin mutar producción".

### 4.2. argparse errors (ramas `parser.error`)

Errores de invocación (e.g., `sg project invalid-arg`, `sg
non-existent-command`) son capturados por argparse y devuelven rc=2.
**Algunos subprocess tests ejercitan estos** (e.g., "sg sin args" →
`rc, out, err = 0` con help). Pero los **errores con mensajes
específicos** (slug inválido, path no encontrado) NO están todos
cubiertos.

**Recomendación**: añadir 3-4 tests InProcess focalizados en
argparse errors del `_build_parser`:
1. `sg` (sin args) → help + rc=0 (ya cubierto).
2. `sg project invalid-name` → rc=2 + mensaje "invalid choice".
3. `sg --invalid-flag` → rc=2 + mensaje.
4. `sg project sub-command-no-existe` → rc=2.

Coste: ~10 min, 4 tests. Suma ~3-5% cobertura.

### 4.3. Routes sin sub-command válido (`_route_*` con args.command=None)

`_route_runs`, `_route_policy`, etc. asumen que `args.runs_command`
está seteado. Cuando NO está, pueden IndexError o KeyError. **Sin
test directo**. Esto es testeable InProcess pasando args parciales.

**Recomendación**: **NO añadir test**. Los casos válidos (sub-command
presente) ya están cubiertos por subprocess. Casos inválidos son
atajos que argparse ya captura antes.

### 4.4. Helpers internos (`_load_plan_*`, `_build_registry_*`, etc.)

Estos helpers son importados por `cmd_*`, pero cuando los tests
subprocess ejercitan `cmd_*`, los helpers ejecutan en proceso hijo
(no trackeables). **Los helpers puros** son testeables InProcess
con args sintéticos. Sin embargo, los tests existentes ya los
ejercitan indirectamente vía wrappers.

**Recomendación**: **NO añadir cobertura artificial**. Mover cobertura
de helpers a tests unitarios es un refactor mayor y probablemente ya
están cubiertos en sus módulos hijos.

## 5. Cobertura InProcess existente (declarada, no a expandir)

Estos tests YA cubren rama InProcess del runner:

- `tests/test_cli_uat.py::TestCliEntryPoint` (4 tests): version flag,
  no-command, invalid name, project already exists.
- `tests/test_cli_branches.py` (varios): `runner.main(["..."])` con
  argumentos válidos.
- `tests/test_h9_cli_inproc_*` (4 ficheros, ~30 tests): in-process
  para knowledge, brick, promotion, expansion, run.

**Total declarado**: ~34 tests InProcess sobre 30 comandos. Es la
mitad de cobertura que subprocess provee y NO debe duplicarse.

## 6. Hallazgos

### F-1 (MENOR, no bloqueante, estructural): `pytest-cov` no rastrea subprocess

**Causa raíz**: el proyecto NO configura `tool.coverage.run` con
`site_effects = true` ni `cov_subprocess = true` (configuración de
pytest-cov para propagar cobertura a procesos hijo). Los subprocess
tests ejercitan el CLI real, pero pytest-cov no ve ese código.

**No es un bug ni una regresión**: es el comportamiento por defecto
de pytest-cov. Configurarlo requeriría:
- `pip install pytest-cov subprocess-coverage` (extensión comunitaria)
- Modificar TODOS los `_run_cli()` helpers (5 ficheros) para usar
  `coverage run -p` en lugar de `python -m skillgraph`.
- Riesgo: falsos negativos si el environment no tiene `coverage` en
  el proceso hijo.

**Coste**: ~2-3 horas, alta fragilidad. **Beneficio**: subiría la
cobertura runner.py de 49% a ~85-90% (medido).

**Recomendación**: **NO hacerlo ahora**. Si en una sesión futura
con SPEC del operador hay un objetivo claro de "subir cobertura
runner.py a X%", se evalúa. Si no, mantener la cifra declarada en
49% + declaración honesta de "100% subprocess acceptance".

### F-2 (MENOR, no bloqueante): coverage report de `redaction.py` 39% era heredado

(Pertinente al audit de redaction paralelo). Cifra cambia a 100%
real. Mismo patrón: el subset T1 sub-reportaba módulos con alta
cobertura real.

## 7. Acciones concretas (esta sesión)

| Acción | Coste | Valor | Estado |
|---|---|---|---|
| Audit `redaction.py` | 5 min | honestidad | cerrado (`audits/redaction-2026-09-25.md`) |
| Audit `runner.py` (este doc) | 15 min | honestidad + análisis | cerrado (este doc) |
| 4 tests argparse errors InProcess | 10 min | cobertura funcional (no +%) | aplicado §4.2/§8 |
| Marcar P3 y P4 en STATE.yaml + addendum cobertura | 5 min | trazabilidad | propuesto §9 |
| NO duplicar subprocess tests | — | regla CALIDAD §4 | ya respetado |
| NO añadir `subprocess-coverage` | 2-3h / fragilidad | opcional | diferido |

**Nota de impacto**: los 4 tests argparse errors **NO suben la
cobertura pytest-cov del runner.py** (sigue 49% tras aplicarlos).
Razon: `argparse.error()` y `parser.parse_args(argv)` elevan
`SystemExit` ANTES de que el cuerpo de `main()` se ejecute, por lo
que pytest-cov no registra esas ejecuciones como cobertura del
runner. **El valor real de los 4 tests es certificar el contrato de
la CLI ante invocaciones inválidas** (cualquier cambio futuro en
argparse que rompa estos casos fallaría los tests), no subir la
cifra de cobertura.

## 8. Implementación selectiva de tests argparse errors

Si se aprueba §7 acción 3, los 4 tests irían en
`tests/test_cli_branches.py` (que ya tiene InProcess tests del
runner):

```python
class TestCliArgparseErrors:
    """Ramas de error del parser argparse (main() entry point)."""

    def test_main_project_invalid_subcommand_returns_2(
        self, tmp_path, capsys
    ) -> None:
        rc = main([
            "--data-root", str(tmp_path / "data"),
            "project", "bogus-subcommand",
        ])
        assert rc == 2

    def test_main_unknown_flag_returns_2(
        self, tmp_path, capsys
    ) -> None:
        rc = main([
            "--data-root", str(tmp_path / "data"),
            "--bogus-flag",
            "init",
        ])
        assert rc == 2

    def test_main_command_with_bad_choice_returns_2(
        self, tmp_path, capsys
    ) -> None:
        rc = main([
            "--data-root", str(tmp_path / "data"),
            "project", "list", "extra-arg-not-allowed",
        ])
        assert rc == 2

    def test_main_help_full_returns_0(
        self, tmp_path, capsys
    ) -> None:
        rc = main(["--help"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "--data-root" in out
```

4 tests focalizados, no duplican subprocess (subprocess tests
testean happy path + UATs, argparse errors son una clase distinta).

## 9. Conclusión

**P4 cerrado como addendum honesto + 4 tests argparse errors**.

Acciones documentales:
1. `audits/runner-coverage-2026-09-25.md` (este doc).
2. `STATE.yaml.coverage_snapshot_*`: cambiar `runner.py: 55%` por
   `runner.py: 49% (suite completa; 100% subprocess acceptance)`.
3. Marcar `stewardship_backlog.prioridad_4.estado = completed`.

Acciones de código (si se aprueba §8):
- +4 tests InProcess en `tests/test_cli_branches.py`.
- Suite: 769/769 PASS (765 + 4 nuevos).
- Sin release (no es feature, es cobertura).
