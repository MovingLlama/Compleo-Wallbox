# **Compleo Wallbox Integration**

[🇩🇪 **Deutsche Beschreibung lesen**](https://www.google.com/search?q=%23compleo-wallbox-integration-f%C3%BCr-home-assistant) | [🇺🇸 **Read English Description**](https://www.google.com/search?q=%23compleo-wallbox-integration-for-home-assistant)

# **Compleo Wallbox Integration für Home Assistant**

Eine benutzerdefinierte Home Assistant Integration für **Compleo Wallboxen** (z.B. Cito, Duo, Solo, eBox) via Modbus TCP.

Diese Integration verwandelt deine Wallbox in einen intelligenten Energiemanager. Sie unterstützt nicht nur das Auslesen von Werten, sondern bietet integrierte Logiken für **PV-Überschussladen**, **Lastmanagement** und spezielle Modi für anspruchsvolle Elektroautos (wie die **Renault Zoe**).

## **✨ Funktionen**

* **Automatische Erkennung:** Erkennt automatisch die Anzahl der Ladepunkte (Solo/Duo).  
* **Echtzeit-Daten:** Leistung, Ströme, Spannungen, Energie (Sitzung & Gesamt/Lifetime), Ladezeit, RFID-Tags, Status- und Fehlercodes.  
* **Steuerung:** Starten/Stoppen (via Leistungsvorgabe), Phasen-Umschaltung (1ph/3ph).  
* **Smart Charging Logik (Integriert):**  
  * **Schnellladen (Fast):** Maximale Power auf Knopfdruck.  
  * **Begrenzt (Limited):** Manuell einstellbares Limit (z.B. 3.6 kW).  
  * **Solar:** Dynamische Regelung basierend auf PV-Überschuss.  
* **ALT Mode (Alternativ-Modus):** Spezielle Hysterese- und Umschaltlogik für Fahrzeuge mit hohem Mindestladestrom (z.B. Renault Zoe).  
* **Robustheit:** "Brute-Force" Modbus-Kommunikation, die auch mit älteren Firmware-Versionen oder schwierigen Schnittstellen zurechtkommt.

## **🔋 Smart Charging Modi**

Jeder Ladepunkt verfügt über ein Dropdown-Menü **"Charging Mode"**.

### **1\. Schnellladen (Fast)**

Die Wallbox wird auf die maximal mögliche Leistung gesetzt (Standard 11 kW, hardwareabhängig). Ignoriert Solarüberschuss.

### **2\. Begrenztes Laden (Limited)**

Die Wallbox lädt mit einem festen Wert, den du im Eingabefeld **"Config: Limited Mode"** einstellen kannst (Standard: 3600 W). Ideal für das langsame Laden über Nacht.

### **3\. Solarladen (Solar)**

Die Wallbox regelt die Leistung dynamisch basierend auf dem verfügbaren Überschuss.

* **Voraussetzung:** Du musst den aktuellen PV-Überschuss (in Watt) zyklisch in die Entität number.compleo\_lpX\_input\_solar\_excess schreiben (siehe Automatisierung unten).  
* **Puffer:** Es werden standardmäßig 500W vom Überschuss abgezogen, um Netzbezug zu vermeiden.

## **🚗 ALT Mode (Alternativ / Zoe)**

Aktivierbar über den Schalter **"ALT Mode"**.

Dieser Modus ist speziell für Elektrofahrzeuge entwickelt, die "zickig" beim Laden sind oder hohe Mindestströme benötigen. Ein prominentes Beispiel hierfür ist die Renault Zoe.  
Die Renault Zoe (und einige andere Smart/Twingo Modelle) benötigt oft mindestens 8A bis 10A Ladestrom, um effizient und fehlerfrei zu laden.  
**Funktionsweise:**

1. **Harte Phasen-Umschaltung:** Der ALT-Modus umgeht die interne "Automatik" der Wallbox. Die Integration entscheidet selbst:  
   * Reicht der Strom für 3-Phasen? \-\> **Befehl: 3-Phasig**.  
   * Reicht er nicht? \-\> **Befehl: 1-Phasig**.  
2. **Mindeststrom:** Einstellbar über **"Config: Min Amps (ALT)"** (Standard 8A).  
3. **Intelligente Hysterese (Schwankungs-Glättung):**  
   * **Strom steigt:** Der Ladestrom wird erst erhöht, wenn der neue Wert für **20 Minuten** stabil verfügbar war (verhindert ständiges Hochregeln bei kurzen Wolkenlücken).  
   * **Strom sinkt (leicht):** Der Ladestrom wird für **15 Minuten** gehalten.  
   * **Strom bricht ein:** Fällt der Überschuss um mehr als **10%**, wird die Leistung **sofort** reduziert.

**Hinweis:** Wenn der ALT Mode deaktiviert wird, stellt die Integration den Phasenmodus automatisch wieder auf "Automatisch" (1) zurück.

## **🛠️ Einrichtung & Konfiguration**

### **Installation via HACS**

1. Füge dieses Repository als "Benutzerdefiniertes Repository" in HACS hinzu.  
2. Installiere "Compleo Wallbox".  
3. Starte Home Assistant neu.

### **Konfiguration**

1. Gehe zu **Einstellungen** \-\> **Geräte & Dienste** \-\> **Integration hinzufügen**.  
2. Suche nach **Compleo Wallbox**.  
3. Gib die **IP-Adresse** deiner Wallbox und den **Port** (Standard 502\) ein.

### **Automatisierungs-Beispiel (Solar)**

Damit das Solarladen funktioniert, musst du deinen Überschuss an die Integration senden. Erstelle eine Automatisierung, die z.B. alle 30 Sekunden läuft:

alias: "Wallbox: Solar Überschuss senden"  
trigger:  
  \- platform: time\_pattern  
    seconds: "/30"  
action:  
  \- service: number.set\_value  
    target:  
      entity\_id: number.compleo\_wallbox\_lp1\_input\_solar\_excess  
    data:  
      \# Beispiel: Sende positiven Wert wenn Einspeisung (negativer Grid-Wert), sonst 0\.  
      value: \>  
        {% set grid \= states('sensor.mein\_smart\_meter\_power') | float(0) %}  
        {% if grid \< 0 %} {{ grid | abs }} {% else %} 0 {% endif %}

## **⚠️ Haftungsausschluss & Rechtliches**

Dies ist ein inoffizielles **Community-Projekt** und steht in **keinerlei Verbindung zur Compleo Charging Solutions AG**.

Die Nutzung dieser Integration und insbesondere der Steuerungsfunktionen erfolgt auf eigene Gefahr. Die Entwickler übernehmen **keine Haftung** für eventuelle Schäden an der Wallbox, dem Fahrzeug oder der elektrischen Installation, die durch die Nutzung dieser Software entstehen könnten. Bitte stelle sicher, dass deine elektrische Installation für die Dauerlasten ausgelegt ist.

## **Lizenz**

MIT

# **Compleo Wallbox Integration for Home Assistant**

A custom Home Assistant integration for **Compleo Wallboxes** (e.g., Cito, Duo, Solo, eBox) via Modbus TCP.

This integration turns your wallbox into an intelligent energy manager. It supports reading real-time values and includes built-in logic for **Solar Excess Charging**, **Load Management**, and special modes for sensitive EVs (like the **Renault Zoe**).

## **✨ Features**

* **Auto-Discovery:** Automatically detects the number of charging points (Solo/Duo).  
* **Real-time Data:** Power, currents, voltages, energy (session & lifetime), charging time, RFID tags, status, and error codes.  
* **Control:** Start/Stop (via power limit), Phase Switching (1ph/3ph).  
* **Smart Charging Logic (Built-in):**  
  * **Fast:** Maximum power at the push of a button.  
  * **Limited:** Manually adjustable limit (e.g., 3.6 kW).  
  * **Solar:** Dynamic regulation based on PV excess.  
* **ALT Mode (Alternative Mode):** Special hysteresis and switching logic for vehicles with high minimum charging currents (e.g., Renault Zoe).  
* **Robustness:** "Brute-Force" Modbus communication logic that handles older firmware versions or unstable connections gracefully.

## **🔋 Smart Charging Modes**

Each charging point has a **"Charging Mode"** dropdown.

### **1\. Fast Charging**

Sets the wallbox to the maximum possible power (Default 11 kW, hardware dependent). Ignores solar excess.

### **2\. Limited Charging**

Charges with a fixed value configurable in **"Config: Limited Mode"** (Default: 3600 W). Ideal for slow overnight charging.

### **3\. Solar Charging**

Dynamically adjusts charging power based on available excess energy.

* **Requirement:** You must cycle the current PV excess (in Watts) to the entity number.compleo\_lpX\_input\_solar\_excess (see automation below).  
* **Buffer:** By default, 500W is subtracted from the excess to prevent grid consumption.

## **🚗 ALT Mode (Alternative / Zoe)**

Can be activated via the **"ALT Mode"** switch.

This mode is designed for EVs that are "picky" about charging or require high minimum currents. A prominent example is the Renault Zoe.  
The Renault Zoe (and some Smart/Twingo models) often requires at least 8A to 10A to charge efficiently and without errors.  
**How it works:**

1. **Forced Phase Switching:** ALT Mode bypasses the wallbox's internal "Automatic" mode. The integration decides:  
   * Enough power for 3-phases? \-\> **Command: 3-Phase**.  
   * Not enough? \-\> **Command: 1-Phase**.  
2. **Minimum Current:** Configurable via **"Config: Min Amps (ALT)"** (Default 8A).  
3. **Smart Hysteresis (Fluctuation Smoothing):**  
   * **Power Rising:** Charging current increases only after the new value has been stable for **20 minutes** (prevents toggling during short cloud breaks).  
   * **Power Falling (Slightly):** Current is held for **15 minutes**.  
   * **Power Drop:** If excess drops by more than **10%**, power is reduced **immediately** to prevent grid usage.

**Note:** Disabling ALT Mode automatically resets the phase mode to "Automatic" (1).

## **🛠️ Setup & Configuration**

### **Installation via HACS**

1. Add this repository as a "Custom Repository" in HACS.  
2. Install "Compleo Wallbox".  
3. Restart Home Assistant.

### **Configuration**

1. Go to **Settings** \-\> **Devices & Services** \-\> **Add Integration**.  
2. Search for **Compleo Wallbox**.  
3. Enter the **IP Address** and **Port** (Default 502).

### **Automation Example (Solar)**

To make solar charging work, send your excess power to the integration. Create an automation running e.g. every 30 seconds:

alias: "Wallbox: Send Solar Excess"  
trigger:  
  \- platform: time\_pattern  
    seconds: "/30"  
action:  
  \- service: number.set\_value  
    target:  
      entity\_id: number.compleo\_wallbox\_lp1\_input\_solar\_excess  
    data:  
      \# Example: Send positive value if feeding grid (negative grid value), else 0\.  
      value: \>  
        {% set grid \= states('sensor.my\_smart\_meter\_power') | float(0) %}  
        {% if grid \< 0 %} {{ grid | abs }} {% else %} 0 {% endif %}

## **⚠️ Disclaimer & Legal Notice**

This is an unofficial **Community Project** and has **no affiliation with Compleo Charging Solutions AG**.

Use of this integration and especially the control functions is at your own risk. The developers assume **no liability** for any damage to the wallbox, the vehicle, or the electrical installation that may result from the use of this software. Please ensure your electrical installation is rated for continuous loads.

## **License**

MIT