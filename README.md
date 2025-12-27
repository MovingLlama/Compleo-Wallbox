# **Compleo Wallbox Home Assistant Integration**

Integration für **Compleo Solo** und kompatible Ladestationen über **Modbus TCP**.

Diese Integration liest Status, Energie, Spannung und Ströme aus der Wallbox und ermöglicht das Setzen der Ladeleistung.

## **Funktionen**

* 🔌 **Echtzeit-Werte:** Aktuelle Leistung, Gesamtenergie (kWh), Spannungen (L1/L2/L3), Ströme.  
* 🚦 **Status:** Anzeige des aktuellen Status (Lädt, Verfügbar, Fehler, etc.) basierend auf OCPP Status Codes.  
* ⚡ **Steuerung:** Setzen der maximalen Ladeleistung (in Watt) über eine Number-Entity.  
* 🆔 **Erkennung:** Automatische Erkennung von Modell, Seriennummer und Firmware-Version.  
* 🏷️ **RFID:** Anzeige des letzten RFID Tags.

## **Voraussetzungen**

1. Die Wallbox muss im gleichen Netzwerk wie Home Assistant sein.  
2. **Modbus TCP** muss auf der Wallbox aktiviert sein (Standardport 502).

## **Installation**

### **Via HACS (Empfohlen)**

1. Füge dieses Repository als "Custom Repository" in HACS hinzu:  
   * URL: https://github.com/MovingLlama/Compleo-Wallbox  
   * Typ: Integration  
2. Suche nach "Compleo Wallbox" und installiere es.  
3. Starte Home Assistant neu.

### **Manuell**

1. Lade den Ordner custom\_components/compleo\_wallbox in dein Home Assistant custom\_components Verzeichnis.  
2. Starte Home Assistant neu.

## **Konfiguration**

1. Gehe zu **Einstellungen** \-\> **Geräte & Dienste**.  
2. Klicke auf **Integration hinzufügen**.  
3. Suche nach **Compleo Wallbox**.  
4. Gib die **IP-Adresse** deiner Wallbox und den **Port** (Standard 502\) ein.

## **Entitäten**

| Entität | Beschreibung |
| :---- | :---- |
| sensor.compleo\_wallbox\_status | Aktueller OCPP Status (z.B. Lädt, Verfügbar) |
| sensor.compleo\_wallbox\_current\_power | Aktuelle Ladeleistung in Watt |
| sensor.compleo\_wallbox\_total\_energy | Geladene Energie (Gesamt) in kWh |
| number.compleo\_wallbox\_charging\_power\_limit | Schieberegler für Leistungslimit (Register 0x0000) |
| sensor.compleo\_wallbox\_last\_rfid | Zuletzt genutzter RFID Tag |
| ... | Spannungen und Ströme pro Phase |

## **Kompatibilität**

Getestet mit:

* Compleo Solo (Modbus Register v16)  
* Andere Compleo Modelle mit gleicher Registermap (P4, P51, P52 Hardware)

## **Lizenz**

MIT