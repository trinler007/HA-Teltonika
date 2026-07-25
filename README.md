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
  Geschwindigkeit und Kurs
- Primärband sowie alle aktiven Carrier-Aggregation-Bänder mit Signaldetails
- aktive physische SIM als Sensor und auswählbare `select`-Entität
- aktives eSIM-Profil als Sensor und auswählbare `select`-Entität auf
  RUTX50-eSIM-Hardware
- aktive Internetverbindung aus Multi-WAN/Failover einschließlich Typ, IP,
  Modem und SIM als Attribute
- DHCP-Erkennung, Reauthentifizierung und URL-Behandlung der Core-Integration

Nicht unterstützte optionale Endpunkte (GPS, Failover oder eSIM) werden
automatisch erkannt und beeinträchtigen die übrigen Entitäten nicht.

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

## Quellen und Kompatibilität

- [Home-Assistant-Core-Integration](https://github.com/home-assistant/core/tree/dev/homeassistant/components/teltonika)
- [Teltonika RUTX50 API 7.24.1](https://developers.teltonika-networks.com/reference/RUTX50/7.24.1/)
- [RUTX50-Handbuch](https://wiki.teltonika-networks.com/view/RUTX50_Manual)

Die API-Felder wurden gegen RutOS 7.24.1 / Web API v1.16.1 entwickelt. Ältere
Firmware kann weniger Entitäten bereitstellen. Der eigentliche Routerzugriff
verwendet weiterhin die auch von Home Assistant eingesetzte Bibliothek
`teltasync`.

## Entwicklung

Die Upstream-Basis und das Verfahren zum Übernehmen neuer Core-Änderungen sind
in [UPSTREAM.md](UPSTREAM.md) dokumentiert. Fehlerberichte sollten möglichst
Diagnosedaten bzw. anonymisierte JSON-Antworten der betroffenen API-Endpunkte
enthalten; Zugangsdaten, Tokens, ICCID, IMSI, IMEI und öffentliche IP-Adressen
müssen vorher entfernt werden.

## Lizenz

Apache License 2.0, entsprechend der Home-Assistant-Core-Integration.
