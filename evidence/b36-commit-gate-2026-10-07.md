# B36 — Un guard que obliga a apagar el gate que lo contiene

> Medición hecha **antes** de escribir una línea.
> Script: `scripts/measure_b36_commit_gate.py`, cinco rondas.
> Sondas: `scripts/mutate_b36_commit_gate.py`, cinco sondas en dos familias.
> Commits: `297cd1c` (medición), `e4a8d81` (los siete harness),
> el del harness de sondas, `89a474c` (cifra).

## EL GUARD NO PODIA PASAR POR LA PUERTA QUE VIGILA

`tests/test_wi116_suelos_de_cobertura.py::TestElHarnessNoBorraTrabajo` afirma
que el árbol de trabajo no tiene nada sin commitear entre `src/` y `scripts/`:
corre `git status --porcelain -- src scripts` y exige vacío.

El hook de pre-commit corre `pytest -q` **sobre los ficheros stageados**
(`scripts/hooks/pre-commit:113`). Luego en todo commit que toque `src/` o
`scripts/` **y** stagee ese test, el guard ve stageado justo lo que se va a
commitear — y se pone rojo.

**Capturado en vivo, no en un repo de pruebas.** El hook real rechazó `5f3a739`,
que era un commit correcto:

```
AssertionError: hay cambios sin commitear en src/ o scripts/:
   M  src/skillgraph/cli/commands/knowledge.py
   M  src/skillgraph/knowledge/observation.py
   M  src/skillgraph/knowledge/observation_ingestion.py
ERROR: el smoke sobre lo staged fallo (pytest=1).
```

`M ` con el espacio en la segunda columna: **stageado**. Salida: `HOOK_SKIP_TESTS=1`.

## Y LA ALARMA ESTABA INVERTIDA

```
RONDA 1   arbol limpio        -> ''
          cambio STAGEADO     -> 'M  src/a.py'      el guard falla
          cambio SIN stagear  -> ' M src/a.py'      el guard falla

RONDA 2   SIN stagear + `git checkout --` -> DESTRUIDO
          STAGEADO     + `git checkout --` -> sobrevive
```

`git checkout --` restaura **del índice**. El estado peligroso es el único que
el hook nunca produce, y el seguro es el único que se puede encontrar. **El
guard avisa por igual de los dos.**

## LO QUE SE APAGA DE VERDAD

`scripts/hooks/pre-commit` tiene **3** etapas de toolchain. La condición de
`HOOK_SKIP_TESTS` se deriva por sangría, no escrita:

```
   47  ruff check src tests scripts          -> corre SIEMPRE
   58  ruff format --check src tests scripts -> corre SIEMPRE
  113  pytest -q $STAGED_PY >"$PYTEST_LOG"   -> SE APAGA con HOOK_SKIP_TESTS=1
   rango de la condicion: (88, 132)          se apagan 1, siguen corriendo 2
```

El bypass **no apaga tres gates: apaga el único que comprueba que lo stageado
sigue pasando.**

## EL GUARD ESTABA FALLANDO EN SU TRABAJO REAL, Y EN EL OTRO

```
RONDA 3   scripts/  .py:64   con git destructivo: 7
            mutate_b10_public_surfaces.py:133     git checkout
            mutate_b11_pack_lifecycle.py:139      git checkout
            mutate_b12_schema_upgrade.py:251      git checkout
            mutate_b13_threat_model.py:344        git checkout
            mutate_b14_truth_single_reader.py:356 git checkout
            mutate_b23_instrumento_verdad.py:170  git checkout
            mutate_b9_gate_1_0.py:134             git checkout
          nueve harnesses restauran escribiendo el contenido de vuelta
```

Todos con la forma `_restaura()` → `git checkout --` y **`cwd=RAIZ`**: el
antipatrón exacto que el guard nació para impedir. Y no podía verlo, porque
mira el **estado** del árbol, no el **código** que lo puede romper.

El docstring de `mutate_b9_gate_1_0.py` ya explicaba que así perdió el arreglo
de B9 entero, y su única defensa era **negarse a empezar** cuando había trabajo
sin commitear.

**La defensa correcta no es negarse a empezar: es no destruir.** Los siete
restauran ahora escribiendo lo que leyeron antes de mutar. Verificado ejecutando
uno de verdad:

```
mutate_b13_threat_model.py   6/6 sondas cazadas, 6 causas distintas, rc=0
git status --porcelain -- src scripts   ->  (vacio)
```

**Y EL MOTIVO DEL PRE-FLIGHT DE B9 CAMBIÓ, Y ANTES MENTÍA.** Decía que
`git checkout --` «BORRaría el trabajo». Ya no hay checkout, luego ese motivo
es falso. El aviso se queda por lo que queda de verdad, que es más pequeño: las
sondas deforman el texto **real** de esos ficheros, y con trabajo sin commitear
debajo el resultado mezcla tu cambio con el de la sonda.

## Que entrega

Dos guards que miden cosas distintas, y por eso no son uno:

| guard | mide | cómo |
|---|---|---|
| `TestElHarnessNoBorraTrabajo` | el **estado**: qué hay sin stagear | columna `Y` de `git status --porcelain` |
| `TestNingunInstrumentoPuedeBorrarTrabajo` | la **capacidad**: qué puede romperlo | AST sobre `scripts/`, por **posición** del argumento |

La decisión sale del módulo, no del test, y se prueba con las cuatro formas
reales de `porcelain` más la que no es `porcelain` y no debe inventar cargos.
Un guard que sólo puede fallar cuando el árbol está sucio no se ha probado
nunca, y en una certificación el árbol está limpio.

