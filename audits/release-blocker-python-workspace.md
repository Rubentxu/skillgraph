# WI-42 — Release bloqueado: el tooling SDDK no soporta proyectos Python

Estado: **BLOQUEADO** (no es un problema de configuracion local).
Evidencia: inspeccion del binario `sddk` 1.171.2 y reproduccion de ambas vias.

## Resumen

El ciclo de release de SDDK exige un lockstep de version entre el workspace
y el tag. Esa comprobacion esta cableada a Cargo workspaces de Rust. En un
proyecto Python, `sddk release plan` se niega antes de actuar y
`sddk release apply` falla antes incluso. No existe override, no existe flag,
y el framework no incluye los ficheros que el segundo necesita.

## B1 — `release plan`: lockstep exclusivo de Rust

Reproduccion:

    sddk release plan --tag v0.16.2 --route local --branch main \
        --cycle p-74299cf88f51dab9/wi-40-test-connection-lifecycle

    VERSION LOCKSTEP ERROR: could not read <root>/Cargo.toml

Evidencia en el binario (`strings $(which sddk)`):

| Cadena observada | Implicacion |
|---|---|
| `could not find \`version\` in [workspace] or [workspace.package] section of` | busca la clave `version` en secciones Cargo |
| `no [workspace] section found` | error explicito cuando no hay workspace Cargo |
| `VERSION LOCKSTEP FAILED: workspace=. Release planning refused until the lockstep rule is satisfied.` | el rechazo es la via de diseño, no un bug |
| `pyproject` | **0 ocurrencias** en todo el binario |

La ultima fila es la concluyente: no existe ninguna referencia a
`pyproject.toml`. No hay rama de codigo que sepa leer un manifiesto Python.
`--route local` no lo evita (el lockstep es previo a elegir ruta).

## B2 — `release apply`: falta `permissions.yaml`

Reproduccion:

    sddk release apply --tag v0.16.2 --route local --branch main \
        --cycle p-74299cf88f51dab9/wi-40-test-connection-lifecycle

    error: failed to read permissions registry
      "<root>/permissions.yaml": No such file or directory

Falla **antes** que B1, con un fichero distinto. El framework 1.171.2 no lo
incluye: `assets/` solo trae `agent-models.yaml`.

No hay comando que lo cree: `sddk permission` expone unicamente
`check` (evaluar), no `init` ni `write`. Fabricar el fichero a mano seria
falsear el registro de permisos, que es exactamente lo que el gate existe
para impedir.

## Superficies descartadas

Se comprobo que no existe via soportada antes de declarar el bloqueo:

- **Override de manifiesto**: `release plan --help` no expone ninguna flag
  de ruta a manifiesto. No es opcion oculta.
- **Fichero de configuracion**: no hay clave de configuracion de lockstep
  ni de manifiesto en el binario.
- **Actualizacion del framework**: el lockstep es logica del binario
  compilado, no un asset. Subir de framework no lo cambia.
- **`sddk ship` / facade**: delegan en `release plan`, mismo refusal.
- **Release manual**: posible con git, pero fabricaria el release-receipt
  que el gate de `archive` despues verifica. Prohibido por las reglas.

## Impacto

Ciclos que no pueden cerrarse por la via del release:

- `p-74299cf88f51dab9/stored-claim-evidence-boundary` (WI-39) — `RELEASE_PENDING`
- `p-74299cf88f51dab9/wi-40-test-connection-lifecycle` (WI-40) — `OPEN`
- `p-74299cf88f51dab9/wi-41-cli-god-module-dispatch` (WI-41) — verificado, pendiente de release

El codigo esta verificado y commiteado. Lo que falta es capacidad de la
herramienta, no trabajo de producto.

## Que NO se ha hecho, deliberadamente

- No se fabrico `Cargo.toml` (falso manifiesto).
- No se fabrico `permissions.yaml` (falso registro de permisos).
- No se creo ningun tag ni receipt a mano.
- No se hizo push de nada.
- No se uso `--no-verify` en ningun commit.

Cada uno de esos habria dejado el historial mintiendo sobre lo que se
verifico, que es peor que un ciclo abierto.

## Recomendacion

Escalar como incidencia del tooling SDDK, no como deuda del proyecto.
La pregunta a resolver por el mantenedor del framework es una sola:

> ¿Debe `release plan` soportar el lockstep de version en `pyproject.toml`
> para proyectos Python, o el release queda acotado a workspaces Rust?

Hasta que se responda, WI-39/40/41 quedan `Done` en cuanto a codigo y
`RELEASE_PENDING` en cuanto a ciclo, y el trabajo sigue su curso sin
liberar.
