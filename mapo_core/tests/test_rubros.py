"""Consistencia de la tabla curada de rubros (mapo_core/rubros/)."""

from mapo_core import rubros


def test_cada_clase_apunta_a_sector_y_rubro_que_existen():
    sectores, tabla_rubros = rubros.sectores(), rubros.rubros()
    for nombre, clase in rubros.clases().items():
        assert clase.sector in sectores, nombre
        if clase.rubro is not None:
            assert tabla_rubros[clase.rubro].sector == clase.sector, nombre


def test_sectores_no_buscables_no_tienen_rubros():
    no_buscables = {s for s, f in rubros.sectores().items() if f["buscable"] == "no"}
    assert no_buscables == {"industria", "mayoreo", "agro_mineria_y_energia"}
    for nombre, clase in rubros.clases().items():
        assert (clase.rubro is None) == (clase.sector in no_buscables), nombre


def test_todo_rubro_tiene_al_menos_una_clase():
    usados = {c.rubro for c in rubros.clases().values()}
    assert set(rubros.rubros()) <= usados


def test_ningun_termino_lleva_a_dos_rubros():
    """El analizador del buscador resuelve un término a un solo rubro o sector;
    si dos comparten nombre o sinónimo, la pregunta sería ambigua sin avisar."""
    vistos: dict[str, str] = {}
    for clave, rubro in rubros.rubros().items():
        for termino in (rubro.nombre, *rubro.sinonimos, *rubro.marcas):
            t = rubros.normalizar(termino)
            assert vistos.setdefault(t, clave) == clave, f"'{termino}' en {vistos[t]} y {clave}"
    for clave, fila in rubros.sectores().items():
        for termino in filter(None, fila["sinonimos"].split("|")):
            t = rubros.normalizar(termino)
            assert vistos.setdefault(t, clave) == clave, f"'{termino}' en {vistos[t]} y {clave}"


def test_clases_de_rubro_sector_y_solo_publicos():
    assert rubros.clases_de(rubro="floreria") == ["Comercio al por menor de plantas y flores naturales"]
    salud = rubros.clases_de(sector="salud")
    hospitales = rubros.clases_de(rubro="hospital", solo_publicos=True)
    assert "Hospitales generales del sector público" in hospitales
    assert all("sector privado" not in c for c in hospitales)
    assert set(hospitales) < set(salud)
    assert rubros.clases_de(rubro="floreria", solo_publicos=True) == []


def test_casos_de_rubros_md():
    """Los casos de ejemplo de docs/producto/rubros.md tienen su rubro."""
    clases = rubros.clases()
    assert clases["Comercio al por menor de plantas y flores naturales"].rubro == "floreria"
    assert clases["Servicios de recepción de llamadas telefónicas y promoción por teléfono"].rubro == "call_center"
    assert clases["Comercio al por menor en supermercados"].rubro == "supermercado"
    assert clases["Consultorios de medicina general del sector público"].rubro == "consultorio_medico"
    assert clases["Hospitales generales del sector público"].rubro == "hospital"
    assert clases["Mantenimiento de la seguridad y el orden público"].rubro == "seguridad_publica"


def test_sector_publico_sale_del_nombre():
    clases = rubros.clases()
    assert clases["Escuelas de educación primaria del sector público"].sector_publico
    assert not clases["Escuelas de educación primaria del sector privado"].sector_publico


def test_sin_clasificar():
    assert rubros.sin_clasificar({"Farmacias sin minisúper", "Clase inventada"}) == ["Clase inventada"]
