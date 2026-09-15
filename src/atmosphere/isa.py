# International Standard Atmosphere (1976), troposphere + lower stratosphere.
# Independent of everything else: pure function of altitude.

from dataclasses import dataclass
import numpy as np

SEA_LEVEL_DENSITY_KG_M3 = 1.225
SEA_LEVEL_PRESSURE_PA = 101325.0
SEA_LEVEL_TEMPERATURE_K = 288.15
LAPSE_RATE_K_PER_M = 0.0065
GAS_CONSTANT_AIR_J_PER_KG_K = 287.05287
GRAVITY_M_S2 = 9.80665
TROPOPAUSE_ALTITUDE_M = 11000.0
TROPOPAUSE_TEMPERATURE_K = 216.65
RATIO_OF_SPECIFIC_HEATS = 1.4


@dataclass(frozen=True)
class AtmosphereState:
    altitude_m: float
    temperature_k: float
    pressure_pa: float
    density_kg_m3: float
    speed_of_sound_m_s: float


def isa_atmosphere(altitude_m: float) -> AtmosphereState:
    if altitude_m <= TROPOPAUSE_ALTITUDE_M:
        temperature_k = SEA_LEVEL_TEMPERATURE_K - LAPSE_RATE_K_PER_M * altitude_m
        pressure_pa = SEA_LEVEL_PRESSURE_PA * (temperature_k / SEA_LEVEL_TEMPERATURE_K) ** (
            GRAVITY_M_S2 / (LAPSE_RATE_K_PER_M * GAS_CONSTANT_AIR_J_PER_KG_K)
        )
    else:
        temperature_k = TROPOPAUSE_TEMPERATURE_K
        pressure_at_tropopause = SEA_LEVEL_PRESSURE_PA * (
            TROPOPAUSE_TEMPERATURE_K / SEA_LEVEL_TEMPERATURE_K
        ) ** (GRAVITY_M_S2 / (LAPSE_RATE_K_PER_M * GAS_CONSTANT_AIR_J_PER_KG_K))
        pressure_pa = pressure_at_tropopause * np.exp(
            -GRAVITY_M_S2 * (altitude_m - TROPOPAUSE_ALTITUDE_M)
            / (GAS_CONSTANT_AIR_J_PER_KG_K * TROPOPAUSE_TEMPERATURE_K)
        )

    density_kg_m3 = pressure_pa / (GAS_CONSTANT_AIR_J_PER_KG_K * temperature_k)
    speed_of_sound_m_s = np.sqrt(RATIO_OF_SPECIFIC_HEATS * GAS_CONSTANT_AIR_J_PER_KG_K * temperature_k)

    return AtmosphereState(
        altitude_m=altitude_m,
        temperature_k=temperature_k,
        pressure_pa=pressure_pa,
        density_kg_m3=density_kg_m3,
        speed_of_sound_m_s=speed_of_sound_m_s,
    )
