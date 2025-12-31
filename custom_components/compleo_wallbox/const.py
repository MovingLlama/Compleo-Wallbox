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

# Neue Input Register (Laut User-Test)
REG_SYS_TOTAL_POWER_READ = 0x0009 # Aktuelle Leistung der ganzen Ladestation
REG_SYS_TOTAL_CURRENT_L1 = 0x000A # Gesamtstrom Phase 1
REG_SYS_TOTAL_CURRENT_L2 = 0x000B # Gesamtstrom Phase 2
REG_SYS_TOTAL_CURRENT_L3 = 0x000C # Gesamtstrom Phase 3
REG_SYS_UNUSED_POWER = 0x000D     # Nicht verwendete Leistung

REG_SYS_RFID_TAG = 0x0010         # RFID Tag (String)

# Strings (Länge 16 Register!)
REG_SYS_ARTICLE_NUM = 0x0020
REG_SYS_SERIAL_NUM = 0x0030
LEN_STRING_REGISTERS = 16 

# --- LADEPUNKTE BASIS-ADRESSEN ---
# Korrigiert auf 0x0100 laut User-Test
ADDR_LP1_BASE = 0x0100
# LP2 lassen wir auf Standard Duo Offset, falls relevant, sonst 0x0200 raten
ADDR_LP2_BASE = 0x0200

# --- LADEPUNKTE OFFSETS ---
OFFSET_STATUS_WORD = 0x001
OFFSET_POWER = 0x002
OFFSET_CURRENT_L1 = 0x003
OFFSET_CURRENT_L2 = 0x004
OFFSET_CURRENT_L3 = 0x005
OFFSET_ENERGY = 0x008
OFFSET_PHASE_SWITCHES = 0x00A
OFFSET_STATUS_CODE = 0x00C
OFFSET_VOLTAGE_L1 = 0x00D
OFFSET_VOLTAGE_L2 = 0x00E
OFFSET_VOLTAGE_L3 = 0x00F

OFFSET_PHASE_MODE = 0x009