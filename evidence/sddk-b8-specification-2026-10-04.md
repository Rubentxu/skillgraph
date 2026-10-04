# B8 — Especificación: el contrato de paquete

**Ciclo**: `p-b7740b96d79ec013/b8`
**Fase**: specify
**Entrega**: `4d72177`

---

## 1. Enunciado

Los seis tipos de paquete existen sobre un contrato explícito, con
`requires` declarado y una forma de saber si un pack encaja en una
instalación.

```yaml
requires:
  skillgraph: ">=0.30,<1"
  capabilities:
    - code.analysis.v1
```

## 2. Requisitos, cada uno con su comprobación

### R1 — El manifiesto es un contrato de primera clase

No un `Brick` con `kind="DomainPack"`, que es el contrato de **tipos**.

| | |
|---|---|
| **Instrumento** | `scripts/measure_b8_package_contract.py`, P1 |
| **Estado** | CERRADO |

### R2 — `requires` es explícito y obligatorio

Un manifiesto sin `requires` no se puede leer, porque no se puede saber si
encaja. **Opcional sería lo mismo que inútil.**

| | |
|---|---|
| **Instrumento** | el mismo medidor, P2 |
| **Estado** | CERRADO |

### R3 — Se puede preguntar si un pack encaja, y la respuesta trae el porqué

| | |
|---|---|
| **Comprobación** | `es_compatible` devuelve motivos, `exigir_compatible` lanza `IncompatiblePackError` con `code` propio |
| **Instrumento** | el medidor, P3, y `TestLaPreguntaDeCompatibilidad` |
| **Estado** | CERRADO |

### R4 — Los seis tipos, no solo uno

| | |
|---|---|
| **Comprobación** | `PACK_KINDS` contiene los seis del enunciado **y está derivado del `Literal`** |
| **Instrumento** | el medidor, P4, y `test_pack_kinds_esta_derivado_y_no_escrito` |
| **Estado** | CERRADO |

### R5 — El aislamiento es un campo ordenado, no un adjetivo

`declarative → subprocess → sandbox` declara una progresión, y una
progresión se comprueba con una comparación.

| | |
|---|---|
| **Comprobación** | `es_al_menos(nivel)` es una propiedad, y `ISOLATION_LEVELS` está **en orden** |
| **Instrumento** | el medidor, P5, y `TestElAislamientoEsUnaComparacion` |
| **Estado** | CERRADO |

### R6 — El manifiesto no comparte memoria con quien lo lee

| | |
|---|---|
| **Comprobación** | `metadatos` es un `MappingProxyType` sobre una **copia**; escribir lanza `TypeError` |
| **Por qué importa** | sin esto, un registro puede ver cambiar un manifiesto ya guardado |
| **Estado** | CERRADO |

## 3. Requisitos que aparecieron al ejecutar

### R7 — El parser tiene que entender el formato del propio gate

**No estaba en el enunciado y hacía falta.** El enunciado escribe
`">=0.30,<1"`, que **mezcla** `>=0.30` —dos componentes— y `<1` —uno solo—.

Un parser que exija `X.Y` rechaza la segunda; uno que exija SemVer completo
rechaza la primera. Con cualquiera de los dos, **ningún pack encaja contra
el formato que el gate define**.

| | |
|---|---|
| **Comprobación** | `test_el_formato_del_gate_se_interpreta_como_lo_que_quiere_decir` |
| **Estado** | CERRADO — lo cazaron seis tests a la vez |

### R8 — La versión de la capability no puede quedar pegada al nombre

`CapabilitySpec` —el puerto— tiene `type_name` y `version` como campos
**distintos**. Una requirement con la versión pegada al nombre no se puede
comparar con lo instalado, y el síntoma es «falta la capability», que es
una respuesta **creíble** y por tanto peligrosa.

| | |
|---|---|
| **Comprobación** | `test_la_forma_corta_trae_la_version_del_puerto` y el round-trip |
| **Estado** | CERRADO |

## 4. Fuera de alcance

### P6 — que un pack se instale de verdad

Depende de un registro remoto y de una política de fijación. El CI no tiene
ninguno de los dos. Se mide el **contrato**, comprobable sin red.

## 5. Criterios de aceptación

1. El medidor sale 0 con 0 huecos en alcance.
2. Los contra-saltos del medidor bajan su pregunta — verificados en ambas
   direcciones.
3. La suite completa en verde.
4. Los contra-saltos del contrato cazan 5/5 con conjuntos distintos.
5. `tests.total` coincide con el recuento real.
6. La cobertura del paquete nuevo llega al suelo de §6.3.

## 6. Cumplimiento a 2026-10-04

| # | Criterio | Resultado |
|---|---|---|
| 1 | medidor sale 0, 0 huecos | `rc=0`, 0 de 5 |
| 2 | contra-saltos del medidor | 4 verificados; uno inicialmente no cazaba y corrigió el medidor |
| 3 | suite completa | **3158 passed, 3 skipped declarados, 0 failed** |
| 4 | contra-saltos del contrato | **5/5 con 5 conjuntos distintos** |
| 5 | `tests.total` | 3161, con el desglose medido (3088 sin el paquete) |
| 6 | cobertura del paquete | **100 %** (el suelo de §6.3 es 90 %) |
