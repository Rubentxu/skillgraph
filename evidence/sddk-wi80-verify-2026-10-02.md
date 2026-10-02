# WI-80 — un rechazo ilegible se presenta como `PROPOSED`, sin avisar

**Fecha**: 2026-10-02
**Ciclo SDDK**: `p-b7740b96d79ec013/wi-80-silent-handler-audit`
**Estado**: verificado, **sin cambios en `src/`**
**Suite**: 2362 → **2368 passed**

---

## 1. Origen: la señal que faltaba en el barrido

WI-76, WI-77, WI-78 y WI-79 atacaron cobertura baja, código muerto y
contrato de salida. Ninguno barrió la señal que el goal lista
explícitamente: **fallbacks silenciosos**.

Barrido mecánico de los 66 handlers de excepción de `src/skillgraph`
(`.pipelinek/wi80_scan_silent_handlers.py`):

| Clasificación | Nº |
|---|---|
| con cuerpo efectivo | **59** |
| cuerpo vacío (`pass`, sin cuerpo) | **0** |
| único cuerpo = `continue` | **7** |

Cero `pass` y cero handlers vacíos: el antipatrón 11.14.4 de AGENTS.md
no está presente en esa forma. Los 7 `continue` son "tolerancia a datos
corruptos" y todos llevan comentario que lo declara.

