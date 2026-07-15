"""NLG — generación de las respuestas del agente, en lenguaje natural.

Cada función redacta el mensaje de una acción del diálogo. Todas comparten la
PERSONA y una regla dura anti-repetición: reciben lo ya dicho/preguntado y
tienen prohibido repetirlo. Producen texto libre (no plantillas) para sonar
humano y acusar recibo de lo que el cliente acaba de decir.
"""

from __future__ import annotations

import os

from agents import llm_client_openai as llm
from agents.soporte_web.estado import DialogueState


def _nombre_agente() -> str:
    return os.environ.get("AGENTE_NOMBRE", "Eva")


def _persona() -> str:
    return (
        f"Eres {_nombre_agente()}, la asistente de soporte de Tekus (señalización digital, "
        "kioscos de autoservicio, vestier digital, medición de audiencia). Hablas español, "
        "tono cálido y cercano de tú, natural y humano, sin sonar a robot ni a formulario. "
        "Frases cortas. Sin emojis. Si te preguntan si eres una persona, respóndelo con "
        "honestidad: eres una asistente virtual, y ofrece pasar a un agente humano. Nunca "
        "inventes información ni menciones números de tickets internos de la empresa."
    )


def _contexto_dialogo(estado: DialogueState) -> str:
    partes = []
    if estado.resumen:
        partes.append(f"Resumen: {estado.resumen}")
    turnos = "\n".join(f"{t.rol}: {t.texto}" for t in estado.ultimos_turnos())
    partes.append(f"Últimos turnos:\n{turnos}")
    if estado.problema:
        partes.append(f"Problema en curso: {estado.problema}")
    return "\n\n".join(partes)


def _evitar(estado: DialogueState) -> str:
    ya = estado.preguntas_hechas[-5:] + estado.pasos_sugeridos[-5:]
    if not ya:
        return ""
    lista = "\n".join(f"- {x}" for x in ya)
    return (
        "\n\nYA dijiste/preguntaste esto antes — NO lo repitas, ni con otras palabras; "
        f"aporta algo nuevo o cambia de enfoque:\n{lista}"
    )


def _generar(estado: DialogueState, instruccion: str) -> str:
    system = _persona()
    user = (
        f"{_contexto_dialogo(estado)}\n\nInstrucción para tu próxima respuesta:\n"
        f"{instruccion}{_evitar(estado)}"
    )
    return llm.completar_texto(system, [{"role": "user", "content": user}])


# --- Nodos de generación (uno por acción de la política) --------------------


def identificar(estado: DialogueState, faltan: list[str], es_primer_turno: bool) -> str:
    saludo = ""
    if es_primer_turno:
        nombre = estado.slots.nombre.strip()
        quien = f" {nombre}" if nombre else ""
        problema = estado.problema.strip()
        sobre = f"solucionar {problema}" if problema else "ayudarte con tu requerimiento"
        saludo = (
            f"Preséntate SOLO en este primer mensaje así (adaptando naturalmente): "
            f"'Hola{quien}, soy {_nombre_agente()} de Tekus y voy a hacer todo lo posible por "
            f"{sobre}.' "
        )
    faltan_txt = ", ".join(faltan) if faltan else ""
    instr = (
        saludo
        + "Confirma en una frase lo que entendiste del cliente (empresa, sede, problema) si lo "
        "tienes. "
        + (
            f"Luego pide, de forma natural y en un mismo mensaje, lo que aún falta: {faltan_txt}. "
            "Pide máximo 2-3 datos a la vez, sin sonar a formulario."
            if faltan
            else "Ya tienes los datos necesarios; dile que con eso es suficiente para continuar."
        )
    )
    return _generar(estado, instr)


def preguntar_ticket_previo(estado: DialogueState) -> str:
    return _generar(
        estado,
        "Pregúntale con naturalidad si ya había reportado este caso antes (si ya tiene un "
        "ticket abierto). Si es así, pídele el número de ticket; si no, dile que no hay "
        "problema, que lo puedes registrar tú.",
    )


