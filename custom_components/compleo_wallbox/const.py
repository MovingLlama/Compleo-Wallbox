"""Constants for the Compleo Wallbox integration."""

DOMAIN = "compleo_wallbox"
DEFAULT_SCAN_INTERVAL = 30
DEFAULT_PORT = 502
DEFAULT_NAME = "Compleo Wallbox"

# --- REGISTER KONFIGURATION ---

# Global / System (HOLDING Register) - Schreibbar / Konfiguration
REG_SYS_POWER_LIMIT = 0x0000  # Leistungsvorgabe (100W)
REG_SYS_MAX_SCHIEFLAST = 0x0002 # Max. Schieflast (0.1A)
REG_SYS_FALLBACK_POWER = 0x0003 # Fallback Leistung (100W)

# Global / System (INPUT Register) - Info / Messwerte
REG_SYS_FW_PATCH = 0x0006
REG_SYS_FW_MAJOR = 0x0007

# Neue Input Register
REG_SYS_TOTAL_POWER_READ = 0x0009 # Aktuelle Leistung der ganzen Ladestation
REG_SYS_TOTAL_CURRENT_L1 = 0x000A # Gesamtstrom Phase 1
REG_SYS_TOTAL_CURRENT_L2 = 0x000B # Gesamtstrom Phase 2
REG_SYS_TOTAL_CURRENT_L3 = 0x000C # Gesamtstrom Phase 3
REG_SYS_UNUSED_POWER = 0x000D     # Nicht verwendete Leistung

# Strings (Länge 16 Register!)
REG_SYS_ARTICLE_NUM = 0x0020
REG_SYS_SERIAL_NUM = 0x0030
LEN_STRING_REGISTERS = 16 

# --- LADEPUNKTE BASIS-ADRESSEN ---
ADDR_LP1_BASE = 0x0100
ADDR_LP2_BASE = 0x0200

# --- LADEPUNKTE OFFSETS ---
# Holding Registers
OFFSET_MAX_POWER = 0x0000       # Max Leistung (Holding)

# Input Registers
OFFSET_STATUS_WORD = 0x001      # Status Word
OFFSET_POWER = 0x002            # Aktuelle Leistung
OFFSET_CURRENT_L1 = 0x003
OFFSET_CURRENT_L2 = 0x004
OFFSET_CURRENT_L3 = 0x005
OFFSET_CHARGING_TIME = 0x006    # Ist Ladezeit (neu)
OFFSET_ENERGY = 0x008

OFFSET_PHASE_MODE = 0x009       # Holding: Phase Mode

OFFSET_PHASE_SWITCHES = 0x00A   # Input: Phasenwechsel
OFFSET_ERROR_CODE = 0x00B       # Fehlercode (neu)
OFFSET_STATUS_CODE = 0x00C      # OCPP Status
OFFSET_VOLTAGE_L1 = 0x00D
OFFSET_VOLTAGE_L2 = 0x00E
OFFSET_VOLTAGE_L3 = 0x00F

OFFSET_RFID_TAG = 0x010         # RFID Tag (Länge 10) (neu)
OFFSET_DERATING_STATUS = 0x01A  # Temperatur Derating (neu)

# --- STATUS MAPPINGS ---

# Charge Point Error Codes (OCPP 1.6)
CHARGE_POINT_ERROR_CODES = {
    0: "NoError",
    1: "ConnectorLockFailure",
    2: "EVCommunicationError",
    3: "GroundFailure",
    4: "HighTemperature",
    5: "InternalError",
    6: "LocalListConflict",
    7: "NoError",
    8: "OtherError",
    9: "OverCurrentFailure",
    10: "PowerMeterFailure",
    11: "PowerSwitchFailure",
    12: "ReaderFailure",
    13: "ResetFailure",
    14: "UnderVoltage",
    15: "OverVoltage",
    16: "WeakSignal"
}

# Temperature Derating Status
DERATING_STATUS_MAP = {
    0: "No derating",
    1: "1st Stage",
    2: "2nd Stage",
    3: "Charging Stopped (OverTemp)",
    4: "Sensor Error"
}