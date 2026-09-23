# ADR-0013-anexo — Trazado de autoridad del recorrido de carga de packs

Fecha: 2026-09-23.
Pregunta: ¿es `pack_loader.py` una ruta alternativa al núcleo o una
capa legítima de preparación que puede entregar recursos al registro
existente?

## Recorrido ordinario de la aplicación (línea de autoridad)

```
CLI (cli/runner.py)
  → ProjectResolver.lookup()        resolución de proyecto y tenant
  → load_defaults()                 BrickRegistry con tipos S0
  → parse_file() + registry.validate()   validación estructural
  → Storage.upsert_resource()       persistencia en resources/
  → (run/expansion) _load_registry() lectura de resources persistidos
```

Puntos de autoridad identificados:

1. **`BrickRegistry` es en memoria** (`resources/registry.py:48`):
   se construye con `load_defaults()` (DecisionNode, ActionNode,
   DomainPack) en cada invocación CLI. No se persiste.
2. **La persistencia de instancias es la tabla `resources`**
   (`platform/storage.py:44`, `upsert_resource`, `list_resources`).
   La expansión H4 lee capacidades desde ahí (`_load_registry`,
   `runner.py:950`).
3. **`cmd_brick_register`** (`runner.py:726`) es el patrón de
   referencia: resolver → parse → validate contra registry →
   upsert_resource.

## Qué hace `pack_loader.py` hoy

- `declare_types_from_pack(registry, pack)`: registra `BrickType`s
  nuevos en un `BrickRegistry` en memoria, generando validadores
  declarativos (sin ejecutar código del pack).
- `validate_instance_against_registry(registry, brick)`: delega en
  `registry.validate()`.

Usa las **mismas primitivas del núcleo**: `BrickRegistry.declare()`,
`BrickType`, `SpecValidator`, `ValidationError`, `UnknownKindError`.
No duplica validación, no parsea por su cuenta, no toca Storage.

## Veredicto

**Es una capa legítima de preparación, NO una ruta alternativa.**
Opera sobre el registro ordinario y reutiliza sus contratos. El
problema no es de autoridad sino de **dos huecos de integración**:

### Hueco-1: los tipos declarados no sobreviven al proceso

`BrickRegistry` vive solo durante la invocación CLI. Un `sg pack load`
que hiciera `declare_types_from_pack(load_defaults(), pack)` dejaría
los tipos en el aire al terminar el proceso. El siguiente comando
no los conocería.

Resolución localizada (sin rediseño): **persistir el DomainPack como
resource** (`upsert_resource`, ya soporta `kind='DomainPack'`) y
reconstruir el registry al inicio de cada comando que lo necesite:

```
_build_registry_for_project(storage) ->
    reg = load_defaults()
    for pack in storage.list_resources(kind='DomainPack'):
        declare_types_from_pack(reg, parse(pack.spec_json))
    return reg
```

Esto además cumple ADR-0003: "cada proyecto habilita explícitamente
sus paquetes" (la habilitación = el pack registrado en el proyecto) y
"la instalación no implica ejecutar extensiones" (la declaración es
declarativa, sin código).

### Hueco-2: nada consume los tipos declarados

`cmd_brick_register` usa `load_defaults()` plano. Un brick `Character`
registrado contra un proyecto con pack cargado fallaría con
`UnknownKindError` aunque el pack esté persistido. La corrección es
cambiar `load_defaults()` por `_build_registry_for_project(storage)`
en los comandos que validan bricks del proyecto (`brick register` y,
cuando exista, `promotion submit`).

## Implicación para H8

- El cambio es **pequeño y localizado**: un helper de reconstrucción
  del registry + dos puntos de llamada. No hay segundo camino de
  ejecución que eliminar.
- El UAT de carga de packs debe recorrer: `sg pack load` → pack
  persistido en resources → `sg brick register` de una instancia del
  tipo del pack aceptada → (invalidación: tipo no declarado rechazado).
- La promoción (`promotion.py`) sí es una capa aparte: su caller
  natural es un comando nuevo `sg promotion *` que consuma
  `submit_proposal/apply_proposal/reconcile_pending` con el storage
  del proyecto. Sin conflicto de autoridad detectado: opera sobre
  `Storage` con transacciones propias.

## Verificación de este trazado

- `registry.py:48-68` (registry en memoria, declare/validate).
- `runner.py:726-760` (`cmd_brick_register`, patrón de autoridad).
- `runner.py:950-979` (`_load_registry` lee resources persistidos).
- `storage.py:44-63, 328-365` (tabla resources, upsert/list).
- `pack_loader.py:103-180` (`declare_types_from_pack` sobre registry).
- ADR-0003 (contrato de Domain Packs: explícito por proyecto, sin
  ejecución de extensiones).
