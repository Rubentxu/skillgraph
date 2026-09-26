# WI-22: deuda H-03 (resources.parser.parse_markdown cc=17)

## Objetivo

Reducir cc de `parse_markdown` (cc=17) en
`src/skillgraph/resources/parser.py`. El alto cc viene de la
secuencia de 6 checks `isinstance(...) or ...`, cada uno +1 por
el `or` corto-circuito y +1 por cada comparacion.

## Cambio

- Extraido `_require_str(data, key, *, source) -> str`: una validacion
  "string no vacio" reutilizable (apiVersion, kind, metadata.name).
- Extraido `_require_dict(data, key, *, source) -> dict`: validacion
  "mapping" con default `{}` si falta (metadata, spec).
- Extraido `_metadata_name(metadata, *, source) -> str`: separacion
  del campo name de metadata (mensaje de error mas preciso).
- Extraido `_metadata_namespace(metadata, *, source) -> str`: igual
  para namespace.

`parse_markdown` queda en cc=2 (solo el guard `text` + happy path
de composicion). Los errores tipados viven en los helpers y
comparten el mismo formato de mensaje "{source}: {key} ausente o
no es string".

## Compatibilidad

- 100% backward-compatible: mismas ParseError con el mismo mensaje
  ("{source}: {key} ausente o no es string" / "{source}: {key}
  debe ser un mapping" / "{source}: metadata.{...}").
- 35/35 tests PASS en test_parser, test_h9_coverage_bricks,
  test_s0_brick_minimo, test_h9_cli_inproc_knowledge_brick.

## Decision previa (D-53)

- **D-53**: Patron extraer-helpers-de-validacion-forma: cuando un
  `parse_X` tiene 4+ checks `isinstance(...) or ...`, cada uno se
  convierte en un helper `_require_*`. El parser solo orquesta.
- **D-54**: Helpers `_require_*` siempre lanzan `ParseError` tipado
  con `source` kwarg para preservar el mensaje exacto.

## Evidencia

- `parse_markdown` cc: 17 -> 2 (~88% reduccion).
- 4 helpers extraidos, todos cc<=3.
- 1044/1044 PASS en suite completa (199.38s).
- ruff: All checks passed.
