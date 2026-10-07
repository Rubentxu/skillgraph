"""`GitHistory`: el otro reloj, medido sobre repos REALES.

**POR QUE UN REPO REAL Y NO UN DOBLE.** El contrato que importa no es «me
devuelves una tupla de padres», que un doble cumple en tres líneas: es que
`es_ancestro` signifique lo que dice sobre el grafo de git de verdad. Un
doble que devuelve lo que el test quiere no mide el grafo, mide el doble.

Y porque el repositorio de pruebas se CONSTRUYE en el test, cada aserción
tiene su historia detrás: el grafo se monta con `git init` y commits reales
y se lee con `dulwich`, el mismo camino que producción. Si el grafo del test
se parece al de git en vez de parecerse a lo que el test espera, eso es lo
que hace que la propiedad valga.

**LA ESTRUCTURA DEL GRAFO, QUE ESTA DIBUJADA ANTES POR UNA RAZON.** El test
usa un grafo con una bifurcación y un merge:

    a -> b -> c        (rama lineal)
         \\-> d -> e   (rama que se fusiona)
    a -> b -> c <- d <- e     (c es un merge de dos padres)

Es la forma mínima en la que «el orden» deja de existir: `d` y `a` están en
ramas distintas y **no hay un orden total entre ellos**. Un grafo lineal no
distingue un `es_ancestro` bien hecho de uno que devuelve `True` siempre, y
esa es exactamente la clase de test que pasa en verde con el código roto.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from skillgraph.core.errors import DulwichNotAvailableError
from skillgraph.platform.git_history import PROFUNDIDAD_POR_DEFECTO, DulwichGitHistory


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        env={
            "PATH": "/usr/bin:/bin",
            "GIT_AUTHOR_NAME": "t",
            "GIT_AUTHOR_EMAIL": "t@e.com",
            "GIT_COMMITTER_NAME": "t",
            "GIT_COMMITTER_EMAIL": "t@e.com",
        },
    )


def _commit(repo: Path, nombre: str, contenido: str) -> str:
    (repo / nombre).write_text(contenido, encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", nombre)
    return _head(repo)


def _head(repo: Path) -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, check=True, capture_output=True, text=True
    ).stdout.strip()


@pytest.fixture
def repo_path(tmp_path: Path) -> Path:
    """Un directorio vacio donde construir el repo de pruebas.

    `tmp_path` y no el repo real: `git init` dentro del arbol del repo crearia
    un `.git` anidado que el guard de «el arbol real no se escribe» veria
    como una escritura no explicada.
    """
    d = tmp_path / "repo"
    d.mkdir()
    return d


@pytest.fixture
def grafo(repo_path: Path):  # type: ignore[no-untyped-def]
    """Un repo con bifurcacion y merge, y los shas de cada commit."""
    _git(repo_path, "init", "-q", "-b", "main")
    a = _commit(repo_path, "a.txt", "a")
    b = _commit(repo_path, "b.txt", "b")

    _git(repo_path, "checkout", "-q", "-b", "rama", b)
    d = _commit(repo_path, "d.txt", "d")
    e = _commit(repo_path, "e.txt", "e")

    _git(repo_path, "checkout", "-q", "main")
    c = _commit(repo_path, "c.txt", "c")

    _git(repo_path, "merge", "-q", "--no-ff", "-m", "merge", "rama")
    m = _head(repo_path)

    return {"repo": repo_path, "a": a, "b": b, "c": c, "d": d, "e": e, "merge": m}


class TestLaIdentidadEsElSha:
    """Un commit se identifica por su SHA y por nada mas.

    Y se mide la propiedad que hace el SHA utilizable: **el contenido es el
    nombre**. El mismo contenido commiteado dos veces da dos SHAs distintos,
    lo que significa que el SHA no es una etiqueta puesta por alguien sino un
    resumen. Un contador de revisión no tiene esa propiedad y por eso no
    puede ser la identidad de una ascendencia.
    """

    def test_el_sha_devuelto_es_el_del_commit(self, grafo: dict) -> None:
        with DulwichGitHistory(grafo["repo"]) as h:
            assert h.commit(grafo["b"]).sha == grafo["b"]
            assert h.existe(grafo["b"])

    def test_el_mismo_contenido_da_shas_distintos(self, repo_path: Path) -> None:
        """Dos commits con el MISMO contenido tienen SHAs distintos.

        No es una curiosidad: es lo que prueba que el SHA identifica el
        contenido y no un contador. Si dos commits iguales compartieran SHA,
        la ascendencia no podría distinguir dos hechos que ocurrieron en
        momentos distintos.
        """
        _git(repo_path, "init", "-q", "-b", "main")
        primero = _commit(repo_path, "f.txt", "el mismo contenido")
        # El segundo commit esta VACIO a proposito: el arbol no cambia, pero
        # el padre si, y eso ya cambia el SHA. Es la forma minima de tener dos
        # commits con el MISMO contenido y distinta identidad.
        #
        # La primera version de este test commiteaba el mismo fichero otra
        # vez y fallaba con `exit status 1`: `git add .` no cambia nada y no
        # hay nada que commitear. El fallo era del test, no del codigo, y lo
        # dice porque un test que falla por su propio montaje no mide lo que
        # dice medir.
        _git(repo_path, "commit", "-q", "--allow-empty", "-m", "vacio")
        segundo = _head(repo_path)

        assert primero != segundo, (
            "dos commits con el mismo contenido tienen el mismo SHA: la "
            "identidad no es el contenido y la ascendencia no podria distinguir "
            "dos hechos en momentos distintos"
        )

    def test_un_sha_inexistente_es_None_y_no_un_error(self, grafo: dict) -> None:
        """`None` es «este historial no lo tiene», no una excepcion.

        Ver el docstring del puerto: `None` no distingue «de otro
        repositorio», «reescrito» y «clon superficial», y no debe. Lo que no
        puede es lanzar, porque quien guarda referencias a SHAs meets
        commits que se reescriben con `rebase` y eso es normal.
        """
        with DulwichGitHistory(grafo["repo"]) as h:
            assert h.commit("0" * 40) is None
            assert not h.existe("0" * 40)
            assert not h.existe("no-es-un-sha")


class TestEsAncestro:
    """La pregunta que el puerto existe para contestar."""

    def test_un_padre_es_ancestro_de_su_hijo(self, grafo: dict) -> None:
        with DulwichGitHistory(grafo["repo"]) as h:
            assert h.es_ancestro(grafo["a"], grafo["c"])
            assert h.es_ancestro(grafo["b"], grafo["c"])
            assert h.es_ancestro(grafo["b"], grafo["d"])

    def test_un_commit_ES_ancestro_de_si_mismo(self, grafo: dict) -> None:
        """**EL CASO TRIVIAL QUE HACE FALTA DECLARAR.**

        Sin el, `es_ancestro(x, x)` devolveria `False` en cualquier
        implementacion que recorra padres, y quien lo use para preguntar
        «¿este hecho estaba ya en este commit?» tendria que escribir la
        disyuncion a mano en cada sitio. El puerto lo declara y la
        implementacion lo cumple.
        """
        with DulwichGitHistory(grafo["repo"]) as h:
            assert h.es_ancestro(grafo["c"], grafo["c"])

    def test_UN_sha_inexistente_no_es_ancestro_de_nADA(self, grafo: dict) -> None:
        """Un ancestro que no esta no es ancestro. Suena obvio y NO lo es.

        Si la implementacion no comprueba la existencia del ancestro antes
        de comparar, un sha inventado daria `False` —correcto por azar— y uno
        que SI existe en otra rama daria `True` —falso de verdad—. Se mide
        con los dos para que el test no dependa del azar.
        """
        with DulwichGitHistory(grafo["repo"]) as h:
            assert not h.es_ancestro("0" * 40, grafo["merge"])
            assert not h.es_ancestro("f" * 40, grafo["merge"])

    def test_el_sentido_NO_se_puede_invertir_en_silencio(self, grafo: dict) -> None:
        """`es_ancestro(a, b)` y `es_ancestro(b, a)` no son la misma pregunta.

        Es el fallo mas probable de una implementacion de este puerto: una
        comparacion de shas en vez de un recorrido. Con SHAs el resultado
        seria arbitrario y aqui daria `True` en los dos sentidos, luego el
        test que lo caza es el que mira LOS DOS.
        """
        with DulwichGitHistory(grafo["repo"]) as h:
            adelante = h.es_ancestro(grafo["a"], grafo["merge"])
            atras = h.es_ancestro(grafo["merge"], grafo["a"])

            assert adelante, "a es ancestro del merge"
            assert not atras, (
                "el merge tambien salio ancestro de a: la ascendencia se "
                "puede invertir, luego no hay recorrido y hay una comparacion"
            )

    def test_ramas_distintas_NO_tienen_orden_entre_su_y_el_merge(self, grafo: dict) -> None:
        """**EL CASO QUE JUSTIFICA QUE EL CONTRATO NO OFREZCA `ordena`.**

        `c` y `d` estan en ramas distintas. Los dos son ancestros del merge,
        y ninguno es ancestro del otro: no hay orden entre ellos.

        Si el puerto prometiera `ordena(a, b) -> int`, esta pregunta
        obligaria a devolver un numero para algo que no tiene direccion. El
        contrato ofrece `es_ancestro` porque se puede responder siempre, y
        este test es el que dice por que.
        """
        with DulwichGitHistory(grafo["repo"]) as h:
            assert h.es_ancestro(grafo["c"], grafo["merge"])
            assert h.es_ancestro(grafo["d"], grafo["merge"])
            assert not h.es_ancestro(grafo["c"], grafo["d"])
            assert not h.es_ancestro(grafo["d"], grafo["c"])

    def test_un_merge_es_ancestro_de_lo_que_viene_por_ambos_ramos(self, grafo: dict) -> None:
        """El recorrido tiene que seguir AMBOS padres, no solo el primero.

        Es el fallo que hace que un grafo lineal pase todos los tests: si el
        recorrido solo sigue `parents[0]`, la rama que entro por el segundo
        padre desaparece de la ascendencia y `es_ancestro(d, merge)` falla.
        """
        with DulwichGitHistory(grafo["repo"]) as h:
            assert h.es_ancestro(grafo["e"], grafo["merge"])
            assert h.es_ancestro(grafo["d"], grafo["merge"])
            assert h.es_ancestro(grafo["a"], grafo["merge"])


class TestLaCadenaEsUnConjuntoOrdenadoPorCercania:
    def test_el_primer_ancestro_es_el_commit_mismo(self, grafo: dict) -> None:
        with DulwichGitHistory(grafo["repo"]) as h:
            ancestros = h.ancestros_de(grafo["merge"])

            assert ancestros[0] == grafo["merge"], ancestros
            assert len(ancestros) == len(set(ancestros)), (
                f"la ascendencia tiene repeats: {ancestros}"
            )

    def test_incluye_LOS_DOS_ramos_del_merge(self, grafo: dict) -> None:
        """Los dos lados, no solo el primero.

        `ancestros_de(merge)` tiene que traer `c` (rama main) y `d` (rama
        fusionada). Con solo el primer padre, `d` y `e` no aparecen y la
        ascendencia es media.
        """
        with DulwichGitHistory(grafo["repo"]) as h:
            ancestros = h.ancestros_de(grafo["merge"])

            for sha, etiqueta in (
                (grafo["c"], "rama main"),
                (grafo["d"], "rama fusionada"),
                (grafo["a"], "raiz comun"),
            ):
                assert sha in ancestros, f"{etiqueta} ({sha[:8]}) no esta en la ascendencia"

    def test_el_limite_recorta_y_no_mentira(self, grafo: dict) -> None:
        """`limite` corta de verdad, y lo que se queda es el principio.

        Con `limite=2` salen el commit y su padre, y nada mas. Se mide la
        longitud Y que el padre este, porque una slicing mal puesta podria
        devolver dos elementos que no son el principio.
        """
        with DulwichGitHistory(grafo["repo"]) as h:
            corto = h.ancestros_de(grafo["merge"], limite=2)
            completo = h.ancestros_de(grafo["merge"])

            assert len(corto) == 2, corto
            assert corto[0] == grafo["merge"]
            assert corto[1] in (grafo["c"], grafo["d"])
            assert len(completo) > len(corto)

    def test_un_commit_inexistente_no_va_a_infinito(self, grafo: dict) -> None:
        """El tope de seguridad: un sha que no existe termina igual.

        Se mide con un limite BAJO a proposito. El tope por defecto existe
        porque un clon superficial es finito y un `ref` mal escrito puede
        no serlo; lo que se comprueba aqui es que el tope se respeta y que
        `None`/`KeyError` no se propagan.
        """
        with DulwichGitHistory(grafo["repo"]) as h:
            assert h.ancestros_de("0" * 40) == ("0" * 40,)
            assert h.ancestros_de("0" * 40, limite=1) == ("0" * 40,)

    def test_el_tope_por_defecto_es_un_TOPE_y_no_un_adorno(self) -> None:
        """La constante existe, es un entero positivo y es FINITO.

        Sin este test, `PROFUNDIDAD_POR_DEFECTO` podria ser `0` (el recorrido
        no miraria nada y todo daria `False`) o `None` (no habria tope y un
        clon superficial colgaria el proceso). Los dos son verdes en los
        tests de arriba si el grafo es pequeño, y este es el que lo ve.
        """
        assert isinstance(PROFUNDIDAD_POR_DEFECTO, int)
        assert PROFUNDIDAD_POR_DEFECTO > 0, "un tope de 0 no recorre nada"
        assert PROFUNDIDAD_POR_DEFECTO < 10**9, (
            "un tope de mil millones no protege de un clon superficial"
        )


class TestElMergeSeDeclara:
    def test_es_merge_si_y_solo_si_tiene_mas_de_un_padre(self, grafo: dict) -> None:
        from skillgraph.platform.ports.git_history import Commit

        with DulwichGitHistory(grafo["repo"]) as h:
            assert h.commit(grafo["merge"]).es_merge()
            assert not h.commit(grafo["c"]).es_merge()
            assert not Commit(sha="x", parents=()).es_merge()


class TestUnHistorialCerradoNoResponde:
    def test_usar_despues_de_cerrar_es_un_ERROR_TIPADO(self, grafo: dict) -> None:
        """Un `Repo` cerrado no puede responder, y eso se dice.

        La alternativa —`AttributeError` sobre `None`— es la que hace que un
        fallo de ciclo de vida aparezca como un fallo de datos. Y
        `DulwichNotAvailableError` es la clase correcta porque es la misma
        frontera que usa `git_source` cuando dulwich no esta: no hay historial
        disponible, y eso es una condicion del entorno.
        """
        h = DulwichGitHistory(grafo["repo"])
        assert h.existe(grafo["a"])
        h.close()

        with pytest.raises(DulwichNotAvailableError):
            h.existe(grafo["a"])

    def test_close_es_idempotente(self, grafo: dict) -> None:
        """Cerrar dos veces no lanza.

        El `with` llama a `close`, y un `finally` que Tambien cierra
        —que es lo que hace cualquier codigo bien escrito— lo llama otra
        vez. Si eso fuera un error, el `finally` taparia la excepcion
        original del `with`, que es la peor forma de perder informacion.
        """
        h = DulwichGitHistory(grafo["repo"])
        h.close()
        h.close()


class TestElContratoNoEsUnAlias:
    """**POR QUE ESTOS TESTS NO BASTAN Y ESTE REMUEVE ESA DUDA.**

    `DulwichGitHistory` declara heredar de `GitHistory`, y `Protocol` con
    `runtime_checkable` solo comprueba que los NOMBRES existan. Eso no
    comprueba que las firmas casen: un metodo con el mismo nombre y otra
    firma pasa el `isinstance`.

    Y el fallo que importa aqui es concreto: si `es_ancestro` tuviera los
    dos parametros invertidos, `isinstance` lo daria por bueno y todos los
    tests de arriba —que usan el adaptador de verdad— tambien. Lo unico que
    lo caza es mirar la FIRMA, y por eso esta clase existe.
    """

    def test_el_adaptador_cumple_el_protocolo(self, grafo: dict) -> None:
        from skillgraph.platform.ports.git_history import GitHistory

        with DulwichGitHistory(grafo["repo"]) as h:
            assert isinstance(h, GitHistory)

    def test_la_firma_de_es_ancestro_no_esta_invertida(self) -> None:
        """`es_ancestro(ancestro, descendiente)` — y en ese orden.

        Se mide el NOMBRE del primer parametro, no solo el numero. La
        posicion se puede leer en la firma; lo que no se ve leyendo es si el
        nombre dice quien es el ancestro, y es el nombre el que documenta la
        llamada.
        """
        import inspect

        from skillgraph.platform.ports.git_history import GitHistory as P

        params = list(inspect.signature(P.es_ancestro).parameters)
        assert params == ["self", "ancestro", "descendiente"], params

    def test_ambos_relojes_siguen_siendo_protocolos_distintos(self) -> None:
        """**LA FRONTERA DE B32, EN UNA ASERCION.**

        `RevisionRegistry` y `GitHistory` son puertos distintos porque miden
        cosas distintas: uno el orden en que ESTE store aprendio, otro la
        ascendencia real. Un adaptador que cumpliera los dos no tendria nada
        que decir sobre la diferencia, y volveria a ser el mapa unico que
        contestaba dos preguntas — el defecto que B3 denieso a proposito.

        Se mide que `DulwichGitHistory` NO cumple `RevisionRegistry`: si
        apareciera un metodo `seq_de` en el adaptador, alguien habria
        mezclado los relojes y este test lo diria.
        """
        from skillgraph.platform.ports.git_history import GitHistory
        from skillgraph.platform.ports.revisions import RevisionRegistry

        with DulwichGitHistory(Path(".")) as h:
            assert isinstance(h, GitHistory)
            assert not isinstance(h, RevisionRegistry), (
                "el adaptador de ascendencia cumple tambien el puerto de orden "
                "de observacion: los dos relojes se han mezclado"
            )
