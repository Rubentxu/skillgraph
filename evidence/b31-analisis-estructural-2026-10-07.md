# B31 — Analisis estructural: de evidencia que nadie preguntaba a afirmaciones

> Medicion hecha **antes** de escribir una linea, con store de verdad.
> Script: `scripts/measure_b31_analisis.py`, tres rondas.
> Instrumento de sondas: `scripts/mutate_b31_analisis.py`, siete sondas.
> ADRs: `ADR-0035`.
> Commits: `444cbf4` (feature), `9eda144` (identidad del claim),
> `68a28d0` (las salidas que subian los suelos).

## La fila del roadmap es FALSA en su primera mitad

La fila de B31 dice:

> No hay analisis estructural real: `line_count = 137` es todo lo que se
> sabe del codigo.

Medido antes de tocar nada (`RONDA 1`):

```
E1  capabilities de analisis de codigo en src/          CERO
E2  de los 7 predicados del Literal, con escritor en src/   1 de 7
E3  record_evidence_for_file_signature -> Evidence, NUNCA Claim
E5  NUCLEO = ("runtime", "core", "resources") -> knowledge/ NO esta
```

El analisis estructural **existe**, es de este repo y es real:
`knowledge/file_signature.py` son 431 lineas puras y deterministas que ya
extraen imports, definiciones y cobertura con regex. La fila no describe lo
que falta; describe lo que nunca se **convirtio**.

`RONDA 2` lo confirma contra el extractor puro, sin store:

```
superficie.py: 24 FileSignature   module=9  def=14
module.foco[0] = src/.../superficie.py::annotations
def.foco[0]    = src/.../superficie.py::def::pregunta

  predicado         sale del extractor?      que haria falta
  line_count        SI — summary.cobertura    1 claim por fichero
  file_exists       SI — summary.state        1 claim por fichero
  function_count    SI — contar contrato=def  1 claim por fichero
  imports_module    SI — contrato=module      1 claim POR MODULO
  defines_symbol    SI — contrato=def         1 claim POR SIMBOLO
  spec_revision     NO — no es del extractor
  test_passes       NO — exige ejecutar la suite
```

Cinco de siete. Los otros dos **se declaran inalcanzables** con su motivo,
no se inventan.

### Lo que E2 decia, y por que los tres `line_count` no eran un claim

`line_count` tenia 6 menciones en `src/`. Tres eran `method="line_count"` en
`file_signature.py`, dos eran METADATA (la constante de
`PREDICADOS_DERIVADOS` y el `Predicate` del Literal) y una era un comentario.
**Ninguna era una escritura de un claim.** Un guard que cuenta menciones de
una cadena habria dicho «tres escritores» y no habria mirado de que eran
tres cosas distintas.

### E4: los tests siembran los siete a mano

```
line_count      69 menciones, ninguna producida por un analizador
imports_module  36 menciones, ninguna producida por un analizador
test_passes      4 menciones, ninguna producida por un analizador
...
```

O sea que la base de pruebas **conoce** los siete predicados y **ninguno** ha
salido de un extractor. Es knowledge escrito a mano.

## El hallazgo que abrio el bloque: 7 observaciones, 5 filas

Montado de punta a punta, con store real:

```
7 observaciones  ->  7 claims  ->  5 filas
```

`imports_module='Final'` y `defines_symbol='abajo'` **desaparecian en
silencio**. Y `impact` respondia 0 sobre esos hechos.

La causa, leida del DDL:

```sql
UNIQUE (subject_entity_id, tenant_id, project_id,
        predicate, source_id, checked_at_revision)
```

**El objeto no forma parte de la identidad.** Un fichero que importa dos
modulos no se contradice: son dos hechos ciertos a la vez, y la clave decia
que solo cabia uno. El segundo se comia al primero sin error, sin evento y
sin log.

Este defecto era invisible a cualquier test anterior porque **no habia nadie
que afirmara dos hechos distintos sobre el mismo par (sujeto, predicado) con
la misma fuente y revision**. Los tests que existian sembraban un objeto, o
dos, pero nunca el caso que lo rompe.

## La decision, y por que abrio una ADR

