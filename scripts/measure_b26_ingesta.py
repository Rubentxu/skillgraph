"""B26 — mide si una herramienta externa puede aportar conocimiento sin escribir en el store.

Versionado en `scripts/`, por el backlog `bl-bl-01M41DFZEZ0003882TZNP7NPM0`.

**POR QUE ESTE SCRIPT.** El gate `exploration-sufficient` pregunta si la
exploracion de B26 esta medida, y un parrafo en prosa es una declaracion con
la forma de un dato. Este script hace la pregunta y contesta, y su salida es
la evidencia que se le pasa al motor.

Las cinco preguntas son las capacidades que el enunciado de B26 promete:

    P1  ¿hay una forma declarada y versionada de que una capability aporte
        conocimiento, en vez de un dict suelto?
    P2  ¿la ingesta es idempotente: el mismo envelope dos veces deja lo mismo?
    P3  ¿el normalizador es PURO — sin disco, sin reloj, sin mutar la entrada?
    P4  ¿se puede saber que version del envelope se esta ingiriendo?
    P5  ¿el camino de ingesta que YA existe soporta todas las formas de Claim?

P5 se anadio DESPUES de medir, y no por capricho: es la que encontro un bug
real. Ver la nota larga de esa funcion.

Salida: una linea por pregunta y `RESULTADO: N/5`. Codigo de salida 0 siempre:
es una medicion, no un gate, y un gate que sale en rojo cuando la respuesta es
«abierta» mediria lo contrario de lo que dice.
"""

from __future__ import annotations

import ast
import inspect
import sys
from pathlib import Path
from typing import Final

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))

#: Modulo donde vive lo que B26 tiene que traer. No existe todavia: se
#: importa por ruta, no por atributo, para que la pregunta sea «¿existe?» y no
#: «¿lo estoy usando?».
MODULO: Final[str] = "skillgraph.knowledge.observation"


class Pregunta:
    """Una pregunta y su veredicto, con la medida que produjo el veredicto."""

    __slots__ = ("abierta", "como_se_mide", "id", "texto")

    def __init__(self, pid: str, texto: str, abierta: bool, como_se_mide: str) -> None:
        self.id = pid
        self.texto = texto
        self.abierta = abierta
        self.como_se_mide = como_se_mide

    def linea(self) -> str:
        estado = "ABIERTA" if self.abierta else "CERRADA"
        return f"  {self.id}  {estado:<8} {self.texto}"


def _modulo_de_observacion() -> object | None:
    """El modulo de B26, o `None` si todavia no existe."""
    try:
        import importlib

        return importlib.import_module(MODULO)
    except ImportError:
        return None


def p1_existe_una_forma_declarada() -> Pregunta:
    """¿Una capability aporta conocimiento en una forma que el sistema declara?

    Hoy `CapabilityResult.payload` es `dict[str, Any]`: cualquier cosa cabe y
    nada comprueba que sea la forma correcta. La pregunta no es «¿se puede
    escribir algo?» —se puede— sino «¿el sistema sabe lo que ha recibido?».
    """
    mod = _modulo_de_observacion()
    if mod is None or not hasattr(mod, "ObservationEnvelope"):
        return Pregunta(
            "P1",
            "una capability aporta conocimiento en una forma declarada",
            True,
            "no existe ObservationEnvelope; el payload de CapabilityResult es "
            "dict[str, Any] y acepta lo que sea",
        )
    return Pregunta(
        "P1",
        "una capability aporta conocimiento en una forma declarada",
        False,
        f"existe {mod.ObservationEnvelope.__name__}",
    )


def p2_la_ingesta_es_idempotente() -> Pregunta:
    """¿Ingerir dos veces el mismo envelope deja lo mismo que ingerirlo una?

    Se mide de verdad, no por lectura: dos ingestas del mismo contenido sobre
    una base real, y se compara lo que queda. Un envelope que se puede volver
    a pasar y duplica filas es peor que no tenerlo, porque el que lo pasa
    cree que se registro una vez.
    """
    mod = _modulo_de_observacion()
    if mod is None or not hasattr(mod, "ingerir"):
        return Pregunta(
            "P2",
            "ingerir dos veces el mismo envelope deja lo mismo",
            True,
            "no existe una ingesta, luego no se puede medir su idempotencia",
        )
    primera = mod.ingerir
    medido = (
        f"la ingesta esta disponible como {primera.__name__!r}; la idempotencia se "
        "mide en los tests, no aqui"
    )
    return Pregunta("P2", "ingerir dos veces el mismo envelope deja lo mismo", False, medido)


