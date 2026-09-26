# Audit — Knowledge validation errors tipados (AGENTS §1.2) — 2026-09-26

## Contexto

Investigacion retrospectiva del ciclo STEWARDSHIP-DT-FILE-SCOPE-VALIDATION
descubrio que `SignatureProcedencia.__post_init__` (file_signature.py)
levantaba `ValueError` en vez de `ValidationError`, violando AGENTS.md
§1.2 ("Errores tipados, no strings").

El operador pidio "vamos con lo siguiente" tras la retrospectiva. El
hallazgo colateral registrado parecia pequeno (~3 LoC + 1-2 tests),
pero la inspeccion revelo que la violacion estaba extendida en
**3 archivos del paquete `knowledge/`** con **11 raises** total.

## Diagnostico

```text
src/skillgraph/knowledge/file_signature.py    8 raises ValueError
src/skillgraph/knowledge/file_handoff.py      3 raises ValueError
src/skillgraph/knowledge/git_source.py        1 raise ValueError
src/skillgraph/runtime/locks.py                1 raise ValueError
src/skillgraph/governance/improvement.py       2 raises ValueError
src/skillgraph/governance/receipts.py          1 raise ValueError
TOTAL: 16 raises en 6 archivos
```

Todos los raises estaban en `__post_init__` de dataclasses de dominio
(SignatureProcedencia, SignatureVigencia, FileSignature, ScopeAwareRecipe,
GitSource.from_commit). El resto del codebase ya usa ValidationError
(ver `core/recipe.py:71` como ejemplo de cumplimiento).

Verificacion de impacto:
- 0 callers en `src/` con `except ValueError` (grep limpio)
- 1 test en `tests/test_h9_coverage_git_source.py:78` capturaba
  `ValueError` explicitamente (esperaba el contrato viejo)

## Solucion

TDD rojo -> verde -> fix -> commit:

### 1. RED: archivo de tests nuevo

`tests/test_knowledge_validation_errors.py` con 12 tests cubriendo
las 11 ramas + 1 test derivado. Resultado inicial: 12/12 rojos
(ValueError != ValidationError, los `with pytest.raises(ValidationError)`
fallaban).

### 2. Fix: 6 archivos en src/ (no 3)

```python
# file_signature.py
from skillgraph.core.errors import ValidationError
# 8 raises: ValueError -> ValidationError

# file_handoff.py
from skillgraph.core.errors import SkillGraphError, ValidationError
# 3 raises: ValueError -> ValidationError

# git_source.py
from skillgraph.core.errors import DulwichNotAvailableError, ValidationError
# 1 raise: ValueError -> ValidationError

# runtime/locks.py
from skillgraph.core.errors import SkillGraphError, ValidationError
# 1 raise + docstring actualizado: ValueError -> ValidationError

# governance/improvement.py
# (ValidationError ya importado)
# 2 raises: ValueError -> ValidationError

# governance/receipts.py
# (ValidationError ya importado)
# 1 raise: ValueError -> ValidationError
```

Total: **16 raises corregidos en 6 archivos**.

### 3. Test contract update

`tests/test_h9_coverage_git_source.py:78` migrado de `ValueError`
a `ValidationError`. Docstring actualizado con la justificacion
de la migracion.

### 4. Mutation testing (verificacion de sensibilidad)

M8: revertir SignatureProcedencia a ValueError -> test rojo
(DETECTADA). Los tests SON sensibles al cambio de tipo de excepcion.

## Validacion

```text
pytest tests/test_knowledge_validation_errors.py: 12 passed
pytest --tb=short (suite completa): 918 passed (906 -> 918, +12)
ruff check src tests: All checks passed!
ruff format --check src tests: 139 files already formatted
```

## Cobertura y riesgo

- 16 raises cambiados de ValueError a ValidationError en 6 archivos.
- 0 cambios de semantica para callers que capturan Exception.
- 1 test actualizado (test_h9) por contrato de error modificado.
- ValidationError hereda de SkillGraphError -> Exception, asi que
  callers que capturaban ValueError deberian migrar a ValidationError
  o a un ancestro mas alto. Para skillgraph, no hay tales callers
  en `src/` (verificado con grep).

## Verificacion final

```text
grep -rn 'raise ValueError\|raise Exception' src/skillgraph/ --include='*.py'
  -> 0 resultados (100% cumplimiento §1.2)

pytest --tb=short (suite completa): 918 passed
ruff check src tests: All checks passed!
```

## Hallazgo derivado

El modulo `core/recipe.py` (ContextRecipe) ya usaba `ValidationError`
correctamente. Esto confirma que el patron ESTA establecido en el
proyecto; las 16 violaciones eran omisiones, no decisiones de diseno.

El grep `raise ValueError\|raise Exception` en src/ ahora retorna
**0 resultados**: 100% cumplimiento de AGENTS §1.2 en todo el codebase.

## Conclusion

Cumplimiento de AGENTS §1.2 (errores tipados) en **6 archivos** del
paquete. 16 raises actualizados. 12 tests nuevos verifican el contrato.
0 cambios funcionales, 0 regresiones, 0 deuda tecnica introducida.
Suite 918/918 verde. ruff limpio. **100% cumplimiento §1.2 verificado
por grep final.**
