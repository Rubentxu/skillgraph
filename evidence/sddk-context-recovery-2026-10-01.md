# Recuperación de contexto SDDK, migración de identidad y cierre documental de ciclos

Fecha: 2026-10-01
Sesión: recuperación de contexto tras corte (operador: "recuperamos
contexto de trabajo con sddk de este proyecto para evaluar como
continuar").

## Qué es (y qué no es) este documento

Es una **nota de estado**: registra (1) la migración de identidad del
proyecto en el store SDDK, (2) el cierre documental de los ciclos que
quedaron OPEN en la identidad anterior, y (3) la re-evaluación del
bloqueador B4 sobre la build actual. NO es un recibo de release ni
introduce trabajo de runtime nuevo.

## 1. Migración de identidad (p-74299 → p-b7740)

El CLI SDDK deriva el `project_id` del remote URL. Entre el 29-sep y
el 1-oct el remote normalizó su casing
(`https://github.com/Rubentxu/skillgraph` →
`https://github.com/rubentxu/skillgraph`), de modo que la resolución
cambió de identidad:

| Campo | Identidad anterior | Identidad actual |
|---|---|---|
| `project_id` | `p-74299cf88f51dab9` | `p-b7740b96d79ec013` |
| `workspace_id` | `w-65c5e70e84b3c9144de10d74` | `w-dd5b21adcb48beb6137c0029` |
| Adoptada | 2026-09-26T11:47:36Z | 2026-10-01T19:40:15Z (`sddk adopt apply`, operador eligió re-adoptar limpio) |
| CLI | runtime 1.171.2 / 2.4.2 | sddk 2.5.3 |

**El historial de la identidad anterior NO se migra.** Queda archivado
en su store XDG (ledger con 84 eventos, 12 ciclos, 74 gate receipts,
backlog de 5 items). La evidencia canónica de este proyecto sigue
siendo la del repositorio: `specs/`, `evidence/`, `audits/`,
`CURRENT.md`, `STATE.yaml`, `SESSION-JOURNAL.md`.

Estado verificado tras `adopt apply`:

- `sddk adopt status` → `complete` (receipt + registro SQLite).
- `sddk knowledge status` → `vault_present: true`, `profile_present: true`.
- `sddk vault validate` → 0 nodos, 0 errores (vault nuevo, vacío, válido).
- `sddk cycle status` → `NoActiveCycle` (0 leases; acción legal
  siguiente: `sddk cycle start` cuando se abra trabajo nuevo).

## 2. Cierre documental de los ciclos OPEN de la identidad anterior

El ledger de `p-74299cf88f51dab9` registraba 6 ciclos en `OPEN` /
fase `explore`. Como esa identidad ya no es resoluble por el CLI
actual (decisión del operador: re-adoptar limpio, no recuperar la
antigua), el cierre es **documental**, en este fichero, con la misma
honestidad por ciclo que los absorbed cycles del 29-sep. Verificación
de pertenencia: `git merge-base --is-ancestor <sha> HEAD` → exit 0.

| Ciclo | Trabajo | Commit(s) | ¿Ancestro de v0.16.8? | Veredicto |
|---|---|---|---|---|
| `wi-31-cast-storage-protocol` | cast del Protocol Storage eliminado; factor `Storage.knowledge_repository()` + 7 tests | `e82c670` (documentado en CURRENT.md, salió en v0.15.0) | sí | **CLOSED / superseded-by-release** |
| `wi-41-cli-god-module-dispatch` | `main` if-chain → tabla de dispatch única | `42fe765`, `a86a2b2`, `394dd0d` | sí | **CLOSED / superseded-by-release** |
| `wi-42-release-blocker-python` | establecido que el release planner SDDK exige `Cargo.toml` (no soporta Python); documento `audits/release-blocker-python-workspace.md` | documental | sí | **CLOSED / documented** (la limitación persiste; el camino manual está acreditado en `evidence/absorbed-cycles-release-receipt.md`) |
| `wi-43-extract-cli-parser` | parser CLI (409 LoC) extraído a módulo propio | `src/skillgraph/cli/parser.py` | sí | **CLOSED / superseded-by-release** |
| `wi-44-resolve-project` | resolución de proyecto centralizada en un único helper (elimina 21 construcciones repetidas) | `e55fc81`, `5885269` | sí | **CLOSED / superseded-by-release** |
| `wi-46-bool-integer-validation` | **sin trabajo**: 0 commits, 0 specs, 0 menciones en el repo | — | — | **DEFERRED / not started** — NO se cierra como absorbed porque no hay trabajo que absorber. Candidato a re-crear como ciclo en la identidad `p-b7740b96d79ec013` si el operador lo prioriza |

Nota de honestidad: cerrar wi-46 como "absorbed" habría sido un verde
falso del tipo que este repositorio prohíbe; se deja DEFERRED con su
contexto para que el próximo `cycle start` pueda retomarlo.

## 3. B4 re-evaluado sobre la build actual (sddk 2.5.3)

`evidence/blocker-B4-debt-report-context.md` documentaba que
`sddk debt report`/`debt gates` resolvían el contexto de **otro**
proyecto (`p-52b95ef55999f9de/kernel-cycle-8`) y respondían `PASS`
sobre `findings: []` (verde falso).

Re-prueba del 2026-10-01 bajo la identidad nueva:

```
$ sddk debt report /tmp/debt-skillgraph-20261001.json
error: debt detection is not implemented in this build, so there is no
report to read and no gate to evaluate.
```

**El falso verde está eliminado por diseño fail-closed**: la build
actual se niega a emitir reporte ni gate sin detección real, y explica
en el propio error por qué el comportamiento anterior era una
fabricación. Estado de B4: **mitigado** (el riesgo activo desapareció);
queda una limitación conocida: la detección de deuda no está
implementada en la build, de modo que los gates
`debt-severity-assigned` / `debt-priority-assigned` siguen **sin poder
usarse como evidencia** en la fase verify de este proyecto. La
alternativa sigue siendo el auditor propio: `python
audits/audit_debt.py` (reproducible, con smoke tests).

## 4. Drift de gobernanza detectado y corregido en esta sesión

`7e6df87` (HEAD del 29-sep) quedó posterior al tag `v0.16.8` con
`__version__ = "0.16.8"` puro → el gate
`tests/test_release_governance.py` fallaba (deriva que AGENTS §12
rechaza). Corregido en `2a3732b` (bump a `0.16.8.dev0` + STATE.yaml +
CURRENT.md; gate 2/2 en verde). El suelto de evidencias del 29-sep se
commiteó en `18e77d3`.

## 5. Estado de salida y próximo paso legal

- Repo: HEAD `18e77d3`, working tree limpio, gate de gobernanza verde,
  suite completa 1754/1754 (hook pre-commit, 2026-10-01).
- SDDK: adoptado limpio en `p-b7740b96d79ec013`, vault válido, 0 ciclos.
- Pendiente de decisión del operador: push de `2a3732b`+`18e77d3`
  (regla: el push lo aprueba el operador) y el siguiente ciclo
  (`sddk cycle start`), con wi-46 como candidato real junto a la deuda
  P2 registrada en el backlog anterior
  (`cmd_promotion_reconcile` cc=14, `_make_schema_validator` cc=13).

## 6. ADDENDUM — divergencia de pipelinek detectada al verificar esta sesión

Tras los commits, se ejecutó la CI local canónica. Resultado: la
verificación directa del árbol es verde (suite completa 1754/1754 dos
veces: hook pre-commit de `2a3732b` en 76.63s y ejecución directa en
78.14s; ruff limpio; gate de gobernanza 2/2), pero **pipelinek no
puede darse por verificado en esta sesión**:

1. **Run 1 (19:42 UTC): FAILURE falso.** El paso `unit-tests` fue
   declarado `StepFailed` a los ~10s con captura vacía, mientras el
   script real siguió ejecutando: el fichero `result.txt` del paso
   quedó en `0` (exit correcto) con mtime ~2 minutos después, justo la
   duración de la suite. Conclusión: el motor dio por muerto el paso
   mientras pytest seguía vivo y terminó bien.
2. **Run 2 (19:47 UTC): SUCCESS sospechoso.** Misma firma de ~10s en
   `unit-tests` (StepStarted 19:47:43.3 → StepFinished 19:47:53.5) con
   **cero `EchoOutputCaptured`**: 1754 tests no caben en 10s (mínimo
   observado en esta máquina: 76s). Verde sin evidencia de ejecución
   real.
3. **Causa raíz probable, con dos capas documentadas**:
   - **Versión sin gobernar**: el shim activo resuelve a pipelinek
     `0.43.0` (asdf; también instalados 0.45.0/0.46.0 y, en mise,
     0.40.0/0.43.0/0.46.0). El canon de AGENTS.md es `v0.39.0` y **no
     está instalado** en ninguna toolchain; ni `mise.toml` ni
     `.tool-versions` fijan la versión.
   - **Interferencia del runtime de escritorio**: en la captura de
     salida de los pasos del run 2 aparecen mensajes del recolector de
     ficheros del entorno agéntico (`mavis-trash: moved to trash:
     .../.cookie`): el mecanismo de supervisión por cookie del engine
     choca con la capa de ficheros del entorno donde se lanzó el run,
     y el motor interpreta la perturbación como muerte del paso
     (run 1) o cierra el paso sin ejecución visible (run 2).
4. **Este patrón ya tiene precedente en el repo**:
   `evidence/pipelinek-cache-does-not-invalidate-on-source-change.md`
   (verde falso por caché, regla fijada en v0.16.5). Aplicando la
   misma doctrina: un SUCCESS de pipelinek cuya unidad decisiva no
   tiene evidencia de ejecución no declara el repositorio verificado.

**Estado honesto de verificación de esta sesión**: árbol verificado
por ejecución directa (pytest 1754/1754, ruff, gate de gobernanza);
pipelinek queda **no concluyente en sesión agéntica** hasta que el
operador (a) fije la versión canónica (p. ej. `pipelinek = "0.39.0"`
en `mise.toml [tools]` o actualizar AGENTS.md al binario elegido) y
(b) ejecute un run de control fuera del entorno agéntico. Pendiente de
decisión del operador; no se modifica AGENTS.md sin su conforme.
