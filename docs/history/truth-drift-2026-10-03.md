# Deriva de verdad — medición del 2026-10-03 (bloque B0)

> **Qué es este documento.** La foto de las contradicciones que B0
> arregló. Está en `docs/history/` a propósito: cuando el repositorio sea
> coherente, este fichero no dirá «qué hacer», dirá «qué estaba mal», y eso
> es historia, no instrucción.
>
> El roadmap vivo es [`ROADMAP.md`](../../ROADMAP.md). El estado vigente se
> pide a `scripts/project_truth.py`.

---

## Qué se midió, y por qué esa pregunta

El proyecto hace **cinco afirmaciones sobre sí mismo**. Ninguna es falsa por
accidente: cada una es cierta en su propio fichero y se contradice con las
demás.

Las cinco, y quién es su dueño:

| verdad | dueño | por qué no puede ser de otro |
|---|---|---|
| versión activa | `src/skillgraph/__init__.py` | de ahí la lee hatchling para el wheel |
| release emitida | `STATE.yaml.release.tag` | es la que se aprovisiona |
| tag real | `git describe --tags` | la verdad del VCS |
| número de tests | `STATE.yaml.tests.total` | el estado durable |
| workitem vivo | `ROADMAP` + `STATE` + `CURRENT` | tres ventanas del mismo bloque |
| roadmap | (no lo tenía) | el futuro necesita un dueño |

## El resultado, con los números

```
B0 — las cinco verdades, medidas sobre el árbol de HOY

  version activa (__init__.py) : 0.22.5.dev0
  release declarada (STATE)    : 0.22.5
  tag real (git describe)      : 0.22.5
  workitem (STATE)             : WI-96
  workitem (CURRENT)           : WI-115
  tests declarados (STATE)     : 2838
  tests colectados (árbol)     : 2844

roadmaps presentes:
  - docs/blueprint/plan/ROADMAP.md
  - external/blueprint-v1/plan/ROADMAP.md
  - external/evolution-v2/plan/ROADMAP.md

CONTRADICCIONES
  ROJO  tests: STATE dice 2838, el árbol colecta 2844
  ROJO  workitem: STATE dice WI-96, CURRENT dice WI-115
  ROJO  no existe ROADMAP.md en la raíz: el roadmap no tiene dueño
```

Instrumento: `.pipelinek/b0_measure.py` (solo lectura).

## Las tres contradicciones, una a una

### 1. `STATE.yaml` vivía 19 workitems atras

`roadmap.current_workitem` decía **WI-96**. `CURRENT.md` decía **WI-115**.
Los dos campos describen lo mismo —el bloque de trabajo en curso— y los dos
tenían razón sobre su propio fichero.

La causa no es que nadie se olvidara de actualizar: es que **el campo se
llenaba a mano al final de un bloque y nadie lo cruzaba con el otro**. El
problema de fondo es que había dos sitios donde escribir el mismo dato y
ninguno que comprobara que dijeran lo mismo.

**El arreglo** no es «actualizar el campo»: es que `scripts/project_truth.py`
cruce los dos y `tests/test_b0_truth_convergence.py` ponga rojo el repo si
se separan otra vez. `STATE.yaml` ahora declara `current_workitem: B0` y
conserva el texto largo de WI-96 en `previous_workitem`.

### 2. La cifra de tests estaba desfasada —y el guard que lo vigila, en rojo

`STATE.yaml` declaraba **2838**; el árbol colectaba **2844**.

Los 6 de diferencia eran `tests/test_wi116_doctest_examples.py`, un fichero
**sin trackear** que se había escrito en el bloque anterior. Al colectar, el
árbol lo cuenta igual: por eso el guard de WI-115
(`test_el_total_declarado_es_el_total_colectado`) estaba **en rojo** antes de
que B0 tocara nada.

Esto merece decirse dos veces, porque es el resultado más útil de la
medición:

> Un guard que funciona se ve feo. Un guard que no funciona no se ve.

El guard de WI-115 existed, estaba bien escrito, y llevaba su contrasalto
contra el cero silencioso. Lo que no podía era ver un fichero sin trackear,
porque «el árbol» para `pytest` incluye lo que no está en git. **El fallo
lo detectó el guard, no la revisión del código.**

**El arreglo**: el fichero se re-hombró a
`tests/test_doctest_examples_are_executable.py` —por su propiedad, no por su
número de workitem, porque la serie WI-91..WI-115 está cerrada— y la cifra
del estado se puso a la verdad.

### 3. El roadmap no tenía dueño

Había **tres** ficheros llamados `ROADMAP.md` y ninguno era el del proyecto
vivo:

- `docs/blueprint/plan/ROADMAP.md` — el roadmap del **blueprint v1**, que
  está terminado. Durante años se leyó como si fuera el plan vigente.
- `external/blueprint-v1/plan/ROADMAP.md` — canon externo de la v1.
- `external/evolution-v2/plan/ROADMAP.md` — la línea H10..H15, cerrada al 100 %.

**El arreglo** crea `ROADMAP.md` en la raíz como autoridad única, y degrada
el del blueprint **en su sitio**: no se mudó, porque la evidencia histórica
del repositorio lo cita por esa ruta y esa evidencia es *provenance*. Mudar
un fichero para que un documento quede más ordenado rompe la trazabilidad de
todos los que lo citan.

## Lo que NO se arregla aquí, y por qué

- **`CURRENT.md` y `STATE.yaml` no se borran.** Seguirían siendo fuentes a
  medias si desaparecieran, pero la diferencia entre una segunda fuente de
  verdad y una ventana que se contrasta con la primera es exactamente lo
  que B0 añade. Borrarlos sería tirar el historial con ellos.
- **El badge de tests del README no lleva cifra.** Se sustituyó por un
  enlace al script que la responde. Un badge con `984/984` congelado es una
  mentira con forma de imagen:-aging sin mechanism. Enlazarlo al script que
  no puede envejecer en silencio es la misma idea que el guard, aplicada a la
  documentación.
- **La línea `984/984` del README no era un descuido de última hora.** Data
  de mucho antes. Es la prueba de que la deriva no se produce en un bloque:
  se acumula en silencio mientras cada documento sigue siendo cierto.

## La lección, dicha una vez

`STATE.yaml` no mentía. `CURRENT.md` no mentía. El README no mentía. Cada
uno era cierto sobre sí mismo y los tres juntos describían un proyecto
imposible.

Un estado sin testigo machine-checkable envejece en silencio, porque nadie
lo relee cuando el código avanza por debajo. Lo que B0 añade no es más
documentación: es el testigo. Y un testigo que no se puede ejecutar —una
tabla, un badge, un párrafo— no es un testigo: es otra afirmación más, que
envejecerá igual.