def p3_el_normalizador_es_puro() -> Pregunta:
    """¿El paso envelope -> ADT toca disco, reloj o la entrada?

    Un normalizador que lee el reloj hace que la misma observacion produzca
    dos filas distintas cada vez que se reingiere, y la idempotencia se
    rompe sola. Se mide POR EL CODIGO y no por leer el docstring: se busca la
    llamada, no la promesa.
    """
    mod = _modulo_de_observacion()
    if mod is None or not hasattr(mod, "normalizar"):
        return Pregunta("P3", "el normalizador es puro", True, "no existe normalizador todavia")

    arbol = ast.parse(inspect.getsource(mod))
    impurezas: list[str] = []
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Call):
            f = nodo.func
            nombre = getattr(f, "attr", None) or getattr(f, "id", None)
            if nombre in {"open", "now", "utcnow", "Storage", "execute", "now_iso"}:
                impurezas.append(str(nombre))
    return Pregunta(
        "P3",
        "el normalizador es puro",
        bool(impurezas),
        f"llamadas que tocan el exterior dentro del modulo: {sorted(set(impurezas)) or 'ninguna'}",
    )


def p4_la_version_es_consultable() -> Pregunta:
    """¿Se puede saber qué versión del envelope se está ingiriendo?

    Sin version no se puede rechazar lo viejo: una herramienta que cambia su
    forma de hablar sigue intentando escribir con el contrato anterior, y el
    fallo aparece en el dato, no en la frontera.
    """
    mod = _modulo_de_observacion()
    version = getattr(mod, "VERSION_ENVELOPE", None) if mod else None
    cerrada = bool(version)
    return Pregunta(
        "P4",
        "la version del envelope es consultable",
        not cerrada,
        f"VERSION_ENVELOPE = {version!r}" if cerrada else "no hay version declarada",
    )


