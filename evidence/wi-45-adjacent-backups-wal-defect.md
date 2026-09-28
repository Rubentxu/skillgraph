# WI-45 (adjunto): `sg backup` produce backups inservibles sobre WAL

> **No forma parte de WI-45.** Se descubrió al medir el único incumplimiento
> real del umbral de cobertura (`governance/backups.py` al 81.59%). Se registra
> aquí para que no se pierda, no para ejecutarlo dentro de este work item.
>
> **Severidad: alta. Tipo: pérdida de datos silenciosa.**

## Resumen

`create_backup` copia los `.sqlite` con `zf.write(src)`, que es una copia
cruda de archivo. El proyecto usa **WAL** (`PRAGMA journal_mode = WAL` en
`platform/storage.py:485` y `resources/catalog.py:48`), así que los datos
confirmados viven en el fichero `-wal`, no en el fichero principal. La copia
cruda del fichero principal se lleva **4096 bytes vacíos** y deja atrás los
datos.

El módulo **ya tiene la función correcta escrita y nunca conectada**:
`_sqlite_backup_to` (líneas 116-134) usa la API `.backup()` de SQLite. No tiene
ningún call site en `src/` ni en `tests/`.

## Test que falla hoy (por qué no es teórico)

```python
# origen: 200 filas confirmadas + 1 en transaccion concurrente = 201
got = sqlite3.connect(str(restored)).execute("SELECT count(*) FROM runs").fetchone()[0]
assert got == 201, f"PERDIDA DE DATOS: 201 -> {got}"
```

```
sqlite3.OperationalError: no such table: runs
```

No es una race condition ni un caso límite: es el estado normal de cualquier
data-root en producción, porque el proyecto abre sus conexiones en WAL y
nunca hace checkpoint antes de respaldar.

## Por qué fallan todos los gates

`create_backup` calcula el SHA-256 del fichero **tal y como está**, y
`verify_backup` lo recalcula sobre ese mismo fichero copiado. Comparan el
archivo vacío consigo mismo: coinciden. `restore_backup` extrae el mismo
archivo vacío y re-hashea: también coincide.

Las tres funciones devuelven éxito. El resultado es un backup que no contiene
los datos. **Ningún gate del sistema puede detectarlo**, porque todos operan
sobre la copia, no sobre la base de datos original.

## Reproducción (API pública, sin mocks)

```
en disco  : 4096 bytes | -wal: 16512 bytes <- datos reales aquí
manifest  : tenants/t1/projects/demo/project.sqlite | sha 0ab48b25cba617ed | bytes 4096
RESTAURADO: ERROR -> no such table: runs

create_backup OK / verify OK / restore OK
-> y el project.sqlite restaurado no tiene ninguna tabla.
```

Mismo fichero, mismo instante, dos métodos:

| Método | Filas recuperadas | Bytes |
|---|---|---|
| `zf.write()` (lo que hace `create_backup`) | **`no such table: t`** | 4096 |
| `.backup()` (`_sqlite_backup_to`, sin usar) | **201** | 8192 |

## Impacto

Un restore de emergencia sobre un data-root real devuelve bases de datos
vacías **sin ningún error**. Es la peor forma de fallo para un backup: el
operador descubre la pérdida cuando ya necesitaba los datos.

## Corrección

En `create_backup`, enrutar los `.sqlite` por `_sqlite_backup_to` a un
staging, y hashear/empacotar el fichero ya consolidado. Añadir un test que
compruebe que las filas confirmadas **con un writer concurrente abierto**
sobreviven al round-trip. El hueco de cobertura no es el bug: es la huella
digital del bug, porque la función rota nunca se ejecutó.

## Lo que NO es

- **No es un zip-slip.** `zf.extractall` no está protegido contra
  path traversal, pero se comprobó empíricamente que CPython 3.13
  (`ZipFile.extractall` sanea `..` y recorta rutas absolutas) lo neutraliza.
  Se deja constancia porque el patrón sigue siendo frágil si el runtime
  baja de versión; no es un finding explotable hoy.
- **No es una regresión.** `git log -S` sitúa `_sqlite_backup_to` en
  `c53f0a7`, el commit que creó el módulo. Nunca estuvo conectada.
