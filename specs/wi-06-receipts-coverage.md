# WI-06 — Coverage hardening: `governance/receipts.py`

> **WorkItem autonumerado**: WI-06
> **Sucesor de**: WI-04/05 (v0.14.5 housekeeping + release).
> **Severidad**: P2 (cumple contrato AGENTS §6.3 = ≥90% en módulos del core;
> valor: calidad + defense-in-depth en UAT-EVO-12..14, capa de governance).
> **Decisiones**: D-17, D-18.

## 1. Contexto y motivación

`src/skillgraph/governance/receipts.py` exporta 3 símbolos cubiertos por la
suite: `ValidationReceipt` (dataclass), `is_receipt_applicable` (función
pura), `record_validation_receipt` (I/O via `KnowledgeController`) y
`list_applicable_receipts` (I/O via `Storage`/`KnowledgeRepository`).

`tests/test_h14_validation_receipts.py` contiene 9 tests (4 cubriendo UAT-EVO-12,
2 UAT-EVO-13, 4 UAT-EVO-14) que ejercitan principalmente el camino feliz
(constructores válidos + `record_*` + `_payload_to_receipt` roundtrip).

**Cobertura actual medida** (HEAD `45a61cc`, baseline post-WI-04/05):

```text
src/skillgraph/governance/receipts.py     125     27     56     19    73%
Uncovered lines:
  98, 100, 102, 104, 106, 108, 110, 112, 116, 118, 122 (is_pass branch),
  184 (dep_revisions provided pero caller no las da),
  258, 260, 262, 264, 266 (record_validation_receipt early validations),
  367, 370, 373-374, 377-378, 380 (list_applicable_receipts defensive paths)
```

Resultado: 73% < 90% (umbral AGENTS §6.3 para módulos del core).
Esto es **deuda implícita** ya presente en `CURRENT.md` (línea "Modulos H11..H15"
publicada en WI-01) pero no resuelta por WI-02b/03/04/05 (todos enfocados
en refactor, no en cerrar lagunas de cobertura de los componentes
*no* modificados).

## 2. Alcance (in/out)

### 2.1 In scope

- Añadir tests rojos-then-green para cada rama uncovered identificada:
  - **Grupo A — `ValidationReceipt.__post_init__`** (10 ramas):
    - `receipt_id` vacío (L98), `command` vacío (L100),
      `revision` vacía (L102), `timestamp` vacío (L104),
      `verdict` ∈ ∉ `RECEIPT_VERDICTS` (L106), `tests_run` < 0 (L108),
      `tests_passed` < 0 (L110), `tests_passed > tests_run` (L112),
      `artifact_path` vacío (L116), `scope` vacío (L118).
  - **Grupo B — `is_receipt_applicable`** (1 rama):
    - `receipt.dependency_revisions` poblado pero caller pasa `None` (L184).
  - **Grupo C — `record_validation_receipt`** (5 ramas early):
    - `command` vacío (L258), `revision` vacío (L260),
      `result` ∉ `RECEIPT_VERDICTS` (L262), `artifact_path` vacío (L264),
      `scope` vacío (L266).
  - **Grupo D — `list_applicable_receipts`** (5 ramas defensive):
    - `row.kind != "validation_receipt"` (L367),
    - `content_json` no es str (L370),
    - `json.JSONDecodeError` (L373-374),
    - `_payload_to_receipt` lanza (L377-378),
    - `scope is not None and receipt.scope != scope` (L380).
  - **Grupo E — `ValidationReceipt.is_pass`** (L122):
    - Cubierto trivialmente en grupo A vía verdict `"fail"`.
    - Coverage adicional: `coverage_ratio` con `tests_run == 0` → 1.0 (L127-129).

### 2.2 Out of scope (deuda diferida)

- `uat-fixtures-auto-refresh` (P3 deferred en `debt-report.json`).
- `catalog-sqlite-direct-access` (P3 deferred).
- Migración `list_applicable_receipts` a `KnowledgeRepository` en vez de
  `Storage` (no hay ciclo de migration pendiente; WI-03 cerró el escape
  hatch `_conn`, el resto es estructuralmente válido).
- Tests para `KnowledgeController.record_evidence` y `_payload_to_receipt`
  indirectamente cubiertos ya.