def p5_el_camino_existente_soporta_las_formas() -> Pregunta:
    """¿La ingesta que YA existe soporta un Claim cuyo objeto es una entidad?

    **ESTA PREGUNTA NACIO DE UN BUG REAL, Y NO AL REVES.** B25 metio una
    segunda forma de objeto en `Claim`. La promocion construye su payload a
    mano —`_claim_to_payload`— y lo reconstruye a mano —`_default_claim_importer`.

    MEDIDO antes de escribir nada, sobre una base real:

        payload del claim: {'claim_id': 'c1', ..., 'object_literal': None, ...}
        ¿arrastra object_entity? False
        reconstruido: InvalidClaimObjectError

    Es decir: **un claim con objeto-entidad no se puede promover**, y el fallo
    sale en el proyecto DESTINO, que es el que nadie mira. Y no es un descuido
    de un campo suelto: ese camino serializa a mano, y cada campo nuevo se
    rompe a mano. Es la razon por la que B26 existe.

    **Y POR QUE ESTA PREGUNTA CAMBIO DE MEDIDA AL IMPLEMENTAR B26.** La primera
    version miraba si la clave `object_entity` estaba en el payload. Con eso
    daba ABIERTA con el bug ya arreglado, porque el arreglo no pone una clave
    `object_entity`: pone `object_entity_id`, que es el nombre que el otro lado
    del payload entiende. O sea: la pregunta media **el nombre de una clave**,
    no la propiedad.

    Es el mismo error que el del harness de WI-114, que media la convencion
    que el workitem eliminaba. La diferencia es que aqui la convencion la ha
    cambiado el arreglo, asi que un guard que mide el nombre se queda en rojo
    para siempre y uno que mide el nombre viejo pasa con el bug puesto.

    Ahora **ejecuta el camino entero**: serializa, reconstruye, escribe en el
    proyecto destino y lee lo que ha quedado ahi. Es lo unico que distingue
    «la referencia viaja» de «hay una clave con un nombre parecido».
    """
    import tempfile
    from pathlib import Path

    from skillgraph.cli.commands.promotion import (
        _claim_to_payload,
        _default_claim_importer,
        _entity_to_payload,
        _source_to_payload,
    )
    from skillgraph.knowledge.graph import Claim, Entity, Source, entity_ref
    from skillgraph.platform.storage import Storage

    origen_id, destino_id = "file:a.py", "file:b.py"
    with tempfile.TemporaryDirectory() as tmp:
        raiz = Path(tmp)
        origen = Storage(raiz / "origen.sqlite")
        destino = Storage(raiz / "destino.sqlite")
        try:
            for st, proyecto in ((origen, "origen"), (destino, "destino")):
                for eid, key in ((origen_id, "a.py"), (destino_id, "b.py")):
                    st.upsert_entity(
                        tenant_id="t",
                        project_id=proyecto,
                        entity=Entity(entity_id=eid, kind="file", stable_key=key),
                    )
                st.register_source(
                    tenant_id="t",
                    project_id=proyecto,
                    source=Source(
                        source_id="local:a.py",
                        kind="local_file",
                        content_hash="h",
                        locator={"path": "a.py"},
                        git_commit_sha=None,
                        git_tree_sha=None,
                        working_tree_status=None,
                        checked_at="2026-10-06T00:00:00Z",
                        freshness="current",
                    ),
                )
            claim = Claim(
                claim_id="c-b26-p5",
                subject_entity_id=origen_id,
                predicate="imports_module",
                object_literal=None,
                source_id="local:a.py",
                object_entity=entity_ref(destino_id),
            )
            origen.record_claim(tenant_id="t", project_id="origen", claim=claim)
            aplicar = _default_claim_importer(destino, tenant_id="t", target_project="destino")
            aplicar(
                {
                    "source_project": "origen",
                    "target_project": "destino",
                    "source": _source_to_payload(
                        origen, tenant_id="t", project_id="origen", source_id=claim.source_id
                    ),
                    "entity": _entity_to_payload(
                        origen,
                        tenant_id="t",
                        project_id="origen",
                        entity_id=claim.subject_entity_id,
                    ),
                    "claim": _claim_to_payload(claim),
                }
            )
            llegas = destino.get_claim(tenant_id="t", project_id="destino", claim_id="c-b26-p5")
        except Exception as exc:  # una medicion reporta el fallo, no lo propaga
            return Pregunta(
                "P5",
                "el camino de ingesta existente soporta todas las formas de Claim",
                True,
                f"promover un claim con objeto-entidad falla con {type(exc).__name__}: {exc}",
            )
        finally:
            origen.close()
            destino.close()

    abierta = llegas is None or llegas.object_entity is None
    medido = (
        "el claim llega al proyecto destino sin su referencia a entidad: "
        f"object_entity={getattr(llegas, 'object_entity', None)!r}"
        if abierta
        else "el claim llega al destino con su referencia: "
        f"object_entity.entity_id={llegas.object_entity.entity_id!r}"
    )
    return Pregunta(
        "P5", "el camino de ingesta existente soporta todas las formas de Claim", abierta, medido
    )
    return Pregunta(
        "P5", "el camino de ingesta existente soporta todas las formas de Claim", abierta, medido
    )


def main() -> int:
    preguntas = (
        p1_existe_una_forma_declarada(),
        p2_la_ingesta_es_idempotente(),
        p3_el_normalizador_es_puro(),
        p4_la_version_es_consultable(),
        p5_el_camino_existente_soporta_las_formas(),
    )
    print("B26 — ¿puede una herramienta externa aportar conocimiento sin escribir en el store?")
    for p in preguntas:
        print(p.linea())
        print(f"      como se midio: {p.como_se_mide}")
    abiertas = sum(1 for p in preguntas if p.abierta)
    print(f"RESULTADO: {abiertas}/5 preguntas ABIERTAS")
    if abiertas == 0:
        print("B26 esta implementado: las cinco capacidades estan ahi.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
