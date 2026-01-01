"""Constants for the Compleo Wallbox integration."""

DOMAIN = "compleo_wallbox"
DEFAULT_SCAN_INTERVAL = 30
DEFAULT_PORT = 502
DEFAULT_NAME = "Compleo Wallbox"

# --- REGISTER KONFIGURATION ---
REG_SYS_POWER_LIMIT = 0x0000
REG_SYS_MAX_SCHIEFLAST = 0x0002
REG_SYS_FALLBACK_POWER = 0x0003
REG_SYS_FW_PATCH = 0x0006
REG_SYS_FW_MAJOR = 0x0007
REG_SYS_NUM_POINTS = 0x0008

REG_SYS_TOTAL_POWER_READ = 0x0009
REG_SYS_TOTAL_CURRENT_L1 = 0x000A
REG_SYS_TOTAL_CURRENT_L2 = 0x000B
REG_SYS_TOTAL_CURRENT_L3 = 0x000C
REG_SYS_UNUSED_POWER = 0x000D
REG_SYS_ARTICLE_NUM = 0x0020
REG_SYS_SERIAL_NUM = 0x0030
LEN_STRING_REGISTERS = 16 

ADDR_LP1_BASE = 0x0100
ADDR_LP2_BASE = 0x0200

OFFSET_MAX_POWER = 0x0000
OFFSET_STATUS_WORD = 0x001
OFFSET_POWER = 0x002
OFFSET_CURRENT_L1 = 0x003
OFFSET_CURRENT_L2 = 0x004
OFFSET_CURRENT_L3 = 0x005
OFFSET_CHARGING_TIME = 0x006
OFFSET_ENERGY = 0x008
OFFSET_PHASE_MODE = 0x009
OFFSET_PHASE_SWITCHES = 0x00A
OFFSET_ERROR_CODE = 0x00B
OFFSET_STATUS_CODE = 0x00C
OFFSET_VOLTAGE_L1 = 0x00D
OFFSET_VOLTAGE_L2 = 0x00E
OFFSET_VOLTAGE_L3 = 0x00F
OFFSET_RFID_TAG = 0x010
OFFSET_METER_READING = 0x018
OFFSET_DERATING_STATUS = 0x01A

# --- STATUS MAPPINGS (Keys for Translation) ---
# Values converted to snake_case for translation keys
CHARGE_POINT_ERROR_CODES = {
    0: "no_error",
    1: "connector_lock_failure",
    2: "ev_communication_error",
    3: "ground_failure",
    4: "high_temperature",
    5: "internal_error",
    6: "local_list_conflict",
    7: "no_error",
    8: "other_error",
    9: "over_current_failure",
    10: "power_meter_failure",
    11: "power_switch_failure",
    12: "reader_failure",
    13: "reset_failure",
    14: "under_voltage",
    15: "over_voltage",
    16: "weak_signal"
}

DERATING_STATUS_MAP = {
    0: "no_derating",
    1: "derating_stage_1",
    2: "derating_stage_2",
    3: "charging_stopped_overtemp",
    4: "sensor_error"
}

# --- SMART CHARGING LOGIC CONSTANTS ---
# Keys for Translation (not display strings anymore)
MODE_FAST = "fast"
MODE_LIMITED = "limited"
MODE_SOLAR = "solar"
CHARGING_MODES = [MODE_FAST, MODE_LIMITED, MODE_SOLAR]

# Defaults
DEFAULT_FAST_POWER = 11000
DEFAULT_LIMITED_POWER = 3600
DEFAULT_SOLAR_BUFFER = 500
DEFAULT_ZOE_MIN_CURRENT = 8

# Timers (Minutes)
TIME_HOLD_RISING = 20
TIME_HOLD_FALLING = 15

# Thresholds
THRESHOLD_DROP_PERCENT = 10