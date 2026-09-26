# WI-17: H-06 Deuda arquitectónica — `import json` redundante

## Objetivo

Eliminar el anti-patrón `import json` redundante en funciones que ya
tienen `json` importado a nivel de modulo. El hallazgo concreto:
`cmd_knowledge_compile` declaraba `import json` localmente pero nunca
usaba `json.*` en su cuerpo.

## Decision previa (D-50)

- **Scope minimo**: solo eliminar imports redundantes detectados.
  No reorganizo imports a nivel modulo (cambio cosmético sin valor).
- **Verificacion**: awk-grep para confirmar `json.` count == 0 antes
  de quitar.
- **Backward-compatible**: cero cambios en API/comportamiento.

## Cambios

### `src/skillgraph/cli/runner.py`

- `cmd_knowledge_compile`: elimina `import json` local redundante
  (no se usaba en el cuerpo de la funcion).

## Hallazgo

```
$ awk '/^def cmd_knowledge_compile/,/^def [a-z]/' runner.py | grep -c "json\."
0
```

Confirma que `json` no se usa en `cmd_knowledge_compile`.

## Compatibilidad

- 0 cambios en API publica.
- 0 cambios en comportamiento.

## Evidencia

- `uv run pytest` (suite completa) -> **1044/1044 PASS** en 236.97s.
- Smoke import OK.
- ruff check pasa (sin warnings).

## Pendiente tras WI-17

- WI-18+ (deuda arquitectónica restante: H-01 Storage god-class,
  H-02 CLI god-module, H-03 funciones cc>10, H-05 `_DummyStorage`,
  H-10 `locks.py` drift Windows).
- Bump `0.14.6.dev0 → 0.14.7` con WI-12..WI-17.
- Push a origin (regla WI-01, ahora 31 commits ahead).
