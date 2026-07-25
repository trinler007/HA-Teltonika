# HA Teltonika Extended

Erweiterte Home-Assistant-Custom-Integration für Teltonika-Router. Sie verwendet
dieselbe Domain `teltonika` wie die Core-Integration und kann diese deshalb
vollständig ersetzen, ohne dass vorhandene Config Entries neu angelegt werden
müssen.

Die Integration basiert auf dem Stand der offiziellen Home-Assistant-Integration
und ergänzt insbesondere Funktionen für den Teltonika RUTX50 mit RutOS 7.24.x.

## Funktionen

- alle Sensoren der offiziellen Core-Integration
- GPS-Position als `device_tracker` für die Home-Assistant-Karte
- GPS-Sensoren für Breiten- und Längengrad, Höhe, Satelliten, HDOP,
  Satellitenfix, Geschwindigkeit und Kurs
- Entfernung zur konfigurierbaren Heimatposition sowie sechsstelliger
  Maidenhead-Locator
- Primärband sowie alle aktiven Carrier-Aggregation-Bänder mit Signaldetails
- IMEI, UICC/ICCID und Mobilfunk-Registrierungsstatus
- aktive physische SIM als Sensor und auswählbare `select`-Entität
- aktives eSIM-Profil als Sensor und auswählbare `select`-Entität auf
  RUTX50-eSIM-Hardware
- aktive Internetverbindung aus Multi-WAN/Failover einschließlich Typ, IP,
  Modem und SIM als Attribute
- aktuelle WAN-IP-Adresse, Router-Firmware und Betriebszeit
- DHCP-Erkennung, Reauthentifizierung und URL-Behandlung der Core-Integration

Nicht unterstützte optionale Endpunkte (GPS, Failover oder eSIM) werden
automatisch erkannt und beeinträchtigen die übrigen Entitäten nicht.

## Heimatposition und HAM-Locator

Der Sensor **Entfernung nach Hause** verwendet standardmäßig die in Home
Assistant konfigurierte Heimatposition. Über
**Einstellungen → Geräte & Dienste → Teltonika → Konfigurieren** können
Breiten- und Längengrad je Router überschrieben werden. Die Entfernung wird als
Großkreisentfernung nach der Haversine-Formel in Kilometern berechnet.

Der **Maidenhead-Locator** wird als sechsstelliger Locator aus der aktuellen
GPS-Position berechnet. Solange der Router keinen Satellitenfix meldet, bleiben
beide berechneten Sensoren unbekannt, damit die vom Router gelieferten
Nullkoordinaten nicht als echte Position interpretiert werden.

IMEI und UICC/ICCID sind eindeutige Geräte- beziehungsweise
Teilnehmerkennungen. Bei der Weitergabe von Screenshots oder Diagnosedaten
sollten diese Werte anonymisiert werden.

## Installation

### HACS

1. HACS öffnen und zu **Integrationen** wechseln.
2. Über das Menü **Benutzerdefinierte Repositories** öffnen.
3. `https://github.com/trinler007/HA-Teltonika` als Typ **Integration**
   hinzufügen.
4. **HA Teltonika Extended** installieren und Home Assistant neu starten.

### Manuell

Den Ordner `custom_components/teltonika` nach
`<config>/custom_components/teltonika` kopieren und Home Assistant neu starten.

Wenn die Core-Integration bereits eingerichtet ist, bleibt der bestehende
Config Entry erhalten. Home Assistant protokolliert beim Start erwartungsgemäß,
dass eine Custom Integration die eingebaute Integration überschreibt.

## SIM-Auswahl

Für Dual-SIM-Modems stellt die Integration eine Select-Entität mit `SIM 1` und
`SIM 2` bereit. Der Router wird nur dann umgeschaltet, wenn die gewählte SIM
nicht bereits aktiv ist. Die Teltonika-API bietet dafür eine
„zur nächsten SIM wechseln“-Aktion; die direkte Auswahl wird durch Vergleich
mit `active_sim` sicher darauf abgebildet.

