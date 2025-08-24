import logging
from typing import Any, List, Optional

from homeassistant.components.climate import HVACMode
from homeassistant.components.climate.const import ClimateEntityFeature
from gehomesdk import ErdAcOperationMode, ErdCode

from ...devices import ApplianceApi
from ..common import GeClimate, OptionsConverter
from .fan_mode_options import (
    AcFanModeOptionsConverter,
    AcFanOnlyFanModeOptionsConverter,
)

_LOGGER = logging.getLogger(__name__)

ECO_PRESET = "eco"


class WacHvacModeOptionsConverter(OptionsConverter):
    """
    Expose only real HVAC modes here. Do NOT map ENERGY_SAVER to HVACMode.AUTO.
    Energy Saver will be handled as a preset (eco) on the entity.
    """
    @property
    def options(self) -> List[str]:
        # Only advertise modes the device truly supports as hvac_mode
        return [HVACMode.COOL, HVACMode.FAN_ONLY, HVACMode.DRY]

    def from_option_string(self, value: str) -> Any:
        try:
            return {
                HVACMode.COOL: ErdAcOperationMode.COOL,
                HVACMode.FAN_ONLY: ErdAcOperationMode.FAN_ONLY,
                HVACMode.DRY: ErdAcOperationMode.DRY,
                # If your device really supports AUTO temperature control (not Energy Saver),
                # you can add: HVACMode.AUTO: ErdAcOperationMode.AUTO
            }.get(value, ErdAcOperationMode.COOL)
        except Exception:  # noqa: BLE001
            _LOGGER.warning("Could not set HVAC mode to %s", value)
            return ErdAcOperationMode.COOL

    def to_option_string(self, value: Any) -> Optional[str]:
        try:
            return {
                ErdAcOperationMode.COOL: HVACMode.COOL,
                ErdAcOperationMode.FAN_ONLY: HVACMode.FAN_ONLY,
                ErdAcOperationMode.DRY: HVACMode.DRY,
                # ErdAcOperationMode.AUTO: HVACMode.AUTO,
            }.get(value, HVACMode.COOL)
        except Exception:  # noqa: BLE001
            _LOGGER.warning("Could not determine operation mode mapping for %s", value)
            return HVACMode.COOL


class GeWacClimate(GeClimate):
    """Window/Room AC climate with Energy Saver exposed as a preset."""

    def __init__(self, api: ApplianceApi):
        super().__init__(
            api,
            WacHvacModeOptionsConverter(),
            AcFanModeOptionsConverter(),
            AcFanOnlyFanModeOptionsConverter(),
        )
        # Advertise preset support in addition to whatever the base already set
        self._attr_supported_features = (
            getattr(self, "_attr_supported_features", 0) | ClimateEntityFeature.PRESET_MODE
        )

        # Local cache of last-known op mode (optional but keeps property reads cheap)
        self._last_op_mode: Optional[ErdAcOperationMode] = None

    # -------- Preset API (eco ⇄ ENERGY_SAVER) --------
    @property
    def preset_modes(self) -> List[str]:
        # If ENERGY_SAVER is conditionally available on some models,
        # you could gate this list on a capability flag from the API.
        return [ECO_PRESET]

    @property
    def preset_mode(self) -> Optional[str]:
        op = self._current_operation_mode
        return ECO_PRESET if op == ErdAcOperationMode.ENERGY_SAVER else "none"

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        if preset_mode == ECO_PRESET:
            await self._set_operation_mode(ErdAcOperationMode.ENERGY_SAVER)
        elif preset_mode in (None, "none"):
            # Choose a sensible non-eco default (Cool is typical)
            await self._set_operation_mode(ErdAcOperationMode.COOL)
        else:
            raise ValueError(f"Unsupported preset_mode: {preset_mode}")

    # -------- Helpers to read/set the device op mode --------
    @property
    def _current_operation_mode(self) -> Optional[ErdAcOperationMode]:
        try:
            op = self._api.get_erd_value(ErdCode.AC_OPERATION_MODE)
            if op is not None:
                self._last_op_mode = op
            return op or self._last_op_mode
        except Exception as ex:  # noqa: BLE001
            _LOGGER.debug("Failed to read AC_OPERATION_MODE: %s", ex)
            return self._last_op_mode

    async def _set_operation_mode(self, mode: ErdAcOperationMode) -> None:
        try:
            await self._api.async_set_erd_value(ErdCode.AC_OPERATION_MODE, mode)
            self._last_op_mode = mode
        except Exception as ex:  # noqa: BLE001
            _LOGGER.warning("Failed to set AC_OPERATION_MODE to %s: %s", mode, ex)

    # -------- Optional: keep caches fresh when the device pushes updates --------
    async def async_update_state(self) -> None:
        """Called by the base when ERD values change; keep a local op-mode cache."""
        try:
            op = self._api.get_erd_value(ErdCode.AC_OPERATION_MODE)
            if op is not None:
                self._last_op_mode = op
        except Exception:
            pass
        await super().async_update_state()
