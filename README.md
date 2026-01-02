# **Compleo Wallbox Integration for Home Assistant**

A custom Home Assistant integration for **Compleo Wallboxes** (e.g., Cito, Duo, Solo, eBox) via Modbus TCP.

This integration transforms your wallbox into an intelligent energy manager. It supports reading real-time values and features built-in logic for **Solar Excess Charging**, **Load Management**, and special modes for "picky" EVs (like the **Renault Zoe**).

## **⚠️ Disclaimer & Legal Notice**

**This is an unofficial Community Project and has NO affiliation, connection, or endorsement from Compleo Charging Solutions AG.**

The use of this integration, and especially the control functions (Smart Charging, Phase Switching), is entirely at your own risk. The developers assume **no liability** for any damage to the wallbox, the vehicle, the electrical installation, or any other property that may result from the use of this software. Please ensure your electrical installation is rated for continuous loads and phase switching.

## **✨ Features**

* **Auto-Discovery:** Automatically detects the number of charging points (Solo/Duo) supported by your station.  
* **Real-time Data:** Reads Power, Currents, Voltages, Session Energy, Lifetime Energy (Odometer), Charging Time, RFID Tags, Status, and Error Codes.  
* **Control:** Start/Stop charging (via power setpoints), Phase Switching (1-phase / 3-phase).  
* **Smart Charging Logic (Built-in):**  
  * **Fast:** Max power immediately.  
  * **Limited:** User-definable constant limit (e.g., 3.6 kW).  
  * **Solar:** Dynamic regulation based on your home's PV excess.  
* **ALT Mode (Alternative Mode):** Special logic with hysteresis and forced phase switching for vehicles with high minimum charging currents (e.g., Renault Zoe).  
* **Robustness:** Uses "Brute-Force" Modbus communication strategies to handle older firmware versions or unstable connections gracefully.

## **🔋 Smart Charging Modes**

Each charging point has a **"Charging Mode"** dropdown menu in Home Assistant.

### **1\. Fast Charging (Max)**

Sets the wallbox to the maximum possible power (Default 11 kW, hardware dependent). Ignores solar excess.

### **2\. Limited Charging**

Charges with a fixed power value configurable in the number entity **"Config: Limited Power"** (Default: 3600 W). Ideal for slow overnight charging to reduce grid strain.

### **3\. Solar Charging**

Dynamically adjusts charging power based on available excess energy.

* **Requirement:** You must feed the current PV excess (in Watts) to the entity number.compleo\_lpX\_input\_solar\_excess via an automation (see example below).  
* **Buffer:** By default, 500W is subtracted from the excess to prevent grid consumption.

### **4\. Charging Disabled**

Stops the charging process by setting the power limit to 0 Watts.

## **🚗 ALT Mode (Alternative / Zoe Mode)**

This mode can be activated via the **"ALT Mode"** switch for each charging point.

It is designed for EVs that are difficult to charge with standard logic or require high minimum currents. A prominent example is the **Renault Zoe** (or Smart EQ / Twingo Electric). These cars often require at least 8A to 10A to charge efficiently and without errors.

**How it works:**

1. **Forced Phase Switching:** ALT Mode bypasses the wallbox's internal "Automatic" phase switching. The integration calculates the best mode:  
   * Is there enough power for **3-phase** charging at the minimum current? \-\> **Command: 3-Phase**.  
   * Is there not enough power? \-\> **Command: 1-Phase**.  
2. **Minimum Current:** Configurable via **"Config: Min Amps (ALT)"** (Default: 8A).  
3. **Smart Hysteresis (Smoothing):**  
   * **Power Rising:** Charging current is only increased after the new higher value has been **stable for 20 minutes**. This prevents constant ramping up/down during short cloud breaks, protecting the car's onboard charger.  
   * **Power Falling (Slightly):** Current is held for **15 minutes** before reducing.  
   * **Power Drop:** If solar excess drops by more than **10%**, power is reduced **immediately** to prevent grid usage.

**Note:** Disabling ALT Mode automatically resets the phase mode register to "Automatic" (1).

## **🛠️ Setup & Configuration**

### **Installation via HACS**

1. Add this repository as a "Custom Repository" in HACS.  
2. Install "Compleo Wallbox".  
3. Restart Home Assistant.

### **Configuration**

1. Go to **Settings** \-\> **Devices & Services** \-\> **Add Integration**.  
2. Search for **Compleo Wallbox**.  
3. Enter the **IP Address** of your wallbox and the **Port** (Default: 502).

### **Automation Example (Solar)**

To enable solar charging, you must send your excess power data to the integration. Create an automation that runs frequently (e.g., every 30 seconds):

alias: "Wallbox: Send Solar Excess"  
description: "Feeds solar excess data to the Compleo integration"  
trigger:  
  \- platform: time\_pattern  
    seconds: "/30"  
action:  
  \- service: number.set\_value  
    target:  
      entity\_id: number.compleo\_wallbox\_lp1\_input\_solar\_excess  
    data:  
      \# Example: Send positive value if feeding into grid (negative grid value), else 0\.  
      \# Replace 'sensor.my\_smart\_meter\_power' with your actual grid sensor.  
      value: \>  
        {% set grid \= states('sensor.my\_smart\_meter\_power') | float(0) %}  
        {% if grid \< 0 %} {{ grid | abs }} {% else %} 0 {% endif %}

## **📊 Available Entities (Selection)**

| Type | Name | Description |
| :---- | :---- | :---- |
| **Sensor** | Total Power (Station) | Total power usage of the entire station. |
| **Sensor** | Energy (Lifetime, Station) | Accumulated energy counter for the station. |
| **Sensor** | Power (Point) | Current power of the specific charging point. |
| **Sensor** | Meter Reading (Lifetime) | Accumulated energy counter for the charging point. |
| **Sensor** | RFID Tag | Last used RFID tag. |
| **Select** | Charging Mode | Logic Selection: Fast / Limited / Solar / Disabled. |
| **Select** | Phase Mode | Hardware Switching: Automatic / 1-Phase / 3-Phase. |
| **Switch** | ALT Mode | Enables special Zoe logic. |
| **Number** | Config: Limited Power | Watt limit for "Limited" mode. |
| **Number** | Config: Min Amps (ALT) | Minimum Amps for ALT Mode calculation. |
| **Number** | Input: Solar Excess | **Target entity** for your solar automation. |

## **License**

MIT