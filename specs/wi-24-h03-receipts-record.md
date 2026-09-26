# WI-24: deuda H-03 (governance.receipts.record_validation_receipt cc=14)

## Objetivo

Reducir cc de `record_validation_receipt` (cc=14) en
`src/skillgraph/governance/receipts.py`. El alto cc venia de:

1. Una cadena de 6 checks `if not X: raise ValidationError(...)`.
2. La construccion in-line del Source + Evidence (3 sentencias
   compuestas).

## Cambio

`record_validation_receipt` queda como orquestador (cc=5) con 4
helpers privados:

- `_require_non_empty(value, *, field, empty_msg="vacio")` (cc=2):
  smart constructor string no vacio. `empty_msg` kwarg
  preserva genero del mensaje historico ("revision vacia",
  "command vacio", etc.).
- `_require_known_verdict(result)` (cc=2): exige pertenencia a
  `RECEIPT_VERDICTS` con mensaje "result invalido: ...".
- `_require_artifact_exists(artifact_path)` (cc=2): exige que el
  path apunte a un archivo en disco.
- `_persist_validation_evidence(controller, *, receipt, source_id,
  timestamp)` (cc=1): encapsula Source+Evidence register.

## Decision previa (D-56)

- **D-56**: Smart constructors `_require_*` con kwarg opcional
  `empty_msg` para preservar genero historico de los mensajes
  sin perder la consolidacion del patron.
- **D-57**: Persistir `_X_evidence` se extrae a helper cuando hay
  register_source + register_evidence acoplados a una entidad del
  dominio (no son dos llamadas independientes).

## Compatibilidad

- 100% backward-compatible: mensajes de error preservados verbatim
  (incluido genero "revision vacia").
- Misma ruta de exito (mismo receipt_id, mismo Source, misma
  Evidence).
- 51/51 tests PASS en el area receipts+attestation+governance.

## Evidencia

- `record_validation_receipt` cc: 14 -> 5.
- 4 helpers extraidos, cc <= 2 cada uno.
- 1044/1044 PASS en suite completa (193.52s).
- ruff: All checks passed.