La pregunta era si el objeto entra en la identidad del claim. Se pregunto al
usuario (`ask_3f945fec4c8e89a89557f290`) porque cambia el esquema y es
irreversible en bases viejas. La respuesta: migracion `0008` con el objeto en
la identidad, **dentro de B31 y con su ADR**.

`ADR-0035` deja escrito por que se metio el objeto **y por que la clave
sigue llevando `source_id`**:

- **Conflicts de B27 intactos.** La clave sigue llevando `source_id`, luego
  dos fuentes distintas sobre el mismo hecho siguen siendo dos claims que
  chocan. Si el objeto hubiera entrado **sustituyendo** al `source_id`, un
  conflicto real se habria convertido en dos hechos que conviven.
- **Deduplicacion de B26 intacta.** Reingerir reconstruye el mismo objeto,
  luego el mismo `claim_id`: idempotente sigue siendo idempotente.

### Y `make_claim_id` cambia JUNTO, no despues

MEDIDO: con el `UNIQUE` de `0008` ya escrito y `make_claim_id` sin el objeto,
**seguian perdiendose 2 de 7**. Los dos claims salian con el mismo
`claim_id` y el segundo chocaba con la PRIMARY KEY — un fallo distinto, con
otro mensaje, en otra capa.

El fallo no se ve leyendo el `UNIQUE`: se ve contando filas. Y por eso esta
sonda, `N1`, es la que mas importa de las siete.

`make_claim_id` separa el objeto por FORMA, con prefijo:

```
l:<literal>      e:<entity>
```

Sin prefijo, `make_claim_id("x", "a:b")` y `make_claim_id("x", "l:a:b")`
darian el mismo id, que es una colision de namespace construida a proposito.

Hay un test que ata las dos mitades
(`test_record_claim_idempotent_on_full_tuple`): la misma llamada **sin**
objeto tiene que dar un id **distinto**.

## La migracion 0008: derivada del DDL existente, preguntando al motor

`0008_claims_identidad_con_objeto` no escribe un `CREATE TABLE` escrito a
mano. Toma el DDL de la tabla ya viva y le quita el `UNIQUE` viejo
(`_ddl_de_claims_con_objeto`), porque el DDL a mano divergiria de la tabla el
dia que una columna nueva se anada y nadie se acuerde de la migracion.

La comprobacion de «ya esta migrado?» la hace **el motor**, no el DDL
(`_el_unique_ya_lleva_objeto`): pregunta a `pragma_index_list` con
`origin='u'`. MEDIDO y escrito en el codigo: un `CREATE UNIQUE INDEX` sale
como `origin='c'`, luego **no cuenta** — un indice unico separado no es el
UNIQUE de la tabla, y confundir los dos daria una base «migrada» que no lo
esta.

Y el `UNIQUE` nuevo vive **solo en la migracion**, igual que el indice de la
ventana de B33. MEDIDO: el indice duplicado en `schema.py` reventaba bases
viejas con `no such column: observed_from`, porque `CREATE TABLE IF NOT
EXISTS` no toca una tabla que ya existe pero si crea el indice que la
referencia.

### Y la migracion que pierde filas falla

`0005` escribio la comparacion del `COUNT` con el criterio «peor que no
migrar». B31 la usa de verdad: `TestLaMigracionEsIdempotente` levanta una base
con el `UNIQUE` viejo y comprueba que se reconstruye **conservando las
filas**, y otro test levanta una migracion que **descarta** una fila y
comprueba que **falla** en vez de seguir como si nada.

Ese segundo test no reimplementa la migracion dentro del test para
provocarla —seria una segunda copia de la regla, que diverge el dia que una
se actualice y la otra no—. La sonda muta el codigo de verdad.

## La capability: el puente, y lo que NO es

`src/skillgraph/knowledge/code_analysis.py`, 458 lineas, `sg.code.analysis`.

Entrega el **puente**: dado el contenido de un fichero, produce el
`ObservationEnvelope` versionado de B26 con los cinco predicados que el
extractor sabe sacar, y `normalizar` lo convierte en `Claim`s.

NO entrega un analizador nuevo. El que hay es mejor que uno nuevo
—determinista, puro, con 431 lineas ya probadas— y duplicarlo seria tener dos
verdades sobre el mismo fichero que divergirian sin que nadie lo notara.

