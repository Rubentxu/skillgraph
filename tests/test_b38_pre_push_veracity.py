"""B38 — el pre-push afirmaba una ejecución que no había comprobado.

**MEDIDO AL ABRIR EL BLOQUE, con `scripts/measure_b38_pre_push.py`** (nueve
rondas, sobre el hook real). El bypass era lo evidente, pero no era el defecto:

    R1  con `HOOK_SKIP_PUSH_TESTS=1` la ULTIMA LINEA es
        `[pre-push] OK: la receta canonica dio SUCCESS sobre <sha>`,
        con la receta sin ejecutar
    R6  un `scripts/ci.sh` que hace `exit 0` y NADA MAS produce la MISMA linea
    R7  un `scripts/ci.sh` que imprime el veredicto de la receta y sale 0
        produce la MISMA linea
    R8  la salida del hook con R6 y con R7 es IDENTICA

**El bypass era UN caso, no el defecto.** El hook delega y solo sabe una cosa:
que el delegado devolvió 0. Un exit code de 0 dice que el proceso terminó, no
que la receta corriera ni que hiciera nada.

**LO QUE SE PUEDE MEDIR, Y NO ES INVENTADO.** `.pipeline.kts` imprime
`Pipeline finished with SUCCESS` —medido en los artefactos del propio repo: 169
apariciones de SUCCESS y 9 de FAILURE— y es la misma cadena que el hook ya
nombraba en su mensaje de error. El hook ya capturaba esa salida en `$_log` y
después la borraba sin haberla mirado. Ahora la **exige**: si el delegado sale
con 0 y no emite su veredicto, el hook se pone rojo en vez de decir SUCCESS.

**POR QUÉ ESTOS TESTS EJECUTAN EL HOOK Y NO LO LEEN.** Un guard que buscara una
cadena en el fichero aprobaría el defecto entero: el hook TIENE `SUCCESS` en su
propio mensaje de error, luego una búsqueda por presencia lo aprueba siempre.
Lo que se mide es lo que el operador **ve** y lo que el hook **hace**: se
copia el hook sin tocarlo a un repo de pruebas con un `ci.sh` de doble y se
mira la salida y el código de retorno.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
HOOK = RAIZ / "scripts" / "hooks" / "pre-push"

#: Lo que `.pipeline.kts` imprime cuando su veredicto es bueno. Aqui solo se
#: usa para CONSTRUIR el doble de `scripts/ci.sh`; el hook tiene su propia
#: copia de la cadena, y que las dos no se separen es lo que mide el ultimo
#: test de este fichero, derivandolo del arbol.
VEREDICTO_RECETA = "Pipeline finished with SUCCESS"


def _repo_con_hook(tmp_path: Path, ci: str) -> Path:
    """Un repo git minimo con el hook REAL y un `ci.sh` con el cuerpo dado.

    El hook se copia sin tocar: si aqui se modificara una linea, el test
    mediria el hook del test y no el del repo.
    """
    repo = tmp_path / "repo"
    (repo / "scripts" / "hooks").mkdir(parents=True)
    (repo / "scripts" / "ci.sh").write_text(ci, encoding="utf-8")
    shutil.copy(HOOK, repo / "scripts" / "hooks" / "pre-push")
    for cmd in (
        ["init", "-q"],
        ["config", "user.email", "b38@b38.invalid"],
        ["config", "user.name", "b38"],
        ["commit", "-q", "--allow-empty", "-m", "b38"],
    ):
        subprocess.run(["git", *cmd], cwd=repo, check=True, capture_output=True)
    return repo


def _correr(repo: Path, **entorno: str) -> tuple[int, str]:
    r = subprocess.run(
        ["sh", "scripts/hooks/pre-push"],
        cwd=repo,
        env={**os.environ, **entorno},
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    return r.returncode, r.stdout + r.stderr


def _afirma_que_la_receta_dio_success(salida: str) -> bool:
    """¿El hook AFIRMA que la receta dio SUCCESS?

    No se busca la cadena `SUCCESS` en toda la salida, y el motivo está medido:
    tras el arreglo el mensaje de error del hook CONTIENE esa cadena («no
    imprimió 'Pipeline finished with SUCCESS'»), luego una búsqueda por
    presencia reporta que el hook sigue diciendo SUCCESS con un hook que ya no
    lo hace. Lo que se mide es la AFIRMACIÓN: una línea que abre el veredicto
    del hook, y que habla del delegado y no de otra cosa.
    """
    for linea in salida.splitlines():
        if linea.startswith("[pre-push] OK"):
            return "receta" in linea or "delegado" in linea
    return False


def test_un_delegado_que_no_hace_nada_no_produce_un_success(tmp_path: Path) -> None:
    """**EL CASO ESTRUCTURAL (R6).** Un `ci.sh` que hace `exit 0` y nada más.

    Antes del arreglo esto imprimía `OK: la receta canonica dio SUCCESS`, que
    es una afirmación sobre una ejecución que no ocurrió. El hook no puede
    saber que la receta corrió por el código de salida, porque un 0 sólo dice
    que el proceso terminó.
    """
    repo = _repo_con_hook(tmp_path, "#!/bin/sh\nexit 0\n")

    rc, salida = _correr(repo)

    assert not _afirma_que_la_receta_dio_success(salida), (
        "el hook afirmo que la receta dio SUCCESS con un delegado que no hizo "
        "nada. Un exit code 0 no dice que la receta se haya ejecutado.\n" + salida
    )
    assert rc != 0, (
        "el hook dejo pasar a un delegado que no emitio su veredicto. El hook "
        f"tiene su salida en $_log y puede exigirla.\n{salida}"
    )


def test_un_delegado_que_si_ejecuta_dice_un_success_verificado(tmp_path: Path) -> None:
    """**EL CONTRASALTO (R7).** El camino bueno no puede perder su anuncio.

    Y la afirmación tiene que seguir siendo del delegado, no del hook: un
    `OK: todo bien` sin decir de qué también sería una afirmación sin
    comprobar.
    """
    repo = _repo_con_hook(tmp_path, f"#!/bin/sh\necho '{VEREDICTO_RECETA}'\nexit 0\n")

    rc, salida = _correr(repo)

    assert rc == 0, f"un delegado que emite su veredicto debe pasar:\n{salida}"
    assert _afirma_que_la_receta_dio_success(salida), (
        "el camino que SI verifica dejo de decirlo, y entonces el camino que no "
        f"verifica vuelve a ser indistinguible de este:\n{salida}"
    )
    assert VEREDICTO_RECETA in salida, (
        "la linea de OK no cita el veredicto que el hook exigio, asi que no se "
        f"puede saber que lo comproboro:\n{salida}"
    )


def test_el_bypass_dice_que_no_ha_sido_verificado(tmp_path: Path) -> None:
    """**EL BYPASS (R1).** Se declara, y no dice SUCCESS.

    Es el mismo defecto de B37 en el pre-commit —un hook que se calla— con una
    palabra más fuerte: allí el `OK` era neutro y aquí el `SUCCESS` afirmaba
    una ejecución que no ocurrió, en el gate que está a un comando de salir
    del repo.
    """
    repo = _repo_con_hook(tmp_path, "#!/bin/sh\necho 'ESTO NO DEBERIA CORRER'\nexit 1\n")

    rc, salida = _correr(repo, HOOK_SKIP_PUSH_TESTS="1")

    assert "ESTO NO DEBERIA CORRER" not in salida, "el bypass no saltó nada"
    assert rc == 0, salida
    assert not _afirma_que_la_receta_dio_success(salida), (
        "con el bypass puesto el hook afirmo que la receta dio SUCCESS. El "
        f"bypass es una excepcion real, pero no es una verificacion.\n{salida}"
    )
    assert "OMITIDOS" in salida and "NO ha sido verificado" in salida, (
        "el bypass tiene que DECIR que no se verifico, no solo saltarse la "
        f"comprobacion en silencio:\n{salida}"
    )


def test_el_hook_exige_el_veredicto_y_no_lo_inventa(tmp_path: Path) -> None:
    """La propiedad del hook, y no un caso: **exige la frase**, no una palabra.

    Un delegado que emite `Pipeline finished with Successful` no es la receta:
    le falta la `S`. Un hook que buscara `SUCCESS` a secas lo aprobaría en el
    mundo real si alguien escribiera el veredicto en otro idioma o con otro
    idioma de carné; uno que exige la frase exacta, no.

    Y un detalle que costó una sonda: `Successful` **no** contiene `SUCCESS`
    porque el `grep` distingue mayúsculas. Una sonda que cambiara el hook a
    `grep -q SUCCESS` NO la mataba con este contraejemplo, y por eso hace falta
    el de la línea entera del test de al lado.
    """
    casi = "Pipeline finished with Successful"
    repo = _repo_con_hook(tmp_path, f"#!/bin/sh\necho '{casi}'\nexit 0\n")

    rc, salida = _correr(repo)

    assert rc != 0, (
        "el delegado emitio una cadena PARECIDA y el hook lo aprobo. Exigir «"
        f"{VEREDICTO_RECETA}» no es lo mismo que buscar «SUCCESS».\n{salida}"
    )


def test_el_veredicto_no_se_acepta_en_otra_capitalizacion(tmp_path: Path) -> None:
    """**POR QUÉ HACE FALTA ESTE CASO, Y NO ES OBVISO.**

        Una sonda que puso el `grep` del hook en modo no-sensible-a-mayúsculas
        dio **INOCUA**, y era porque el contraejemplo anterior —«Successful»— no
        distingue: `Successful` no es `SUCCESS` con otra capitalización, es otra
        palabra más larga, luego el `grep` la rechazaba igual con y sin `-i`. Es
        decir: esa sonda no medía nada y parecía medir.

        El caso que sí distingue es una **variante de capitalización** de la frase
        exacta. La receta emite `Pipeline finished with SUCCESS` en mayúsculas —
    medido, 20 líneas byte a byte iguales en los artefactos—, así que
        `pipeline finished with success` no es su veredicto: es otra cosa que se
        le parece. Un `-i` lo aceptaría.
    """
    minusculas = VEREDICTO_RECETA.lower()
    repo = _repo_con_hook(tmp_path, f"#!/bin/sh\necho '{minusculas}'\nexit 0\n")

    rc, salida = _correr(repo)

    assert rc != 0, (
        "el delegado emitio el veredicto en otra capitalizacion y el hook lo "
        f"aprobo. La receta emite «{VEREDICTO_RECETA}» y el hook exige esa "
        f"cadena, no una variante.\n{salida}"
    )


def test_el_hook_exige_la_linea_entera_y_no_una_subcadena(tmp_path: Path) -> None:
    """**EL AGUJERO QUE DEJÓ `grep -qF` SIN `-x`, Y QUE SONDAS MEDIRON.**

    Exigir que la frase ESTÉ en la salida no es lo mismo que exigir que SEA el
    veredicto: un delegado que imprimiera
    `Pipeline finished with SUCCESS (rehecho)` contiene la frase entera y no
    ha ejecutado la receta. Con `grep -qF` —sin `-x`— el hook lo aceptaba.

    Lo que lo cierra no es una arbitrariedad del hook: es MEDIDO que la receta
    emite esa frase **sola en su línea** —20 apariciones byte a byte iguales en
    los artefactos del repo—, luego exigir la línea completa no rejecta nada
    real.
    """
    rehecho = f"{VEREDICTO_RECETA} (rehecho por un RecipeRun)"
    repo = _repo_con_hook(tmp_path, f"#!/bin/sh\necho '{rehecho}'\nexit 0\n")

    rc, salida = _correr(repo)

    assert rc != 0, (
        "el delegado emitio una linea que CONTIENE el veredicto pero no es el "
        f"veredicto, y el hook lo aprobo. Exigir la LINEA entera no es lo mismo "
        f"que buscar la frase.\n{salida}"
    )


def test_el_veredicto_exigido_es_el_que_emite_la_receta() -> None:
    """**El veredicto está DERIVADO del árbol, no escrito a mano.**

    El hook exige una cadena literal. Si mañana `.pipeline.kts` —o el motor que
    la ejecuta— deja de emitir esa frase, el hook rechazaría todos los pushes
    sin que nadie sepa por qué: un guard que se rompe por un cambio de
    contrato y no lo dice.

    Por eso aquí no se compara con una copia escrita en el test —el guard que
    compara contra su propia copia es el error de WI-106— sino con lo que el
    propio repo **declara** que la receta emite. El conjunto sale de buscar en
    el árbol, y no de una lista mantenida a mano.
    """
    hook = HOOK.read_text(encoding="utf-8")
    exigida = [
        linea.strip() for linea in hook.splitlines() if linea.startswith("VEREDICTO_RECETA=")
    ]
    assert exigida, f"el hook ya no declara que veredicto exige:\n{hook}"
    cadena_del_hook = exigida[0].split("=", 1)[1].strip().strip("'\"")

    # Quien mas nombra el veredicto en este repo. Cada uno es una autoridad
    # que puede desincronizarse del hook sin que ninguna se entere.
    autoridades = {
        "scripts/ci.sh",
        "scripts/diagnose_pytest_run.sh",
        "scripts/check_pipeline_receipt.py",
    }
    declaradas: set[str] = set()
    for rel in autoridades:
        ruta = RAIZ / rel
        if not ruta.exists():
            continue
        texto = ruta.read_text(encoding="utf-8")
        declaradas.update(
            linea.strip() for linea in texto.splitlines() if "Pipeline finished with" in linea
        )

    assert declaradas, (
        "ningun instrumento del repo nombra ya el veredicto de la receta, luego "
        "no hay contraejemplo que construir. Si los tres han cambiado a la vez, "
        "esta cadena es la que hay que revisar."
    )
    assert any(cadena_del_hook in d for d in declaradas), (
        f"el hook exige {cadena_del_hook!r} y ningun otro instrumento del repo "
        f"declara esa frase. Declaradas: {sorted(declaradas)}. Si el veredicto "
        "cambio, hay que cambiarlo en el hook Y en quien lo emite."
    )
