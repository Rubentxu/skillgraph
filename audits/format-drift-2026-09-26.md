# Auditoría — drift de `ruff format` post-Etapa 7 + evolution-v2

**Fecha**: 2026-09-26
**WorkItem**: STEWARDSHIP-DT-FORMAT-DRIFT
**Trigger**: Inspección del estado de salud del repositorio al iniciar sesión
2026-09-26. `mise exec -- uv run ruff format --check src tests` reportó **15
archivos sin formatear** + 122 ya formateados. El CI gate `format/format --check`
estaba **roto** desde los commits H11-H15 evolution-v2 (5c52750 + 116a2b5,
2026-09-25).

**Tipo de deuda**: técnica testeable, cosmética, sin impacto funcional. La
lógica de los 15 archivos es idéntica antes y después del format; los tests
siguen pasando sin cambios semánticos.

## Inventario del drift

15 archivos con cambios pendientes de format:

| Archivo | Naturaleza del cambio | LoC delta |
|---|---|---|
| `src/skillgraph/governance/improvement.py` | línea en blanco extra post-docstring (l.318) | +1/-0 |
| `src/skillgraph/governance/receipts.py` | collapse raise ValidationError multilínea | -3/-1 |
| `src/skillgraph/knowledge/file_handoff.py` | collapse TypeError multilínea + tuples | -7/-4 |
| `src/skillgraph/knowledge/file_scope.py` | reorganización FILE_SCOPES + tuples | -19/+11 |
| `src/skillgraph/knowledge/file_signature.py` | collapse signatures + tuples | -5/-3 |
| `src/skillgraph/knowledge/knowledge_controller.py` | reorganización UnknownSourceError + tuples | -16/+4 |
| `tests/test_h11_file_signature.py` | reorganización fixtures (multi-line tuples) | -23/+6 |
| `tests/test_h12_file_signature_scopes.py` | reorganización fixtures | +8/-8 |
| `tests/test_h13_handoff_expert.py` | reorganización fixtures | -2/-2 |
| `tests/test_h14_validation_receipts.py` | reorganización fixtures + claims | -25/+18 |
| `tests/test_h15_improvement.py` | reorganización fixtures | -15/+5 |
| `tests/test_t3_s2_claim_message_no_claim_id.py` | collapse message args | -4/-4 |
| `tests/test_t3_s2_entity_message_no_entity_id.py` | collapse message args | -6/-6 |
| `tests/test_t3_s2_message_no_source_id.py` | collapse message args | -6/-6 |
| `tests/test_t3_threat_model_attestation.py` | reorganización fixtures | -42/+25 |

**Total**: 97 insertions, 188 deletions, **-91 LoC netos**.

## Naturaleza del drift

Verificada leyendo los diffs uno-por-uno:

1. **Collapse de f-strings multilínea a single-line** (5 sitios). Cuando el
   f-string cabe en `line-length=100` (configurado en `pyproject.toml`),
   ruff format lo colapsa. Esto pasa cuando el cambio anterior era una
   edición pequeña que dejó la línea en dos.

2. **Reorganización de llamadas con kwargs** (8 sitios). Cuando los kwargs
   exceden `line-length=100`, ruff format los reordena. Esto pasa tras
   añadir un kwarg nuevo.

3. **Reordenamiento de tuplas/listas en fixtures** (12 sitios). Tests H11-H15
   tienen fixtures con tuplas largas; el format las reordena para minimizar
   líneas.

**No hay cambios semánticos**. Verificado con:
- `ruff check src tests` post-format → All checks passed.
- `mise exec -- uv run pytest -q` → **855/855 PASS** en 251s, 0 regresiones.

## Origen del drift

Trazabilidad inversa (`git log --pretty=format:"%H %s"` por archivo):

- **5 archivos `src/skillgraph/`** — commits `116a2b5` (H15 governance
  improvement) + `c5f8a94` (H14 receipts) + `dc1ef18` (H13 handoff) +
  evolución H11/H12 (sesión 2026-09-25).
- **9 archivos `tests/`** — mismos commits de features H11-H15 + t3/t3-s2.

El patrón común: las features de evolution-v2 (H11, H12, H13, H14, H15)
se introdujeron en commits feature sin re-correr `ruff format` antes del
commit. La regla `AGENTS.md §6` ("TDD rojo → verde → refactor") **no
obliga** explícitamente a `ruff format` pre-commit, pero el CI gate
`format/format --check` queda roto tras cada feature.

**Recomendación para evitar regresión** (futuro ciclo, sin acción ahora):
añadir un pre-commit hook (`pre-commit` framework + `.pre-commit-config.yaml`)
que ejecute `ruff format --check src tests` y `ruff check src tests` antes
de cada commit. Coste estimado: ~30 min. No requiere spec operadora. Lo dejo
documentado en este audit como derivado.

## Verificación post-fix

```text
$ mise exec -- uv run ruff check src tests
All checks passed!

$ mise exec -- uv run ruff format --check src tests
137 files already formatted

$ mise exec -- uv run pytest -q
855 passed in 251.35s (0:04:11)
```

**CI gate `format/format --check`**: ✅ desbloqueado.

## Resultado

- 15 archivos reformateados.
- 0 cambios semánticos.
- 855/855 tests PASS (0 regresiones).
- ruff check + format limpios.
- Sin bump de release (style/format, sin cambio de contrato observable).

**Commit**: `3031795 style(format): cerrar drift de ruff format (CI gate desbloqueado)`.

## Próximos pasos derivados (opcionales, sin spec)

1. **Pre-commit hook** (recomendado): añadir `.pre-commit-config.yaml`
   con `ruff format --check` + `ruff check` + `pytest -q -x` antes de cada
   commit. Evita regresión de drift. Coste: ~30 min. No requiere spec.
2. **CI workflow**: añadir `.github/workflows/ci.yml` que ejecute
   `ruff format --check` + `ruff check` + `pytest` en cada push. Coste:
   ~20 min. No requiere spec.
3. **Audit de advisories upstream** (siguiente en backlog opcional del
   checkpoint 2026-09-25): verificar que pytest/ruff/pyyaml/dulwich no
   tengan GHSA advisories críticos. Requiere acceso a GitHub Security
   Advisories (sin red local, hacerlo en próxima sesión con red).
