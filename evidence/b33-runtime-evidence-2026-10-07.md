# B33 — Runtime evidence vertical

> Medición hecha **antes** de escribir una línea, con store de verdad.
> Script: `/tmp/b33_measure.py` y `/tmp/b33_measure2.py` (se guardaron fuera
> del repo a propósito, porque la certificación de B32 estaba corriendo y
> editar durante una certificación la invalida — B23).

## El gate que el roadmap escribe, y por qué no puede ser el gate

La fila de B33 dice:

> Un claim runtime que contradice un ADR abre conflicto; `actual_behavior`
> prefiere runtime e `intended_architecture` prefiere la decisión aceptada.

Montado sobre un store de verdad, **antes de escribir nada**:

```
fuentes:  adr:0001           kind=external_doc   c-adr       "psycopg"  human-asserted
          runtime:ventana-1  kind=external_doc   c-runtime  "sqlite3"  observed

conflicts_for       -> 1 conflicto: [c-adr, c-runtime]
resolver actual_behavior   -> c-runtime
resolver intended_behavior -> c-adr
```

Funciona. Y es **exactamente el ejemplo con el que B28 certificó su propio
bloque**: su `_el_conflicto_del_bloque` se llama `c-runtime` contra `c-adr`
(`tests/test_b28_autoridad.py:99`).

Es decir: **el gate de B33 mide el resolver de B28**. Se puede «cerrar» el
bloque sin escribir una sola línea, y no se vería en ninguna cifra. Por eso
`TestElGateDelRoadmapYaLoCumpliaB28` monta el caso **sin B33** y ata que la
afirmación siga siendo cierta — para que quien lo lea sepa que por eso hace
falta OTRO gate, no que el de B28 era mentira.

## Lo que sí faltaba: las cinco entregas

```
E1 telemetry.query.v1        CERO en src/, fuera de prosa
E2 adapter Chronos/OTel      CERO; no hay adapters/ en ninguna parte
E3 temporal window sources   CERO: checked_at y observed_at son INSTANTES,
                             y la ventana de Claim es por REVISION (B29)
E4 runtime claims            la MECANICA existe (normalizar ya pone
                             assertion_origin="observed"), pero la fuente
                             salia como external_doc
E5 perfil actual_behavior    YA EXISTE (B28)
```

## Y para registrar una observación de runtime había que MENTIR

```
[1] las dos filas se ven IGUALES por kind
    adr:0001           kind=external_doc
    runtime:ventana-1  kind=external_doc      -> 1 valor distinto
[2] json_extract(locator_json, '$.producer')  FUNCIONA -> ['runtime:ventana-1']
[3] indices sobre sources: idx_sources_project, idx_sources_commit
    NINGUNO sobre locator_json, NINGUNO sobre kind
[4] columnas de sources: ni producer, ni adapter, ni type_name
```

El discriminante **existe** y **se puede consultar**, pero cuesta abrir el
JSON y recorrer la tabla. Y la pregunta que B33 quiere responder es
precisamente la que responde `actual_behavior` —«¿qué devolvió producción de
verdad?»—, que es la que más lo necesitaba.

## La decisión estaba pendiente desde B26, y ESTÁ ESCRITA EN EL CÓDIGO

`src/skillgraph/knowledge/observation.py` (antes de B33), sobre el kind que
usaba:

> `external_doc`, y NO un kind nuevo. `SourceKind` es un Literal cerrado y
> AGENTS.md 2.1 dice que anadir un valor es un cambio de contrato que
> necesita ADR.

**Esa ADR nunca se abrió.** Se abrió en este bloque: `ADR-0034`.

### Radio de impacto, MEDIDO y pequeño

- `Source.__post_init__` valida contra `typing.get_args(SourceKind)`, luego
  el valor nuevo se acepta sin tocar la validación.
- La regla `kind.startswith("git_")` exige SHA: `runtime_observation` no
  empieza por `git_`, luego no lo exige — y es correcto, porque una
  observación de runtime no viene de un commit.
- **No hay `CHECK` de SQL sobre `sources.kind`** (leído del DDL), luego no
  hay migración que forzar sobre filas que ya existen.
- `test_runtime_events.py` mira `skill_pack in SOURCE_KINDS` y que
  `SOURCE_KINDS` se derive del `Literal`: las dos siguen cumpliéndose, y la
  segunda es la regla QW-E, que se cumple creciendo el **`Literal`** y no la
  constante.

## Lo que entra