**NO lee el disco.** El contenido entra por `request.arguments['content']`,
por el mismo motivo que en `telemetry_query.py`: una capability que abre
ficheros tiene I/O oculto, y `AGENTS.md` 1.3 lo prohibe en el nucleo. Quien
decide que se analiza es quien tiene el fichero; esta capa solo sabe que
significa.

**NO escribe en el store**, por `ADR-0027`: un adaptador que escribe deja de
ser un adaptador y pasa a ser la razon por la que hay que confiar en el.

### `local_file` ya existia: no se abre ADR para no usar el kind correcto

`SourceKind` ya tenia `local_file` desde antes de que existiera esta
capability. B33 si abrio `ADR-0034` porque `runtime_observation` **no
existia**. Aqui el valor que corresponde ya existe y ya significa
exactamente esto; abrir una ADR para no usarlo seria fabricar trabajo.

### La frontera, y por que NO hay un guard nuevo

`RONDA 3` lo mide:

```
con `import cognicode` en knowledge/telemetry_query.py: rc=0
    VERDE <-- el hueco
```

`TestElNucleoNoImportaAdapters` da **VERDE** con un import de CogniCode
dentro de `knowledge/`, porque `NUCLEO = ("runtime", "core", "resources")` no
incluye `knowledge/`.

Y **no se arregla en B31**, y el motivo esta escrito: anadir `knowledge` a
`NUCLEO` no amplía la comprobacion, **cambia que se considera nucleo**, que
es la decision de B3 y no de B31. Ese guard es una lista de **paquetes**, no
de ficheros, y cambiar la lista es redefinir la frontera.

B31 se sostiene **por construccion**: no importa ningun producto externo,
porque no hace falta ninguno —`extract_file_signatures` ya es de este repo—.
Y eso se declara en el docstring del modulo, para que el siguiente que
llegue lea el porqué antes de decidir si añade un import.

### `extraction_method` va en la OBSERVACION, no en el envelope

MEDIDO sobre un fichero real: el extractor produce **tres** metodos —
`line_count`, `regex_import`, `regex_def`— y los tres son ciertos para
observaciones distintas del mismo analisis. Un envelope con un unico metodo
solo podria ser verdad para una de las tres.

Por eso `extraction_method` se anadio a `Observation` y no al envelope.
`None` significa «metodo externo» (`METODO_EXTERNO`), que es exactamente lo
que decia el codigo antes de B31: los envelopes de B26 y B33 siguen dando
claims **identicos**, verificado.

Y `function_count` declara `regex_def` aunque no salga de una firma
concreta, porque el NUMERO sale de recorrer con ese regex. Se escribe como
constante, y no se deduce de `s.procedencia`: deducirlo seria tomar el
metodo de la primera firma y aplicarlo a un hecho que no produjo ninguna.

### `imports_module` lleva un NOMBRE, no una entidad

Aqui `Claim.object_entity` (B25) **no aplica**: lo que se afirma es *el texto
del modulo importado*, no una entidad del grafo. `imports_module` de `x.py`
vale `"os"`, no vale «la entidad `module:os`», porque esa entidad no esta
registrada en ninguna parte y apuntarla seria inventar un enlace que nadie
creo.

## Cuatro tests que afirmaban lo contrario, actualizados SIN DEBILITARSE

Un bloque que cambia la identidad de un claim rompe tests que afirmaban la
identidad vieja. La tentacion es ajustarlos. Los cuatro se ajustaron
**haciendolos mas fuertes**, y cada uno tiene ahora un hermano que dice lo
contrario:

| fichero | test | antes | ahora |
|---|---|---|---|
| `test_b27_conflictos.py` | `test_la_fila_anterior_no_se_toca` | la fila vieja se conserva | **las dos** filas intactas |
| `test_b27_conflictos.py` | `test_el_overwrite_no_toca_la_fila_que_ya_esta` | idem | idem |
| `test_r1f_identidad_claim.py` | `_insert_crudo` con objeto fijo | `"otro"` vs `"psycopg"` | objeto es **parametro** |
| `test_knowledge_controller.py` | `test_record_claim_idempotent_on_full_tuple` | (42, 42) | (42, 42) + que sin objeto el id **difiere** |

Y dos tests **nuevos**, que antes no existian porque no habia nada que
probar:

