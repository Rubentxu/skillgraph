# WI-80 — un rechazo ilegible se degradaba a `PROPOSED` sin avisar: corregido

- **Fecha:** 2026-10-02
- **BASE:** `d01e96f` (post-release `v0.16.12.dev0`)
- **Commit:** `eb19942`
- **Tipo:** `fix` → PATCH
- **Origen:** punto (h) de `STATE.yaml.roadmap.next_workitem`, que dos
  bloqueslo dieron por cerrado sin ejecutar sin ejecutar

## El defecto

`_collect_rejection_ids` (`expansion.py:73`) se saltaba con `continue` un
`expansion_rejections/*.json` ilegible. El `proposal_id` se perdía,
`_infer_proposal_stage` caía a `PROPOSED`, y `expansion list` imprimía:

```
- <proposal_id>: stage=PROPOSED author=... created_at=...
```

con **exit 0** y **sin una línea de aviso**, para una propuesta que **sí
fue rechazada** y tiene su evidencia persistida en disco.

Dos consecuencias medidas:

1. Un operador que filtra por `--stage REJECTED` **no la ve**: la
   propuesta desaparece del filtro.
2. Un operador que lee la lista concluye que hay una propuesta
   **pendiente** que en realidad ya fue rechazada.

Es peor que un simple dato ausente. `None` y «no aparece en la lista» son
afirmaciones que el operador puede interpretar; aquí la degradación es la
**afirmación contraria**, y silenciosa.

## Por qué no se corrigió en su día, y por qué el criterio era erróneo

El bloque WI-72..WI-81 lo midió, escribió una red de 6 tests que
**consignaban el defecto** a propósito, y decidió no tocarlo con este
razonamiento: *«cambiar la salida de `expansion list` es cambio de
contrato externo del CLI (AGENTS §6.4) y tiene un coste de migración de
consumidores»*.

El criterio era erróneo por una confusión concreta: **cambiar un
contrato no es corregir una afirmación falsa**.

- El contrato de `--stage REJECTED` nunca fue «oculta las rechazadas cuyo
  fichero está roto». Eso nunca fue un contrato; fue un
  defecto.
- Ningún consumidor razonable depende de que se imprima `stage=PROPOSED`
  para algo que sí fue rechazado.
- La corrección hace el contrato **más honesto**, no menos.

El propio proyecto ya tenía el criterio escrito en
`knowledge/git_source.py:365`:

> Antes devolvía `{}` ante cualquier fallo, y ese `{}` viaja dentro del
> Source.locator. Un repo roto, o no-repo, se convertía así en un Source
> que afirma 'no hay cambios pendientes': un dato plausible y falso, que
> es peor que un error.

Y `governance/backups.py:358` acota el alcance:

> Backup corrupto o sin manifest: lo ignoramos en `list`, pero NO lo
> borramos (preservar evidencia para el operador).

## El fix, y por qué no adivina

La pieza que faltaba medir: **cómo se nombra un fichero de rechazo**.
`record_rejection` (`graph_expansion.py:618`) escribe siempre:

```python
target = target_dir / f"{proposal.proposal_id}.json"
```

Es decir, **el stem del fichero ES el `proposal_id` por construcción**.
Recuperarlo no es una heurística: es la convención de escritura leída al
revés.

`_collect_rejection_ids` deja de saltarse el fichero:

- JSON ilegible → `ids.add(p.stem)` y se registra en `unreadable`.
- JSON válido pero sin `proposal_id` → mismo tratamiento.
- Devuelve un `RejectionScan(ids, unreadable)` (dataclass frozen, slots).

`list` y `show` usan `scan.ids` y llaman a `_warn_unreadable_rejections`,
que escribe en **stderr**:

```
WARNING: evidencia de rechazo ilegible en <path>; se infiere proposal_id=<stem> del nombre del fichero
```

### Por qué el aviso es obligatorio