**El conjunto se deriva, no se escribe:** sale de `scripts/`, con contrasalto
de que traiga al menos veinte módulos. Sin él, una derivación rota daría verde
con la propiedad rota.

### El falso positivo, medido en las dos direcciones

```
sin stagear   ' M scripts/...'  -> FALLA        (es lo que un checkout perdería)
stageado      'M  scripts/...'  -> 20 passed    (es lo que sobrevive)
```

**El guard antes rechazaba las dos.**

### Y UN CONJUNTO DE ESTADOS ESCRITO DE MEMORIA NO ES UNA ESPECIFICACION

MEDIDO al escribirlo: la columna de estados de `git status --porcelain` se
escribió de memoria y se le olvidó el `?` del índice, con lo que `??` —un
fichero **nuevo**— dejó de contar. `git checkout --` no lo destruye, pero
`git clean -fd` sí, que es el otro extremo del mismo antipatrón.

## EL INSTRUMENTO MENTIO TRES VECES, Y LAS TRES ANTES DE ESCRIBIR UN GUARD

1. Buscaba la palabra suelta en cualquier literal, luego contaba como llamada
   `print("RONDA 2 — QUE ESTADO DESTRUYE `git checkout --`")`. **Prosa**, y la
   prosa de este mismo repo. Es la **quinta** vez que sale este defecto — el
   guard de B15, el de WI-92, el de B34 con su sonda M10, y las dos anteriores
   de hoy.
2. Peor: exigía que el primer argumento fuera una **cadena**, luego
   `subprocess.run(["git", "checkout", ...])` — una **lista** — nunca se miraba.
   **Falso negativo sobre todas las llamadas reales.** Los «0 instrumentos» del
   primer borrador eran ceros falsos.
3. Y la ronda 5 filtraba las etapas que redirigen su salida (`and ">" not in
   linea`), lo que excluía **justo la etapa que se apaga**. Decía «se apagan 0,
   siguen corriendo 2», que es lo contrario de lo que hace el hook. Si alguien
   lo hubiera creído, la evidencia de este bloque sería falsa.

Las tres están corregidas y escritas en el código con el número que las cazó.
**Un instrumento que se contradice con el fichero que mide no mide.**

## Lo que el guard derivado NO puede abarcar

`tests/` tiene una llamada legítima: `test_r1e_harness_comun.py:204` llama
`git checkout --` sobre un **repo temporal que el propio test crea**. Un guard
derivado de todo el reposorio daría un falso positivo ahí.

El alcance es `scripts/`, no por una lista de ficheros —la trampa de WI-99— sino
por la frontera estructural entre **instrumentos** y **tests**. Y escanear el
árbol entero sin excluir lo que no es código de este repo devolvió **34 falsos
positivos** de `dulwich` y `urllib3`, dentro de una copia vendorizada del propio
repo en `.pipelinek/`.

## Sondas: 5/5, en dos familias

```
cazadas 5/5   invalidas 0   sin sonda 0   tras restaurar rc=0

E1  el stageado vuelve a contar como sucio   -> el defecto que B36 arregla
E2  la decisión del guard se vacía            -> `if False:`
E3  un fichero nuevo deja de contar           -> sin `?` en la columna del indice
I1  se planta un `git checkout --` real      -> la llamada de verdad, en un
                                                instrumento real
I2  el contrasalto del derivado no dispara    -> si el derivado se vacia
```

**Y LAS SONDAS DE B35 SIGUEN 8/8**, que es lo que había que comprobar al
cambiar un guard que comparten.

## Recibo de certificación

```
suite        4113 passed, 3 skipped, 0 failed, 858.89 s   rc=0
             4113 + 3 = 4116  ==  STATE.yaml tests.total
suelos       rc=0 — todo modulo gobernado por AGENTS 6.3 cumple su suelo
             cli/ 93.31 % · commands/knowledge.py 94.81 % · global 97.13 %
verdad       project_truth rc=0 — 4116 declarados == 4116 colectados
arquitectura check_architecture_ratchet rc=0 — las CINCO a cero
sondas B36   cazadas 5/5, invalidas 0, sin sonda 0
sondas B35   cazadas 8/8, invalidas 0, sin sonda 0  — no se rompieron
lint         ruff check — All checks passed;  ruff format — 427 ficheros
```

## Lo que este bloque DEJA, con nombre

1. **`HOOK_SKIP_TESTS=1` sigue siendo necesario para commitear `src/`.** El
   smoke corre sobre lo stageado y `tests/test_wi116_suelos_de_cobertura.py`
   sigue entre los ficheros stageados de un bloque de guards: hay que verlo.
   Lo que ya no pasa es que **el guard sea el que bloquea**.
2. **La guarda de capacidad cubre `scripts/`, no `tests/`.** Un test que
   construye un repo temporal y llama a `git checkout --` es correcto; un
   instrumento que lo hace contra `RAIZ` no lo es. La frontera es
   instruments-vs-tests, y está escrita.
3. **Doce harnesses de `scripts/` restauran escribiendo; siete restauraban con
   `git checkout --` y ahora escriben.** Los doce usan el mismo patrón y ninguno
   puede perder trabajo con el árbol sucio.

## Lo que NO se comprueba

- Que un harness **interrumpido con `SIGKILL`** entre la mutación y la
  restauración deje el fichero como estaba. `git checkout --` tampoco lo
  garantizaba; lo que se ha ganado es que la restauración es determinista y no
  depende del estado del índice.
- Que la guarda de capacidad detecte un verbo destructivo escrito de otra
  forma —`["git", "che" + "ckout"]`, o un `os.system` con una cadena montage—.
  Es una evasión deliberada y no un descuido, y queda declarado en vez de
  descubrirse.