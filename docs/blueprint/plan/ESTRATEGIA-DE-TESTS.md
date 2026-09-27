# Estrategia de pruebas

## 1. Jerarquía

- Tests unitarios de validación y relaciones.
- Tests de contrato de recursos.
- Tests de integración con SQLite.
- Tests de recuperación de ejecuciones.
- Tests de Domain Packs.
- UAT de la CLI instalada.
- Escenarios reales con agentes cuando corresponda.

## 2. Propiedades

### Transiciones

Un outcome no declarado no cambia el estado.

### Idempotencia

Una operación confirmada no se ejecuta de nuevo
por recibir un evento duplicado.

### Revisiones

Una instancia conserva la revisión del brick
con la que fue creada.

### Aislamiento

Una referencia no autorizada entre tenants
no produce datos.

### Contexto

Un handoff no incluye recursos fuera
de su ámbito autorizado.

### Expansión

Un GraphPatch inválido no modifica el grafo.

### Conocimiento

Una afirmación desactualizada no se presenta
como verificada para una revisión posterior.

## 3. Negative-space testing

Comprobar ausencia de:

- Ejecución duplicada.
- Fallback oculto.
- Filtración entre proyectos.
- Escalada de capacidades.
- Escrituras internas en repositorios fuente.
- Activación automática de scripts importados.
- Reescritura de resultados históricos.
- Ampliaciones silenciosas del alcance.

## 4. Baseline

Registrar los fallos preexistentes.

Un cambio no debe ampliar el conjunto
de fallos conocidos sin una justificación explícita.

## 5. Tests históricos

No reescribir pruebas de una revisión anterior
para fingir que siempre describieron
el comportamiento de la revisión nueva.

## 6. Fixtures

Los primeros escenarios deben poder ejecutarse
sin credenciales, red ni proveedor LLM.

Las pruebas con agentes reales se incorporarán
después de certificar el núcleo determinista.

## 7. CI inicial

Ejecutar:

- Formato y análisis estático.
- Tests unitarios.
- Tests de contratos.
- Tests de SQLite.
- Validación de ejemplos Markdown/YAML.
- UAT deterministas seleccionados.

## 8. Criterio de salida

Una feature no está terminada por tener
únicamente tests unitarios.

Debe existir una evidencia del recorrido
real que utilizará la persona desde la CLI.
