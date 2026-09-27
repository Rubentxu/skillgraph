# ActiveGraph, agit y adaptadores externos

## 1. Principio

SkillGraph conserva sus contratos.

Las dependencias externas son adaptadores
intercambiables y deben demostrar una necesidad.

## 2. ActiveGraph

Candidato para aportar:

- Registro persistente de eventos.
- Grafo de estado reactivo.
- Relaciones tipadas.
- Suscripciones a cambios.
- Vistas acotadas.
- Patches con control de concurrencia.
- Bifurcación y comparación de ejecuciones.

No delegar automáticamente:

- El lenguaje de bricks.
- Los contratos de handoff.
- La autoridad sobre workflows.
- El modelo multitenant.
- La semántica de conocimiento.
- La política de ampliaciones.

El proyecto se define como un runtime de
estado reactivo, no como un motor de workflows.

## 3. Criterio de integración

Un spike debe implementar el mismo escenario
con una capa propia mínima y con ActiveGraph.

Medir:

- Complejidad del adaptador.
- Persistencia y recuperación.
- Incorporación de nodos declarativos.
- Aislamiento por proyecto.
- Trazabilidad.
- Control de capacidades.
- Compatibilidad con nuestro modelo de recursos.

No mantener dos motores completos en producción.

## 4. Agit / agent-git

Interés potencial:

- Versionado de sesiones.
- Trazabilidad de conversaciones.
- Referencias entre sesiones y revisiones.
- Recuperación opcional de conversaciones.

No utilizar la conversación como fuente de verdad
de decisiones, resultados o conocimiento.

El ExecutionReceipt debe permitir continuar
sin recuperar la sesión original.

## 5. Adaptadores de agentes

Contrato genérico:

```python
class AgentAdapter:
    async def execute(self, handoff):
        raise NotImplementedError
```

El adaptador devuelve un resultado estructurado.

No recibe acceso directo al almacenamiento interno.

## 6. Primera implementación

Utilizar un FakeAgentAdapter determinista.

El adaptador real de Claude Code u otro proveedor
se añade después de certificar el ciclo de vida.

## 7. Referencias

Consultar references/FUENTES.md.

Las versiones concretas de las dependencias
deberán fijarse durante los spikes.
