from __future__ import annotations

from dataclasses import dataclass

# IFC-produkter uten solid geometri — utelates fra både 3D- og plan-laget.
SKIP_CLASSES = {"IfcAnnotation", "IfcRoadPart", "IfcRoad", "IfcSite", "IfcGeomodel"}


@dataclass
class ClassifiedElement:
    global_id: str
    ifc_klasse: str
    navn: str
    kategori: str
    fag_gruppe: str


def classify_from_fields(ifc_klasse: str, predefined_type: str | None,
                         object_type: str | None, name: str | None) -> tuple[str, str]:
    """Returner (kategori, fag_gruppe) fra IFC-klasse + type-koder + navn.

    Baseres primært på PredefinedType/ObjectType (rene ASCII-koder). Navn-feltet
    har encoding-artefakter (æ/ø/å som mojibake), så nøkkelordmatch bruker
    ASCII-trygge delstrenger (f.eks. "relag" for Bærelag).
    """
    k = ifc_klasse or ""
    pt = (predefined_type or "").upper()
    ot = (object_type or "").upper()
    n = (name or "").lower()

    if k == "IfcKerb":
        return ("Kantstein", "Vegbane")
    if k == "IfcDistributionChamberElement" or pt == "TRENCH":
        return ("Grøft", "Drenering")
    if k == "IfcCourse":
        if ot == "TRAFFICLANE_SURFACE" or "breddeutvidelse" in n:
            return ("Kjørefelt", "Vegbane")
        if ot == "ROADSHOULDER_SURFACE":
            return ("Skulder", "Vegbane")
        if "slitelag" in n:
            return ("Slitelag", "Vegoverbygning")
        if "bindlag" in n:
            return ("Bindlag", "Vegoverbygning")
        if "relag" in n:  # Bærelag (æ kan være mojibake)
            return ("Bærelag", "Vegoverbygning")
        return ("Kjørefelt", "Vegbane")
    if k == "IfcPavement":
        return ("Slitelag", "Vegoverbygning")
    if k == "IfcReinforcedSoil":
        return ("Forsterket grunn", "Underbygning")
    if k in ("IfcEarthworksFill", "IfcEarthworksCut"):
        if "forsterkningslag" in n:
            return ("Forsterkningslag", "Vegoverbygning")
        if "filterlag" in n:
            return ("Filterlag", "Vegoverbygning")
        if "avrunding" in n:
            return ("Avrunding", "Terreng")
        if any(t in n for t in ("jordskj", "fjellskj", "incutsoil", "incutrock",
                                 "rockcutface", "dypsprenging")):
            return ("Skjæring", "Terreng")
        if "fyllingslag" in n:  # MÅ sjekkes før "fylling" (delstreng-kollisjon)
            return ("Forsterket grunn", "Underbygning")
        if pt in ("SLOPEFILL", "EMBANKMENT") or "fylling" in n:
            return ("Fylling", "Terreng")
        return ("Planum", "Underbygning")  # constructionbed / subgrade / øvrig
    return ("Uklassifisert", "Annet")