| qué | antes | después |
|---|---|---|
| `SourceKind` | 5 valores | **6** (`runtime_observation`) |
| `Source` | 9 campos | **11** (`observed_from`, `observed_to`) |
| `sources` | 11 columnas | **13** |
| `ObservationEnvelope` | 7 campos | **10** (`kind`, `observed_from`, `observed_to`, todos con default) |
| capability | — | `sg.telemetry.query` (E1) |
| migración | `0006` | **`0007_sources_ventana_de_runtime`** |
| índice | — | **`idx_sources_ventana`**, parcial |

Un envelope de B26 **sigue produciendo exactamente lo mismo**: `kind=None`
significa `external_doc`, y está medido con un test que se llama
`test_un_envelope_sin_kind_sigue_siendo_external_doc` y que dice en su
docstring que es «el que NO debe cambiar».

## Lo que este bloque NO hace, declarado

1. **No entrega un cliente de Chronos ni de OpenTelemetry.** Entrega el
   **contrato**. El adaptador que sabe es el despliegue, y lo recibe por un
   `Protocol` (`LectorTelemetria`). Medido: `chronos`, `opentelemetry` y
   `otel` **no están en `pyproject.toml`**; añadir un cliente de red para
   poder medir un contrato sería comprar una dependencia sin criterio para
   no medir nada.
2. **No deduce el kind de la forma del envelope.** «Trae ventana → es de
   runtime» se rechazó: una medición de test también cubre un periodo, y
   esa regla haría que `normalizar` publicara un kind distinto para el mismo
   tipo de observación según quién la mire. El kind lo **declara** el
   envelope, y `None` es lo que siempre meaning.
3. **No abre el `por_que`.** Es de B33/B34 según el roadmap original, y B32
   dejó un guard que ata que no exista.
4. **No mete la ventana en el `locator`.** Se midió que ahí funciona pero
   sin índice, y con `sources` creciendo con la serie B25..B32, no es un
   sitio donde viva una columna que se consulta.

## El defecto que casi se lleva el bloque

La primera versión puso `idx_sources_ventana` **también** en `schema.py`,
junto al `CREATE TABLE`. Sobre una base nueva funciona. Sobre una base
**vieja** —que ya tiene `sources` sin las columnas— el
`CREATE TABLE IF NOT EXISTS` es un no-op y el `CREATE INDEX` siguiente
revienta con `no such column: observed_from`, **antes de que corra ninguna
migración**. Lo caza `TestUnaBaseViejaSeAbre`, de B25.

El índice quedó **solo** en la migración `0007`, y el motivo está escrito en
`schema.py` **junto al sitio donde NO está**, que es donde alguien lo
volvería a poner.

## Las sondas: 8/8, y una estuvo mal anclada

`.pipelinek/b33_mutate.py`, con baseline verificado antes (si el baseline
está roto, cada sonda sería «cazada» por una causa que no es la suya):

```
baseline rc=0: 37 passed
  CAZADA  M1 normalizar vuelve a external_doc
  CAZADA  M2 la ventana no se valida en el Source
  CAZADA  M3 ventana sobre cualquier kind
  CAZADA  M4 la migracion 0007 no corre
  CAZADA  M5 el indice deja de ser parcial
  CAZADA  M6 el payload omite la ventana
  CAZADA  M7 ventana sin `desde` se acepta
  CAZADA  M8 la capability ignora la ventana
cazadas 8/8   invalidas 0   sin sonda 0
tras restaurar: rc=0
```

**M8 dio INOCUA la primera vez, y no era un guard roto: era la sonda
apuntando al test que no distingue.** `test_dos_invocaciones_dan_el_mismo_
envelope` compara dos envelopes, y con `observed_to=None` en los dos siguen
siendo iguales — la property que mide es la idempotencia, y mutar el final
de la ventana no la rompe. MEDIDO antes de corregir el anclaje: apuntando a
`TestLaVerticalEntera::test_la_capability_produce_un_envelope_de_runtime_
con_ventana`, `rc=1`.

Es el mismo error que la M3 de B29 y que el error 32 de WI-113: **la sonda
tiene que apuntar a la property, no al fichero que parece conveniente**. El
harness distingue `SIN_SONDA`, `CAZADA`, `INOCUA` e `INVALIDA` por eso.

## Cobertura y suelo

`knowledge/telemetry_query.py` entra nuevo y hay que medirlo, no suponerlo:
`check_coverage_floors.py` decide, y su suelo es el del paquete —90 %.
## La certificacion, y una causa que NO era del codigo

