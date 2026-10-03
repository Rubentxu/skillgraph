"""B4 — la mitad OBSERVADA de un recurso, como tipo.

Este módulo es el otro lado de `Brick`. `Brick` es lo **declarado**: lo que
alguien escribe y pide que exista. `ResourceStatus` es lo **observado**: lo
que se ha comprobado de él.

**POR QUÉ NO ES UN CAMPO DE `Brick`.** Porque si lo fuera, un Domain Pack
podría declarar el estado de su propio recurso, y la mitad observada
dejaria de estar observada: pasaria a ser una declaracion mas escrita por la
misma parte que pide. El sistema no podria distinguir `observed` de
`human-asserted` — que es justo la distincion que B6 necesita para poder
responder «¿quien afirmo esto?»—, y no por falta de un campo sino porque la
FORMA del dato lo borra antes de llegar a la base.

La separacion es de **tipo**, no de convencion:
`tests/test_b4_observed_state.py::TestElTipoDeclaradoNoTieneStatus` la vigila
por AST.

**POR QUE `Unknown` Y NO UN `bool`.** Porque «falló» y «todavia no se ha
intentado» son dos preguntas y un operador las lee distinto. Con `bool`, un
recurso recien creado se lee como roto, y la tercera mitad de la respuesta se
convierte en la segunda.

**Y POR QUE UN `type` DE CONDICION NO PUEDE REPETIRSE.** `Ready=True` y
`Ready=False` a la vez no significan «dos estados»: significan que el que
escribe el status no sabe que esta observando. Se valida al **construir**,
no al persistir, porque el error es de quien lo construye y se le tiene que
decir a quien lo construye: persistir y fallar ahi haria que un status mal
formado se descubriera al leerlo, que es cuando ya no lo arregla quien lo
escribio.

**`observed_generation` NO SE DECLARA, SE LEE.** Quien escribe el status
copia de la fila la generacion que esta observando. Si el status declarara
su propia generacion, el campo mentiria en cuanto el spec cambiara por
debajo: seguiria diciendo lo que el status CREIA, no lo que observo. Es el
dato que permite responder «este status es de la generacion 3 y el spec ya
va por la 4».
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Final, Literal

from skillgraph.core.errors import ValidationError

__all__ = [
    "CONDITION_STATUSES",
    "Condition",
    "ConditionStatus",
    "ResourceStatus",
    "status_from_json",
    "status_to_json",
]

#: ADT cerrado (`AGENTS.md 2.1`). `Unknown` NO es `False`: es la tercera
#: mitad de la pregunta de un operador sobre un recurso, y colapsarla en un
#: booleano hace que un recurso recien creado parezca roto.
ConditionStatus = Literal["True", "False", "Unknown"]

#: El conjunto canonico, con tipo, para validar en runtime (`AGENTS.md 2.4`).
CONDITION_STATUSES: Final[frozenset[str]] = frozenset({"True", "False", "Unknown"})


@dataclass(frozen=True, slots=True)
class Condition:
    """Una observacion sobre un recurso, con su motivo y su instante.

    `type` es el NOMBRE de lo que se observa (`Ready`, `Synced`,
    `Degraded`…), no su valor: el valor es `status`, y separarlos es lo que
    permite tener varias condiciones del mismo recurso sin que una pise a
    la otra.
    """

    type: str
    status: ConditionStatus
    reason: str
    message: str
    last_transition: str

    def __post_init__(self) -> None:
        if not self.type or not self.type.strip():
            raise ValidationError("Condition.type no puede estar vacio")
        if self.status not in CONDITION_STATUSES:
            raise ValidationError(
                f"Condition.status {self.status!r} no es un valor de {sorted(CONDITION_STATUSES)}"
            )
        if not self.reason or not self.reason.strip():
            raise ValidationError(
                f"Condition.reason no puede estar vacio: una condicion sin "
                f"motivo no dice POR QUE esta en {self.status!r} y obliga a "
                f"mirar el log para averiguarlo"
            )

    def to_dict(self) -> dict[str, str]:
        return {
            "type": self.type,
            "status": self.status,
            "reason": self.reason,
            "message": self.message,
            "last_transition": self.last_transition,
        }


@dataclass(frozen=True, slots=True)
class ResourceStatus:
    """Lo observado de un recurso. El otro lado de `Brick`.

    `conditions` es una **tupla** y su orden es el de declaracion: el
    operador lee la primera condicion que le importa y un `set` no tiene
    orden (`AGENTS.md 1.1`).

    `observed_generation` es la generacion del **spec** que este status
    observa. No la declara quien lo construye: la copia el que escribe, de
    la fila, en el momento de escribir.
    """

    phase: str
    conditions: tuple[Condition, ...] = field(default_factory=tuple)
    observed_generation: int = 1

    def __post_init__(self) -> None:
        # COERCION A TUPLA, y no es cosmetica. El tipo de la anotacion dice
        # `tuple[...]`, pero Python no lo hace cumplir: sin esto, un `list`
        # que entra por la frontera se queda dentro del dominio y quien lo
        # recibe puede mutarlo. Es el mismo motivo por el que WI-113 metio
        # `deepcopy` en `AgentResult.result`: el valor que sale de la
        # frontera no puede ser modificado por quien lo recibio, y una
        # declaracion de tipos no es una garantia.
        #
        # `object.__setattr__` porque el dataclass es `frozen`: la
        # coerccion ocurre en la CONSTRUCCION, una vez, y despues el valor
        # es inmutable de verdad.
        if not isinstance(self.conditions, tuple):
            object.__setattr__(self, "conditions", tuple(self.conditions))
        if not self.phase or not self.phase.strip():
            raise ValidationError("ResourceStatus.phase no puede estar vacio")
        if self.observed_generation < 1:
            raise ValidationError(
                f"observed_generation={self.observed_generation} no es una "
                "generacion valida: `generation` arranca en 1"
            )
        vistos: dict[str, str] = {}
        for cond in self.conditions:
            if cond.type in vistos:
                raise ValidationError(
                    f"dos condiciones de tipo {cond.type!r} en el mismo "
                    f"status: {vistos[cond.type]!r} y {cond.status!r}. No es "
                    "«dos estados», es un status que no sabe que observa."
                )
            vistos[cond.type] = cond.status

    def condicion(self, type_name: str) -> Condition | None:
        """La condicion de ese tipo, o `None`. Una consulta, no un fallo."""
        for cond in self.conditions:
            if cond.type == type_name:
                return cond
        return None

    def to_dict(self) -> dict[str, object]:
        return {
            "phase": self.phase,
            "observed_generation": self.observed_generation,
            "conditions": [c.to_dict() for c in self.conditions],
        }


def status_to_json(status: ResourceStatus) -> str:
    """Serialización ESTABLE, por el motivo de `AGENTS.md 8`.

    `sort_keys=True` no es cosmetico: dos statuses con las mismas condiciones
    tienen que dar el MISMO texto. Sin el, el orden de las claves depende del
    `dict` de Python, comparar dos status se convierte en una casualidad, y
    deduplicar escrituras deja de ser posible.
    """
    return json.dumps(status.to_dict(), sort_keys=True)


def status_from_json(texto: str) -> ResourceStatus:
    """La capa de uso que convierte el texto crudo del DTO en tipo.

    `StoredResource.status_json` es texto a proposito (`dto.py:191`:
    *«preservando la frontera de persistencia»*). Esta funcion es donde se
    cruza esa frontera, y por eso **valida**: un `status_json` escrito por
    una version anterior del esquema no puede entrar al dominio como un dict
    cualquiera y fallar tres capas mas abajo.
    """
    try:
        bruto = json.loads(texto)
    except json.JSONDecodeError as exc:
        raise ValidationError(f"status_json no es JSON valido: {exc}") from exc
    if not isinstance(bruto, dict):
        raise ValidationError(f"status_json debe ser un objeto, es {type(bruto).__name__}")
    condiciones = tuple(
        Condition(
            type=str(c.get("type", "")),
            status=c.get("status", "Unknown"),  # type: ignore[arg-type]
            reason=str(c.get("reason", "Desconocido")),
            message=str(c.get("message", "")),
            last_transition=str(c.get("last_transition", "")),
        )
        for c in bruto.get("conditions", [])
    )
    return ResourceStatus(
        phase=str(bruto.get("phase", "")),
        conditions=condiciones,
        observed_generation=int(bruto.get("observed_generation", 1)),
    )
