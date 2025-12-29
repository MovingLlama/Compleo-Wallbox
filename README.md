# **Compleo Wallbox Integration for Home Assistant**

This custom integration connects **Compleo Charging Stations** (e.g., Compleo Solo, Compleo Duo) to Home Assistant via Modbus TCP.

It is designed to automatically detect available charging points and provides extensive monitoring and control capabilities.

## **✨ Features**

* **Auto-Discovery:** Automatically detects Compleo wallboxes on your network via Zeroconf.  
* **Multi-Point Support:**  
  * Works with **Compleo Solo** (1 Charging Point).  
  * Works with **Compleo Duo** (2 Charging Points) \- automatically creates a separate device for the second point.  
* **Real-Time Monitoring:**  
  * Current Power (W)  
  * Total Energy (kWh)  
  * Current per Phase (L1, L2, L3)  
  * Voltage per Phase (L1, L2, L3)  
  * Status Codes (translated to readable text)  
* **Control:**  
  * **Charging Power Limit:** Set the maximum allowed charging power (Watts) globally for the station.

## **🚀 Installation**

### **Option 1: Via HACS (Recommended)**

1. Open HACS in Home Assistant.  
2. Go to "Integrations" \> Top right menu \> "Custom repositories".  
3. Add the URL of this repository and select category **Integration**.  
4. Search for **Compleo Wallbox** and install it.  
5. Restart Home Assistant.

### **Option 2: Manual Installation**

1. Download the custom\_components/compleo\_wallbox folder from this repository.  
2. Copy the folder into your Home Assistant config/custom\_components/ directory.  
3. Restart Home Assistant.

## **⚙️ Configuration**

1. Navigate to **Settings** \> **Devices & Services**.  
2. Click **\+ Add Integration**.  
3. Search for **Compleo Wallbox**.  
4. **Auto-Discovery:** If your wallbox is found automatically, simply click "Configure".  
5. **Manual:** If not found, enter the **IP Address** and **Port** (Default: 502).

## **📊 Entities & Devices**

The integration creates a structured device hierarchy:

### **1\. Main Device: "Compleo Wallbox"**

Represents the physical unit and global settings.

* **Number:** Charging Power Limit (Slider, 0W \- 22000W)  
* **Diagnostic:** Firmware Version

### **2\. Sub-Devices: "Charging Point 1" (and "Charging Point 2")**

Represents the individual charging sockets.

* **Sensor:** Power (W)  
* **Sensor:** Total Energy (kWh)  
* **Sensor:** Status (Ready, Charging, Error, etc.)  
* **Sensor:** Voltage L1, L2, L3 (V)  
* **Sensor:** Current L1, L2, L3 (A)

## **🐛 Troubleshooting & Debugging**

If you experience issues (e.g., entities showing "Unknown" or connection drops), you can enable detailed Modbus debugging. This will log exactly which registers are read and the raw data received.

Add this to your configuration.yaml:

logger:  
  default: info  
  logs:  
    custom\_components.compleo\_wallbox: debug

Restart Home Assistant and check the logs (**Settings** \> **System** \> **Logs**) for lines starting with custom\_components.compleo\_wallbox.

## **Technical Details**

* **Protocol:** Modbus TCP  
* **Default Port:** 502  
* **Update Interval:** 30 seconds (default)

*Disclaimer: This integration is an open-source project and not officially affiliated with Compleo Charging Solutions.*