`return None` no se marca: en este repo es valor de negocio legítimo
(`git_source.py:375` distingue "no se pudo determinar" de "working tree
limpio" justamente devolviendo `None`).

## 2. Los cuatro `except Exception` anchos

AGENTS.md 11.14.4 señala `except Exception` sin re-raise ni registro. Hay
cuatro, y los cuatro están justificados en el propio código:

| Ubicación | Por qué | Qué hace con la causa |
|---|---|---|
| `governance/promotion.py:116` | Frontera con `apply_fn` inyectado | **Se pierde**: `mark_promotion_failed` solo escribe el status |
| `governance/graph_expansion.py:583` | Construir `WorkflowPlan` | Se convierte en `InvalidProposal` con el original en `reason` |
| `runtime/node_execution_delegations.py:260` | Frontera con el `Adapter` | Se guarda en el nodo FAILED |
| `knowledge/git_source.py:376` | `dulwich` falla con varias familias | `return None`, explícitamente **para no disfrazarse de "working tree limpio"** |

Los tres `except BaseException` (`platform/storage.py:476`, `:600`,
`platform/run_repository.py:559`) son rollback de transacción y
**re-lanzan** con `raise`. Correcto: estrechar a `Exception` dejaría el
`BEGIN` abierto ante un `ValidationError` o un `Ctrl-C`.

**Deuda declarada, no hallazgo**: `promotion.py:116` tiene un comentario
`DEUDA CONOCIDA` que dice que el motivo del FAILED no se persiste porque
`promotion_outbox` no tiene columna. Se comprobó: la tabla
(`platform/schema.py:253`) efectivamente no la tiene, no hay evento ni
log, y `tests/test_h7_promocion.py:198` ya afirma que FAILED no
reintenta. Es deuda **consciente y fijada**, no un hallazgo.

## 3. Hipótesis refutada: el registry incompleto

`_load_registry` (`cli/commands/expansion.py:109`) hace `continue`
cuando un resource tiene `spec_json` ilegible, así que sus capabilities
no entran en el registro. Ese registro alimenta `apply_expansion` y
`validate`.

Hipótesis: el registro incompleto hace que la validación de colisiones
concluya "sin conflicto" y acepte una propuesta que colisiona.

**Refutada por lectura del consumidor.** `graph_expansion.py:341`:

```python
def _check_capabilities(proposal, registry):
    """I3+I4: caps/deps NO en registry."""
    if any(not _ref_exists(cap, registry) for cap in proposal.capabilities_needed):
        violated.append("I3")
```

El registry es un **allowlist de existencia**, no un detector de
colisiones. Un registro incompleto hace que la comprobación **falle**
con I3, no que pase. Es *fail-closed*. Ninguna invariante (I0..I6)
depende de que el registro esté completo.

**Hipótesis retirada sin tocar código.**

## 4. El hallazgo: `_collect_rejection_ids`

El segundo `continue` con consecuencias es
`cli/commands/expansion.py:86`:

```python
for p in rejections_dir.iterdir():
    if p.suffix != ".json":
        continue
    try:
        d = json.loads(p.read_text())
    except (json.JSONDecodeError, OSError):
        continue          # <- el rechazo desaparece
    if isinstance(d, dict) and "proposal_id" in d:
        ids.add(str(d["proposal_id"]))
```

Un `expansion_rejections/*.json` ilegible se salta. El id de la
propuesta **no se registra**, y `_infer_proposal_stage`
(`expansion.py:52`, precedencia `ARCHIVED > APPLIED > REJECTED >
PROPOSED`) cae al último caso: **`PROPOSED`**.

### Por qué esto es peor que la tolerancia que sí tiene el repo

El repo ya tiene dos precedentes de degradación de dato corrupto, y los
dos son **honestos**:

`knowledge/git_source.py:365`:
> "Antes devolvía `{}` ante cualquier fallo, y ese `{}` viaja dentro del
> `Source.locator`. Un repo roto, o no-repo, se convertía así en un
> Source que afirma 'no hay cambios pendientes': un dato plausible y
> falso, que es peor que un error."

`governance/backups.py:358`:
> "Backup corrupto o sin manifest: lo ignoramos en `list`, pero NO lo
> borramos (preservar evidencia para el operador)."

En ambos casos lo que el operador ve es interpretable: `None` o
ausencia. Aquí la degradación es la **afirmación contraria** — "esta
propuesta NO está rechazada" — y se imprime sin una línea de aviso. Un
rechazo ilegible es un dato plausible y falso, exactamente el patrón que
`git_source.py` ya decidió corregir.

### Alcance medido, no supuesto

- **No es un falso éxito de escritura.** `cmd_expansion_apply` **no**
  consulta `_collect_rejection_ids`. Re-aplicar una propuesta rechazada la
  re-valida contra el plan, así que `apply` es idempotente por
  **re-validación**, no por consulta de rechazos. Nada se aplica dos
  veces por esta vía.
- **Es un defecto de visualización.** `cmd_expansion_list`
  (`expansion.py:450`) y `cmd_expansion_show` (`expansion.py:482`).
  Ambos devuelven `EXIT_OK`.

### Consecuencia operativa, medida

| Escenario | `sg expansion list demo` | `sg expansion list demo --stage REJECTED` |
|---|---|---|
| rechazo legible | `stage=REJECTED` | la lista |
| rechazo corrupto | `stage=PROPOSED`, exit 0, **sin aviso** | `(sin propuestas en stage=REJECTED)` |

Una propuesta rechazada **desaparece del filtro** y **aparece como
pendiente**. El fichero corrupto sigue en disco: la evidencia no se
borra, que es la parte correcta.

## 5. La red

`tests/test_wi80_expansion_rejection_visibility.py`, 6 tests, **sin
tocar `src/`**. Pone el caso base y el caso degradado lado a lado para
que la diferencia sea visible:

| Test | Qué fija |
|---|---|
| `test_legible_devuelve_el_id` | Caso base: 1 rechazo legible |
| `test_ilegible_se_salta_en_silencio` | Comportamiento real: se pierde, sin excepción ni aviso |
| `test_ilegible_cambia_el_stage_inferido` | `REJECTED` → `PROPOSED` |
| `test_caso_base_muestra_rejected` | Contrato externo del caso base |
| `test_caso_corrupto_muestra_proposed_y_no_avisa` | El defecto, con el fichero preservado |
| `test_filtrar_por_rejected_oculta_la_propuesta` | La consecuencia operativa |

## 6. Mutaciones

| # | Mutación | Resultado |
|---|---|---|
| M1 | `continue` → `raise` (la tolerancia se pierde) | **CAZADA**, 4 failed |
| M2 | Fallback por nombre de fichero: el rechazo ilegible cuenta como rechazado | **CAZADA**, 4 failed |

M2 es **la corrección candidata**: cuatro líneas que hacen que un
rechazo truncado siga contando. Que la red se ponga roja con ella es
justo lo que se busca — si el operador decide arreglar el defecto, el
test obliga a hacerlo de forma deliberada y a revisar la Doc.

## 7. Por qué no se corrige aquí

Cambiar la salida de `expansion list` es **cambio de contrato externo del
CLI** (AGENTS.md §6.4) y tiene un consumidor: `--stage REJECTED`, que hoy
imprime `(sin propuestas en stage=X)`.

Además hay dos salidas posibles y no son equivalentes:

1. **Fallback por nombre** (M2). El marcador se llama
   `<proposal_id>.json`, así que el id es recuperable aunque el JSON esté
   truncado. Barato, y para el truncamiento funciona. Pero un fichero
   con el nombre cambiado o renombrado a mano daría un `proposal_id`
   equivocado: convertiría "no sé" en "sí, rechazada", que es un falso
   dato en la dirección contraria.
2. **Aviso explícito.** `list` imprime qué ficheros no se pudieron leer
   y con qué error, sin cambiar la clasificación. Es el patrón de
   `backups.py` ("lo ignoramos en list, pero preservamos evidencia"),
   con el aviso que aquí falta.

La segunda es la que encaja con el criterio del repo, pero **elegirla es
decisión de producto**: cambia la salida de un comando publicado.

## 8. Lo que este workitem no hace

- **No toca `src/`.** El defecto se reporta y se fija con test.
- **No "corrige" `_collect_rejection_ids`.** Ver §7.
- **No reabre la deuda de `promotion.py`.** Está declarada y fijada (§2).
- **No fuerza ningún ciclo a `CLOSED`.** Ver el estado de ciclos en el
  recibo de cierre.

## 9. Verificación

```
2362 passed in 95.32s        (CI canónica sobre d69879f)
2368 passed                  (suite con la red WI-80)
ruff check: All checks passed!
ruff format --check: limpio
src/ sin modificar: 0 ficheros
```
