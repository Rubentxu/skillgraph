# B7 — Especificación: la superficie de render y las diez proyecciones

**Ciclo**: `p-b7740b96d79ec013/b7`
**Fase**: specify
**Entrega**: `0d9d423`

---

## 1. Enunciado del requisito

Los diez widgets nombrados por el gate de B7 existen **sobre las mismas APIs y
query models**, y cada uno escala de summary card a panel a full-screen.

Widgets: `Graph` · `Timeline` · `Evidence` · `Decisions` · `Resources` · `Diff` ·
`Runs` · `Policies` · `Capabilities` · `Knowledge`.

## 2. Requisitos, cada uno con su comprobación

Los cinco son verificables por ejecución. Ninguno se acepta por inspección.

### R1 — Existe una superficie de presentación

| | |
|---|---|
| **Comprobación** | existe un paquete `src/skillgraph/presentation/` con símbolos que expongan render |
| **Instrumento** | `scripts/measure_b7_operational_ux.py`, P1 |
| **Estado** | CERRADO |

### R2 — Un operador y un agente leen lo mismo

Un comando de solo lectura declara `--format` con sus dos representaciones.

| | |
|---|---|
| **Comprobación** | ≥ 1 comando declara `--format {text,json}` |
| **Instrumento** | el mismo medidor, P2 |
| **Estado** | CERRADO (2 comandos: `runs list`, `runs show`) |

### R3 — Los diez widgets tienen un query model que los alimente

| | |
|---|---|
| **Comprobación** | las diez proyecciones existen, cada una con su test |
| **Instrumento** | el mismo medidor, P3, y `test_las_diez_proyecciones_existen` |
| **Estado** | CERRADO |

### R4 — Las dos representaciones salen de los MISMOS campos

Esta es la propiedad que hace que la pieza sirva, y la razón por la que la
superficie no es diez `print` distintos.

| | |
|---|---|
| **Comprobación** | los conjuntos de claves del texto y del JSON coinciden; el valor coincide en lo que no es un vacío; el vacío se declara en las dos formas **a propósito** |
| **Instrumento** | `test_text_y_json_dicen_lo_mismo`, `test_el_json_dice_lo_mismo_que_el_texto` |
| **Estado** | CERRADO |

> **Por qué el vacío se compara aparte.** `executed_nodes` se imprime `-` en
> texto y `[]` en JSON. No es una discrepancia: `-` es lo que lee una persona y
> lo que fijaba el contrato antiguo; `[]` es lo que una máquina necesita para no
> tener que distinguir «vacío» de «la cadena `-`». La aserción lo declara
> explícitamente para que nadie lo lea como un descuido.

### R5 — Una vista no es una segunda vía de consulta

| | |
|---|---|
| **Comprobación** | el paquete `presentation/` no importa `sqlite3` ni `platform.storage`, y no abre ninguna ruta |
| **Instrumento** | `test_el_paquete_no_importa_storage_ni_sqlite`, `test_el_paquete_no_abre_ninguna_ruta`, por AST |
| **Estado** | CERRADO |

## 3. Requisito que se añadió al encontrar el defecto

### R6 — B7 no rompe el contrato externo que ya existía

**No estaba en el enunciado del gate, y hacía falta.** `cmd_runs_show` promete
`clave=valor` en su docstring, y `test_cli_runs_inspect.py` lo fija.

| | |
|---|---|
| **Comprobación** | sin `--format`, `runs show` sigue emitiendo `run_id=…`, `state=…`, `current_node=…`, y NO es el panel |
| **Por qué por subprocess** | el defecto estaba en el **cableado** entre el comando y la vista, no en la vista. Un test que mira la vista lo da verde. |
| **Instrumento** | `TestB7NoRompeElContratoExterno` (3 tests) |
| **Estado** | CERRADO |

**Defecto real que R6 existe para cazar**, medido contra:

```
_emit -> vista.to_text(vacio="(sin runs)")
TypeError: DetailView.to_text() got an unexpected keyword argument 'vacio'
```

`TableView.to_text` acepta `vacio`; `DetailView.to_text` no. Y `runs show` sin
`--format` es el camino por defecto — el que se usa siempre que nadie pasa la
bandera nueva.

## 4. Fuera de alcance

### P4 — que la TUI sea usable de verdad

Depende de un terminal y de una interacción humana que el CI no tiene. Se
**registra** y no baja el veredicto: el medidor lo muestra como `FUERA` sin
contarlo ni a favor ni en contra.

## 5. Criterios de aceptación del bloque

1. `scripts/measure_b7_operational_ux.py` sale 0 con 0 huecos en alcance.
2. Sus contra-saltos bajan la pregunta correspondiente — verificado en ambas
   direcciones.
3. La suite completa en verde.
4. Los contra-saltos de B7 cazan **3/3**, cada uno con su propia causa.
5. `tests.total` coincide con el recuento real del árbol.

## 6. Cumplimiento a 2026-10-04

| # | Criterio | Resultado |
|---|---|---|
| 1 | medidor sale 0, 0 huecos | `rc=0`, 0 de 3 |
| 2 | contra-saltos del medidor | 3 verificados, incluido P3 con `policy_view` fuera |
| 3 | suite completa | **3085 passed, 3 skipped, 0 failed** |
| 4 | contra-saltos de B7 | **3/3**, causas distintas; M3 la cazó un guard nuevo |
| 5 | `tests.total` | 3088, con el desglose medido (3055 sin el paquete + 33) |