- `test_B31_mismo_ambito_distinto_objeto_SI_se_puede_escribir`
- `test_record_claim_distinto_objeto_es_otro_claim`

39 tests en `tests/test_b31_analisis.py`, 11 clases. Los tres usos de
`line_count` que E2 senalo como metadata tienen su propio
`TestLaProcedenciaEsVerdadera`, que es la clase que mide que cada
observacion declara **su** metodo.

## Sondas de mutacion: 7/7

```
cazadas 7/7   invalidas 0   sin sonda 0
baseline rc=0: 71 passed
```

Dos familias, y la division es el bloque:

```
S1..S3  la vertical   — que cinco observaciones produce, y de verdad
N1..N4  ADR-0035     — que la identidad del claim siga sosteniendose
```

**Dos sondas fueron INOCUA la primera vez, y sus motivos importan mas que
sus arreglos.**

### N2 apuntaba al `UNIQUE` de `schema.py`, y ahi no se puede romper

Cambiar el `UNIQUE` de `schema.py` a pelo **no rompe NADA**, porque `0008`
reconstruye la tabla de una base nueva igual que de una vieja. Ese `UNIQUE`
es una redundancia que la migracion siempre repara — y una sonda que mide
una propiedad que no se puede romper por ahi es vigilar una verdad imposible
de violar.

Rehecha contra el DDL de la **migracion**, que es el que decide sobre las
bases viejas, y que `schema.py` no alcanza.

### N4 apagaba un `if` que nunca se enciende

La sonda apagaba el `if` del `COUNT` con `if False:` y no pasaba nada: en el
camino feliz la copia conserva todas las filas, luego ese `if` no se activa
nunca. Un guard que solo se dispara en un caso que nadie construye no esta
midiendo: esta decorado.

Rehecha **rompiendo la COPIA** (`LIMIT 1`), que es lo que haria de verdad una
migracion mal escrita. Entonces la comparacion del `COUNT` se enciende sola y
la migracion levanta.

### Un bug del harness que hacia que las sondas no midieran nada

`TESTS_ID` era un **string** con espacios pasado a pytest como un argumento
unico, luego pytest recibia una ruta que no existe: `rc=4: no tests ran`. El
harness lo contaba como «BASELINE ROTO» y se paraba — es decir, la sonda mas
importante, la N1, nunca llego a correr.

Convertido a tupla, con el motivo escrito en el propio codigo.

## Una rama INALCANZABLE se quito, y por que no se testeo con carton

La primera version de `sujeto_de` envolvia la llamada a `entity_id` en un
`except Exception` que re-lanzaba tipado «porque puede reventar por mas de
una razon».

MEDIDO sobre `graph.py:96`, que es toda la regla:

```
entity_id rechaza DOS cosas: vacio, o sin `:`.
```

Y como ahi siempre se antepone `file:`, el resultado **siempre** tiene dos
puntos. **La rama era inalcanzable**, y una rama inalcanzable con un `except
Exception` dentro es la peor version de un guard: no mide nada, y ademas
obliga a fabricar una entrada falsa para poder probarla —que es fabricar una
prueba que no prueba el caso real—.

Se **quito** la rama. No se fabrico un test de carton para cubrirla.

Y al quitarlo aparecio `code_analysis.py` en 88,76 %: el suelo de §6.3 hizo el
trabajo que un test de carton habria hecho peor. Las dos salidas de error que
quedaron (`content` que no es `str`, y `path`/`observed_at` ausentes) se
cubrieron con tests de verdad, y el modulo subio a **100 %**.

## Un guard de seguridad se instrumenta aunque hoy sea inalcanzable

Los filtros de nombre de indice de `migrations.py` protegen una **interpolacion
SQL**: nunca se ejecutan con una base real, porque los indices los crea la
migracion. Se instrumentaron con un cursor falso **y con un contrasalto**
que exige que el guard encuentre al menos un filtro.

La razon por la que no se dejan sin cubrir es que protegen SQL, y un filtro
de nombres de indice que alguien escribiera mal no se Discovering en la
prueba: se descubre en produccion.

## Recibo de certificacion

Sobre los datos de ESTA corrida (`/tmp/b31_cert3.txt`, commit `68a28d0`):

