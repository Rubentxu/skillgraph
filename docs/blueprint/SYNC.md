# Política de versionado del blueprint (QW-I)

Este directorio `docs/blueprint/` es un **snapshot versionado** del
blueprint en `external/blueprint-v1/` (origen no versionado).

## Estructura

```text
docs/blueprint/
├── README.md             # el README original del blueprint (intacto)
├── 01-producto.md ... 12-integraciones.md   # 12 capitulos de spec
├── SYNC.md               # este fichero (politica de versionado)
├── adr/                  # ADR-0001..0012 (architecture decision records)
├── plan/                 # HITOS, ROADMAP, SPIKES, UAT, etc.
└── references/           # referencias externas curadas
```

## Origen → snapshot

| Origen                                          | Snapshot                                 |
|-------------------------------------------------|------------------------------------------|
| `external/blueprint-v1/*.md`                    | `docs/blueprint/*.md`                    |
| `external/blueprint-v1/adr/*.md`                | `docs/blueprint/adr/*.md`                |
| `external/blueprint-v1/plan/*.md`               | `docs/blueprint/plan/*.md`               |
| `external/blueprint-v1/references/*.md`         | `docs/blueprint/references/*.md`         |

## Reglas

1. **No editar manualmente** ficheros bajo `docs/blueprint/` excepto
   este `SYNC.md` y `SOURCE_SHA`. Cualquier cambio manual es invisible
   para el origen y se pierde en la próxima re-sincronización.

2. **Tras cambios en `external/blueprint-v1/`**, ejecutar:

   ```bash
   bash scripts/sync_blueprint.sh
   ```

   El script:
   - Calcula SHA256 de los archivos del origen.
   - Si difiere del último registrado en `SOURCE_SHA`, copia.
   - Graba el nuevo SHA en `SOURCE_SHA`.

3. **Commitear la sincronización** con mensaje descriptivo:

   ```text
   docs(blueprint): sync con external/blueprint-v1 <sha>
   ```

4. **El test `test_uats_can_be_loaded_as_documentation`** lee
   `docs/blueprint/plan/UAT.md` y verifica la presencia literal de
   los UAT-01..03. Si añades nuevos UAT a verificar, amplía el test
   (no el snapshot).

## Por qué se versiona

- Antes: tests referenciaban `external/blueprint-v1/` que está
  gitignored → CI los saltaba con `pytest.skip`.
- Después: snapshot bajo `docs/blueprint/` permite a CI limpio
  ejecutar la verificación sin depender del origen.

## Cuándo re-sincronizar

- Antes de un release que cambie contratos.
- Después de aceptar un ADR.
- Después de añadir/modificar UATs en `plan/UAT.md`.

No es necesario sincronizar en cada commit: la política es
**on demand** (semVer-aware), no continua.