## 3. Decisiones

- **D-17**: WI-06 = coverage hardening quirúrgico. NO incluye refactor
  ni cambios de contrato en `governance/receipts.py`. Solo tests.
  Justificación: TDD strict (AGENTS §6.1) — los tests rojos ejercitan el
  contrato actual; si rojo → ajustar contrato (en WI futuro).

- **D-18**: tras CI verde, bump `0.14.5 → 0.14.5.dev0` (housekeeping-style,
  no release). NO tag nuevo hasta aprobación explícita del operador.
  Justificación: AGENTS §7 + regla vigente "no `--force`" + decisión de no
  micro-release trivial (regla 6 del operator).

## 4. Criterios de aceptación (verificables)

| ID | Criterio | Comando |
|---|---|---|
| AC-1 | `governance/receipts.py` ≥90% coverage | `uv run pytest --cov=skillgraph.governance.receipts --cov-report=term-missing tests/test_h14_validation_receipts.py` |
| AC-2 | Suite completa sin regresiones (929 + N tests, todos PASS) | `uv run pytest --no-header -q` |
| AC-3 | `ruff format` limpio | `uv run ruff format --check src tests` |
| AC-4 | `ruff check` limpio | `uv run ruff check src tests` |
| AC-5 | Commit atómico con mensaje Conventional Commits | `git log -1 --format=%s` debe matchear `^(feat|fix|test|docs|chore|...)` |
| AC-6 | Bump `0.14.5 → 0.14.5.dev0` post-cambio, sin tag | `grep __version__ src/skillgraph/__init__.py` |
| AC-7 | `SESSION-JOURNAL.md` actualizado con entrada WI-06 | `tail -50 SESSION-JOURNAL.md` |
| AC-8 | `CURRENT.md` actualizado (cobertura + estado) | inspección |

## 5. Plan TDD (orden)

1. **RED**: escribir 12-18 tests en `tests/test_h14_validation_receipts.py`
   cubriendo Grupos A-E. Cada test verifica el contrato actual con un caso
   mínimo.
2. **GREEN**: ejecutar; algunos ya pasarán (cubiertos transitivamente), otros
   fallarán porque los argumentos no se validaban con `pytest.raises`. Tras
   ejecutar el suite, los rojos que aparecen son **bugs reales del dataclass
   validation** que el actual happy path no ejercita (regla TDD: rojo válido
   → fix mínimo).
3. **REFACTOR**: consolidar tests en clases (`TestReceiptValidation`,
   `TestRecordEarlyValidation`, `TestListDefensivePaths`); añadir docstrings
   que referencien UAT-EVO-* cuando aplique.
4. **COVERAGE CHECK**: ejecutar comando AC-1; verificar ≥90%.
5. **CI**: AC-2, AC-3, AC-4.
6. **DOC**: AC-7, AC-8.
7. **RELEASE-PREP**: AC-6.

## 6. Riesgos y mitigación

- **R1 — Tocar `governance/receipts.py` rompe 929 tests**: el spec es
  **solo tests** (no producción). Si algún test rojo revela bug en
  producción, NO se parchea producción en WI-06 — se documenta en
  `SESSION-JOURNAL.md` como WI-07 (fix) candidato. **Aplica regla
  `autonomo` §3 (CIERRE REAL)**: un criterio no cumplido se cierra por
  WI-07, no se mezcla.
- **R2 — Coverage no llega a 90%**: si tras AC-1 sigue <90%, identificar
  las líneas restantes y decidir: (a) añadir más tests (in-scope), o
  (b) documentar las ramas como `pragma: no cover` con justificación
  (e.g. `defensive-only`). Opción (b) requiere approval explícita del
  operador (regla autonomo §5).

## 7. Trazabilidad con la deuda existente

Esta WI cierra la línea "Modulos H11/H12/H13/H14/H15: governance/receipts.py 73%"
en `CURRENT.md` (WI-01 release notes) — **deuda implícita reconocida pero
no abordada por WI-02b/03/04/05**.

No contradice los 2 P3 deferred (UAT fixtures, catalog SQLite).
No requiere abrir nueva ADR (no cambia contrato).
