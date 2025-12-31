# **Compleo Wallbox Integration für Home Assistant**

Eine benutzerdefinierte Home Assistant Integration für **Compleo Wallboxen** (z.B. Cito, Duo, Solo, eBox) via Modbus TCP.

Diese Integration verwandelt deine Wallbox in einen intelligenten Energiemanager. Sie unterstützt nicht nur das Auslesen von Werten, sondern bietet integrierte Logiken für **PV-Überschussladen**, **Lastmanagement** und spezielle Modi für zickige Elektroautos (wie die **Renault Zoe**).

## **✨ Funktionen**

* **Automatische Erkennung:** Erkennt automatisch die Anzahl der Ladepunkte (Solo/Duo).  
* **Echtzeit-Daten:** Leistung, Ströme, Spannungen, Energie (Sitzung & Gesamt/Lifetime), RFID-Tags, Status- und Fehlercodes.  
* **Steuerung:** Starten/Stoppen (via Leistungsvorgabe), Phasen-Umschaltung (1ph/3ph).  
* **Smart Charging Logik (Integriert):**  
  * **Schnellladen:** Maximale Power auf Knopfdruck.  
  * **Begrenzt:** Manuell einstellbares Limit (z.B. 3.6 kW).  
  * **Solar:** Dynamische Regelung basierend auf PV-Überschuss.  
* **ALT Mode (Alternativ-Modus):** Spezielle Hysterese- und Umschaltlogik für Fahrzeuge mit hohem Mindestladestrom (z.B. Renault Zoe).  
* **Robustheit:** "Brute-Force" Modbus-Kommunikation, die auch mit älteren Firmware-Versionen oder zickigen Schnittstellen zurechtkommt.

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
Die Renault Zoe (und einige andere Smart/Twingo Modelle) benötigt oft mindestens 8A bis 10A Ladestrom, um effizient und fehlerfrei zu laden, unabhängig ob 1- oder 3-phasig.  
**Funktionsweise im Solar-Modus mit aktivem ALT Mode:**

1. **Phasen-Management:** Solange der Solarüberschuss nicht für 3-phasiges Laden mit dem eingestellten Mindeststrom reicht (z.B. 3 \* 230V \* 8A \= ca. 5.5 kW), wird **1-phasiges Laden** erzwungen. Erst wenn der Überschuss stabil darüber liegt, wird auf 3 Phasen geschaltet.  
2. **Mindeststrom:** Einstellbar über **"Config: Min Amps (ALT)"** (Standard 8A). Hier stellst du ein, was dein Auto mindestens braucht (Zoe meist 8-10A).  
3. **Intelligente Hysterese (Schwankungs-Glättung):**  
   * **Strom steigt:** Der Ladestrom wird erst erhöht, wenn der neue Wert für **20 Minuten** stabil verfügbar war (verhindert ständiges Hochregeln bei kurzen Wolkenlücken, was die Zoe Ladeelektronik schonen soll).  
   * **Strom sinkt (leicht):** Der Ladestrom wird für **15 Minuten** gehalten, bevor er reduziert wird.  
   * **Strom bricht ein:** Fällt der Überschuss um mehr als **10%**, wird die Leistung **sofort** reduziert, um Netzbezug zu verhindern.

**Wichtig:** Wenn der ALT Mode deaktiviert wird, stellt die Integration den Phasenmodus automatisch wieder auf "Automatisch" zurück.

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
description: "Sendet den aktuellen PV-Überschuss an die Compleo Wallbox Logik"  
trigger:  
  \- platform: state  
    entity\_id: sensor.mein\_smart\_meter\_power  \# Dein Sensor (Negativ \= Einspeisung, Positiv \= Bezug)  
    \# ODER Zeitgesteuert:  
  \- platform: time\_pattern  
    seconds: "/30"  
condition: \[\]  
action:  
  \- service: number.set\_value  
    target:  
      entity\_id: number.compleo\_wallbox\_lp1\_input\_solar\_excess  
    data:  
      \# Beispiel: Wenn Einspeisung negativ ist (z.B. \-2000W), sende 2000\. Sonst 0\.  
      value: \>  
        {% set grid \= states('sensor.mein\_smart\_meter\_power') | float(0) %}  
        {% if grid \< 0 %}  
          {{ grid | abs }}  
        {% else %}  
          0  
        {% endif %}  
mode: single

## **📊 Verfügbare Entitäten (Auszug)**

| Typ | Name | Beschreibung |
| :---- | :---- | :---- |
| **Sensor** | Total Power (Station) | Gesamte aktuelle Leistung der Station |
| **Sensor** | Station Energy (Lifetime) | Gesamtzählerstand (alle Ladepunkte) |
| **Sensor** | LP1 Power | Aktuelle Leistung Ladepunkt 1 |
| **Sensor** | LP1 Total Energy (Lifetime) | Zählerstand Ladepunkt 1 |
| **Sensor** | LP1 RFID Tag | Zuletzt genutzte RFID Karte |
| **Sensor** | LP1 Status / Error | Text-Status (z.B. "Charging", "OverTemp") |
| **Select** | LP1 Charging Mode | Modus-Wahl: Fast / Limited / Solar |
| **Select** | LP1 Phase Mode | Hardware-Umschaltung: Auto / 1-Phase / 3-Phase |
| **Switch** | LP1 ALT Mode | Aktiviert die Zoe-Logik |
| **Number** | LP1 Config: Limited Mode | Watt-Limit für den "Limited" Modus |
| **Number** | LP1 Config: Min Amps (ALT) | Mindeststrom für Zoe-Logik (z.B. 8A) |
| **Number** | LP1 Input: Solar Excess | **Hier** muss der PV-Überschuss rein |

## **Fehlerbehebung**

* **"Unavailable" / Keine Verbindung:** Prüfe, ob die Wallbox erreichbar ist (Ping). Manche Compleo-Boxen erlauben nur eine aktive Modbus-Verbindung gleichzeitig. Stoppe andere Systeme (z.B. EVCC), falls vorhanden.  
* **Geister-Ladepunkt:** Die Integration liest Register 0x0008 um die Anzahl der Punkte zu bestimmen. Falls das bei dir falsch ist, wird standardmäßig 1 Punkt angenommen.

## **Lizenz**

MIT