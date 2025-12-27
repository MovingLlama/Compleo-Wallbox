"""Constants for the Compleo Wallbox integration."""
from logging import getLogger

LOGGER = getLogger(__package__)

DOMAIN = "compleo_wallbox"
DEFAULT_NAME = "Compleo Wallbox"
DEFAULT_SCAN_INTERVAL = 30
DEFAULT_PORT = 502

# Configuration Keys
CONF_HOST = "host"
CONF_PORT = "port"
CONF_SCAN_INTERVAL = "scan_interval"

# Modbus Registers (Based on provided PDF)
# Global
REG_POWER_ABS_SETPOINT = 0x0000  # RW, 100W steps
REG_POWER_PERCENT_SETPOINT = 0x0001 # RW, %
REG_MAX_UNBALANCED = 0x0002 # RW, 0.1A
REG_FW_PATCH = 0x0006 # RO
REG_FW_MAJOR_MINOR = 0x0007 # RO
REG_NUM_POINTS = 0x0008 # RO
REG_SERIAL = 0x0020 # RO, String 16 regs
REG_ARTICLE = 0x0030 # RO, String 16 regs

# Charge Point 0 Base Address = 0x0100
# The PDF says offset is added to base.
BASE_CP = 0x0100

REG_CP_MAX_POWER = BASE_CP + 0x00 # RW, 100W steps
REG_CP_STATUS_WORD = BASE_CP + 0x01 # RO, Bitmask
REG_CP_ACTIVE_POWER = BASE_CP + 0x02 # RO, 100W steps
REG_CP_CURRENT_L1 = BASE_CP + 0x03 # RO, 0.1A
REG_CP_CURRENT_L2 = BASE_CP + 0x04 # RO, 0.1A
REG_CP_CURRENT_L3 = BASE_CP + 0x05 # RO, 0.1A
REG_CP_TIME = BASE_CP + 0x06 # RO, Seconds (2 regs)
REG_CP_ENERGY = BASE_CP + 0x08 # RO, 100Wh steps
REG_CP_SINK_MODE = BASE_CP + 0x09 # RW, 0=Unavail, 1=Auto, 2=1ph, 3=3ph
REG_CP_ERROR_CODE = BASE_CP + 0x0B # RO
REG_CP_STATUS_CODE = BASE_CP + 0x0C # RO (OCPP Status)
REG_CP_VOLT_L1 = BASE_CP + 0x0D # RO, V
REG_CP_VOLT_L2 = BASE_CP + 0x0E # RO, V
REG_CP_VOLT_L3 = BASE_CP + 0x0F # RO, V
REG_CP_TEMP_DERATING = BASE_CP + 0x1A # RO, Enum

# Mappings
STATUS_CODE_MAP = {
    0: "Available",
    1: "Preparing",
    2: "Charging",
    3: "Suspended EVSE",
    4: "Suspended EV",
    5: "Finishing",
    6: "Reserved",
    7: "Unavailable",
    8: "Faulted",
}

ERROR_CODE_MAP = {
    0: "No Error",
    1: "ConnectorLockFailure",
    2: "EVCommunicationError",
    3: "Ground Failure",
    4: "High Temperature",
    5: "InternalError",
    9: "OverCurrentFailure",
    10: "OverVoltage",
    15: "Under Voltage",
}

SINK_MODE_MAP = {
    0: "Unavailable",
    1: "Automatic",
    2: "1-Phase",
    3: "3-Phase",
}
SINK_MODE_REVERSE = {v: k for k, v in SINK_MODE_MAP.items()}