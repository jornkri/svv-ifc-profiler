"""Smoke-tester: sjekk at modulene kan importeres og at API-en svarer."""


def test_imports():
    from src.ifc_processor import (
        Centerline,
        CrossSection,
        Station,
        TINLayer,
        generate_cross_sections,
        load_centerline,
        read_ifc_tins,
        run_pipeline,
        sample_stations,
    )
    assert callable(load_centerline)
    assert callable(read_ifc_tins)
    assert callable(run_pipeline)
    assert callable(sample_stations)
