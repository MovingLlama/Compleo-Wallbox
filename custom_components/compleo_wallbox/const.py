"""Constants for the Compleo Wallbox integration."""

DOMAIN = "compleo_wallbox"
DEFAULT_SCAN_INTERVAL = 30
DEFAULT_PORT = 502
DEFAULT_NAME = "Compleo Wallbox"

# --- REGISTER KONFIGURATION ---
# Passen Sie diese Werte an Ihr Modell an.

# Global / System (HOLDING Register)
# Schreibbar
REG_SYS_POWER_LIMIT = 0x0000  # Leistungsvorgabe (100W Schritte)

# Global / System (INPUT Register)
# Nur lesbar
REG_SYS_FW_PATCH = 0x0006
REG_SYS_FW_MAJOR = 0x0007
REG_SYS_ARTICLE_NUM = 0x0020  # Startadresse String
REG_SYS_SERIAL_NUM = 0x0030   # Startadresse String

# --- LADEPUNKTE BASIS-ADRESSEN ---
# Basis-Adresse für den ersten Ladepunkt (LP1).
# Compleo Duo/Cito/Pro: meist 0x1000
# Compleo Solo (Legacy): meist 0x0000
ADDR_LP1_BASE = 0x1000

# Basis-Adresse für den zweiten Ladepunkt (LP2)
# Compleo Duo: meist 0x2000
ADDR_LP2_BASE = 0x2000

# --- LADEPUNKTE OFFSETS ---
# Diese Offsets werden zur Basis-Adresse addiert.
# Beispiel: Spannung L1 (LP1) = ADDR_LP1_BASE (0x1000) + OFFSET_VOLTAGE_L1 (0x00D) = 0x100D

# Input Register Offsets
OFFSET_STATUS_WORD = 0x001
OFFSET_POWER = 0x002          # 100W Schritte
OFFSET_CURRENT_L1 = 0x003     # 0.1A Schritte
OFFSET_CURRENT_L2 = 0x004
OFFSET_CURRENT_L3 = 0x005
OFFSET_ENERGY = 0x008         # 100Wh Schritte
OFFSET_PHASE_SWITCHES = 0x00A # Anzahl Phasenwechsel
OFFSET_STATUS_CODE = 0x00C    # OCPP Status Code
OFFSET_VOLTAGE_L1 = 0x00D     # Volt
OFFSET_VOLTAGE_L2 = 0x00E
OFFSET_VOLTAGE_L3 = 0x00F

# Holding Register Offsets
OFFSET_PHASE_MODE = 0x009     # Senken-Modus (Automatik/1ph/3ph)