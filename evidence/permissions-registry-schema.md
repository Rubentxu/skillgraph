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

## Resuelto el 2026-09-28: qué capacidades exige de verdad el release

Con `permissions.yaml` escrito, `sddk release apply` dejó de fallar en
parseo y pasó a **autorización**, que es la comprobación que faltaba. Las
capacidades que el flujo de release exige, descubiertas iterativamente
contra el binario (cada intento revelaba la siguiente):

```
core.release-planning@v1
git.inspect
git.tag
git.push
```

Las tres últimas no estaban en el inventario de "capacidades que declara
el binario" documentado antes: aquel solo recogía las `core.*` y omitía
las `git.*` que el flujo de release además exige.

El **actor** tampoco se adivina: lo dicta el propio error, que dice
literalmente `agent sddk-release is not declared in the permission
registry`. Escribir `release-agent` fue un intento fallido mío que el
error corrigió.

Sobre el alcance por fase: `phases` es restrictivo y se comprobó. Con
`phases: [apply]`, pedir la misma capacidad en `release` o `archive`
devuelve `allowed: false`. Por eso el permiso de release se declara para
la fase `release` y no para `apply`, y por eso dos agentes con nombres
parecidos no son intercambiables: `apply-agent` y `sddk-release` viven
en fases distintas.

## Resumen para la decisión

| Pregunta | Respuesta verificada |
|---|---|
| ¿Es un archivo del framework? | No. Del proyecto, en la raíz del repo |
| ¿`adopt apply` lo genera? | No, no tiene subcomando para eso |
| ¿Cuál es el esquema? | `agents: { <nombre>: { phases: [...], capabilities: [...] } }` |
| ¿Bastaría con escribirlo? | Sí para B2. B1 sigue bloqueando `release plan` |
| ¿Es default-deny de verdad? | Sí: registro vacío deniega todo |
| ¿El actor se adivina? | No. Lo dicta el error: `sddk-release` |

La decisión que queda es de política, no de técnica: si el repositorio
declara o no un registro de permisos para sus agentes, y con qué
contenido. Nada de lo anterior depende de esa respuesta.
