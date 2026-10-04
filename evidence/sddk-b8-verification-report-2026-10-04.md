# B8 — Informe de verificación

**Ciclo**: `p-b7740b96d79ec013/b8`
**Fase**: verify
**Entrega**: `4d72177` · evidencia `ba6106a`
**Base**: `7363f0f`

---

## 1. Criterios de aceptación, uno a uno

| # | Criterio | Evidencia | Veredicto |
|---|---|---|---|
| 1 | El medidor sale 0 con 0 huecos | `rc=0`, 0 de 5 | CUMPLE |
| 2 | Sus contra-saltos bajan su pregunta | 4 verificados; uno no cazaba y corrigió el medidor | CUMPLE |
| 3 | Suite completa en verde | ver §2 | CUMPLE |
| 4 | Los contra-saltos del contrato cazan 5/5 con conjuntos distintos | `scripts/mutate_b8_package_contract.py` | CUMPLE |
| 5 | `tests.total` coincide con el árbol | 3161, desglose medido | CUMPLE |
| 6 | Cobertura del paquete nuevo ≥ 90 % | **100 %** | CUMPLE |

## 2. Certificación

```
3158 passed, 3 skipped, 0 failed
```

Los 3 `skipped` son los declarados en `SKIPS_PLATAFORMA`: el UAT real con
proveedor, opt-in porque cuesta dinero y necesita una credencial que este
entorno no tiene.

## 3. La medición que abrió el bloque

`scripts/measure_b8_package_contract.py`: **5 de 5 ABIERTAS**.

Y el hallazgo no es que falte un campo: lo que existe es un `Brick` con
`kind="DomainPack"`, que es el contrato de **tipos**, no el de **paquete**.

### Contra-saltos, y el que no cazaba

| Contra-salto | Efecto |
|---|---|
| Manifiesto vacío | P1 → CERRADA, P2..P5 ABIERTAS |
| `PACK_KINDS` con 1 de 6 | P4 → ABIERTA |
| Seis tipos, sin aislamiento | P4 CERRADA, P5 ABIERTA |
| Seis tipos + aislamiento | P4 y P5 CERRADAS |

El tercero **no cazaba**, y por eso se corrigió el medidor **antes** de
escribir una línea de producción. Dos bugs del instrumento:

1. `ast.literal_eval` no lee `frozenset(get_args(PackKind))` — que es la
   forma **correcta** de declarar un conjunto derivado. El medidor le decía
   al código correcto que su conjunto no existía, que es el peor resultado
   posible: **un guard que obliga a escribir peor para poder ser medido**.
2. El índice de alias solo miraba `AnnAssign`, y `PackKind = Literal[...]`
   es un `Assign` a secas. Sin él, `get_args(PackKind)` no resolvía.

## 4. Contra-saltos del contrato — 5/5, conjuntos distintos

| Sonda | Qué rompe | Quién la caza |
|---|---|---|
| M1 | las cláusulas se evalúan con `or` en vez de con `and` | 4 tests |
| M2 | tener la capability basta, la versión ya no se comprueba | 1 test |
| M3 | `PACK_KINDS` escrito a mano y corto | 3 tests |
| M4 | el aislamiento deja de ser una comparación | 2 tests |
| M5 | `metadatos` vuelve a ser el dict vivo del llamante | 1 test |

**5 conjuntos distintos de 5 sondas.** Ninguna sonda hereda el fallo de la
anterior, que es el defecto que hizo que el 8/8 de B6 fuera un número que
no se podía desarmar.

## 5. El fallo del harness que vale más que el bloque

**«Árbol restaurado byte a byte» NO es «el árbol está como estaba».**

Se vio porque M5 —que muta el fichero de test— cazaba los tests de M4, que
muta el de producción. El `finally` restauraba los bytes, `git status`
salía limpio y el `sha` coincidía. Y aun así los tests de M4 seguían
fallando.

La causa: al restaurar se reescribe el `.py` con los mismos bytes, el
`mtime` puede no avanzar lo suficiente, y Python sigue ejecutando el `.pyc`
de la versión **mutada**. El árbol estaba restaurado y ejecutando la versión
equivocada **a la vez**.

