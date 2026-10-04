# B8 — Exploración: el contrato de paquete, y por qué es la primera pieza

**Ciclo**: `p-b7740b96d79ec013/b8`
**Fecha**: 2026-10-04
**Base**: `7363f0f`
**Entrega**: `9ab6c1e` (verificada tras el commit)

---

## 1. Qué pide el gate, y por qué no es un bloque

`ROADMAP.md` §B8 enumera:

1. Los seis tipos de paquete
2. Aislamiento progresivo `declarative → subprocess → sandbox`
3. `mise` · `asdf` · `uv tool` · PyPI · paquete standalone
4. Upgrade / migración
5. `install` / `update` / `remove` de packs
6. Matriz de compatibilidad
7. El formato `requires` explícito

**Siete no es un bloque: son siete.** Medirlos juntos daría un veredicto
único que no dice por dónde empezar, y un bloque así no se puede entregar.

## 2. La pieza de la que los otros seis dependen

Es el **manifiesto**, y la dependencia no es una preferencia de orden:

- **Sin `requires` declarado no hay versión que comparar**, luego no hay
  matriz de compatibilidad ni forma de rechazar un pack.
- **Sin un contrato versionado no hay `upgrade`**: no hay contra qué
  comparar dos versiones del mismo pack.
- **Sin contrato no hay `install`/`update`/`remove`** que valga como algo
  más que copiar ficheros a un directorio.

## 3. La costura ya estaba puesta desde B3

Medido en `src/skillgraph/platform/ports/capabilities.py`:

```python
#: B8 pide un formato de compatibilidad explicito
#: (`requires.capabilities: [code.analysis.v1]`), y para que ese formato
#: tenga sentido tiene que haber una version que versionar.
CAPABILITY_VERSION: Final[str] = "v1"
```

Y en `knowledge_query.py`, con la misma justificación.

**Sin `CAPABILITY_VERSION` en el puerto, B8 no tiene contra qué comparar.**
Si la versión viviera en cada adaptador, cada uno inventaría la suya. Este
bloque no inventó el requisito: lo ejecutó.

## 4. Lo que hay hoy, y por qué no es el contrato

`src/skillgraph/domain/pack_loader.py` define un `Brick` con
`kind == "DomainPack"` y `spec.types` como lista de
`{kind, schema}`.

Eso es el contrato de **tipos** —qué campos tiene un tipo de recurso— y no
el de **paquete**. Un paquete tiene nombre, versión, clase y requisitos; un
`Brick` con `spec.types` no tiene ninguno de los tres.

La CLI tiene `pack load` y `pack import`, que cargan tipos. No hay
manifiesto.

## 5. Medición inicial

`scripts/measure_b8_package_contract.py`: **5 de 5 preguntas ABIERTAS.**

| | Pregunta | Antes |
|---|---|---|
| P1 | ¿Contrato de paquete de primera clase, o solo un `Brick`? | ABIERTA |
| P2 | ¿`requires` explícito? | ABIERTA |
| P3 | ¿Se puede preguntar si un pack encaja? | ABIERTA |
| P4 | ¿Los seis tipos en el contrato? | ABIERTA |
| P5 | ¿El aislamiento es un campo o una promesa? | ABIERTA |
| P6 | ¿Un pack se instala de verdad? | FUERA |

### Contra-saltos del medidor, antes de escribir producción

| Contra-salto | Resultado |
|---|---|
| Manifiesto vacío | P1 → CERRADA, P2..P5 siguen ABIERTAS |
| `PACK_KINDS` con 1 de 6 | P4 → ABIERTA |
| Seis tipos, sin aislamiento | P4 CERRADA, **P5 ABIERTA** |
| Seis tipos + aislamiento | P4 y P5 CERRADAS |

El tercero **no cazaba** y por eso se corrigió el medidor antes de escribir
una línea de producción. Dos bugs del instrumento:

1. `ast.literal_eval` no lee `frozenset(get_args(PackKind))` — y esa es la
   forma **correcta** de declarar el conjunto. El medidor le decía al código
   correcto que su conjunto no existía, que es el peor resultado posible:
   **un guard que obliga a escribir peor para poder ser medido**.
2. El índice de alias solo miraba `AnnAssign`, y `PackKind = Literal[...]`
   es un `Assign` a secas. Sin él, `get_args(PackKind)` no resolvía a nada.

## 6. Fuera de alcance

**P6** — que un pack se instale de verdad. Depende de un registro remoto y
de una política de fijación, y el CI no tiene ninguno de los dos. Se mide el
**contrato**, que es comprobable sin red.

## 7. Lo que queda para los siguientes bloques

Sobre este manifiesto se pueden construir, en orden:

- **La matriz de compatibilidad** — el manifiesto ya tiene `requires`.
- **El `upgrade`** — comparar dos manifiestos del mismo `name`.
- **`install`/`update`/`remove`** — operar sobre manifiestos validados.
- **El aislamiento ejecutable** — `subprocess` y `sandbox` son hoy campos
  **declarados**, no mecanismos. Declarar un nivel sin ejecutarlo es la
  forma más fácil de mentir sobre seguridad, y por eso el contrato los
  declara y el roadmap sigue diciendo que están por hacer.
