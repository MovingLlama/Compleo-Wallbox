# **Compleo Wallbox Integration für Home Assistant**

Eine Home Assistant custom\_component zur lokalen Steuerung und Überwachung von Compleo Ladestationen (z.B. Compleo Solo, eBOX Professional) über **Modbus TCP**.

Diese Integration ermöglicht es dir, deine Wallbox direkt in Home Assistant einzubinden – ganz ohne Cloud, mit direkter lokaler Kommunikation.

## **✨ Features**

* **Überwachung:**  
  * Aktuelle Ladeleistung (W)  
  * Gesamtenergieverbrauch (kWh)  
  * Spannung & Stromstärke pro Phase (L1, L2, L3)  
  * Status der Wallbox (Bereit, Lädt, Fehler, etc.)  
  * Detaillierte Fehlercodes  
  * Temperatur-Derating Status  
* **Steuerung:**  
  * **Ladeleistung begrenzen:** Setze das Limit in Watt direkt über einen Schieberegler.  
  * **Phasen-Umschaltung:** Wechsle zwischen Automatisch, 1-Phasig und 3-Phasig (sofern von der Hardware unterstützt).

## **🚀 Installation**

### **Option 1: Via HACS (Empfohlen)**

1. Öffne HACS in deinem Home Assistant.  
2. Klicke oben rechts auf die drei Punkte ... \-\> **Benutzerdefinierte Repositories**.  
3. Füge die URL dieses Repositories hinzu: https://github.com/MovingLlama/compleo\_wallbox  
4. Wähle als Kategorie **Integration**.  
5. Klicke auf **Hinzufügen** und suche dann nach "Compleo Wallbox" in der HACS-Liste, um es zu installieren.  
6. Starte Home Assistant neu.

### **Option 2: Manuell**

1. Lade die neueste Version aus den [Releases](https://www.google.com/search?q=https://github.com/MovingLlama/compleo_wallbox/releases) herunter.  
2. Entpacke die ZIP-Datei.  
3. Kopiere den Ordner compleo\_wallbox in dein Home Assistant Verzeichnis unter /config/custom\_components/.  
4. Starte Home Assistant neu.

## **⚙️ Konfiguration**

1. Gehe in Home Assistant zu **Einstellungen** \-\> **Geräte & Dienste**.  
2. Klicke unten rechts auf **Integration hinzufügen**.  
3. Suche nach **Compleo Wallbox**.  
4. Gib die **IP-Adresse** deiner Wallbox ein.  
   * **Port:** Standard ist 502\.  
   * **Update Intervall:** Wie oft Daten abgerufen werden sollen (Standard: 30 Sekunden).

### **Voraussetzungen an der Wallbox**

* Die Wallbox muss im gleichen Netzwerk wie Home Assistant sein.  
* **Modbus TCP** muss aktiviert sein (bei manchen Modellen standardmäßig an, bei anderen muss es über das Webinterface oder DIP-Schalter aktiviert werden).

## **📊 Entitäten**

Nach der Einrichtung stehen dir folgende Entitäten zur Verfügung:

| Entität | Typ | Beschreibung |
| :---- | :---- | :---- |
| sensor.compleo\_status | Sensor | Aktueller Status (Charging, Available...) |
| sensor.compleo\_power | Sensor | Aktuelle Leistung in Watt |
| sensor.compleo\_energy\_charged | Sensor | Gesamtzähler in kWh |
| number.compleo\_power\_limit | Number | Schieberegler für das Ladelimit (Watt) |
| select.compleo\_phase\_mode | Select | Moduswahl (Auto/1-Phasig/3-Phasig) |

... und viele weitere Sensoren für Spannung und Strom pro Phase.

## **⚠️ Disclaimer**

Dies ist keine offizielle Software der Compleo Charging Solutions GmbH. Die Nutzung erfolgt auf eigene Gefahr.

Entwickelt von [MovingLlama](https://www.google.com/search?q=https://github.com/MovingLlama)