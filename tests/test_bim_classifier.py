from pathlib import Path

import pytest
from src.ifc_processor.bim_classifier import classify_from_fields, classify_ifc, ClassifiedElement

SAMPLE = Path(__file__).parent.parent / "samples" / "m_f_veg_12200_Veg.ifc"


@pytest.mark.slow
def test_classify_ifc_against_sample():
    if not SAMPLE.exists():
        pytest.skip("12200 IFC-sample mangler")
    result = classify_ifc(SAMPLE)

    # Returnerer dict keyet på GlobalId med ClassifiedElement-verdier
    assert isinstance(result, dict)
    assert all(isinstance(v, ClassifiedElement) for v in result.values())

    kats = [ce.kategori for ce in result.values()]
    grupper = {ce.fag_gruppe for ce in result.values()}

    # Alle 92 grøfter (IfcDistributionChamberElement) skal være Grøft/Drenering
    grofter = [ce for ce in result.values() if ce.ifc_klasse == "IfcDistributionChamberElement"]
    assert len(grofter) == 92
    assert all(ce.kategori == "Grøft" and ce.fag_gruppe == "Drenering" for ce in grofter)

    # Forventede fag-grupper er representert
    assert {"Vegoverbygning", "Vegbane", "Underbygning", "Terreng", "Drenering"} <= grupper

    # Annotasjoner/struktur er utelatt
    assert not any(ce.ifc_klasse in {"IfcAnnotation", "IfcRoadPart", "IfcRoad", "IfcSite"}
                   for ce in result.values())

    # Ingenting med solid geometri skal ende som Uklassifisert
    assert kats.count("Uklassifisert") == 0


@pytest.mark.parametrize("ifc_klasse,pt,ot,name,expected", [
    ("IfcKerb", None, None, "12200 | 3.07 | H.Tillegg 7", ("Kantstein", "Vegbane")),
    ("IfcDistributionChamberElement", "TRENCH", None, "12200 | 4.01 | H. Grøft 1", ("Grøft", "Drenering")),
    ("IfcCourse", "USERDEFINED", "TRAFFICLANE_SURFACE", "12200 | 1.01 | H. Kjørefelt 1", ("Kjørefelt", "Vegbane")),
    ("IfcCourse", "USERDEFINED", "ROADSHOULDER_SURFACE", "12200 | 2.01 | H. Skulder 1", ("Skulder", "Vegbane")),
    ("IfcCourse", "USERDEFINED", None, "12200 | Slitelag", ("Slitelag", "Vegoverbygning")),
    ("IfcCourse", "USERDEFINED", None, "12200 | Bindlag 1", ("Bindlag", "Vegoverbygning")),
    ("IfcCourse", "USERDEFINED", None, "12200 | Bærelag 2", ("Bærelag", "Vegoverbygning")),
    ("IfcCourse", "USERDEFINED", None, "12200 | -1.02 | V. breddeutvidelse", ("Kjørefelt", "Vegbane")),
    ("IfcPavement", "RIGID", None, "12200|RIGID", ("Slitelag", "Vegoverbygning")),
    ("IfcEarthworksFill", "USERDEFINED", None, "12200 | Forsterkningslag 1", ("Forsterkningslag", "Vegoverbygning")),
    ("IfcEarthworksFill", "USERDEFINED", None, "12200 | Filterlag", ("Filterlag", "Vegoverbygning")),
    ("IfcEarthworksFill", "USERDEFINED", "ROUNDING", "12200 | Avrunding | Solid", ("Avrunding", "Terreng")),
    ("IfcEarthworksFill", "SLOPEFILL", None, "12200 | 7.11 | H. Fylling 11", ("Fylling", "Terreng")),
    ("IfcEarthworksFill", "USERDEFINED", None, "12200 | -6.11 | V. Jordskj. 11", ("Skjæring", "Terreng")),
    ("IfcEarthworksFill", "USERDEFINED", None, "12200 | -5.11 | V. Fjellskj. 11", ("Skjæring", "Terreng")),
    ("IfcEarthworksCut", "USERDEFINED", None, "12200 | Constructionbed | InCutRock", ("Skjæring", "Terreng")),
    ("IfcEarthworksCut", "OVEREXCAVATION", None, "12200 | Dypsprenging | Solid", ("Skjæring", "Terreng")),
    ("IfcEarthworksFill", "EMBANKMENT", None, "12200 | Fyllingslag | Solid", ("Forsterket grunn", "Underbygning")),
    ("IfcReinforcedSoil", "REPLACED", None, "12200 | Fyllingslag | Solid", ("Forsterket grunn", "Underbygning")),
    ("IfcEarthworksFill", "SUBGRADEBED", None, "12200 | Constructionbed | OnTerrainSurfaceSoil", ("Planum", "Underbygning")),
    ("IfcEarthworksFill", "USERDEFINED", None, "12200 | SubgradeSurface Inside Pavement", ("Planum", "Underbygning")),
    ("IfcFooBar", None, None, "noe ukjent", ("Uklassifisert", "Annet")),
])
def test_classify_from_fields(ifc_klasse, pt, ot, name, expected):
    assert classify_from_fields(ifc_klasse, pt, ot, name) == expected