```
pytest              4065 passed, 3 skipped, 0 failed   855,69 s   RC=0
TOTAL cobertura     97 %   (global 97,14 %, fail_under 80 %)

suelos AGENTS 6.3   todo modulo gobernado cumple su suelo          RC=0
  cli/                        93,18 %   (suelo 70 %)   11 modulos
  runtime/                    98,41 %   (suelo 90 %)   12 modulos
  code_analysis.py            100 %
  observation.py              100 %
  observation_ingestion.py    100 %
  superficie.py               100 %   (de B34)
  knowledge_query.py          100 %   (de B34)
  schema.py                   100 %
  knowledge_controller.py      96 %
  migrations.py                95 %   (192-194 y 351, de 0001/0005;
                                         571-572 = rollback de 0008)

arquitectura (ratchet) 5/5 a cero                                      RC=0
  god modules > 800: 0 · complejidad publica >= 20: 0 · SQL en el dominio: 0
  dominio -> platform: 0 · referencias normativas rotas: 0

sondas de mutacion B31  7/7   invalidas 0   sin sonda 0             RC=0
project_truth       4068 declarados == 4068 colectados                RC=0
```

`tests.total` paso de **4029 a 4068**, sincronizado en `STATE.yaml`,
`ROADMAP.md` y `CURRENT.md`. El recuento viene de `pytest --collect-only`
sobre el arbol real, no de una copia escrita en el test (la regla de WI-115).

Las 3 lineas que `migrations.py` deja sin cubrir se **declaran** en vez de
taparse: dos son de `0001`/`0005` y una es el **rollback** de `0008`, que
ningun camino de produccion ejecuta porque una migracion que se deshace
deberia ser un acto deliberado, no el efecto secundario de un fallo.

## El bug latente que aparecio al arreglar el otro

Al meter el objeto en `make_claim_id`, la reconstruccion del `Claim` al
leerlo de la base **seguia perdiendo `object_entity` y `assertion_origin`**.

Es decir: un claim con entidad se escribia bien y se releia sin ella. Y como
`Observation` exige **exactamente un** objeto (literal XOR entidad, desde
B25), perder `object_entity` sin su `object_literal` habria roto el XOR en
silencio.

No lo buscaba nadie porque antes de B31 **nada producia** un
`object_entity` desde analisis. Lo arreglo el mismo commit, porque un test
que escribe con entidad y no lee con entidad es un test que no cierra el
ciclo.

## Lo que este bloque DEJA, con nombre

1. **`spec_revision` y `test_passes` siguen sin escritor.** No es deuda de
   B31: no salen del extractor. Cada uno necesita un analizador distinto y
   ninguno es un analizador de estructura de fichero.

2. **El guard de la frontera (`NUCLEO`) no incluye `knowledge/`.** MEDIDO y
   VERDE con un import de CogniCode dentro. Arreglarlo es redefinir que es
   nucleo, que es decision de B3, y por eso queda escrito aqui y no tocado.

3. **36 citas de instrumentos no versionados siguen abiertas.** El coste de
   esta evidencia es cero en git, pero las citas que apuntan a
   `.pipelinek/*.py` no se pueden reproducir con un clon. Las de B31..B34 se
   migraron a `scripts/` en `f698979`; las 36 restantes son de bloques
   anteriores y **no** se des-ignoran mientras 8 de esos 137 scripts
   hardcodeen rutas de esta maquina.

4. **`NUCLEO` como lista de paquetes** es una fragilidad que ya ha dado un
   falso verde. El nombre del paquete, no sus ficheros, es lo que se vigila;
   anadir un subdirectorio a `knowledge/` no lo cambia y no se veria.

## Lo que NO se comprueba

- Que un `UNIQUE` con 8 columnas se beneficie de un indice en SQLite. Se
  migration por **correccion semantica**, no por rendimiento; con el tamano de
  tabla de este repo el escaneo lineal no se nota, y nadie ha medido el
  contrario.
- Que el extractor `file_signature.py` siga siendo correcto. MEDIDO: esta al
  97 %, con 4 lineas sin cubrir (87, 95, 118, 169) que son **anteriores** a
  B31. No se tocaron porque corregir un extractor que nadie ha reportado mal
  es refactorizar algo cuya falha no esta medida.