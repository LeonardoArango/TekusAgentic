"""Estado de diálogo del motor conversacional de soporte.

Es la "memoria de trabajo" de una conversación: qué sabemos del cliente y su
problema, qué ya preguntamos/sugerimos (anti-repetición), en qué fase vamos y
un resumen para conversaciones largas. Se persiste en Redis por
conversation_id (ver `memoria.py`). Diseñado independiente del canal —
WhatsApp y la consola web comparten esta estructura (ver ADR 0006).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum


class Fase(StrEnum):
    SALUDO = "saludo"
    DIAGNOSTICO = "diagnostico"
    RECOLECCION_DATOS = "recoleccion_datos"
    ESCALADO = "escalado"
    CERRADO = "cerrado"


@dataclass
class Slots:
    """Datos del cliente que se van reuniendo en la conversación."""

    nombre: str = ""
    correo: str = ""
    cuenta: str = ""
    telefono: str = ""
    # Ubicación/punto del equipo — clave para soporte técnico en sitio y para
    # que el agente humano coordine la visita (mapea a los campos de ubicación
    # del ticket de Odoo).
    sede: str = ""


@dataclass
class Turno:
    rol: str  # 'user' | 'assistant'
    texto: str


@dataclass
class DialogueState:
    conversation_id: str
    canal: str = "web"  # 'web' | 'whatsapp'
    fase: Fase = Fase.SALUDO

    slots: Slots = field(default_factory=Slots)

    # Problema
    problema: str = ""  # descripción canónica, en tercera persona
    sintomas: list[str] = field(default_factory=list)
    pasos_intentados: list[str] = field(default_factory=list)

    # Anti-repetición: qué ya dijimos/preguntamos
    preguntas_hechas: list[str] = field(default_factory=list)
    pasos_sugeridos: list[str] = field(default_factory=list)
    intentos_por_dato: dict[str, int] = field(default_factory=dict)

    # Memoria de conversación
    resumen: str = ""  # resumen acumulado de turnos viejos
    turnos: list[Turno] = field(default_factory=list)  # historial completo (se resume al crecer)

    intencion: str = "soporte"  # soporte | venta | mixto
    sentimiento: str = "neutral"  # neutral | frustrado | enojado
    ticket_ref: str | None = None

    # ---- helpers ----

    def agregar_turno(self, rol: str, texto: str) -> None:
        self.turnos.append(Turno(rol=rol, texto=texto))

    def ultimos_turnos(self, k: int = 8) -> list[Turno]:
        return self.turnos[-k:]

    def datos_contacto_completos(self) -> bool:
        return bool(self.slots.nombre.strip() and self.slots.correo.strip())

    def intentos(self, dato: str) -> int:
        return self.intentos_por_dato.get(dato, 0)

    def registrar_intento(self, dato: str) -> None:
        self.intentos_por_dato[dato] = self.intentos(dato) + 1

    # ---- serialización (para Redis) ----

    def to_dict(self) -> dict:
        d = asdict(self)
        d["fase"] = self.fase.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> DialogueState:
        slots = Slots(**data.get("slots", {}))
        turnos = [Turno(**t) for t in data.get("turnos", [])]
        return cls(
            conversation_id=data["conversation_id"],
            canal=data.get("canal", "web"),
            fase=Fase(data.get("fase", Fase.SALUDO.value)),
            slots=slots,
            problema=data.get("problema", ""),
            sintomas=list(data.get("sintomas", [])),
            pasos_intentados=list(data.get("pasos_intentados", [])),
            preguntas_hechas=list(data.get("preguntas_hechas", [])),
            pasos_sugeridos=list(data.get("pasos_sugeridos", [])),
            intentos_por_dato=dict(data.get("intentos_por_dato", {})),
            resumen=data.get("resumen", ""),
            turnos=turnos,
            intencion=data.get("intencion", "soporte"),
            sentimiento=data.get("sentimiento", "neutral"),
            ticket_ref=data.get("ticket_ref"),
        )
