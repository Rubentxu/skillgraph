# Corrección de B1 y B2: `permissions.yaml` es del proyecto, no del framework

> Corrige `evidence/wi-45-release-failure-evidence.md` y el recibo de
> release, que clasificaban B2 como un defecto del framework.
> Verificado sobre el binario instalado **2.0.1** el 2026-09-28.

## B2 estaba mal diagnosticado

El texto de la sesión anterior:

> El framework 1.171.2 **no provee** `permissions.yaml`
> (`find $FRAMEWORK -name permissions.yaml` → sin resultados).

La observación es cierta y la conclusión es falsa. Es un archivo **del
proyecto**, en la **raíz del repositorio**, y el propio binario lo dice:

```
cannot load the agent permission registry:
create permissions.yaml at the repository root with an `agents` mapping
```

Más el código de salida:

```
error: failed to read permissions registry
  /var/mnt/DiscoChino2-fast/Proyectos/python/skillgraph/permissions.yaml:
  No such file or directory (os error 2)
```

La ruta es el **cwd del repositorio**, no `$FRAMEWORK`. `find $FRAMEWORK`
no iba a encontrarlo nunca, porque no está ahí. Buscar en el sitio
equivocado produjo una conclusión que sonaba firme y era falsa.

**Consecuencia:** no es un bug del framework ni algo que haya que esperar
a que upstream lo arregle. Es un archivo que este repositorio no tiene y
que su propia adopción exige. Se corrige aquí.

## Por qué no lo fabricamos igual

La conclusión anterior (no inventar el archivo) **sigue siendo correcta**,
pero por otro motivo y con otro matiz:

`permissions.yaml` es un registro **default-deny** que mapea agente → fases
permitidas. Un archivo inventado no "desbloquea" nada: autoriza
exactamente lo que el autor del archivo escriba, y en este caso lo escribiría
la misma persona que concede el permiso. Fabricarlo para que `release apply`
pase es fabricar la autorización.

Lo correcto es **declarar** el registro, no fabricarlo. La diferencia es
intención y trazabilidad, no resultado.

## B1 se mantiene

`Cargo.toml` en un proyecto Python sin Rust (regla 8 de `AGENTS.md`) sigue
sin tener sentido, y la comprobación de lockstep sigue exigiéndolo. B1 no se
reclasifica.

Añadido el 2026-09-28 tras el corte de `v0.16.3`: se leyó el binario para
confirmar que no existe una vía soportada que no sea fabricar el manifiesto.
Las cadenas relevantes del error son:

```
VERSION LOCKSTEP ERROR: could not read <root>/Cargo.toml
VERSION LOCKSTEP ERROR: could not find `version` in [workspace]
  or [workspace.package] section of generated escalation
```

El lockstep **solo** lee `[workspace]` o `[workspace.package]` de un
`Cargo.toml`. No hay bandera, variable de entorno ni clave de manifiesto que
declare "este workspace no es Rust", y `.sddk/` —que sí es un marcador de
project root reconocido— no evita el lockstep: el error se dispara al leer
el `Cargo.toml`, no al detectar el tipo de proyecto.

Por tanto las dos opciones restantes son fabricar un `Cargo.toml` para un
workspace Rust que no existe, o dejar el ciclo en `RELEASE_PENDING`. Se
elige lo segundo. Fabricar el manifiesto sería **declarar un componente
inexistente** para apagar un gate, que es peor que un bloqueo honesto.

## El push no es una decisión pendiente: es prohibido aquí

La última pregunta abierta era si el push de 36 commits a `origin/main`
era un human gate o un olvido. No es un olvido: es una **prohibición
estructural**, escrita en el framework.

`prompts/sddk/phases/apply.md`, sección `## Push Discipline (binding)`:

> Apply agents MUST NOT invoke `git push` of any form. Push is the
> exclusive responsibility of `sddk-release` (push-to-main) and the
> orchestrator's branch-creation step (push-to-feature-branch).

La misma sección añade una lista de comandos prohibidos en fase apply
("cycle-17 hardening"). El `pre-push` hook de SDDK solo bloquea por
closeouts pendientes y por fallo de verificación del ledger —ambos
verificados limpios—, así que el hook no es lo que retiene el push: es la
regla de fase.

Consecuencia práctica: mientras B1 bloquee `sddk release apply`, **no
existe la superficie legítima que puede hacer el push**. `v0.16.3` queda
correctamente publicado solo en local, y eso no es un descuido del proceso
sino la consecuencia directa de B1.

## Corrección adicional: el sha256 de los artefactos

También era un diagnóstico erroneous, por buscar en el store equivocado.
La ruta autoritativa la declara el propio recibo de adopción
(`adoption.json → paths.cycle_artifacts`):

```
/home/rubentxu/.local/share/sddk/projects/<project>/cycle-artifacts/<project>/<cycle>/
```

Ahí **sí** hay sidecars `.sha256`, con el formato clásico:

```
87dee7dc49c5ffce7dc901a6bc9ebf49566c5451fe98601e98f71d5fdaad57b9  inventory.json
```

Lo que era cierto sigue siendo cierto: el directorio de artefactos de
**wi-45 no existe**, y el manifiesto de los 11 ciclos informa `sha256: null`
en todos ellos, incluido el ciclo `CLOSED`. Así que el hallazgo se mantiene
en su forma útil, pero por un motivo distinto al que se le atribuía antes:
no es un campo que el framework rellene al transicionar, es que **este
ciclo nunca escribió sus artefactos en el store**, que es donde el
framework calcula y registra el hash.

## Resumen de los tres diagnósticos revisados hoy

| Afirmación | Veredicto |
|---|---|
| B1: falta `Cargo.toml` | **Se mantiene**, y no tiene salida limpia sin fabricar un workspace Rust inexistente |
| B2: el framework no provee `permissions.yaml` | **Falsa.** Es del proyecto, en la raíz del repo |
| `sha256: null` es un hueco del manifiesto | **Parcial.** El store sí calcula hashes; wi-45 simplemente no escribió allí |
| El push a `origin/main` está pendiente por decisión | **Falsa.** Es una prohibición estructural de la fase apply, y B1 elimina la superficie legítima que lo haría |
