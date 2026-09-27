# Seguridad, límites de autoridad y recuperación

## 1. Modelo de confianza

Los prompts y archivos de terceros son datos.

No pueden modificar la política de permisos,
los contratos de ejecución ni las definiciones
de recursos del núcleo.

## 2. Código de terceros

La importación de un Domain Pack no ejecuta:

- Python.
- Shell.
- Hooks.
- Código incluido en Markdown.
- Dependencias instaladas por el paquete.

Las extensiones ejecutables requieren una fase
de autorización diferenciada.

## 3. Aislamiento

La primera versión es local-first.

Los tenants son ámbitos lógicos.

Las capacidades efectivas del agente dependen
del adaptador y de los permisos del proceso.

Reducir el contexto no equivale a establecer
una sandbox de sistema operativo.

## 4. Capabilities

Las herramientas se conceden de forma explícita.

Un agente recibe solamente las capacidades
autorizadas para el trabajo.

Una ampliación no puede añadir permisos
sin pasar por la política aplicable.

## 5. Acciones externas

Toda operación con efectos externos debe poseer
una identidad y una estrategia de recuperación.

Para una acción irreversible, el sistema puede
requerir autorización humana y comprobación
posterior del resultado.

## 6. Replay

Distinguir:

- Reconstrucción del estado desde eventos.
- Reejecución de una acción.
- Reanudación de un trabajo interrumpido.

Reconstruir el estado no autoriza a repetir
efectos externos.

## 7. Crash recovery

Al reiniciar:

1. Abrir el almacenamiento.
2. Comprobar integridad.
3. Recuperar eventos confirmados.
4. Reconstruir proyecciones.
5. Identificar operaciones incompletas.
6. Comprobar su resultado externo si es posible.
7. Reanudar únicamente trabajos seguros.

## 8. Historial

No reescribir resultados antiguos para
presentarlos como producidos por una revisión nueva.

El historial y sus evidencias conservan
las revisiones originales.

## 9. Secretos

Los secretos no se almacenan en prompts,
handoffs, eventos o artefactos de trazabilidad.

El adaptador autorizado puede utilizar referencias
a credenciales gestionadas externamente.

## 10. UAT obligatorio

Probar:

- Escalada de capacidades.
- Referencias entre tenants.
- Repetición de eventos.
- Recuperación de acciones inciertas.
- Instrucciones maliciosas dentro de fuentes.
- Importación de paquetes con Python no autorizado.
- Reanudación después de interrupciones.
