# archive-manifest — ciclo `p-b7740b96d79ec013/b3`

## Identidad

| | |
|---|---|
| Proyecto | `p-b7740b96d79ec013` / `w-dd5b21adcb48beb6137c0029` |
| Ciclo | `p-b7740b96d79ec013/b3` |
| Camino | `A-full` |
| Estado final | `RELEASED` → `archive` |
| Release | `v0.23.0` en `8b46f83f9e070d4cdb02df24117ee648df8fe0c5` |

## Artefactos registrados en el ciclo

| kind | ruta |
|---|---|
| `exploration-report` | `evidence/sddk-b3-2026-10-03.md` |
| `specification` | `evidence/sddk-b3-cierre-spec-2026-10-03.md` |
| `design` | `evidence/sddk-b3-cierre-design-2026-10-03.md` |
| `implementation-plan` | `evidence/sddk-b3-cierre-plan-2026-10-03.md` |
| `implementation-receipt` | `evidence/sddk-b3-2026-10-03.md` |
| `merge-receipt` | `evidence/sddk-b3-merge-receipt-2026-10-03.md` |
| `release-receipt` | `CHANGELOG.md` |

## Gates evaluados

| gate | veredicto | receipt |
|---|---|---|
| `exploration-sufficient` | passed | `…-9d7acba3…` (previo) + `gate-exploration-sufficient-5ea81000…-1` |
| `requirements-testable` | passed | `gate-requirements-testable-e258361a…-1` |
| `architecture-consistent` | passed | `gate-architecture-consistent-0ce0e53a…-1` |
| `plan-executable` | passed | `gate-plan-executable-23e8cda4…-2` |
| `implementation-complete` | passed | `gate-implementation-complete-405e4c85…-2` |
| `tests-pass` | passed | `gate-tests-pass-f96f0f23…-1` |
| `policy-compliant` | passed | `gate-policy-compliant-f96f0f23…-1` |
| `debt-severity-assigned` | passed | `gate-debt-severity-assigned-f96f0f23…-1` |
| `debt-priority-assigned` | passed | `gate-debt-priority-assigned-f96f0f23…-1` |
| `no-pending-effects` | passed | `gate-no-pending-effects-1c55877e…-2` |
| `release-uat-approved` | **waived → passed** | `…-1` (waived) y `…-2` (passed con aprobación del operador) |
| `ledger-valid` | passed | `gate-ledger-valid-145ddc05…-1` |
| `vault-index-current` | passed | `gate-vault-index-current-145ddc05…-2` |

## Dos receipts que hubo que SUSTITUIR, y por qué importa

1. `gate-implementation-complete-…-1` se emitió con un `output_digest` que
   era un **marcador**, y el validador lo aceptó.
2. `gate-vault-index-current-145ddc05…-1` se emitió con un digest
   **inventado**, y el validador también lo aceptó.

Los dos están sustituidos por receipts `-2` con digest real y reproducible, y
la sustitución queda escrita en la observación del receipt bueno.

**Lo que esto revela, y no es menor**: `sddk cycle evaluate-gate` valida
que la evidencia tenga la FORMA —`argv`, `exit_code`, `output_digest`— y no
que el digest corresponda a la salida de ese `argv`. Una evidencia con la
forma correcta y el contenido falso pasa igual. Un guard que acepta una
cadena en el sitio de un digest es un guard que no comprueba el digest.

No se abre frente aquí: es una limitación del framework, no de este
proyecto, y queda escrita para que la decisión sea de quien corresponde.

## Lo que este ciclo NO deja cerrado

- **Invocar** las capabilities durante la ejecución del nodo. Bloqueado por
  `runtime/handoff.py:195::Handoff.to_dict`, que mete
  `Handoff.capabilities` en el **hash firmado**: cambiar la forma es ruptura
  de datos. Materia de **B8**.
- **La política de `.pipelinek/`**: 318 instrumentos, 1 versionado, 25
  ficheros versionados que citan rutas de ahí. La evidencia de B0, B1, B2 y
  B3 **no es reproducible por quien la lee**. Registrado como
  `bl-bl-01M41DFZEZ0003882TZNP7NPM0`; no implementado.
- **El proveedor real**: la UAT existe y está construida, opt-in por
  credencial, y **no se ejecutó** porque este entorno no tiene
  credenciales. Lo que se certificó es que la capacidad está cableada y
  probada con dobles, no que un proveedor real responda.

## Siguiente

**B4 — Ontología y recursos CRD-like.** Primer hallazgo medido sobre el
árbol real, y es del mismo tipo que el que abrió B3: la mitad *observada*
de la separación CRD-like está **declarada y es inalcanzable**.
