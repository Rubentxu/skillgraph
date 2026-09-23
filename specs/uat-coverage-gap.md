# Audit: cobertura UAT en CI (pytest vs uat_audit.py)

> Generada 2026-09-23 como verificación honest de qué UATs del
> blueprint se validan automáticamente en CI vs cuáles dependen
> de ejecución manual de `tests/uat_audit.py`.

## Contexto

`tests/uat_audit.py` (1651 LoC) implementa 16 funciones
`uat_NN()` que ejecutan cada UAT contra el binario `sg` real y
emiten `tests/uat-evidence/UAT-NN.json` con PASS/BLOCKED.

`scripts/ci.sh` ejecuta `uv run pytest --tb=short` pero NO
ejecuta `uat_audit.py`. Esto significa que cuando CI corre:
- ✅ Tests pytest validados (incluyendo `_emit_uat_xx_evidence`
  para UAT-08/09).
- ❌ UAT-05, UAT-10..13, UAT-15..16 NO validados en CI.

## Mapa de cobertura real

| UAT | pytest | uat_audit.py | Ambos | Gap |
|---|---|---|---|---|
| UAT-01 proyecto sin contaminacion | ✅ `test_cli_uat.py` | ✅ | ✅ | NO |
| UAT-02 aislamiento proyectos | ✅ `test_cli_uat.py` | ✅ | ✅ | NO |
| UAT-03 brick declarativo | ✅ `test_cli_uat.py` | ✅ | ✅ | NO |
| UAT-04 ejecucion determinista | ✅ `test_cli_run_uat.py` + `test_runcontroller.py` | ✅ | ✅ | NO |
| UAT-05 handoff con ContextRecipe | ❌ | ✅ `uat_05()` | ❌ | **SI** |
| UAT-06 recuperacion | ✅ `test_cli_run_uat.py` + 2 mas | ✅ | ✅ | NO |
| UAT-07 idempotencia | ✅ `test_cli_run_uat.py` + 2 mas | ✅ | ✅ | NO |
| UAT-08 ampliacion dinamica | ✅ `test_h4_expansion_cli.py` | ✅ | ✅ | NO |
| UAT-09 ampliacion no autorizada | ✅ `test_h4_expansion_cli.py` + `test_h4_expansion.py` | ✅ | ✅ | NO |
| UAT-10 invalidacion conocimiento | ❌ | ✅ `uat_10()` | ❌ | **SI** |
| UAT-11 asimilacion skill | ❌ | ✅ `uat_11()` | ❌ | **SI** |
| UAT-12 dominio especializado (Character/StoryArc) | ❌ | ✅ `uat_12()` (espera BLOCKED) | ❌ | **SI** (esperado: H6 no implementado) |
| UAT-13 promocion entre bases | ❌ | ✅ `uat_13()` (espera BLOCKED) | ❌ | **SI** (esperado: H7 no implementado) |
| UAT-14 codigo de terceros | ✅ `test_skill_importer.py` (`test_script_never_executes_during_import`) | ✅ | ✅ | NO |
| UAT-15 fuente maliciosa | ❌ | ✅ `uat_15()` | ❌ | **SI** |
| UAT-16 estado historico | ❌ | ✅ `uat_16()` | ❌ | **SI** |

**Resumen:**
- 9/16 UATs validados en pytest (56%).
- 7/16 UATs SOLO validados en uat_audit.py (44%).
- 2/7 (UAT-12, UAT-13) son esperados BLOCKED — H6/H7 no implementados.
- 5/7 (UAT-05, UAT-10, UAT-11, UAT-15, UAT-16) son gaps reales
  donde H3/H5 está implementado pero pytest no lo valida.

## Riesgos del gap

1. **Refactor silencioso.** Si alguien modifica
   `src/skillgraph/knowledge_invalidator.py` (H3 slice 4) sin
   actualizar `test_knowledge_invalidation.py`, los tests pytest
   siguen verde pero UAT-10 (invalidación) podría romperse en
   `uat_audit.py`. El CI no lo detectaría hasta que alguien
   ejecute el script manualmente.

2. **Falsa sensación de cobertura.** Los 284 tests pytest verde
   podrían sugerir "todo OK", pero UAT-05 (handoff con
   ContextRecipe) podría romperse sin que pytest se entere.

3. **Desincronización tests↔realidad.** `uat_audit.py` ejecuta
   el binario `sg` con flujos completos; los tests pytest suelen
   ser unitarios o in-process. La verificación E2E via binario
   es más realista para UATs que pytest no captura bien (e.g.
   UAT-05 que requiere un run completo con handoff).

## Recomendaciones (NO implementadas)

### Recomendación 1: pytest wrapper para uat_audit

Crear `tests/test_uat_audit.py` que importe las funciones
`uat_NN()` de `tests/uat_audit.py` y las ejecute dentro de
pytest, con timeout y captura de evidencia. Esto convierte
7 UATs (UAT-05, 10, 11, 14, 15, 16) en tests pytest
automáticos.

Esfuerzo estimado: 1-2 horas. Bajo riesgo (es wrapper, no
cambia lógica). Cubre los 5 gaps reales (excluyendo UAT-12/13
que son BLOCKED esperados).

### Recomendación 2: añadir uat_audit.py a CI

Modificar `scripts/ci.sh` para ejecutar
`uv run python -m tests.uat_audit` después de pytest. Esto NO
convierte uat_audit en tests pytest pero garantiza que corre
en CI (aunque sea un script).

Esfuerzo estimado: 15 min. Riesgo: si uat_audit es lento
(~1-2 min total estimado por 16 UATs), CI se alarga.

### Recomendación 3: marcar UAT-12/13 como skip en pytest

Crear tests pytest `test_uat_12_blocked_h6_not_implemented` y
`test_uat_13_blocked_h7_not_implemented` que asertan
explícitamente el estado BLOCKED esperado. Esto da
visibilidad en CI de que esos UATs están honestamente
bloqueados, no olvidados.

Esfuerzo estimado: 30 min. Cubre el "gap honesto" donde
UAT-12/13 NO se mencionan en pytest pero SI en uat_audit.

### Recomendación 4: documentar el contrato

Añadir a `AGENTS.md` una sección §13 "UAT coverage contract":
"Estos 9 UATs se validan automáticamente en pytest. Estos
7 UATs se validan solo al ejecutar `tests/uat_audit.py`
manualmente. UAT-12/13 son BLOCKED esperados hasta que H6/H7
se implementen."

Esfuerzo estimado: 10 min. Documentación pura.

## Mi propuesta

Recomendación 4 + Recomendación 1 (sólo los 5 gaps reales;
UAT-12/13 se documentan como esperados BLOCKED).

Si el operador aprueba:
- 1 commit con `tests/test_uat_audit.py` (wrapper pytest para
  uat_audit.py).
- 1 commit con AGENTS.md §13 (contrato de cobertura).
- Sin cambios funcionales al código de uat_audit.py.

## NO implementado en este commit

Este spec es DRAFT. La implementación requeriría refactor de
1651 LoC de script a suite pytest, lo cual es trabajo material
(1-2h). Mejor esperar visto bueno del operador antes de tocar
uat_audit.py.