Sin él, la corrección habría sustituido una mentira silenciosa por otra
más pequeña: decir `REJECTED` **como si la evidencia estuviera sana**.
El operador necesita distinguir «lo sé porque lo leí» de «lo sé porque el
nombre del fichero lo dice».

Y por eso el aviso es **por lectura fallida**, no por presencia de
rechazos: si `list` gritara en cada rechazo, el aviso dejaría de informar.
Hay un test que fija exactamente eso.

### Lo que NO cambia

- El listing sale con **exit 0**: una sola evidencia corrupta no debe
  volver inútil el comando.
- El fichero roto **no se borra**: se preserva para el operador
  (`backups.py:358`).

## Alcance, medido y no supuesto

**No era un falso éxito de escritura.** `cmd_expansion_apply` no consulta
`_collect_rejection_ids`; re-aplicar una propuesta rechazada la re-valida
contra el plan. `apply` es idempotente por re-validación, no por consulta
del registro de rechazos. El alcance era de **visualización**
(`cmd_expansion_list` y `cmd_expansion_show`).

## La red

`tests/test_wi80_expansion_rejection_visibility.py` pasa de **6 a 8**.

Los 4 tests que consignaban el defecto **se invierten, no se borran**:
describían el comportamiento real, y ahora describen el correcto
(AGENTS §6.2 — un test cuyo objeto desaparece se borra; uno cuyo
*contrato* cambia deliberadamente se actualiza).

| Antes (fijaba el defecto) | Ahora (fija el contrato) |
|---|---|
| `test_ilegible_se_salta_en_silencio` | `test_ilegible_conserva_el_id_por_nombre` + `unreadable` no vacío |
| `test_ilegible_cambia_el_stage_inferido` → `PROPOSED` | `test_ilegible_ya_no_cambia_el_stage_inferido` → `REJECTED` |
| `test_caso_corrupto_muestra_proposed_y_no_avisa` | `test_caso_corrupto_sigue_diciendo_rejected_y_avisa` |
| `test_filtrar_por_rejected_oculta_la_propuesta` | `test_filtrar_por_rejected_la_sigue_listando` |

Nuevos:

- `test_json_valido_sin_proposal_id_tambien_se_recupera` — mismo nombre,
  misma regla.
- `test_evidencia_sana_no_avisa` — cierra el contrato por el otro lado. Sin
  este test, «avisar siempre» parecería una mejora.

## Mutaciones

`.pipelinek/wi80b_mutate.sh` — 3/3 cazadas:

| # | Mutación | Resultado |
|---|---|---|
| M1 | vuelve el `continue` silencioso (el defecto original) | 4 failed, 4 passed |
| M2 | recupera el id **sin** avisar — la misma mentira, más pequeña | 1 failed, 7 passed |
| M3 | avisa también con evidencia sana (ruido) | 2 failed, 6 passed |

M2 es la que importa: demuestra que el fix no es «que el id aparezca» sino
«que el id aparezca **y se diga de dónde salió**».

## Verificación

```
$ mise exec -- uv run pytest -q
2416 passed in 107.09s (0:01:42)
```

- Afectados (`-k 'expansion or h4 or cli'`): 352 passed
- H4 (emisores de UAT-08/09): 6 passed
- `ruff check` y `ruff format` limpios
- CI canónica: `Pipeline finished with SUCCESS`

## Conocimiento negativo

- Una red puede **consignar un defecto a propósito** y seguir siendo verde
  durante bloques. Es útil para caracterizar, pero envejece: cuando el
  defecto se corrige, esos tests pasan a afirmar lo contrario de lo
  correcto y hay que invertirlos, no borrarlos.
- «No tocar el contrato externo» es un criterio correcto en general y
 fue aplicado aqui donde no procedia. Distinguir **cambiar un contrato**
  de **corregir una afirmación falsa** es la lección; el resto del
  criterio sigue en pie para lo que de verdad es contrato.
- Un fichero cuyo nombre lo determina el dato que contiene es un canal de
  recuperación **legítimo**. Antes de inventar una heurística, mirar cómo
  se escribió el fichero.
