# WI-72 — Diseño y plan: un constructor de payload para las propuestas

> Ciclo `p-b7740b96d79ec013/wi-72-p3-expansion-apply`, fases Design y Plan.
> Especificación en `evidence/sddk-wi72-spec-2026-10-02.md`.

## 1. Tres funciones privadas nuevas en `expansion.py`

Siguen la convención del fichero: prefijo `_`, módulo-local, sin estado.

### `_proposal_payload(proposal, operations_ref) -> dict[str, object]`

Construye las 9 claves. El segundo parámetro es **el valor ya
convertido a texto** que va en `operations`, no el `Namespace`: así el
constructor no depende de argparse y cada comando conserva su nombre de
argumento sin que el constructor tenga que saberlo.

```python
def _proposal_payload(
    proposal: GraphExpansionProposal, operations_ref: str
) -> dict[str, object]:
    return {
        "proposal_id": proposal.proposal_id,
        "author": proposal.author,
        "created_at": proposal.created_at,
        "problem_observed": proposal.problem_observed,
        "operations": operations_ref,
        "capabilities_needed": list(proposal.capabilities_needed),
        "new_dependencies": list(proposal.new_dependencies),
        "attachment_point": proposal.attachment_point,
        "authorization_mode": proposal.authorization.mode,
    }
```

FUNCIONA como la unión literal de los dos dict originales: las 9 claves,
mismos nombres, mismos valores. La duplicación era byte a byte y solo
cambia `operations`.

### `_applied_payload(proposal) -> dict[str, object]`

Las 3 claves del marker `.applied`, verbatim.

### `_write_json(path, payload, *, overwrite: bool) -> bool`

Escritor único. `overwrite=False` hace que no escriba si el destino ya
existe, y devuelve `False` en ese caso; `overwrite=True` escribe siempre.
Devuelve si escribió, para que el llamador pueda decirlo en su flujo.

El `encoding="utf-8"` va aquí, explícito (REQ-WI72-3). Es byte-idéntico
al comportamiento actual de `apply`, y en `propose` **tampoco cambia un
byte**: `json.dumps` escapa lo no-ASCII por defecto (`ensure_ascii=True`),
así que su salida es ASCII puro y el locale nunca llega a decidir. La
divergencia (3) que la exploración dio por un bug de locale era inerte.
El `encoding` explícito se queda porque fija el formato en el código y no
en el entorno, no porque arregle nada observable.

## 2. Por qué `overwrite` es un parámetro y no dos funciones

`propose` sobrescribe y `apply` no. Podrían ser dos funciones
(`_write_proposal_record` y `_write_proposal_record_if_absent`), pero eso
duplicaría el `json.dumps(indent=2, sort_keys=True)` y la ruta. Un
parámetro booleano con nombre en la llamada
(`overwrite=False` en apply, `overwrite=True` en propose) hace que la
diferencia sea legible en el sitio donde importa, que es la llamada.

Es el mismo criterio que ya usa el repo: `if not proposal_json.is_file()`
no desaparece, cambia de sitio y se lee en la firma.

## 3. El `plan` de doble significado (REQ-WI72-5)

Hoy:

```python
if args.plan_file is not None:
    plan = _load_plan_from_path(args.plan_file)   # valor DESCARTAADO
    _write_plan_to_storage(project_dir, plan)     # solo importa el efecto
try:
    plan = _load_plan_from_storage(project_dir)   # reenlace
```

El primer enlace existe solo por el efecto de la escritura. Se elimina
el enlace y queda:

```python
if args.plan_file is not None:
    _write_plan_to_storage(project_dir, _load_plan_from_path(args.plan_file))
```

Mismo orden, mismos efectos, un enlace menos que mentir.

## 4. Lo que NO se toca

- `apply_expansion`, el dominio y sus invariantes.
- Los exit codes y el texto de `OK:` y `REJECTED:`.
- El esquema: mismas 9 claves.
- La escritura del marker `.applied` (ocurre siempre, incluso si el
  proposal JSON ya existía).

## 5. Red prevista (`tests/test_wi72_expansion_payload.py`)

| Test | Qué demuestra |
|---|---|
| `test_propose_and_apply_write_the_same_payload` | **Oráculo diferencial**: reconstruye las 9 claves como literal y compara contra el JSON de disco escrito por cada comando |
| `test_apply_does_not_overwrite_existing_record` | REQ-WI72-2 |
| `test_propose_overwrites_existing_record` | REQ-WI72-2, el otro lado |
| `test_payload_has_exactly_nine_keys` | una clave de más o de menos rompe la red |
| `test_both_commands_delegate_to_one_builder` | REQ-WI72-1, por AST: el literal no puede existir en ninguno de los dos comandos |
| `test_apply_flow_has_no_json_literals` | REQ-WI72-4 |
| `test_applied_marker_payload_shape` | las 3 claves del marker |
| `test_write_json_respects_overwrite_flag` | el parámetro hace lo que dice |
| `test_written_payload_roundtrips_non_ascii` | REQ-WI72-3, y documenta que la divergencia de `encoding` es inerte |

Verificación en ambos sentidos: quitar una clave del constructor
compartido, o pasar `overwrite=True` en `apply`, deben romper la red.

## 6. Plan de ejecución

1. Test en rojo (los 9 tests de la tabla).
2. Los tres helpers, cuerpos verbatim de los dos dict originales.
3. `cmd_expansion_apply` y `cmd_expansion_propose` delegan.
4. Verde, mutación + restauración, suite completa.
5. `refactor(cli)` + `docs(state)`, verificación con la CI canónica.
