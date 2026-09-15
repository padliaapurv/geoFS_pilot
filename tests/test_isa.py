import numpy as np
from src.atmosphere.isa import isa_atmosphere, SEA_LEVEL_DENSITY_KG_M3


def test_sea_level_matches_standard_constants():
    atm = isa_atmosphere(0.0)
    assert np.isclose(atm.density_kg_m3, SEA_LEVEL_DENSITY_KG_M3, atol=1e-3)


def test_density_decreases_with_altitude():
    atm_low = isa_atmosphere(1000.0)
    atm_high = isa_atmosphere(10668.0)
    assert atm_high.density_kg_m3 < atm_low.density_kg_m3


def test_stratosphere_isothermal():
    atm_11km = isa_atmosphere(11000.0)
    atm_15km = isa_atmosphere(15000.0)
    assert np.isclose(atm_11km.temperature_k, atm_15km.temperature_k, atol=1e-6)
