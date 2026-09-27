# Controladores y plano de control

## 1. Principio

El controlador observa recursos, compara el estado
deseado con el observado y propone operaciones.

El núcleo valida y aplica esas operaciones.

Un controlador no necesita ser un agente LLM.

## 2. Controladores iniciales

### RegistryController

Registra tipos, paquetes, capacidades y versiones.

### GraphController

Valida relaciones, dependencias y GraphPatches.

### RunController

Mantiene las instancias y calcula la frontera
de trabajos disponibles.

### ContextController

Construye handoffs y resuelve conocimiento obligatorio.

### KnowledgeController

Mantiene procedencia, vigencia, invalidaciones
y solicitudes de actualización.

### AgentController

Invoca adaptadores de agentes y recibe resultados.

### AssimilationController

Gestiona importación, validación y activación
de capacidades de Domain Packs.

## 3. Contrato Python

```python
from dataclasses import dataclass
from typing import Protocol

@dataclass(frozen=True)
class ReconcileRequest:
    resource_ref: str
    resource_version: int
    event_id: str

@dataclass(frozen=True)
class ProposedOperation:
    kind: str
    target_ref: str
    expected_version: int
    payload: dict

class Controller(Protocol):
    def reconcile(
        self,
        request: ReconcileRequest,
        view: object,
    ) -> list[ProposedOperation]:
        ...
```

Este contrato es una propuesta de interfaz pública.

El controlador recibe una vista autorizada,
no una conexión SQLite con acceso irrestricto.

## 4. Propiedades obligatorias

- Idempotencia.
- Validación de operaciones.
- Control de concurrencia optimista.
- Ausencia de efectos ocultos durante la inspección.
- Observabilidad.
- Presupuestos.
- Resultados tipados.
- Capacidad de recuperación.

## 5. Controladores declarativos

Un Domain Pack puede declarar:

- Tipo observado.
- Eventos de activación.
- Condiciones.
- Acción permitida.
- Salidas esperadas.

Solo se admiten operadores declarativos registrados.
No se ejecutan expresiones Python arbitrarias
incluidas en YAML.

## 6. Extensiones Python

Una extensión especializada debe:

- Declarar versión del SDK.
- Declarar permisos.
- Declarar entradas y salidas.
- Ejecutarse mediante un adaptador autorizado.
- Devolver resultados estructurados.
- No acceder directamente a bases de otros proyectos.

La importación de un Domain Pack nunca ejecuta
automáticamente sus scripts Python.

## 7. Bucle de reconciliación

```text
EVENT
  -> localizar controladores interesados
  -> construir vista del recurso
  -> calcular diferencia relevante
  -> generar propuesta de operación
  -> validar
  -> aplicar transaccionalmente
  -> registrar evento
  -> activar controladores afectados
```

Los eventos duplicados no deben duplicar acciones.

La ausencia de diferencias relevantes produce NOOP.

## 8. Acciones externas

Una operación con efectos externos debe registrar:

- Identidad de la operación.
- Clave de idempotencia.
- Estado previo.
- Resultado observado.
- Evidencia de ejecución.
- Política de recuperación.

No se permite repetirla automáticamente si su
resultado anterior es incierto y no existe
una comprobación segura de su estado.
