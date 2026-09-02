Markdown
# Arquitectura del Agente de IA Local (Gemma 4 12B)

Este documento contiene el flujo lógico para implementar un agente de IA desde cero utilizando Python puro y Ollama, aprovechando el soporte nativo de *Tool Calling*.

---

## Diagrama de Flujo (Ciclo ReAct)

```mermaid
graph TD
    A([Inicio: Entrada del usuario]) --> B[Inicializar historial de mensajes con el Prompt]
    
    %% Bucle Principal
    B --> C[Enviar historial + Schemas de herramientas a Gemma 4]
    C --> D{¿La respuesta contiene 'tool_calls'?}
    
    %% Rama de Salida
    D -- NO --> E[Extraer texto de la respuesta final]
    E --> F[Mostrar resultado al usuario]
    F --> G([Fin])
    
    %% Rama de Acción
    D -- SÍ --> H[Iterar por cada llamada a función solicitada]
    H --> I[Mapear nombre de función y extraer argumentos]
    I --> J[Ejecutar la función nativa en Python]
    J --> K[Formatear resultado como un mensaje de rol 'tool']
    K --> L[Apendizar mensaje de la herramienta al historial]
    
    %% Retorno al ciclo
    L --> C