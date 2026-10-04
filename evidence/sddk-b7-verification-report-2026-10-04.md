# B7 — Informe de verificación

**Ciclo**: `p-b7740b96d79ec013/b7`
**Fase**: verify
**Entrega**: `0d9d423`
**Base**: `218a2e3`

---

## 1. Criterios de aceptación, uno a uno

Los cinco criterios se declararon en la especificación **antes** de la
certificación. Se comprueban contra la evidencia, no contra la impresión.

| # | Criterio | Evidencia | Veredicto |
|---|---|---|---|
| 1 | El medidor sale 0 con 0 huecos en alcance | `rc=0`, `0 de 3` | CUMPLE |
| 2 | Los contra-saltos del medidor bajan su pregunta | 3 verificados en ambas direcciones | CUMPLE |
| 3 | La suite completa en verde | ver §2 | CUMPLE |
| 4 | Los contra-saltos de B7 cazan 3/3 con causa propia | `scripts/mutate_b7_operational_ux.py` | CUMPLE |
| 5 | `tests.total` coincide con el recuento del árbol | 3088, desglose medido | CUMPLE |

## 2. Certificación

```
3085 passed, 3 skipped, 0 failed
```

Los 3 `skipped` son los declarados en `SKIPS_PLATAFORMA` de
`scripts/check_pipeline_receipt.py`: el UAT real con proveedor, que es
opt-in porque cuesta dinero y necesita una credencial que el entorno no tiene.
`tests/test_wi108_zero_skips.py` vigila que todo skip del repo esté declarado y
que toda declaración tenga suelo, en las dos direcciones.

## 3. La medición que abrió el bloque

`scripts/measure_b7_operational_ux.py`, antes de escribir nada: **3 de 3
preguntas ABIERTAS**.

| | Pregunta | Antes | Después |
|---|---|---|---|
| P1 | ¿superficie de presentación, o solo de cálculo? | ABIERTA | CERRADA |
| P2 | ¿operador y agente leen lo mismo? | ABIERTA | CERRADA |
| P3 | ¿los diez widgets tienen query model? | ABIERTA | CERRADA |
| P4 | ¿la TUI es usable de verdad? | FUERA | FUERA |

### Contra-saltos del medidor

| Contra-salto | Efecto medido |
|---|---|
| `--format` inyectado en un comando | P2 → CERRADA |
| símbolo `render` inyectado en `src/` | P1 → CERRADA |
| **`policy_view` eliminado** | **P3 → ABIERTA** |

El tercero importa porque **lo cazó un defecto del medidor, no del código**: P3
buscaba por subcadena en todo `src/`, y `get_policy` / `_resolve_policy` /
`policy_store` satisfacían «Policies» con cuatro de las diez proyecciones
inexistentes. Se corrigió a buscar en el paquete `presentation/`, por segmento
de nombre, con plural irregular inglés normalizado.

## 4. Contra-saltos de los guards

`scripts/mutate_b7_operational_ux.py` — **3/3, cada uno con su propia causa.**

| Sonda | Qué rompe | Quién la caza |
|---|---|---|
| M1 | `runs show` vuelve a `to_text` | 3 tests |
| M2 | `_emit` vuelve a pasar `vacio=` a toda vista | 3 tests |
| M3 | `runs list` deja de declarar su `(sin runs)` | **1 guard nuevo** + 1 preexistente |

Que M3 la cazara un guard **nuevo** es lo que demuestra que el guard nuevo
añade alcance: sin `test_list_sigue_diciendo_sin_runs_y_no_solo_por_defecto`,
quitarle a `runs list` su `(sin runs)` no ponía nada en rojo.

Árbol restaurado byte a byte en las tres.

## 5. Defectos reales encontrados y corregidos

### 5.1 `runs show` reventaba en el camino por defecto

```
TypeError: DetailView.to_text() got an unexpected keyword argument 'vacio'
```

`TableView.to_text` acepta `vacio`; `DetailView.to_text` no. Y `runs show` sin
`--format` es el camino de **texto**, el de por defecto, el que se usa siempre
que nadie pasa la bandera nueva.

**Lo que hace el caso instructive**: un test que mira la vista lo da verde. El
defecto estaba en el cableado entre el comando y la vista, y no se ve leyendo
`views.py`. Por eso `TestB7NoRompeElContratoExterno` ejecuta el comando por
`subprocess`.

