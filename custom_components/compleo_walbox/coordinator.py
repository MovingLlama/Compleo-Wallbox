"""DataUpdateCoordinator for Compleo Solo."""
from datetime import timedelta
import logging
from pymodbus.client import AsyncModbusTcpClient
from pymodbus.payload import BinaryPayloadDecoder
from pymodbus.constants import Endian

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    DOMAIN, LOGGER,
    REG_SERIAL, REG_ARTICLE, REG_FW_MAJOR_MINOR, REG_FW_PATCH,
    REG_POWER_ABS_SETPOINT, REG_CP_STATUS_WORD, REG_CP_ACTIVE_POWER,
    REG_CP_CURRENT_L1, REG_CP_CURRENT_L2, REG_CP_CURRENT_L3,
    REG_CP_ENERGY, REG_CP_SINK_MODE, REG_CP_STATUS_CODE, REG_CP_ERROR_CODE,
    REG_CP_VOLT_L1, REG_CP_VOLT_L2, REG_CP_VOLT_L3, REG_CP_TEMP_DERATING
)

class CompleoCoordinator(DataUpdateCoordinator):
    """Class to manage fetching data from the Compleo Wallbox."""

    def __init__(self, hass: HomeAssistant, host: str, port: int, scan_interval: int):
        """Initialize."""
        self.client = AsyncModbusTcpClient(host, port=port)
        self.host = host
        super().__init__(
            hass,
            LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=scan_interval),
        )

    def close(self):
        """Close modbus client."""
        self.client.close()

    async def _async_update_data(self):
        """Fetch data from Modbus."""
        if not self.client.connected:
            await self.client.connect()

        data = {}
        try:
            # --- Read Block 1: Global Info (Serial, Article) ---
            # Reading 32 registers starting at 0x0020 (Serial + Article)
            rr = await self.client.read_input_registers(REG_SERIAL, 32, slave=1)
            if not rr.isError():
                decoder = BinaryPayloadDecoder.fromRegisters(rr.registers, byteorder=Endian.Big, wordorder=Endian.Big)
                # Serial (String32 = 16 regs)
                data["serial"] = decoder.decode_string(32).decode("ascii").strip('\x00')
                # Article (String32 = 16 regs)
                data["article"] = decoder.decode_string(32).decode("ascii").strip('\x00')

            # --- Read Block 2: Global Settings ---
            # Read Power Setpoint (Holding 0x0000)
            rr = await self.client.read_holding_registers(REG_POWER_ABS_SETPOINT, 1, slave=1)
            if not rr.isError():
                # 100W steps
                data["power_setpoint"] = rr.registers[0] * 100

            # --- Read Block 3: Charge Point Data ---
            # Reading a chunk from 0x0100 to 0x011A is large, let's split or read relevant parts.
            # To be safe and fast, we read specific registers or small blocks.
            
            # Read 0x0100 - 0x010F (16 regs) covers most dynamic data
            rr = await self.client.read_input_registers(0x0100, 16, slave=1) # Note: Some are input, some are holding?
            # PDF says "Alle Holding-Register sind lesbar... Input-Register nur lesbar".
            # The charge point block 0x0100 mixed holding and input in PDF logic?
            # Actually PDF lists 0x0000 global as Holding.
            # 0x0100 (Max Power) is Holding. 0x0101 (Status) is Input.
            # Mixing read commands for contiguous block of different types usually fails in Modbus.
            # We must read Holding and Input separately.

            # 1. Charge Point Holding Registers
            # 0x0100 (Max Power), 0x0109 (Sink Mode)
            rr_h = await self.client.read_holding_registers(0x0100, 10, slave=1) 
            if not rr_h.isError():
                 data["cp_max_power"] = rr_h.registers[0] * 100 # 0x0100
                 data["cp_sink_mode"] = rr_h.registers[9] # 0x0109

            # 2. Charge Point Input Registers
            # Start 0x0101 (Status) to 0x010F (Volt L3) = 15 registers
            rr_i = await self.client.read_input_registers(0x0101, 15, slave=1)
            if not rr_i.isError():
                regs = rr_i.registers
                # offsets relative to 0x0101:
                # 0x0101 -> index 0
                data["status_word"] = regs[0]
                data["current_power"] = regs[1] * 100 # 100W steps
                data["current_l1"] = regs[2] / 10.0 # 0.1A steps
                data["current_l2"] = regs[3] / 10.0
                data["current_l3"] = regs[4] / 10.0
                # 0x0106/7 is Time (2 regs) -> index 5, 6
                data["energy"] = regs[7] / 10.0 # 0x0108, 100Wh steps -> 0.1 kWh
                # 0x0109 is holding, skipped in Input map or read as 0? Skip index 8
                data["error_code"] = regs[10] # 0x010B
                data["status_code"] = regs[11] # 0x010C
                data["volt_l1"] = regs[12] # 0x010D
                data["volt_l2"] = regs[13] # 0x010E
                data["volt_l3"] = regs[14] # 0x010F

            # 3. Temp Derating (0x011A Input)
            rr_t = await self.client.read_input_registers(REG_CP_TEMP_DERATING, 1, slave=1)
            if not rr_t.isError():
                data["temp_derating"] = rr_t.registers[0]

        except Exception as e:
            LOGGER.error("Error reading Modbus data: %s", e)
            raise UpdateFailed(e)

        return data

    async def async_write_register(self, address, value):
        """Write a holding register."""
        if not self.client.connected:
            await self.client.connect()
        try:
            await self.client.write_register(address, value, slave=1)
            await self._async_update_data() # Force refresh
        except Exception as e:
            LOGGER.error("Error writing register %s: %s", address, e)