eSIM-Entitäten werden ausschließlich erstellt, wenn der Router Profile über
`/api/esim/config` meldet. Beim Auswählen wird das gewählte Profil aktiviert.

## Beispiel für eine Dashboard-Karte

Die eingebauten Tile Cards benötigen keine zusätzliche Frontend-Erweiterung.
Die tatsächlichen Entity IDs können je nach Gerätename abweichen:

```yaml
type: grid
columns: 2
square: false
cards:
  - type: tile
    entity: select.rutx50_internal_modem_active_sim
    name: Aktive SIM
    icon: mdi:sim
    features:
      - type: select-options
  - type: tile
    entity: sensor.rutx50_active_internet_connection
    name: Internet
    icon: mdi:wan
  - type: tile
    entity: sensor.rutx50_internal_modem_carrier_aggregation_bands
    name: Mobilfunkbänder
    icon: mdi:signal
  - type: map
    entities:
      - device_tracker.rutx50_gps_location
    hours_to_show: 24
```

Bei RUTX50-eSIM-Hardware kann eine weitere Tile Card für die erzeugte
`select.*_active_esim_profile`-Entität ergänzt werden.

## Quellen, Herkunft und Markenrechte

Für Entwicklung und Dokumentation wurden insbesondere folgende Quellen
verwendet:

- [Home-Assistant-Core-Integration `teltonika`](https://github.com/home-assistant/core/tree/dev/homeassistant/components/teltonika);
  die konkrete Upstream-Basis ist
  [Commit `702a9cb`](https://github.com/home-assistant/core/commit/702a9cb7289e535927f5279190bcad6ffc5d3fd0)
- [`teltasync`](https://codeberg.org/dmho/teltasync), die von der
  Home-Assistant-Integration verwendete API-Clientbibliothek
- [Teltonika RUTX50 API 7.24.1](https://developers.teltonika-networks.com/reference/RUTX50/7.24.1/)
- [Teltonika RUTX50 Manual](https://wiki.teltonika-networks.com/view/RUTX50_Manual)
- [offizielle Teltonika Brand Guidelines und Brand Assets](https://www.teltonika-iot-group.com/brand-guidelines)

Der von Home Assistant abgeleitete Quellcode und `teltasync` stehen unter der
Apache License 2.0. Änderungen und Ergänzungen dieses Projekts werden ebenfalls
unter der in [LICENSE.md](LICENSE.md) enthaltenen Apache License 2.0
bereitgestellt.

**Markenhinweis:** Teltonika, die Namen der Teltonika-Produkte, das
Teltonika-Logo und weitere Markenelemente gehören den jeweiligen Unternehmen
der Teltonika-Gruppe. Dieses unabhängige Open-Source-Projekt ist weder mit
Teltonika verbunden noch von Teltonika gesponsert oder offiziell unterstützt.
Das in `custom_components/teltonika/brand` enthaltene offizielle Logo wird
ausschließlich zur Identifikation der unterstützten Produkte verwendet. Für
seine Verwendung gelten die Teltonika Brand Guidelines; durch die
Apache-2.0-Lizenz dieses Projekts werden keine Rechte an Namen, Marken oder
Logos von Teltonika eingeräumt.

Die API-Felder wurden gegen RutOS 7.24.1 / Web API v1.16.1 entwickelt. Ältere
Firmware kann weniger Entitäten bereitstellen.

## Entwicklung

Die Upstream-Basis und das Verfahren zum Übernehmen neuer Core-Änderungen sind
in [UPSTREAM.md](UPSTREAM.md) dokumentiert. Fehlerberichte sollten möglichst
Diagnosedaten bzw. anonymisierte JSON-Antworten der betroffenen API-Endpunkte
enthalten; Zugangsdaten, Tokens, ICCID, IMSI, IMEI und öffentliche IP-Adressen
müssen vorher entfernt werden.

## Lizenz

Apache License 2.0, entsprechend der Home-Assistant-Core-Integration.