La primera certificacion de B33 termino en `rc=1` con **13 fallos y 141
errores**. Los errores de setup eran todos el mismo:

```
OSError: could not create numbered dir with prefix ... in
         /tmp/pytest-of-rubentxu/pytest-1985 after 10 tries
```

La primera hipótesis fue la concurrencia —había corrido diagnósticos durante
la primera certificación, que es el modo de fallo que este repo ya conoce—,
así que se paró, se limpió y se relanzó **sin tocar nada**. Falló igual.

Medido entonces:

```
df -i /tmp
tmpfs  1048576  1022426   26150  98 %      <- INODOS
```

`/tmp` tenía **26 150 inodos libres** y 536 directorios de pytest
acumulados, más 721 `/tmp/tmp.*` huérfanos de las certificaciones
canceladas. No era el repositorio: pytest no podía ni crear su directorio
temporal. Liberados (26150 -> 97540), la tercera certificación pasó limpia.

**Lo que se aprende, y no es «hay que limpiar /tmp»:** el `glob('.coverage*')`
que se usó para limpiar los datos de cobertura **también borra
`.coverage.rc`**, que es el fichero de CONFIGuración. No rompe nada porque
`coverage.sh` lo regenera en cada corrida —y por eso las tres
certificaciones funcionaron— pero una corrida dirigida con `--cov-config`
falla con `Couldn't read '.coverage.rc'`. El patrón correcto es borrar
`.coverage` y `.coverage.parallel*`, y **no** `.coverage.rc`.

## Resultado

```
pytest                 3957 passed, 3 skipped, 0 failed   779,83 s   rc=0
cobertura total        97 %
  src/skillgraph/knowledge/telemetry_query.py   100 %  (56 stmts, 0 missing)
  src/skillgraph/knowledge/observation.py       100 %
  src/skillgraph/knowledge/graph.py              99 %
  src/skillgraph/platform/knowledge_sources.py  100 %
check_coverage_floors   rc=0   «todo modulo gobernado por §6.3 cumple su suelo»
check_architecture      5/5 a cero
project_truth           rc=0   coherente, 0 contradicciones,
                               tests declarados 3965 == 3965 colectados
```

El módulo nuevo entró en **91 %**, justo sobre el suelo del 90 %. Se subió a
**100 %** cubriendo las cuatro formas en que una petición puede venir rota
—`ventana` ausente, `ventana` que no es mapping, mapping sin `desde`, y
`hasta=""`— porque son caminos reales y alcanzables, no ramas defensivas.
Subir el módulo es lo que se hace; bajar el suelo no.

## Los siete fallos de la suite que NO eran de B33

Al correr la suite completa aparecieron siete, y ninguno era del bloque:

| fallo | causa | cerrado por |
|---|---|---|
| `test_b15`, `test_wi97` | `check_package_build.py rc=1`: el sdist incluía ficheros que **git no versionaba** | commitear antes de certificar |
| `test_b0`, `test_b14` | las ventanas de verdad declaraban 3920 con 3960 en el árbol | sincronizar a 3965 |
| `test_wi116` | había trabajo sin commitear entre `scripts/` y `src/` | commit |
| `test_wi92` | la cita `observation.py:242` **no nombraba símbolo** | `observation.py:250::normalizar` |

El de WI-92 tiene dos caras y las dos son suyas: la cita no decía a qué
símbolo apuntaba —ese guard existe porque `fichero.py:352` es cierto y no
dice nada— **y además la línea 242 ya no decía lo que la cita afirmaba**,
porque B33 movió el código que la cita describía. El formato es
`fichero.py:LINEA::simbolo` con **dos** puntos.

## La certificacion FINAL, sobre el arbol definitivo

Despues de anadir los cinco tests de entrada malformada (`047e29b`), la
corrida completa sobre el commit definitivo:

```
pytest                 3962 passed, 3 skipped, 0 failed   813,62 s   rc=0
cobertura total        97 %   (7639 stmts, 171 missing)
  src/skillgraph/knowledge/telemetry_query.py   100 %  (56 stmts, 0 missing)
check_coverage_floors   rc=0   suelo global 97,06 %
check_architecture      5/5 a cero
project_truth           rc=0   coherente, 0 contradicciones,
                               3965 declarados == 3965 colectados,
                               workitem_current == workitem_state == B33
```

3962 + 3 skips = **3965**, que es la cifra declarada. Los 3 skips son los
de plataforma de `SKIPS_PLATAFORMA`, contados en las dos direcciones por el
guard de WI-108.
