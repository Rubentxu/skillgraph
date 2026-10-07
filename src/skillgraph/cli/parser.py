"""Construccion del parser de argumentos del CLI.

Modulo separado de `runner.py` (WI-43) por tamano: `_build_parser` ocupa
409 lineas y declaraba 83 `add_argument` y 41 `add_parser`. No contiene
logica de negocio, solo la forma de la linea de comandos: los handlers
siguen viviendo en `skillgraph.cli.runner`.

Autocontenido por construccion (verificado por AST al extraerlo): sus
unicos nombres libres son `argparse`, `Path`, `int` y `float`, y no
llama a ninguna funcion de este paquete. Por eso puede importarse sin
arrastrar los handlers ni el almacenamiento.

ADR-0016 (WI-88): la unica excepcion es `skillgraph.cli.exit_codes`, un
modulo hoja sin dependencias. Hace falta porque `argparse` abortaba los
errores de invocacion con su codigo **2**, que en esta CLI ya significa
`EXIT_BAD_NAME` (`runner.py:131` lo devuelve vivo). Tres fallos sin
relacion devolvian el mismo numero y un script no podia separarlos.
`_UsageParser` devuelve `EXIT_USAGE`; el unico coste es un import de una
tabla de doce enteros, que no arrastra ni handlers ni almacenamiento.

`runner._build_parser` se mantiene como reexport, de modo que cualquier
import previo del simbolo sigue funcionando sin cambios.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Final, NoReturn

from skillgraph.cli.exit_codes import EXIT_USAGE

__all__ = ["build_parser"]


class _UsageParser(argparse.ArgumentParser):
    """Parser cuyos errores de invocacion salen con `EXIT_USAGE`.

    `argparse` aborta con 2, que es su convencion universal pero que en
    esta CLI colisiona con `EXIT_BAD_NAME`. Sobrescribir `error()` lo
    resuelve sin envolver `main` en un `except SystemExit`, que no
    podria distinguir el 2 de `argparse` del 2 de un handler una vez
    ocurrido.

    `argparse` propaga `type(self)` a los subparsers y a los
    sub-subparsers, de modo que una sola clase cubre los tres niveles.
    `--help` no pasa por aqui: usa `exit(0)` y sigue saliendo con 0.
    """

    def error(self, message: str) -> NoReturn:
        self.print_usage(sys.stderr)
        self.exit(EXIT_USAGE, f"{self.prog}: error: {message}\n")


_PREGUNTAS_SUPERFICIE: Final[dict[str, str]] = {
    "what": "Lo que se afirma del sujeto, sin jerarquizar.",
    "why": "Por que se AFIRMO esa afirmacion (procedencia, no causa).",
    "impact": "A que afecta: quien menciona esta entidad como objeto.",
    "changed": "Que se sabia, en una revision o desde un commit.",
    "conflicts": "Que se contradice; con --at-revision, quien gana.",
    "evidence": "De donde sale cada afirmacion del sujeto.",
}
"""**B34.** El catalogo de las seis preguntas, y vive aqui y no repartido en
seis `add_parser`.

Un `help` escrito seis veces son seis textos que se desincronizan, y el
nombre de la pregunta vive en tres sitios —este mapa, el `Literal` de
`knowledge/superficie.py` y la tabla de despacho del runner—. Con el mapa,
un bucle genera los seis y el nombre sale de un sitio.

**Y POR QUE ES UN `dict` Y NO UNA LISTA.** El orden de las claves es el
orden en que `--help` los lista, y el orden de un `--help` es lo primero
que lee una persona. Un `set` de seis cadenas no tiene orden y lo deja al
azar de la tabla hash.