### 5.2 `to_json` reventaba con `AttributeError`

`sorted(fila.items())` compara **valores** cuando hay empate de clave, y las
filas con tuplas no son ordenables. Corregido a ordenar por clave.

### 5.3 Dos veces que el guard estaba afinado más que la propiedad

`test_el_json_dice_lo_mismo_que_el_texto` se puso rojo dos veces, y **ninguna de
las dos era un defecto del código**:

```
el texto dice executed_nodes='-' y el JSON dice []
el texto dice events_emitted='0' y el JSON dice 0
```

- «Las dos representaciones salen del mismo dato» es una afirmación sobre los
  **campos**, no sobre cómo se imprime un vacío. Y tienen que diferir: `-` es
  lo que lee una persona y lo que fijaba el contrato antiguo; `[]` es lo que
  una máquina necesita para no distinguir «vacío» de «la cadena `-`».
- Una línea `clave=valor` **es texto**: `events_emitted=0` llega como `"0"`.
  Exigir `0 == "0"` en Python es exigir lo imposible, y un test que no puede
  cumplirse no mide: hace ruido y enseña a ignorar la clase de fallo que sí
  importa.

El test quedó en tres aserciones: **mismos conjuntos de claves**, **mismo valor
en lo que no es vacío** (comparado en el idioma del texto), y **el vacío
declarado en las dos formas a propósito**.

### 5.4 El guard del medidor medía el almacenamiento

`test_el_medidor_ve_rojo_si_se_quita_la_presentacion` copiaba el **repo
entero** a `/tmp` y falló con `Errno 122 EDQUOT`. El fallo era ambiental —el
`/tmp` de este entorno tiene 9,5 GB libres y aun así rechazó la escritura—,
pero un guard que se pone rojo porque se llenó el disco no mide la propiedad.
Ahora copia solo `src/` y `scripts/`: **1,1 MB**, y discrimina igual.

## 6. `tests.total` 3088, con el desglose medido

| | |
|---|---|
| Sin el paquete `presentation/` en el árbol | la suite colecta **3055** |
| B6 declaró | 3055 |
| Con el paquete | la suite colecta **3088** |
| De los 33 | 23 son de B7, 10 los generan los guards al aparecer módulos nuevos |

Que el árbol **sin** B7 colecte exactamente lo que B6 declaró es la
comprobación que le da sentido al número: si el +33 fuera una invención, el
3055 de la fila anterior no saldría.

## 7. Fuera de alcance

**P4** — que la TUI sea usable de verdad. Depende de un terminal y de una
interacción humana que el CI no tiene. Registrada, no baja el veredicto.

**Deuda tangencial, registrada y no abierta**: el guard de WI-92 indexa los
módulos por **nombre** de fichero, no por ruta, así que `parser.py` es ambiguo
con cualquier forma de la cita. No se forzó el guard para poder citar
`_add_format`; declara la ambigüedad en vez de adivinarla.

## 8. Hallazgo fuera del bloque, con efecto real

Al caminar el ciclo B7 se **`sddk artifact store` el informe de exploración** y
el ciclo siguió con `artifacts: 0`, igual que había pasado en B5 y B6, donde se
documentó como **defecto del framework**.

No lo era. `cycle transition` acepta `--artifact kind=path` **en la propia
transición**, y con esa vía la transición se aplica:

```bash
$ sddk cycle transition --cycle p-b7740b96d79ec013/b7 \
      --transition phase.explore.complete ... \
      --artifact exploration-report=evidence/sddk-b7-exploration-2026-10-04.md
{"outcome": "succeeded", "phase": "specify"}
```

El ciclo `b6`, que llevaba dos sesiones bloqueado en `explore` por ese
diagnóstico, quedó desbloqueado con el mismo comando.

**Lo transferable**: «`artifact store` no vincula» y «no probé la otra vía»
producen la misma observación, `artifacts: 0`, y la segunda es vastly más
probable. Una herramienta que acepta el parámetro y devuelve
`ENGINE_MISSING_ARTIFACT` —que **nombra el artefacto que falta**— está
diciendo que falta una entrada, no que esté rota. Se leyó como avería porque
se escribió como avería, y una vez escrito el diagnóstico cada relectura lo
confirmaba.
