# B7 — Exploración: la UX operacional, por debajo de la TUI

**Ciclo**: `p-b7740b96d79ec013/b7`
**Fecha**: 2026-10-04
**Base**: `218a2e3`
**Entrega**: `0d9d423`

---

## 1. Qué pide el gate

`ROADMAP.md`, sección B7:

> Los diez widgets existen **sobre las mismas APIs y query models**, y cada uno
> escala de summary card a panel a full-screen.

Widgets nombrados: `Graph` · `Timeline` · `Evidence` · `Decisions` · `Resources` ·
`Diff` · `Runs` · `Policies` · `Capabilities` · `Knowledge`.

## 2. Qué se midió antes de escribir nada

`scripts/measure_b7_operational_ux.py` sobre el árbol real. **3 de 3 preguntas
ABIERTAS.**

| | Pregunta | Antes |
|---|---|---|
| P1 | ¿Existe una superficie de presentación, o solo de cálculo? | ABIERTA |
| P2 | ¿Un operador o un agente pueden leer lo mismo? | ABIERTA |
| P3 | ¿Los diez widgets tienen un query model que los alimente? | ABIERTA |
| P4 | ¿La TUI es usable de verdad? | FUERA DE ALCANCE |

### El hallazgo

La palabra cargada del gate es **«las mismas»**, y medido no tenía a qué
referirse:

- **Cero** declaraciones de `--format` o `--json` en 7 módulos de comando.
- **Cero** símbolos en `src/` que expusieran render.

El hueco no es «falta la TUI». Es que **falta la pieza de la que la TUI
depende**. Sin ella, «las mismas APIs» es una afirmación sin sujeto.

## 3. Por qué P4 queda fuera y no baja el veredicto

Que la TUI sea usable requiere un terminal y una interacción humana que el CI
no tiene. Lo comprobable sin humano es la pieza de abajo: la superficie de
render, las proyecciones y las representaciones. P4 queda **registrada** y el
medidor la muestra como `FUERA`, sin contarla ni a favor ni en contra.

## 4. Contra-saltos del medidor, verificados en las dos direcciones

Un medidor que solo sabe dar verde no mide.

| Contra-salto | Resultado |
|---|---|
| Inyectar una declaración `--format` en un comando | P2 baja a CERRADO |
| Inyectar un símbolo `render` en `src/` | P1 baja a CERRADO |
| **Quitar `policy_view`** | **P3 baja a ABIERTA** |

El tercero es el que importa, y lo es por un defecto que se encontró **en el
medidor**, no en el código: P3 buscaba por subcadena en todo `src/`, y
`get_policy` / `_resolve_policy` / `policy_store` satisfacían «Policies» aunque
`policy_view` no existiera. Se corrigió a buscar solo en el paquete
`presentation/`, por segmento de nombre, con normalización de plural irregular
inglés (`capabilities` → `capability`, `policies` → `policy`).

## 5. Qué se entregó

```
src/skillgraph/presentation/views.py     Column, TableView, DetailView
src/skillgraph/presentation/widgets.py   las diez proyecciones puras
src/skillgraph/presentation/__init__.py  la superficie pública
src/skillgraph/cli/parser.py             --format {text,json} en dos comandos
src/skillgraph/cli/commands/runs.py      un único _emit
```

## 6. Los tres bugs reales que aparecieron durante el bloque

### 6.1 `to_json` reventaba con `AttributeError`

Ordenaba con `sorted(fila.items())`, que compara **valores** cuando hay empate
de clave, y las filas con tuplas no son ordenables. Corregido a ordenar por
clave: `sorted(fila)`.

### 6.2 `runs show` salía con `TypeError` en el camino de TEXTO

El más grave, y no lo enseñaba ninguna lectura del código:

```
_emit -> vista.to_text(vacio="(sin runs)")
TypeError: DetailView.to_text() got an unexpected keyword argument 'vacio'
```

`TableView.to_text` acepta `vacio`; `DetailView.to_text` no. Y `runs show` sin
`--format` es **el camino por defecto**, el que se usa siempre que nadie pasa
la bandera nueva. Es decir: el fallo estaba en la representación que todo el
mundo usa, y solo se veía **ejecutando el comando**.

Por eso `TestB7NoRompeElContratoExterno` va por `subprocess` y no contra la
vista. Un test que mira la vista no lo ve.

### 6.3 El contra-salto del propio medidor medía el almacenamiento

`test_el_medidor_ve_rojo_si_se_quita_la_presentacion` copiaba el **repo
entero** a `/tmp` y falló con `Errno 122 EDQUOT` al escribir cientos de MB. El
fallo era ambiental, no del guard — pero un guard que se pone rojo porque se
llenó el disco no mide la propiedad. Ahora copia solo `src/` y `scripts/`:
**1,1 MB**, y discrimina igual.

## 7. Una distinción que el bloque tuvo que hacer

La primera versión de `test_el_json_dice_lo_mismo_que_el_texto` comparaba valor a
valor entre el texto y el JSON, y se puso rojo dos veces:

```
el texto dice executed_nodes='-' y el JSON dice []
el texto dice events_emitted='0' y el JSON dice 0
```

Ninguno de los dos rojos era un defecto del código. Eran el test afinándose más
que la regla:

- **«Las dos representaciones salen del mismo dato» es una afirmación sobre los
  CAMPOS, no sobre cómo se imprime un vacío.** Y tienen que diferir: `-` es lo
  que lee una persona y lo que el contrato antiguo de `runs show` fijaba; `[]`
  es lo que una máquina necesita para no tener que distinguir «vacío» de «la
  cadena `-`». Exigir que coincidieran habría obligado a romper uno de los dos.
- **Una línea `clave=valor` es texto**, así que `events_emitted=0` llega como
  la cadena `"0"`. Exigir `0 == "0"` en Python es exigir algo que no puede
  cumplirse, y un test que no puede cumplirse no mide: hace ruido y enseña a
  ignorar la clase de fallo que sí importa.

El test quedó en tres partes: **mismos conjuntos de claves** (la propiedad),
**mismo valor en lo que no es vacío** (comparado en el idioma del texto), y
**el vacío declarado en las dos formas a propósito** (la aserción explícita de
que la diferencia es deliberada).

## 8. Verificación

- 23 tests en `tests/test_b7_operational_ux.py`.
- Contra-saltos **3/3**, cada uno con su propia causa:
  - M1 `runs show` vuelve a `to_text` → cazada por 3 tests.
  - M2 `_emit` vuelve a pasar `vacio=` a toda vista → cazada por 3 tests.
  - M3 `runs list` deja de declarar su `(sin runs)` → cazada por **un guard
    nuevo** y uno preexistente.
- Árbol restaurado byte a byte.
- Suite completa en el hook del commit: **3085 passed, 3 skipped, 0 failed**.
- `tests.total` 3088, con el desglose **medido**: sin el paquete `presentation`
  la suite colecta 3055 — la cifra exacta que B6 declaró —; al devolverlo,
  3088. Los 10 restantes los genera `wi47` al aparecer los módulos nuevos.

## 9. Lo que sigue abierto

**P4** — que la TUI sea usable de verdad. Depende de un terminal y de un humano.
Se mide cuando haya alguien usándola.

**Deuda tangencial registrada, no abierta**: el guard de WI-92 indexa los
módulos por **nombre** de fichero, no por ruta, así que `parser.py` es ambiguo
con cualquier forma de la cita (existe en `cli/` y en `resources/`). No se forzó
el guard para poder citar `_add_format`; declara la ambigüedad en vez de
adivinarla, que es lo correcto.
