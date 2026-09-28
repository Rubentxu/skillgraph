# `permissions.yaml`: esquema verificado y lo que realmente bloquea

> Complementa `b1-b2-diagnosis-correction.md`. Determinado empíricamente
> el 2026-09-28 con un directorio desechable, **sin escribir nada** en el
> repositorio.

## El esquema, verificado (no deducido)

```yaml
agents:
  apply-agent:
    phases: [apply]
    capabilities: [core.workflow-orchestration@v1]
```

La clave es `capabilities`, no `allowed_capabilities`. Comprobado: con
`allowed_capabilities` el chequeo devuelve `allowed: false`; con
`capabilities` devuelve `allowed: true` y la razón
`agent apply-agent is allowed core.workflow-orchestration@v1 in phase apply`.

Capacidades que el binario declara:

```
core.contract-review@v1
core.release-planning@v1
core.workflow-orchestration@v1
```

## Default-deny es real, no decorativo

Con `capabilities: []` el registro deniega:

```
allowed: false
reason: agent apply-agent is not allowed capability core.release-planning@v1
```

Escribir un archivo vacío **no** desbloquea el release: concede cero
capacidades. Esto confirma la decisión de no fabricarlo a ciegas por una
razón mecánica, no solo ética: un registro mal escrito deniega igual que
uno ausente, pero con más pasos.

## Lo que el registry NO hace

`release apply` falla en `read permissions registry` **antes** de
evaluar ninguna capacidad. Es decir: hoy el bloqueo es de *parseo*, no de
*autorización*. Con un registro presente, el comando pasaría a la
siguiente comprobación, que es donde B1 (`Cargo.toml`) vuelve a aparecer.

Esto tiene una consecuencia práctica: **declarar el registro no basta para
liberar 0.16.2**. Aunque se escribiera con contenido legítimo, B1
seguiría bloqueando `release plan`. Son dos bloqueos independientes, y
solo uno de ellos es nuestro.

## Por qué B1 no tiene salida limpia

`release plan` exige `Cargo.toml` por *lockstep de versión*. Este proyecto
es Python puro y la regla 8 de `AGENTS.md` prohíbe introducir Rust en el
bootstrap. Fabricar un `Cargo.toml` para satisfacer el lockstep sería
declarar un componente que no existe.

La superficie **`sddk git tag`** sí funciona sin lockstep: se usó para
crear etiquetas en ciclos anteriores que acabaron `CLOSED`. Ese es el
camino que el recibo de release ya identificó como honesto.

## Resumen para la decisión

| Pregunta | Respuesta verificada |
|---|---|
| ¿Es un archivo del framework? | No. Del proyecto, en la raíz del repo |
| ¿`adopt apply` lo genera? | No, no tiene subcomando para eso |
| ¿Cuál es el esquema? | `agents: { <nombre>: { phases: [...], capabilities: [...] } }` |
| ¿Bastaría con escribirlo? | No. B1 seguiría bloqueando el release |
| ¿Es default-deny de verdad? | Sí: registro vacío deniega todo |

La decisión que queda es de política, no de técnica: si el repositorio
declara o no un registro de permisos para sus agentes, y con qué
contenido. Nada de lo anterior depende de esa respuesta.
