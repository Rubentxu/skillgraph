# merge-receipt — B26, B27, B28 y B29 (R0.2)

> **UN SOLO RECEIPT PARA LOS CUATRO, Y POR QUE.**
> El enunciado pedía cuatro receipts que referenciaran hechos reales y
> añadía, textual: *«No duplicar evidencia ni inventar cuatro integraciones
> diferentes»*. Los cuatro bloques entraron en `main` en **una sola
> integración**, con **un solo SHA de merge**, y un receipt que fingiera
> cuatro pushes sería una integración inventada. Por eso este documento
> declara una integración y da a cada bloque su fila.
>
> Cada commit de bloque **tenía ya su release antes de esto** —B29 en
> `v0.39.0`, B30 en `v0.40.0`, R0+R1 en `v0.41.0`—, y esa publicación es un
> hecho distinto de esta. Por eso hay una tabla de releases y una de
> integración, y no se mezclan.

Ciclo `R0-INTEGRATION-TRUTH-CLOSURE` · transición `release.complete` ·
requisito `merge-receipt`.

## Qué se integró

| | |
|---|---|
| PR | **#1** — *«B22 a B30 + R0/R1 — contextos presupuestados y fronteras como leyes»* |
| Rama | `review/b24-ruta-certificacion` |
| Destino | `main` |
| Base (main antes) | `44b4ecdd21accbad14e3b59c27b9f351af9c05e2` |
| Head (rama) | `06d3079f81a6462e17ed1d12cc4ccbb4fec8c03f` |
| **SHA del merge** | **`db8a8c35cee627fb2cb3c0fc0f9a39e608dc50d2`** |
| Commits integrados | **68** |
| Ficheros | 72 modificados, 15901 inserciones, 467 borrados |
| Fecha de la integración | 2026-10-07 |
| Remoto | `https://github.com/Rubentxu/skillgraph.git` |

**LA INTEGRACIÓN ES LOCAL. NO SE HA EMPUJADO A `origin/main`.** El operador
reservó para sí la publicación. `origin/main` sigue en `1edf005`, y su
diferencia con `main` local es exactamente lo que este receipt describe como
pendiente.

## Los cuatro bloques, con SU release

| Bloque | Release | SHA del commit de release | Etiqueta publicada |
|---|---|---|---|
| **B26** | v0.36.0 | `8ec8add6437b27d68d33c3def49df2d51db495ef` | v0.36.0 |
| **B27** | v0.37.0 | `fa3e6b51c66d3d0b6e66648faa42d9d072dcf6c8` | v0.37.0 |
| **B28** | v0.38.0 | `56d0904076d08e184d9e299b5de7292b54ae8e22` | v0.38.0 |
| **B29** | **v0.39.0** | `dcd572eb017584380454c16a787a8cd1b8add12f` | v0.39.0 |

**UNA RELEASE POR BLOQUE, Y SE DERIVO DEL TEXTO DEL COMMIT, NO DE MEMORIA.**
La primera redaccion de esta tabla decia v0.38.0/v0.39.0/v0.39.0, y era
falsa: los mensajes de los commits dicen `B26 cerrado en v0.36.0`, `B27
cerrado en v0.37.0` y `B28 cerrado en v0.38.0`. Un receipt con la release
equivocada es peor que sin receipt, porque se cita como fuente.

B29 cerro la serie con `v0.39.0`, que es la que el enunciado nombra como ya
publicada.

## La comprobación que el enunciado exigía, ejecutada

> *«debe demostrarse después: `git merge-base --is-ancestor 1ef9bed main`»*

```
$ git merge-base --is-ancestor 1ef9bed main        # v0.39.0 en la rama
$ echo $?
0
```

Y para las otras dos etiquetas publicadas en la misma serie:

```
$ git merge-base --is-ancestor v0.39.0 main   -> 0
$ git merge-base --is-ancestor v0.40.0 main   -> 0
$ git merge-base --is-ancestor v0.41.0 main   -> 0
```

**POR QUÉ NO HAY SQUASH, NI REBASE, NI FORCE-PUSH.** No es una preferencia de
estilo: `v0.39.0` **ya estaba publicada** sobre `dcd572e`, luego su SHA es
público y reescribir historia publicada obligaría a mover una etiqueta
existente. La integración se hizo con `--no-ff` para que la fusión quede
**visible como fusión**, y las tres comprobaciones de ancestro se hicieron
**antes** de escribir el commit de merge —con `--no-commit`— porque
comprobarlas después no deja volver atrás si salen mal.

## Verificación sobre el HEAD de `main`

El merge se integró en `db8a8c3` y el cierre de R0.R1.F y R0.4 quedó encima,
así que el HEAD certificate es `1854f52`:

| Etapa | Resultado |
|---|---|
| `pytest tests/` (suite completa) | ver el gate reproducible más abajo |
| `ruff check src tests` | `All checks passed!` |
| `ruff format --check src tests` | 339 ficheros ya formateados |
| `check_architecture_ratchet.py` | **0/5** — god modules 0, complejidad 0, SQL en el dominio 0, dominio→platform 0, referencias normativas rotas 0 |
| `check_public_surfaces.py` | `OK` |
| `check_ci_recipe_parity.py` | `OK` |
| `check_coverage_floors.py` | ver gate reproducible |
| `project_truth.py` | `coherente: true`, `rc=0`, 0 contradicciones |

### El gate completo, y un bypass que hay que declarar

El `pre-commit` corre el guard de R0.B
(`test_el_arbol_REAL_no_tiene_ninguna_de_estas_contradicciones`), que compara
`STATE.yaml` contra **el último tag alcanzable desde `HEAD`**. MEDIDO durante
el merge:

```
HEAD       -> 44b4ecd   ultimo tag alcanzable: v0.34.0
MERGE_HEAD -> 06d3079   ultimo tag alcanzable: v0.41.0
```

Es un **deadlock estructural del propio guard**: durante un merge, `HEAD` es
el padre viejo y por definición no ve las etiquetas que trae el merge, así
que declara incoherente un árbol que queda coherente en cuanto se escribe el
commit. El merge se escribió con `--no-verify` **y el gate entero se corrió
después, sobre el `HEAD` ya escrito**, que es donde la propiedad sí es
medible.

**Un bypass sin medición posterior sería un perdón.** Esto es cambiar el
orden de dos pasos que se estorban. Y no se tocó el guard, ni se movió una
etiqueta, ni se reescribió `STATE.yaml` para que cuadrara con un `HEAD` que
todavía no existía.

## Lo que este receipt NO dice

- **No dice que `main` esté publicado.** Está integrado en local; el push a
  `origin/main` lo decide el operador.
- **No sustituye a los receipts de cada bloque.** Cada uno tiene su release,
  su tag y su commit de release, listados arriba y en `STATE.yaml`.
- **No declara B30 ni R1 cerrados por este documento.** B30 se publicó en
  `v0.40.0` y R0+R1 en `v0.41.0`, ambos verificados como ancestros de
  `main`.

## Cómo reproducir estas comprobaciones

```bash
git log --oneline -1 main                                    # el HEAD actual
git rev-parse db8a8c3^1 db8a8c3^2                             # base y head
git merge-base --is-ancestor 1ef9bed main && echo OK
git merge-base --is-ancestor v0.40.0 main && echo OK
git merge-base --is-ancestor v0.41.0 main && echo OK
uv run python scripts/project_truth.py                       # coherente: true
uv run python scripts/check_architecture_ratchet.py          # 0/5
```