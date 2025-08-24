import logging
from typing import Any, List, Optional

from homeassistant.components.climate import HVACMode
from gehomesdk import ErdAcOperationMode
from ...devices import ApplianceApi
from ..common import GeClimate, OptionsConverter
from .fan_mode_options import AcFanModeOptionsConverter, AcFanOnlyFanModeOptionsConverter

_LOGGER = logging.getLogger(__name__)

class WacHvacModeOptionsConverter(OptionsConverter):
    @property
    def options(self) -> List[str]:
        return [HVACMode.COOL, HVACMode.FAN_ONLY]  # add HVACMode.AUTO only if the device truly supports it
    def from_option_string(self, value: str) -> Any:
        return {
            HVACMode.COOL: ErdAcOperationMode.COOL,
            HVACMode.FAN_ONLY: ErdAcOperationMode.FAN_ONLY,
            # HVACMode.AUTO: ErdAcOperationMode.AUTO,  # only if real AUTO exists
        }.get(value, ErdAcOperationMode.COOL)
    def to_option_string(self, value: Any) -> Optional[str]:
        return {
            ErdAcOperationMode.COOL: HVACMode.COOL,
            ErdAcOperationMode.FAN_ONLY: HVACMode.FAN_ONLY,
            # ErdAcOperationMode.AUTO: HVACMode.AUTO,
        }.get(value, HVACMode.COOL)
  
from homeassistant.components.climate import ClimateEntity
from homeassistant.components.climate.const import ClimateEntityFeature

ECO_PRESET = "eco"

class GeWacClimate(GeClimate):
    """Window AC with Energy Saver preset"""
    def __init__(self, api: ApplianceApi):
        super().__init__(api, WacHvacModeOptionsConverter(),
                          AcFanModeOptionsConverter(), AcFanOnlyFanModeOptionsConverter())

        # Advertise preset support
        self._attr_supported_features = getattr(self, "_attr_supported_features", 0) | ClimateEntityFeature.PRESET_MODE
        self._eco_active = False  # internal state cache (optional)

    # --- Preset API ---
    @property
    def preset_modes(self) -> list[str]:
        # If Energy Saver is always available, return [ECO_PRESET]; otherwise gate by capability
        return [ECO_PRESET]

    @property
    def preset_mode(self) -> str | None:
        # Read current operation mode from the appliance and reflect eco on/off
        op = self._get_current_operation_mode_from_api()  # you likely already have this in GeClimate
        return ECO_PRESET if op == ErdAcOperationMode.ENERGY_SAVER else "none"

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        if preset_mode == ECO_PRESET:
            await self._api.async_set_operation_mode(ErdAcOperationMode.ENERGY_SAVER)
        elif preset_mode in ("none", None):
            # pick a sensible non-eco default, e.g., leave current hvac_mode in COOL
            await self._api.async_set_operation_mode(ErdAcOperationMode.COOL)
        else:
            raise ValueError(f"Unsupported preset_mode: {preset_mode}")
