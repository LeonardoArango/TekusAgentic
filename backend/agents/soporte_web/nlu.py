"""NLU — comprensión del último mensaje del cliente.

Un solo nodo que clasifica el acto de diálogo del ÚLTIMO turno y extrae lo que
el cliente aportó (datos, síntomas, pasos que ya intentó, sentimiento). Es la
pieza que hoy falta: sin esto el agente es sordo a "¿eres humano?" o
"¿no puedes venir de una vez?" y cae en bucles.

Recibe el resumen + los últimos turnos (no todo el historial) para escalar en
conversaciones largas.
"""

from __future__ import annotations

from agents import llm_client_openai as llm
from agents.soporte_web.estado import DialogueState

# Actos de diálogo posibles del último mensaje del cliente.
ACTOS = [
    "reportar_problema",  # describe un problema técnico
    "dar_detalle",  # aporta más info del problema (síntoma, modelo, qué intentó)
    "responder_pregunta",  # responde algo que el agente preguntó (sí/no/valor)
    "dar_datos_contacto",  # da nombre/correo/sede/teléfono
    "meta_pregunta",  # "¿eres humano?", "¿con quién hablo?"
    "objecion_frustracion",  # se queja, insiste, está molesto
    "smalltalk_saludo",  # saludo o charla trivial
    "pedir_humano",  # pide explícitamente un agente humano
    "fuera_de_tema",  # nada que ver con soporte
    "despedida",  # se despide / da por terminado
    "otro",
]

_TOOL = {
    "type": "function",
    "function": {
        "name": "entender_mensaje",
        "description": "Clasifica el último mensaje del cliente y extrae lo que aporta.",
        "parameters": {
            "type": "object",
            "properties": {
                "acto": {"type": "string", "enum": ACTOS},
                "sentimiento": {"type": "string", "enum": ["neutral", "frustrado", "enojado"]},
                "intencion": {"type": "string", "enum": ["soporte", "venta", "mixto"]},
                "problema": {
                    "type": "string",
                    "description": (
                        "Si aporta/actualiza el problema: descripción en tercera persona para "
                        "completar 'entiendo que ...' (ej. 'tu pantalla no muestra imagen'). "
                        "Vacío si este turno no habla del problema."
                    ),
                },
                "producto": {
                    "type": "string",
                    "enum": ["", "senalizacion_digital", "kiosco", "vestier", "medicion", "otro"],
                    "description": "Producto Tekus involucrado si se puede inferir; vacío si no.",
                },
                "reporto_antes": {
                    "type": "string",
                    "enum": ["", "si", "no"],
                    "description": "'si' si ya lo reportó antes; 'no' si no; '' si no se sabe.",
                },
                "numero_ticket": {
                    "type": "string",
                    "description": "Número de ticket que mencione el cliente; vacío si no.",
                },
                "sintomas_nuevos": {"type": "array", "items": {"type": "string"}},
                "pasos_intentados_nuevos": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Cosas que el cliente dice que YA intentó/revisó.",
                },
                "datos": {
                    "type": "object",
                    "description": "Datos de contacto que aparezcan en el mensaje (vacío si no).",
                    "properties": {
                        "nombre": {"type": "string"},
                        "correo": {"type": "string"},
                        "cuenta": {"type": "string"},
                        "telefono": {"type": "string"},
                        "sede": {"type": "string"},
                    },
                },
            },
            "required": ["acto", "sentimiento", "intencion"],
        },
    },
}


def _contexto_conversacion(estado: DialogueState) -> list[dict]:
    """Mensajes para el LLM: resumen (si hay) + últimos turnos crudos."""
    msgs: list[dict] = []
    if estado.resumen:
        msgs.append(
            {
                "role": "system",
                "content": f"Resumen de la conversación hasta ahora:\n{estado.resumen}",
            }
        )
    for t in estado.ultimos_turnos():
        msgs.append({"role": "assistant" if t.rol == "assistant" else "user", "content": t.texto})
    return msgs


def entender(estado: DialogueState) -> dict:
    """Clasifica el último turno (que ya debe estar en estado.turnos)."""
    system = (
        "Eres el módulo de comprensión del asistente de soporte de Tekus (pantallas, "
        "kioscos, players). Clasifica el ÚLTIMO mensaje del cliente y extrae SOLO lo que "
        "dijo explícitamente; no inventes. Distingue bien: una meta-pregunta ('¿eres "
        "humano?', '¿con quién hablo?'), una objeción/queja ('¿no puedes venir de una "
        "vez?'), de un reporte de problema o de datos de contacto."
    )
    return llm.clasificar(system, _contexto_conversacion(estado), _TOOL, model=llm.modelo_dialogo())


_TOOL_PROBLEMA = {
    "type": "function",
    "function": {
        "name": "decidir_problema",
        "description": "Con el contexto recuperado, decide si resolver, aclarar o escalar.",
        "parameters": {
            "type": "object",
            "properties": {
                "accion": {
                    "type": "string",
                    "enum": ["resolver", "aclarar", "escalar"],
                    "description": (
                        "'resolver' si el contexto alcanza para dar una solución útil que el "
                        "cliente aún no ha intentado. 'aclarar' si falta UN dato del problema "
                        "y hay una pregunta NUEVA que hacer. 'escalar' si no hay nada útil en "
                        "el contexto o si ya se intentó y no converge."
                    ),
                },
                "borrador_respuesta": {
                    "type": "string",
                    "description": "Si 'resolver': idea de la solución.",
                },
                "sugerencia_pregunta": {
                    "type": "string",
                    "description": "Si 'aclarar': la pregunta nueva.",
                },
                "fuentes_usadas": {"type": "array", "items": {"type": "integer"}},
            },
            "required": ["accion"],
        },
    },
}


def decidir_problema(estado: DialogueState, fragmentos: list[str]) -> dict:
    """Decide la acción para un turno del problema, con el contexto recuperado."""
    contexto = "\n\n".join(f"[{i}] {f}" for i, f in enumerate(fragmentos))
    ya = estado.preguntas_hechas + estado.pasos_intentados
    system = (
        "Decides el siguiente paso de soporte usando EXCLUSIVAMENTE el contexto. Prefiere "
        "AYUDAR: resolver si hay algo útil, aclarar si falta un dato y hay una pregunta "
        "nueva. Escala solo si el contexto no tiene nada útil o ya se intentó sin converger. "
        "No propongas pasos ni preguntas que ya se hicieron."
    )
    entrada = [
        {"role": "user", "content": f"Problema: {estado.problema}\nYa hecho/preguntado: {ya}"},
        {"role": "system", "content": f"Contexto recuperado:\n{contexto}"},
    ]
    return llm.clasificar(system, entrada, _TOOL_PROBLEMA, model=llm.modelo_dialogo())
