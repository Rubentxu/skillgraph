# Audit — file_scope.py validation branches — 2026-09-26

## Contexto

Auditoría de cobertura del módulo `src/skillgraph/knowledge/file_scope.py`
(H12 Scopes y consultas composables). Tras búsqueda exhaustiva del
backlog opcional y del "qué puedo avanzar con criterio propio", esta es
la mejora de stewardship de mayor valor disponible: subir la cobertura
de branches de validación sin cambiar API ni contratos.

## Diagnóstico

Coverage report (pytest-cov, modo term):

```text
src/skillgraph/knowledge/file_scope.py     90     12     40     12    82%
                                           líneas  branches
```

12 líneas no cubiertas, todas en ramas tristes (validación). 11 son
`raise ValidationError(...)` con mensajes específicos; 1 es dedup por
foco en `aggregate_signatures` (línea 288).

## Líneas objetivo

| Línea | Función                      | Validación                            |
|-------|------------------------------|---------------------------------------|
| 62    | `validate_bounded_context_name` | regex mismatch (3 tests: empty, digit-start, hyphen-prefix) |
| 82    | `ScopeQuery.__post_init__`   | `scope_kind` inválido                 |
| 86    | `ScopeQuery.__post_init__`   | `target` vacío                        |
| 111   | `ScopeResolution.__post_init__` | `scope_kind` inválido              |
| 113   | `ScopeResolution.__post_init__` | `target` vacío                     |
| 116   | `ScopeResolution.__post_init__` | `member_source_ids` vacío         |
| 164   | `resolve_directory_scope`    | `directory_path` vacío                |
| 166   | `resolve_directory_scope`    | `member_paths` vacío                  |
| 202   | `resolve_package_scope`      | `declared_members` vacío              |
| 207   | `resolve_package_scope`      | miembro fuera de prefix               |
| 235   | `resolve_bounded_context_scope` | `member_source_ids` vacío          |
| 288   | `aggregate_signatures`       | dedup por `foco` (primera gana)       |

## Solución

TDD rojo → verde con clase `TestFileScopeValidation` en
`tests/test_h12_file_signature_scopes.py`. 15 tests nuevos:

- 4 sobre `validate_*_name`
- 2 sobre `ScopeQuery.__post_init__`
- 3 sobre `ScopeResolution.__post_init__`
- 2 sobre `resolve_directory_scope`
- 2 sobre `resolve_package_scope`
- 1 sobre `resolve_bounded_context_scope`
- 1 sobre `aggregate_signatures` (dedup)

## Validación

```text
pytest tests/test_h12_file_signature_scopes.py
  → 23 passed (8 originales + 15 nuevos)

coverage src/skillgraph/knowledge/file_scope.py
  → 99% (90 líneas, 1 miss línea 284; branch 1 miss 284→286)
```

Las 2 líneas restantes (284 y branch 284→286) son la rama donde
`signatures_per_source` tiene entries cuyo tuple está vacío Y el source
NO está en `files_with_sigs`. Es corner case interno del loop de
agregación. No lo persigo: su cobertura es difícil de expresar
claramente y el comportamiento ya está cubierto por el camino feliz.

## Hallazgo colateral

### `SignatureProcedencia.__post_init__` levanta `ValueError` (no `ValidationError`)

```python
# src/skillgraph/knowledge/file_signature.py:42-43
def __post_init__(self) -> None:
    if not self.extraction_method:
        raise ValueError("extraction_method no puede estar vacio")
    if not self.extractor_version:
        raise ValueError("extractor_version no puede estar vacia")
```

Violación de AGENTS §1.2 ("Errores tipados, no strings"). `ValueError`
es uno de los tipos genéricos prohibidos en código de dominio.

**Decisión**: NO lo arreglo en este commit. Razones:

1. Scope creep: es un fix en `file_signature.py`, no en `file_scope.py`.
2. El camino feliz NO toca estas ramas (los constructores se llaman con
   strings válidos desde producción y desde tests).
3. Ya está cubierto por el helper `_proc()` del archivo de tests
   (línea 60: `_proc()` siempre pasa strings no vacíos).

**Acción derivada**: registrar como `STEWARDSHIP-DT-*` opcional para
próximo ciclo que aborde `file_signature.py` completo. No bump, no
urgencia.

## Métricas finales

| Métrica | Antes | Después |
|---|---|---|
| Tests en archivo | 8 | 23 (+15) |
| Tests totales del proyecto | 889 | 904 (+15) |
| Cobertura `file_scope.py` | 82% | 99% (+17pp) |
| Líneas no cubiertas | 12 | 1 (corner case interno) |
| Contratos rotos | 0 | 0 |
| Cambios en `src/skillgraph/` | 0 | 0 |

## Riesgo y reversibilidad

- **Riesgo**: mínimo. Solo se añade tests + 1 import (`re`).
- **Reversibilidad**: trivial. `git revert` del commit devuelve el
  archivo a su estado anterior.
- **Scope**: 1 archivo de tests, 0 archivos de `src/`.

## Conclusión

Ciclo stewardship-DT-FILE-SCOPE-VALIDATION cerrado. Mejora la cobertura
de branches de validación sin tocar contratos ni API. Hallazgo
colateral documentado (`ValueError` en `file_signature.py`) sin
reparar (scope creep fuera del objetivo).