Se declara aqui y no en `superficie.py` porque es informacion de la
SUPERFICIE, no del dominio: el dominio no sabe que existe una CLI.
"""


def _add_format(parser: argparse.ArgumentParser, help_text: str) -> None:
    """Anade `--format {text,json}` a un comando de SOLO LECTURA (B7).

    Por que existe: medido antes de escribir nada
    (`scripts/measure_b7_operational_ux.py`), CERO de los siete modulos de
    comando declaraban una via de salida estructurada, y toda la salida
    eran cadenas formateadas dentro de cada `print`. Eso obliga a que
    cualquier consumidor que no sea una persona —una TUI, un agente, un
    script— PARSEE COLUMNAS, y el ancho de columna no es un contrato: en
    cuanto una columna crece, el parseo se rompe en silencio.

    Se declara SOLO en comandos de lectura a proposito. En un comando que
    muta, el JSON no es una representacion: es otro modo de hacer la
    operacion, y por eso necesita su propio contrato y sus propias
    pruebas, no una bandera.

    `default="text"` porque la CLI **sigue siendo primera clase** para
    una persona: añadir esta bandera no degrada nada, da una segunda via.
    """
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help=help_text,
    )


def build_parser() -> argparse.ArgumentParser:
    p = _UsageParser(
        prog="skillgraph",
        description="SkillGraph: workflows declarativos para agentes.",
    )
    p.add_argument(
        "--data-root",
        type=Path,
        default=None,
        help="Raíz de datos interna (default: ~/.local/share/skillgraph).",
    )
    p.add_argument(
        "--version",
        action="store_true",
        help="Muestra la versión y sale.",
    )
    sub = p.add_subparsers(dest="command", required=False)

    sub.add_parser("init", help="Inicializa el directorio de datos raíz.")

    # WI-15 (T5 Backups CLI).
    bkp = sub.add_parser(
        "backup",
        help="Crea, lista o restaura backups del data-root.",
    )
    bkp_sub = bkp.add_subparsers(dest="backup_command", required=True)
    bkp_sub.add_parser("create", help="Crea un backup .zip del data-root.")
    bkp_list = bkp_sub.add_parser("list", help="Lista backups existentes.")
    bkp_list.add_argument(
        "--dir",
        type=Path,
        default=None,
        help="Directorio de backups (default: <data-root>/backups).",
    )
    bkp_restore = bkp_sub.add_parser(
        "restore", help="Restaura un backup .zip a un data-root destino."
    )
    bkp_restore.add_argument(
        "backup",
        type=Path,
        help="Ruta al .zip de backup a restaurar.",
    )
    bkp_restore.add_argument(
        "target",
        type=Path,
        help="Directorio destino (data-root) donde restaurar.",
    )
    bkp_restore.add_argument(
        "--overwrite",
        action="store_true",
        help="Permite restaurar sobre un target no vacio.",
    )

    proj = sub.add_parser("project", help="Gestión de proyectos.")
    proj_sub = proj.add_subparsers(dest="project_command", required=True)
    pc = proj_sub.add_parser("create", help="Crea un proyecto.")
    pc.add_argument("name", help="Slug del proyecto (a-z0-9-_, máx 64).")
    proj_sub.add_parser("list", help="Lista proyectos del tenant actual.")
    pi = proj_sub.add_parser("inspect", help="Inspecciona un proyecto.")
    pi.add_argument("name", help="Nombre del proyecto a inspeccionar.")

    bp = sub.add_parser(
        "brick",
        help="(experimental) valida y registra un brick Markdown en un proyecto.",
    )
    bp.add_argument("project", help="Proyecto destino.")
    bp.add_argument("path", type=Path, help="Ruta al archivo .md del brick.")
    bp.add_argument(
        "--kind",
        default=None,
        help="(reservado) override de kind para tests avanzados.",
    )

    # H5 skill_import: pack import (asimila una skill, conserva fuente,
    # genera informe; NO ejecuta scripts).
    pp = sub.add_parser(
        "pack",
        help="Asimilacion de skills externas (H5).",
    )
    pp_sub = pp.add_subparsers(dest="pack_command", required=True)
    pi = pp_sub.add_parser(
        "import",
        help="Importa una skill: conserva fuente y genera informe de estructuracion.",
    )
    pi.add_argument("project", help="Proyecto destino (donde se registra el Source).")
    pi.add_argument("path", type=Path, help="Ruta al directorio o archivo de la skill.")
    pi.add_argument(
        "--report",
        type=Path,
        default=None,
        help="Ruta donde escribir el informe JSON. Default: stdout.",
    )
    pl = pp_sub.add_parser(
        "load",
        help="Carga un Domain Pack en un proyecto: declara sus tipos (H8).",
    )
    pl.add_argument("project", help="Proyecto destino (donde se persiste el pack).")
    pl.add_argument("path", type=Path, help="Ruta al archivo Markdown del Domain Pack.")

    # B11: el ciclo de vida. Es lo que el gate de 1.0 pide literally:
    # «pack/controller lifecycle» y su predicado mira install/update/remove.
    # El manifiesto que valido B8 viaja en `spec.manifest` del propio pack,
    # luego un pack instalable es un Markdown como los demas y no un
    # directorio con dos ficheros.
    pinst = pp_sub.add_parser(
        "install",
        help="Instala un pack: valida su manifiesto y lo deja vivo en el proyecto.",
    )
    pinst.add_argument("project", help="Proyecto destino.")
    pinst.add_argument("path", type=Path, help="Ruta al Markdown del pack, con `spec.manifest`.")
    pupd = pp_sub.add_parser(
        "update",
        help="Actualiza un pack instalado. Exige que la version nueva SUBA.",
    )
    pupd.add_argument("project", help="Proyecto destino.")
    pupd.add_argument("path", type=Path, help="Ruta al Markdown del pack nuevo.")
    prem = pp_sub.add_parser(
        "remove",
        help="Retira un pack instalado. Lo que no esta instalado se dice.",
    )
    prem.add_argument("project", help="Proyecto destino.")
    prem.add_argument("name", help="Nombre del pack a retirar.")
    plst = pp_sub.add_parser(
        "list",
        help="Lista los packs instalados: version y aislamiento.",
    )
    plst.add_argument("project", help="Proyecto a listar.")

    # H8: promotion entre bases (UAT-13 ruta publica)
    pr = sub.add_parser(
        "promotion",
        help="Promocion de conocimiento entre bases/proyectos (H8).",
    )
    pr_sub = pr.add_subparsers(dest="promotion_command", required=True)
    ps = pr_sub.add_parser(
        "submit",
        help="Registra una propuesta de promocion (PENDING) desde un Claim.",
    )
    ps.add_argument("project", help="Proyecto origen (donde vive el Claim).")
    ps.add_argument("claim_id", help="Identificador del Claim a promover.")
    ps.add_argument("target", help="Proyecto/catalogo destino.")
    ps.add_argument(
        "--proposal-id",
        default=None,
        help="Identificador de propuesta. Default: promo-<claim_id>.",
    )
    pll = pr_sub.add_parser(
        "list",
        help="Lista propuestas del outbox.",
    )
    pll.add_argument("project", help="Proyecto (su project.sqlite contiene el outbox).")
    pll.add_argument(
        "--pending",
        action="store_true",
        help="Solo PENDING/IN_PROGRESS.",
    )
    prc = pr_sub.add_parser(
        "reconcile",
        help="Aplica las propuestas pendientes sin duplicar (UAT-13).",
    )
    prc.add_argument("project", help="Proyecto dueño del outbox.")
    prc.add_argument(
        "--target",
        default=None,
        help="Proyecto destino donde aplicar los claims. Default: el mismo proyecto.",
    )

    rp = sub.add_parser(
        "run",
        help="Crea un Run desde un WorkflowPlan.md y reconcilia hasta terminal.",
    )
    rp.add_argument("project", help="Proyecto destino (debe existir).")
    rp.add_argument("plan", type=Path, help="Ruta al WorkflowPlan.md.")
    rp.add_argument(
        "--fixtures-root",
        type=Path,
        default=None,
        help="Raíz de fixtures de agentes (default: <data-root>/agents).",
    )
    rp.add_argument(
        "--adapter",
        choices=["fake", "http"],
        default="fake",
        help="Tipo de adapter: 'fake' (fixtures locales, default) o 'http' (LLM real via Anthropic/OpenAI).",
    )
    rp.add_argument(
        "--llm-provider",
        choices=["anthropic", "openai"],
        default="anthropic",
        help="Proveedor LLM cuando --adapter=http (default: anthropic).",
    )
    rp.add_argument(
        "--llm-model",
        default=None,
        help="Modelo LLM especifico (default: modelo recomendado del proveedor).",
    )
    rp.add_argument(
        "--llm-timeout-s",
        type=float,
        default=30.0,
        help="Timeout HTTP en segundos para el adapter (default: 30.0).",
    )
    rp.add_argument(
        "--max-iterations",
        type=int,
        default=50,
        help="Maximo de pasadas de reconcile_run (default: 50).",
    )
    rp.add_argument(
        "--budget-visits",
        type=int,
        default=None,
        help="Limite de ejecuciones por nodo (S4 Etapa 7).",
    )
    rp.add_argument(
        "--budget-runtime-seconds",
        type=int,
        default=None,
        help="Limite (reservado) de duracion total en segundos (S4 Etapa 7).",
    )
    rp.add_argument(
        "--budget-events",
        type=int,
        default=None,
        help="Limite de eventos emitidos por el Run (S4 Etapa 7).",
    )

    # ----- expansion subcommand (H4 Slice 1) ---------------------------
    # DISCOVER -> PROPOSE -> VALIDATE -> AUTHORIZE -> APPLY.
    # Ver specs/h4-slice-1.md y blueprint §5 §5-§6.
    ex = sub.add_parser(
        "expansion",
        help="Expansion controlada del WorkflowPlan (H4).",
    )
    ex_sub = ex.add_subparsers(dest="expansion_command", required=True)

    ep = ex_sub.add_parser(
        "propose",
        help="Crea una propuesta desde un archivo JSON.",
    )
    ep.add_argument("project", help="Proyecto destino (debe existir).")
    ep.add_argument(
        "proposal_json",
        type=Path,
        help="Archivo JSON con la propuesta.",
    )

    ea = ex_sub.add_parser(
        "apply",
        help="Aplica una propuesta (validacion + APPLY).",
    )
    ea.add_argument("project", help="Proyecto destino.")
    ea.add_argument("--proposal", type=Path, required=True)
    ea.add_argument(
        "--plan-file",
        type=Path,
        default=None,
        help="WorkflowPlan a expandir (default: <data>/plans/<project>.json).",
    )

    er = ex_sub.add_parser(
        "rejections",
        help="Lista propuestas rechazadas (UAT-09 evidencia).",
    )
    er.add_argument("project", help="Proyecto destino.")

    eval_p = ex_sub.add_parser(
        "validate",
        help="Solo valida, no aplica. Imprime el resultado.",
    )
    eval_p.add_argument("project", help="Proyecto destino.")
    eval_p.add_argument("--proposal", type=Path, required=True)
    eval_p.add_argument("--plan-file", type=Path, default=None)

    # ----- slice-3 subcommands -----
    el = ex_sub.add_parser(
        "list",
        help="Lista propuestas registradas (slice-3).",
    )
    el.add_argument("project", help="Proyecto destino.")
    el.add_argument(
        "--stage",
        choices=("PROPOSED", "EVALUATED", "AUTHORIZED", "APPLIED", "REJECTED", "ARCHIVED"),
        default=None,
        help="Filtra por stage (default: todas).",
    )

    es = ex_sub.add_parser(
        "show",
        help="Muestra una propuesta por proposal_id (slice-3).",
    )
    es.add_argument("project", help="Proyecto destino.")
    es.add_argument("proposal_id", help="ID de la propuesta a mostrar.")

    ea2 = ex_sub.add_parser(
        "archive",
        help="Archiva una propuesta (stage ARCHIVED, slice-3).",
    )
    ea2.add_argument("project", help="Proyecto destino.")
    ea2.add_argument("proposal_id", help="ID de la propuesta a archivar.")

    # ----- knowledge subcommand (H3 Slice 5) -----
    kn = sub.add_parser(
        "knowledge",
        help="Gestion del subsistema de conocimiento (H3).",
    )
    kn_sub = kn.add_subparsers(dest="knowledge_command", required=True)

    # ----- policy subcommand (Etapa 7 / S5) -----
    pol = sub.add_parser(
        "policy",
        help="Politicas de redaccion por tenant (S5).",
    )
    pol_sub = pol.add_subparsers(dest="policy_command", required=True)

    pol_get = pol_sub.add_parser(
        "get",
        help="Muestra la politica de redaccion del tenant.",
    )
    pol_get.add_argument("project", help="Proyecto (su tenant es el target).")

    pol_set = pol_sub.add_parser(
        "set",
        help="Configura la politica de redaccion del tenant.",
    )
    pol_set.add_argument("project", help="Proyecto (su tenant es el target).")
    pol_set.add_argument(
        "--redact-policy",
        choices=("none", "metadata", "payload", "full"),
        required=True,
        help="Politica de redaccion a aplicar al tenant.",
    )

    # ----- runs subcommand (Etapa 7 / S1) -----
    # Gestion del ciclo de vida de Runs existentes (cancel, etc.).
    # No crea Runs: eso es `sg run <project> <plan>`.
    rn = sub.add_parser(
        "runs",
        help="Operaciones sobre Runs existentes.",
    )
    rn_sub = rn.add_subparsers(dest="runs_command", required=True)

    # sg runs list <project> [--state S] [--limit N]
    rl = rn_sub.add_parser(
        "list",
        help="Lista Runs existentes (mas reciente primero).",
    )
    rl.add_argument("project", help="Proyecto destino.")
    rl.add_argument(
        "--state",
        default=None,
        help="Filtra por estado (CREATED, ACTIVE, COMPLETED, FAILED, CANCELLED).",
    )
    rl.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Numero maximo de Runs a listar (default 20).",
    )
    _add_format(rl, "Salida: texto para una persona, o JSON estructurado.")

    # sg runs show <project> <run-id>
    rs = rn_sub.add_parser(
        "show",
        help="Muestra el snapshot de un Run.",
    )
    rs.add_argument("project", help="Proyecto destino.")
    rs.add_argument("run_id", help="Run ID a inspeccionar.")
    _add_format(rs, "Salida: texto para una persona, o JSON estructurado.")

    # sg runs logs <project> <run-id> [--limit N]
    rl2 = rn_sub.add_parser(
        "logs",
        help="Muestra el timeline de eventos de un Run.",
    )
    rl2.add_argument("project", help="Proyecto destino.")
    rl2.add_argument("run_id", help="Run ID a inspeccionar.")
    rl2.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Numero maximo de eventos a mostrar (default: todos).",
    )

    rc = rn_sub.add_parser(
        "cancel",
        help="Cancela un Run en curso (ACTIVE/WAITING/CREATED).",
    )
    rc.add_argument("project", help="Proyecto destino.")
    rc.add_argument("run_id", help="Run ID a cancelar.")

    # sg runs budget <project> <run-id>
    rbu = rn_sub.add_parser(
        "budget",
        help="Muestra el RunBudget activo de un Run (S4 Etapa 7).",
    )
    rbu.add_argument("project", help="Proyecto destino.")
    rbu.add_argument("run_id", help="Run ID a inspeccionar.")

    ks = kn_sub.add_parser("stale", help="Lista Claims stale.")
    ks.add_argument("project", help="Proyecto destino.")

    ki = kn_sub.add_parser("invalidate", help="Invalida Claims desde un source.")
    ki.add_argument("project", help="Proyecto destino.")
    ki.add_argument("--source", required=True, help="source_id a invalidar.")
    ki.add_argument("--max-hops", type=int, default=2, help="Cap de hops (default 2).")

    kr = kn_sub.add_parser("refresh", help="Refresca Claims de un source.")
    kr.add_argument("project", help="Proyecto destino.")
    kr.add_argument("--source", required=True, help="source_id a refrescar.")
    kr.add_argument(
        "--revision",
        required=True,
        help="Nueva revision que re-valida los Claims stale.",
    )

    kc = kn_sub.add_parser("compile", help="Compila un handoff.")
    kc.add_argument("project", help="Proyecto destino.")
    kc.add_argument(
        "recipe",
        help='source_id o JSON literal "{"..."} con la receta completa.',
    )
    kc.add_argument("--strict", action="store_true", help="Aplica strict freshness.")
    kc.add_argument("--token-budget", type=int, default=8000, help="Chars maximos.")
    kc.add_argument(
        "--overflow",
        default="drop_optional",
        choices=["drop_optional", "fail", "truncate_finding"],
        help="Que hacer si overflow (default drop_optional).",
    )
    kc.add_argument("--run", default=None, help="run_id del handoff.")
    kc.add_argument("--node", default=None, help="node_execution_id.")
    kc.add_argument("--revision", default=None, help="source_revision del handoff.")

    kt = kn_sub.add_parser("trace", help="Extrae un OutcomeTrace desde run.")
    kt.add_argument("project", help="Proyecto destino.")
    kt.add_argument("--run", required=True, help="run_id del que extraer trace.")
    kt.add_argument("--name", default=None, help="Nombre del trace (opcional).")

    krz = kn_sub.add_parser(
        "resolve",
        help="Resuelve los conflictos de un sujeto PARA UNA INTENCION (B28).",
    )
    krz.add_argument("project", help="Proyecto destino.")
    krz.add_argument("subject", help="subject_entity_id cuyas afirmaciones se oponen.")
    krz.add_argument(
        "--intent",
        required=True,
        help=(
            "Para que se pregunta. El valor DECIDE que afirmacion gana, "
            "y por eso no es una nota: es lo unico que separa dos respuestas "
            "distintas sobre el mismo conflicto."
        ),
    )
    krz.add_argument(
        "--json",
        action="store_true",
        help="Salida en JSON en vez de la lectura humana.",
    )
    krz.add_argument(
        "--at-revision",
        default=None,
        help=(
            "Pregunta POR UNA REVISION en vez de por HEAD (B29). Sin este "
            "flag solo se ve lo que no ha caducado, que es una pregunta "
            "distinta de la que hace un mes."
        ),
    )

    # ----- B35: la puerta de la ingesta de codigo -----
    # Un unico comando y no uno por capability, porque aqui no se elige la
    # capability: la elige lo que se pide. Anadir `ingest-runtime` cuando haya
    # un `LectorTelemetria` de verdad es anadir un subparser, no un modulo.
    kic = kn_sub.add_parser(
        "ingest-code",
        help="Analiza un fichero y convierte el analisis en afirmaciones.",
    )
    kic.add_argument("project", help="Proyecto destino.")
    kic.add_argument("file", help="Ruta del fichero a analizar.")
    kic.add_argument(
        "--revision",
        default=None,
        help=(
            "Revision contra la que se registra. Por defecto es el sha256 del "
            "contenido: lo que cambia en un fichero local es su contenido, y "
            "asi lo anterior queda en su propia revision en vez de "
            "contradecir al nuevo."
        ),
    )

    # ----- B34: las seis preguntas de la superficie -----
    # Todas comparten los mismos TRES flags opcionales y ninguno es
    # obligatorio salvo donde la pregunta lo necesita: `--claim-id` solo lo
    # usa `why`, y `Consulta.__post_init__` dice el QUE si falta. Declarar
    # aqui los tres para las seis, en vez de uno por pregunta, es lo que
    # hace que anadir una septima pregunta sea un `Literal` y no seis
    # bloques de argparse.
    for _nombre, _ayuda in _PREGUNTAS_SUPERFICIE.items():
        _k = kn_sub.add_parser(_nombre, help=_ayuda)
        _k.add_argument("project", help="Proyecto destino.")
        _k.add_argument("subject", help="Sujeto (entity_id) sobre el que se pregunta.")
        _k.add_argument(
            "--claim-id",
            default=None,
            help="La afirmacion concreta. Solo `why` la exige.",
        )
        _k.add_argument(
            "--at-revision",
            default=None,
            help=(
                "Pregunta POR UNA REVISION (B29, orden de observacion local). "
                "En `conflicts` es la INTENCION por la que se resuelve (B28)."
            ),
        )
        _k.add_argument(
            "--commit",
            default=None,
            help="Pregunta por la ascendencia de un commit (B32). Solo `changed`.",
        )
        _k.add_argument(
            "--json",
            action="store_true",
            help="Salida en JSON en vez de la lectura humana.",
        )

    return p
