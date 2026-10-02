# WI-73 — Diseño y plan: `_sources_in_scope`

> Ciclo `p-b7740b96d79ec013/wi-73-p3-aggregate-file-signatures`, fases
> Design y Plan. Especificación en `evidence/sddk-wi73-spec-2026-10-02.md`.

## 1. Un método nuevo, no una función de módulo

El bucle usa `self.get_source` y `self.knowledge.source_exists_anywhere`.
Podría ser una función de módulo que recibiera el controller, pero eso
introduce un parámetro que no es un dato del dominio: es el contexto.
La clase ya es el contexto, y todos los métodos hermanos viven en ella.
Se queda como **método privado**.

## 2. El nombre

```python
def _sources_in_scope(self, *, member_source_ids: tuple[str, ...]) -> tuple[str, ...]:
```

`_sources_in_scope` dice qué devuelve (los sources que **sí** están en
el scope) y, por el nombre, que rechaza los que no. El docstring explica
la regla de los tres casos. El invariante pasa de estar solo en el
docstring de la clase y en el nombre de un test a tener un nombre en el
código.

## 3. Firma y cuerpo

```python
def _sources_in_scope(self, *, member_source_ids: tuple[str, ...]) -> tuple[str, ...]:
    """Filtra `member_source_ids` a los que pertenecen a este scope.

    UAT-EVO-08. Tres casos, y el tercero es el que no se ve:

    1. el source pertenece a (tenant_id, project_id) de este controller:
       se incluye;
    2. existe en OTRO proyecto: se rechaza con `UnknownSourceError` y un
       mensaje que NO revela el `source_id` (no se filtra contenido);
    3. no existe en ninguna parte: se omite en silencio (typo del caller).

    El caso 2 se distingue del 3 a proposito: filtrar en silencio el
    contenido de otro proyecto seria una fuga, y omitir un typo seria
    perder feedback. Se rechazan, no se filtran.
    """
    sources_in_scope: list[str] = []
    for source_id in member_source_ids:
        try:
            self.get_source(source_id=source_id)
            sources_in_scope.append(source_id)
        except UnknownSourceError:
            # Distinguir: source-en-otro-proyecto vs no-existe.
            cross = self.knowledge.source_exists_anywhere(source_id=source_id)
            if cross:
                # Existe en OTRO tenant/project: rechazo explicito.
                # El mensaje NO revela el source_id (regla E2E-08:
                # no filtrar contenido de otro proyecto).
                raise UnknownSourceError(
                    "Uno o mas sources pertenecen a otro proyecto; "
                    "rechazado sin filtrar contenido (UAT-EVO-08)"
                ) from None
            # No existe en ningun proyecto: omitir silenciosamente.
    return tuple(sources_in_scope)
```

El cuerpo es el bucle original **movido**, con la `list` y el `return`
como única adicion. Ni una palabra del razonamiento cambia.

## 4. El método público queda asi

```python
sources_in_scope = self._sources_in_scope(member_source_ids=member_source_ids)

# Recolectar FileSignatures de cada source existente en el scope.
signatures_per_source = {
    source_id: self.list_file_signatures_for_source(source_id=source_id, only_stale=False)
    for source_id in sources_in_scope
}

return aggregate_signatures(signatures_per_source=signatures_per_source, scope=scope_query)
```

El segundo bucle pasa a comprehension (REQ-4, AGENTS §11.8). El orden de
inserción del dict comprehension es el de iteracion, igual que el del
bucle, asi que `aggregate_signatures` recibe el mismo dict.

## 5. Lo que NO cambia

- El lazy import y su posicion: sigue al principio del metodo.
- El guard `isinstance` -> `TypeError` (REQ-6).
- El camino de `member_source_ids` vacio.
- El **orden**: la comprobacion de aislamiento termina antes de leer
  ninguna firma. Si el bucle se moviera despues de la recoleccion, un
  source de otro proyecto ya habria leido su contenido.

## 6. Red prevista (`tests/test_wi73_scope_isolation.py`)

| Test | Qué demuestra |
|---|---|
| `test_isolated_helper_agrees_with_the_original_loop` | **Oráculo diferencial**: el helper contra una reimplementación del bucle original, en los tres casos y con combinaciones (varios sources, mezcla de válidos e inválidos) |
| `test_cross_project_source_is_rejected_without_leaking_id` | el mensaje no contiene el `source_id` |
| `test_unknown_source_is_silently_skipped` | caso 3 |
| `test_all_valid_sources_are_returned` | caso 1, con orden preservado |
| `test_isolation_is_checked_before_any_signature_is_read` | **orden**: ningún `list_file_signatures_for_source` ocurre si hay un cruce |
| `test_helper_exists_with_a_name_that_states_the_invariant` | estructura: el invariante tiene nombre |
| `test_public_method_has_no_inlined_isolation_loop` | estructura: el bucle no sigue en el metodo publico |
| `test_type_guard_still_raises_type_error` | REQ-6, el guard no se tocó |
| `test_empty_members_still_short_circuits` | camino vacio intacto |

Mutaciones a verificar: (a) el helper omite el `raise` y devuelve lo que
hay; (b) el helper **filtra en silencio** en vez de rechazar — que es la
fuga de contenido que UAT-EVO-08 prohíbe; (c) la comprehension se mueve
antes del aislamiento.

La (b) es la importante: es la mutación que convierte el bug de seguridad
en un test verde si la red está mal escrita.

## 7. Plan de ejecución

1. Test en rojo (los 9 tests de la tabla).
2. `_sources_in_scope` con el cuerpo verbatim.
3. `aggregate_file_signatures` delega; comprehension; docstring del
   helper.
4. Verde, tres mutaciones aplicadas y restauradas, suite completa.
5. Audit regenerado, `refactor(knowledge)` + `docs(state)`, CI canónica.