def reportar_ticket_existente(estado: DialogueState, resumen_ticket: str) -> str:
    return _generar(
        estado,
        "Cuéntale al cliente el estado de su ticket existente con estos datos (no inventes "
        f"nada fuera de esto): {resumen_ticket}. Sé claro y humano, y dile que vas a "
        "revisarlo.",
    )


def responder_meta(estado: DialogueState) -> str:
    return _generar(
        estado,
        "El cliente hizo una meta-pregunta (quién eres / si eres humano). Respóndela con "
        "honestidad y calidez en 1-2 frases, ofrécele pasar a un agente humano si lo "
        "prefiere, y retoma con naturalidad el problema pendiente (si hay uno).",
    )


def atender_objecion(estado: DialogueState) -> str:
    return _generar(
        estado,
        "El cliente está insistiendo o algo frustrado (p. ej. quiere que vayas ya, o algo no "
        "le sirve). Valida su molestia con empatía, sé honesto sobre lo que sí puedes hacer "
        "(no puedes enviar un técnico tú mismo, pero puedes dejar el caso listo para que un "
        "agente coordine la visita) y ofrécele el siguiente paso concreto.",
    )


def responder_social(estado: DialogueState) -> str:
    return _generar(
        estado,
        "El cliente saludó o hizo charla trivial. Responde breve y cálido, y guíalo hacia en "
        "qué lo puedes ayudar hoy.",
    )


def aclarar(estado: DialogueState, sugerencia_pregunta: str) -> str:
    return _generar(
        estado,
        "Necesitas UN dato más del problema para ayudar. Haz UNA sola pregunta concreta y "
        f"nueva (idea: '{sugerencia_pregunta}'). Antes de preguntar, reconoce brevemente lo "
        "que el cliente ya te contó.",
    )


def resolver(estado: DialogueState, borrador: str, fragmentos: list[str]) -> str:
    contexto = "\n\n".join(f"[{i}] {f}" for i, f in enumerate(fragmentos))
    return _generar(
        estado,
        "Da la solución al problema, paso a paso y clara, SALTANDO lo que el cliente ya dijo "
        "haber intentado. Básate únicamente en este contexto (documentación de Tekus); si "
        "citas algo, es de la documentación pública, nunca tickets internos. Borrador de "
        f"apoyo: {borrador}\n\nContexto:\n{contexto}",
    )


def recolectar_dato(estado: DialogueState, faltan: list[str]) -> str:
    listado = " y ".join(faltan)
    return _generar(
        estado,
        f"Para crear el caso y que un agente humano lo atienda, necesitas: {listado}. "
        "Pídelo de forma natural y variada (no como formulario), reconociendo primero lo que "
        "el cliente ya dijo. Pide como máximo dos datos a la vez.",
    )


def recolectar_dato_ultimo_intento(estado: DialogueState, faltan: list[str]) -> str:
    listado = " y ".join(faltan)
    return _generar(
        estado,
        f"Ya pediste {listado} y el cliente no lo ha dado. NO vuelvas a preguntar igual: "
        "explica en una frase por qué lo necesitas (para que el agente pueda contactarlo) y "
        "hazlo fácil; si aun así no quiere, dile que igual dejarás el caso registrado.",
    )


def escalar(estado: DialogueState, ticket_ref: str | None) -> str:
    if ticket_ref:
        instr = (
            f"Cierra el paso a humano: dile con calidez que dejaste su caso registrado con el "
            f"número {ticket_ref} y que un agente de Tekus lo contactará. Reconoce brevemente "
            "el problema."
        )
    else:
        instr = (
            "Dile con calidez que escalas su caso a un agente humano de Tekus que lo "
            "contactará. Reconoce brevemente el problema."
        )
    return _generar(estado, instr)


def cerrar(estado: DialogueState) -> str:
    return _generar(
        estado,
        "El cliente da por resuelto o se despide. Despídete con calidez, dile que puede "
        "volver a escribir cuando quiera.",
    )
