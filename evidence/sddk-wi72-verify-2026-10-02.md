# WI-72 — Informe de verificación

> Ciclo `p-b7740b96d79ec013/wi-72-p3-expansion-apply`, fase Verify.
> Implementación en `0afd146`, corrección de flake en `a873d91`.
> Base del workitem: `dcc81b5`.

## 1. Requisitos: uno a uno

| Requisito | Cómo se verifica | Resultado |
|---|---|---|
| REQ-1 constructor único | `test_both_commands_delegate_to_one_builder` (AST sobre los dos comandos) | PASS |
| REQ-2 no-sobrescritura preservada | `test_apply_does_not_overwrite_existing_record` + `test_propose_overwrites_existing_record` + `test_write_json_respects_the_overwrite_flag` | PASS |
| REQ-3 encoding explícito | `test_written_payload_roundtrips_non_ascii` | PASS, **con hallazgo** (§4) |
| REQ-4 sin literales JSON en el flujo | `test_apply_flow_has_no_json_literal` (AST, 0 dicts con claves constantes) | PASS |
| REQ-5 sin `plan` de doble enlace | lectura del diff: el enlace al plan del `--plan-file` desaparece; el valor se conserva como argumento de la escritura | PASS |
| REQ-6 invariantes intactas | los 50 tests de expansion preexistentes, sin modificar | PASS |
| REQ-7 oráculo diferencial | §2 | PASS, **con corrección** (§3) |

## 2. Equivalencia medida

- `cmd_expansion_apply`: 92 → 73 LoC, cc 7 → 6, por debajo del umbral P3.
- `cmd_expansion_propose`: 25 → 19 LoC.
- Funciones P3: 6 → 5. God modules: 0. cc máximo del repo: 10.
- Los 50 tests de expansion (`test_h4_expansion_cli`,
  `test_h4_expansion_cli_slice3`, `test_wi52_cli_expansion_strangler`,
  `test_h9_cli_inproc_promo_pack`) pasan **sin haber sido modificados**.

## 3. La red cazó un defecto propio: el flake del reloj

La primera ejecución de la CI canónica dio **FAILURE con 2196 passed**:
`{'created_at': '2026-10-02T09:55:40+00:00'} !=
{'created_at': '2026-10-02T09:55:41+00:00'}`.

Diagnóstico: el defecto estaba en el **test**, no en producción.
`created_at` lo estampa `propose()` en cada invocación, y el oráculo
comparaba los payloads enteros de **dos procesos distintos**. Si el
segundo cae en el segundo siguiente, difieren en ese campo y solo en
ese. En local pasaban los dos dentro del mismo segundo; bajo la CI, con
cachés frías y ~92 s de suite, no.

Corrección: excluir el valor **por invocación** de la igualdad y exigir
que ambos sean ISO-8601 UTC. `proposal_id` **no** se excluye: es hash
estable del contenido y su igualdad es parte del contrato.

Verificado en ambos sentidos, porque excluir un campo puede cegar un
test: 5 ejecuciones seguidas en verde, y dos mutaciones de producción
sobre `created_at` (vacío, y con forma rota) cazadas por 2 tests cada
una.

## 4. Me equivoqué en la exploración y lo degradé

Afirmé en la exploración que la divergencia de `encoding` entre los dos
escritores era un bug de locale en `propose`. Al implementarlo se ve que
es **inerte**: `json.dumps` usa `ensure_ascii=True` por defecto, su
salida es ASCII puro y el `encoding` de `write_text` no toca un byte.

REQ-3 se degrada de "cambio de comportamiento deliberado" a "higiene
del formato". Los tres artefactos del ciclo (spec, design, plan)
quedaron corregidos. Unificar el `encoding` se mantiene porque fija el
formato en el código y no en el entorno, no porque arregle nada.

## 5. Mutaciones: seis, todas detectadas

| # | Mutación | Detectada por |
|---|---|---|
| M1 | quitar `authorization_mode` del constructor compartido | 3 tests |
| M2 | `overwrite=True` en `apply` | test de no-sobrescritura |
| M3 | reintroducir el literal en el flujo | test estructural AST |
| M4 | cambiar **solo el valor** de `operations` | oráculo de valores |
| M5 | `created_at` vacío | 2 tests |
| M6 | `created_at` con forma rota | 2 tests |

M4 es la que distingue un oráculo de verdad de un recuento de claves.

## 6. Severidad y prioridad de la deuda restante

- **Severidad**: ninguna introducida. El corte no añade deuda; elimina
  una clase (doble escritor de un contrato en disco).
- **Prioridad restante**: la deuda que este workitem NO cierra y que
  sigue viva es `aggregate_file_signatures` (86 LoC, cc 8), la única
  candidata P3 con cc alto que queda. Agendada como WI-73 en
  `STATE.yaml`, con la advertencia de que su corte toca la invariante
  de aislamiento UAT-EVO-08.
- **Descartadas por medición, no por opinión**: `build_parser` (409
  LoC, cc 1, declarativo), `compile_handoff` (90, cc 2) y
  `compile_handoff_from_scopes` (85, cc 1), ambas lineales.

## 7. Verificación de gobernanza

`Pipeline finished with SUCCESS`, runId `5578bf80`, 7 `StepStarted`,
7 `StepFinished`, 5/5 `StageFinished` en `success`, 0 `StepFailed`, y
`2197 passed in 92.09s` capturado en `EchoOutputCaptured`. Binario
`0.39.0` (el pineado en `mise.toml`). `.pipeline.kts` sin drift.
