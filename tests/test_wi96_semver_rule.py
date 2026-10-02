"""WI-96: la regla de SemVer esta escrita, no verificada, y es falsa tal cual.

Por que este fichero existe
---------------------------
El repositorio declara COMO se deriva la version de una release, y lo hace en
un unico sitio: la cabecera de `CHANGELOG.md`.

    - `feat` -> MINOR (nueva capacidad observable).
    - `fix` -> PATCH (correccion).
    - `feat!` / `fix!` / footer `BREAKING CHANGE` -> MAJOR.
    - `refactor`, `test`, `docs`, `spec`, `chore`, `style` -> sin bump.

Y MEDIDO sobre los 47 tags reales, contra la regla tal como esta escrita:

    releases cuyo SemVer NO se deduce de ella ... 9
    de las cuales llevan un `BREAKING CHANGE` real ... 3
        v0.7.0  (eliminacion de 20 shims de retro-compatibilidad)
        v0.15.0 (su propio commit de release dice «MINOR por 1 BREAKING»)
        v0.16.2 (su commit dice «MINOR y MAJOR quedan fuera y corresponde PATCH»)

O sea: **la regla dice que un breaking change es MAJOR, y el proyecto ha
publicado tres breaking changes sin llegar nunca a 1.0.0.** La exencion 0.x
que lo explica existe **solo** en los mensajes de commit de esas tres
releases: no esta en `AGENTS.md §12`, no esta en la cabecera del CHANGELOG, y
no la lee nadie que no haga `git log`.

Peor: `AGENTS.md §12` se titula «Regla de release» y **no contiene la regla
de derivacion**. Solo contiene las reglas mecanicas (fuente de verdad, tag vs
`__version__`, `.devN`). La unica declaracion de como se deriva la version
esta en un fichero que no es el dueño de la gobernanza de releases — que es
exactamente el patron de dos fuentes que WI-95 acaba de cerrar para los
registros, y aqui sigue abierto para la regla.

Y la derivacion se hace **a mano**, release tras release. Este bloque comprueba
que el calculo este disponible, que la regla tenga un dueno unico, y que la
exencion 0.x quede escrita donde se lee.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path
from typing import Final

ROOT: Final = Path(__file__).resolve().parent.parent
AGENTS: Final = ROOT / "AGENTS.md"
CHANGELOG: Final = ROOT / "CHANGELOG.md"
SCRIPT: Final = ROOT / "scripts" / "derive_semver.py"
SEMVER: Final = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")

# Era en la que la regla se cumple. Medido: v0.16.3 -> v0.16.20 son 18/18
# coherentes. Antes de ahi el proyecto operaba con otra politica, y fingir que
# la regla de hoy tambien gobernaba 2026-09 seria tan falso como el problema
# que se esta corrigiendo.
BASELINE: Final = "v0.16.3"


# --- Utilidades ------------------------------------------------------------


def _seccion12() -> str:
    texto = AGENTS.read_text(encoding="utf-8")
    m = re.search(r"^## 12\..*?(?=^## 13\.|\Z)", texto, re.M | re.S)
    assert m, "AGENTS.md ya no tiene la seccion 12"
    return m.group(0)


def _tags() -> list[str]:
    salida = subprocess.run(
        ("git", "tag", "--list", "v*"),
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return sorted(
        (t for t in salida.stdout.split() if SEMVER.match(t)),
        key=lambda t: tuple(int(p) for p in SEMVER.match(t).group(1, 2, 3)),
    )


sys.path.insert(0, str(ROOT / "scripts"))


def _version(tag: str) -> tuple[int, int, int]:
    return tuple(int(p) for p in SEMVER.match(tag).group(1, 2, 3))  # type: ignore[return-value]


def _divergencias_de_tipo(tags_: list[str]) -> set[str]:
    """Etiquetas cuya version contradice el TIPO de bump que dicta la regla.

    «Tipo» y no «numero»: la regla define si toca MINOR, PATCH o MAJOR, y un
    `0.14.7` donde la regla pedia MINOR diverge aunque el calculo aritmetico
    cuadre. Lo que no se compte aqui es «la regla no pide release y se
    etiqueto», que es otra cosa.
    """
    import derive_semver as ds

    salida: set[str] = set()
    for tag in tags_:
        esperado = ds.derivacion_esperada(tags_, tag)
        if esperado is not None and not ds.coincide(tag, esperado):
            salida.add(tag)
    return salida


def _etiquetas_sin_release(tags_: list[str]) -> set[str]:
    """Etiquetas que existen donde la regla no pedia ninguna."""
    import derive_semver as ds

    return {t for t in tags_ if ds.derivacion_esperada(tags_, t) is None}


# --- 1. La regla tiene UN dueno, y es AGENTS §12 ---------------------------


class TestLaReglaTieneUnDueno:
    def test_agients_12_declara_la_derivacion(self) -> None:
        """La seccion que se titula «Regla de release» tiene que tener la regla.

        MEDIDO en WI-96: `AGENTS.md §12` no menciona `feat`, ni `MINOR`, ni
        `PATCH`. Todo el cálculo de version estaba en la cabecera del
        CHANGELOG, que no es el dueño de la gobernanza de releases.
        """
        s = _seccion12()
        for token in ("MINOR", "PATCH", "MAJOR"):
            assert token in s, f"AGENTS.md §12 no declara la derivacion ({token} ausente)"

    def test_la_regla_no_esta_duplicada_en_el_changelog(self) -> None:
        """El CHANGELOG **referencia** la regla, no la reescribe.

        Dos enunciados de la misma regla en dos ficheros son dos fuentes que
        se pueden desincronizar, y una que ya se ha desincronizado. Es la
        misma leccion de WI-95 aplicada a la regla y no a los registros.

        El patron acepta `->` y `→`: la primera version de este test buscaba
        solo el guion y pasaba en verde **con la tabla presente**, porque el
        fichero usa la flecha tipografica. Un guard que no encuentra lo que
        busca no vigila nada, y un `assert` que pasa por el motivo equivocado
        es peor que no tener el test.
        """
        cabecera = CHANGELOG.read_text(encoding="utf-8")[:2000]
        reescribe = re.search(r"^[-*]\s*`feat`\s*(?:->|→)\s*MINOR", cabecera, re.M)
        assert not reescribe, (
            "la cabecera del CHANGELOG vuelve a escribir la regla de derivacion. "
            "Debe referenciar AGENTS.md §12, que es su dueno"
        )
        assert "AGENTS.md" in cabecera, (
            "la cabecera del CHANGELOG deberia remitir a AGENTS.md §12, que es donde vive la regla"
        )


# --- 2. La exencion 0.x esta escrita donde se lee --------------------------


class TestLaExencionEstaDocumentada:
    def test_agients_12_explica_el_0x(self) -> None:
        """Un breaking change en 0.x no es MAJOR. Decirlo es parte de la regla.

        Sin esta clausula, la regla escrita es la que el proyecto ha violado
        tres veces, y el proximo breaking change obliga a improvisar entre
        saltar a 1.0.0 —un salto que nadie ha planeado— y repetir una
        exencion que solo vive en un mensaje de commit.

        La asercion NO busca la cadena «0.x»: la busco y M1 la dejO puesta
        mientras vaciaba la clausula, y el guard no lo noto. Busca la
        **seccion** y, sobre todo, que la regla de 1.0.0 aparezca
        **negada** — que es lo que hace la clausula. Un texto que contiene
        «0.x» sin negar el salto a 1.0.0 no dice nada.
        """
        s = _seccion12()
        assert "### Salvedad 0.x" in s, (
            "AGENTS.md §12 no tiene la seccion de salvedad 0.x, que es la que "
            "ha governado de facto los tres breaking changes del proyecto"
        )

        # La regla debe decir que 1.0.0 NO es obligatorio, no solo nombrar 0.x.
        negada = re.search(
            r"(no\s+(obliga|fuerza|requiere|exige|arrastra)|quedan fuera|"
            r"no\s+saltar?\s+a\s+1\.0\.0|excepto\s+1\.0\.0)",
            s,
            re.I,
        )
        assert negada, (
            "AGENTS.md §12 nombra 0.x pero no niega que un breaking change "
            "oblige a 1.0.0: la clausula esta de adorno"
        )
        assert "1.0.0" in s, "la clausula deberia nombrar el 1.0.0 que exonera"

    def test_los_breaking_historicos_estan_nombrados(self) -> None:
        """Un precedente que se invoca tiene que poder citarse.

        `v0.7.0`, `v0.15.0` y `v0.16.2` son las tres veces que se aplico la
        exencion. Nombrarlas es lo que convierte «se hizo asi» en «se
        decidio asi»; sin nombre, la proxima sesion vuelve a medirlo desde
        cero.
        """
        s = _seccion12()
        ausentes = [t for t in ("v0.7.0", "v0.15.0", "v0.16.2") if t not in s]
        assert not ausentes, (
            f"AGENTS.md §12 invoca la exencion 0.x sin nombrar los precedentes: {ausentes}"
        )


# --- 3. El bump se calcula, no se recuerda ---------------------------------


class TestElBumpSeCalcula:
    def test_el_script_de_derivacion_existe(self) -> None:
        """Derivar a mano durante 47 releases es una fuente de error esperando.

        `test_release_governance` ata la etiqueta a `__version__`. Eso es una
        mitad: comprueba que el numero sea coherente consigo mismo, no que
        sea el que corresponde al historial. Esta es la otra mitad.
        """
        assert SCRIPT.exists(), "no hay forma mecanica de derivar el bump; se esta haciendo a mano"

    def test_el_script_esta_versionado_y_no_es_una_tarea(self) -> None:
        salida = subprocess.run(
            ("git", "ls-files", "--error-unmatch", str(SCRIPT.relative_to(ROOT))),
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        assert salida.returncode == 0, (
            "scripts/derive_semver.py no esta versionado: un script sin version "
            "no es un script, es una costumbre"
        )

    def test_el_script_deriva_la_era_coherente(self) -> None:
        """Desde `v0.16.3` la regla se cumple en cuanto al **tipo** de bump.

        Este es el único rango donde el guard puede exigir coincidencia sin
        reescribir historia: antes de la baseline el proyecto operaba con
        otra política, y exigir la de hoy sería tan falso como el defecto
        que se corrige.

        Se exige que no haya **divergencias de tipo**: un tag cuya etiqueta
        contradiga el bump que dicta la regla. Los dos tags de la era que la
        regla dice que no deberían existir (`v0.16.5`, `v0.16.8`) se permiten
        aquí y se registran mas abajo, porque son otra cosa: no contradicen
        la regla, la incumplen por existir.
        """
        tags_ = _tags()
        desde = tuple(int(p) for p in SEMVER.match(BASELINE).group(1, 2, 3))
        en_era = [t for t in tags_ if _version(t) >= desde]
        assert len(en_era) >= 10, f"la baseline deja solo {len(en_era)} tags; revisa BASELINE"

        malas = [t for t in en_era if t in _divergencias_de_tipo(tags_)]
        assert not malas, f"desde {BASELINE} el bump no se deduce del historial: {malas}"


# --- 4. Las divergencias historicas son hechos, no olvido ------------------


class TestLasDivergenciasEstanRegistradas:
    """No se corrigen. Se dejan escritas, y se vigila que no cambien.

    Cambiar el número de una etiqueta publicada es reescribir provenance, y
    este proyecto lleva cinco bloques sin hacerlo. Lo que se puede —y se
    hace— es que la lista sea un hecho medido y testeado, para que nadie la
    descubra de nuevo ni la tome por un olvido.

    El test es **bidireccional**: ni una divergencia nueva, ni una vieja que
    se «arregle» sin que alguien quite su nombre de la lista. Un guard que
    solo comprueba que las viejas siguen ahí permite que se añada una
    séptima sin darse cuenta.
    """

    # MEDIDO el 2026-10-02 con `scripts/derive_semver.py` sobre 47 etiquetas.
    DIVERGENCIA_ESPERADA: Final = frozenset(
        {
            # La regla pide MINOR y se publico un PATCH (feat dentro de un patch).
            "v0.3.0",
            "v0.7.1",
            "v0.7.2",
            "v0.7.3",
            "v0.14.1",
            "v0.14.7",
            # La regla no pide release alguna y se etiqueto de todos modos.
            "v0.8.1",
            "v0.14.2",
            "v0.14.3",
            "v0.14.4",
            "v0.14.5",
            "v0.14.6",
            "v0.14.8",
            "v0.16.5",
            "v0.16.8",
        }
    )

    def test_el_conjunto_de_divergencias_no_cambia(self) -> None:
        tags_ = _tags()
        reales = frozenset(_divergencias_de_tipo(tags_) | _etiquetas_sin_release(tags_))

        nuevas = sorted(reales - self.DIVERGENCIA_ESPERADA)
        assert not nuevas, (
            f"divergencias de SemVer NO registradas: {nuevas}. Anyadelas a "
            "DIVERGENCIA_ESPERADA con su motivo, o corrige el bump"
        )

        resueltas = sorted(self.DIVERGENCIA_ESPERADA - reales)
        assert not resueltas, (
            f"estas divergencias ya NO existen: {resueltas}. Quitalas de "
            "DIVERGENCIA_ESPERADA, o explica como se resolvieron sin "
            "reescribir una etiqueta publicada"
        )