El harness ahora borra `__pycache__` antes y después de cada mutación, y
**vuelve a pasar la suite al final**. Esa última vuelta es la comprobación
que faltaba: no que los bytes sean los de antes, sino que el árbol
**ejecute** como estaba.

## 6. Defectos reales del código, cazados por los tests

### 6.1 El parser rechazaba el formato del propio gate

El enunciado escribe `">=0.30,<1"`, que **mezcla** `>=0.30` —dos
componentes— y `<1` —uno solo—. La regex exigía `X.Y` o SemVer completo:
rechazaba el primer caso o el segundo, y con cualquiera de los dos
**ningún pack encajaba contra el formato que el gate define**. Lo cazaron
seis tests a la vez.

### 6.2 La capability larga se rompía en silencio

`{type_name, version}` producía `type_name="a.b.v2@v2"` —con la versión
pegada— y la del puerto en el campo `version`. Una requirement así no se
puede comparar con un `CapabilitySpec` instalado, que los tiene separados,
y el síntoma es «falta la capability»: una respuesta **creíble**, que es lo
que hace un fallo peligroso.

## 7. Un `skip` mío y un test que no podía fallar

Dos cosas que el repo devolvio en mi propio trabajo y que no eran del código de
producción:

- **Un `pytest.skip` propio**, puesto «si el contrato pierde la progresión,
  saltar». Es **esconder un fallo**, que es lo que `AGENTS.md` §6.2 prohíbe
  y lo que `test_wi108_zero_skips.py` caza. Lo grave no era el skip: estaba
  porque la aserción de verdad —«un pack declarativo NO llega a
  sandbox»— no se había escrito, y en su lugar se puso un guard que salta
  justo cuando la propiedad se rompe. Ahora son dos aserciones y ninguna se
  salta.
- **Un test que no podía fallar**: mutaba `requires.skillgraph` en el dict
  de origen. Los strings son inmutables en Python, luego eso no puede
  cambiar un `frozen` dataclass: era verde por construcción. La sonda M5
 inicialmente apuntaba ahí y salió `NO CAZADA` — el harness diciendo la
  verdad en lugar de contar un 5/5 falso. Se quitó esa aserción y la sonda
  se movió a `metadatos`, donde el alias sí es posible.

**Un test que no puede fallar no mide nada: ocupa el sitio de una
comprobación que sí podría.**

## 8. `tests.total` 3161, con el desglose medido

| | |
|---|---|
| Sin el paquete `packaging/` en el árbol | la suite colecta **3088** |
| B7 declaró | 3088 |
| Con el paquete | la suite colecta **3161** |
| De los 73 | 66 propios, 6 de `wi47` (264 → 270), 1 de `wi107` (23 → 24) |

Que el árbol **sin** B8 colecte exactamente lo que B7 declaró es la
comprobación que le da sentido al número. Es la **tercera vez** que la
predicción de B6 se cumple —«si el bloque crea módulos nuevos en `src/`, los
guards se mueven»— y por eso conviene no leerla al revés.

## 9. Fuera de alcance

**P6** — que un pack se instale de verdad. Depende de un registro remoto y
de una política de fijación que el CI no tiene. Se mide el contrato.

**Declarado y no hecho, a propósito**: `subprocess` y `sandbox` son campos
**declarados**, no mecanismos. Declarar un nivel sin ejecutarlo es la forma
más fácil de mentir sobre seguridad, y por eso el contrato los declara
mientras el roadmap sigue diciendo que están por hacer.

## 10. Lo que sigue abierto

Sobre este manifiesto se pueden construir, en orden: la **matriz de
compatibilidad** (el manifiesto ya tiene `requires`), el **`upgrade`**
(comparar dos manifiestos del mismo `name`), el
**`install`/`update`/`remove`**, la **distribución** (`mise`/`asdf`/
`uv tool`/PyPI) y el **aislamiento ejecutable**.
