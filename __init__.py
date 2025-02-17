"""The TISControl integration."""
#test14

from __future__ import annotations

import logging
import os
from typing import TypeAlias
from attr import dataclass
from TISControlProtocol.api import TISApi, GetKeyEndpoint, ScanDevicesEndPoint, TISEndPoint
from TISControlProtocol.Protocols.udp.ProtocolHandler import TISProtocolHandler

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import DEVICES_DICT, DOMAIN


@dataclass
class TISData:
    """TISControl data stored in the ConfigEntry."""

    api: TISApi

PLATFORMS: list[Platform] = [Platform.LIGHT, Platform.SENSOR, Platform.BINARY_SENSOR, Platform.SWITCH, Platform.COVER, Platform.CLIMATE, Platform.SELECT, Platform.LOCK, Platform.FAN]
TISConfigEntry: TypeAlias = ConfigEntry[TISData]
protocol_handler = TISProtocolHandler()

async def async_setup_entry(hass: HomeAssistant, entry: TISConfigEntry) -> bool:
    """Set up TISControl from a config entry."""
    try:
        current_directory = os.getcwd()
        os.chdir('/config/custom_components/tis_integration')
        reset = os.system('git reset --hard HEAD')
        pull = os.system('git pull')
        os.chdir(current_directory)
        if pull == 0 and reset == 0: 
            logging.warning(f"Updated TIS Integrations")
        else:
            logging.warning(f"Could Not Update TIS Integration: exit error {pull}")

    except Exception as e:
        logging.error(f"Could Not Update TIS Integration: {e}")
        
    tis_api = TISApi(
        port=int(entry.data["port"]),
        hass=hass,
        domain=DOMAIN,
        devices_dict=DEVICES_DICT,
        display_logo="./custom_components/tis_integration/images/logo.png",
    )
    entry.runtime_data = TISData(api=tis_api)

    hass.data.setdefault(DOMAIN, {"supported_platforms": PLATFORMS})
    try:
        await tis_api.connect()
        hass.http.register_view(TISEndPoint(tis_api))
        hass.http.register_view(ScanDevicesEndPoint(tis_api))
        hass.http.register_view(GetKeyEndpoint(tis_api))
        hass.async_add_executor_job(tis_api.run_display)
    except ConnectionError as e:
        logging.error("error connecting to TIS api %s", e)
        return False
    # add the tis api to the hass data
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: TISConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        return unload_ok

    return False