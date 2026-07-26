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
  Satellitenfix, Geschwindigkeit, Kurs und Kursrichtung auf einer
  16-teiligen Windrose
- optionaler TCP-NMEA-Empfänger für GPS-Livewerte ohne engmaschiges
  API-Polling
- Diagnose-Binärsensor für TCP-Verbindung und zuletzt empfangene NMEA-Daten
- Entfernung zur konfigurierbaren Heimatposition sowie sechsstelliger
  Maidenhead-Locator
- optionaler weltweiter Ortsnamensensor über einen konfigurierbaren
  Nominatim-kompatiblen Reverse-Geocoding-Dienst
- Primärband sowie alle aktiven Carrier-Aggregation-Bänder mit Signaldetails
- geschätzte Download-Spitzenkapazität aus Funkstandard, Kanalbandbreite und
  Signalqualität sowie eine für Sprachassistenten geeignete Beschreibung
- zusammengefasste Mobilfunk-Signalqualität mit 0 bis 4 Balken
- IMEI, UICC/ICCID und Mobilfunk-Registrierungsstatus
- aktive physische SIM als Sensor und auswählbare `select`-Entität
- je ein Aktionsbutton für SIM 1 und SIM 2
- aktives eSIM-Profil als Sensor und auswählbare `select`-Entität auf
  RUTX50-eSIM-Hardware
- aktive Internetverbindung aus Multi-WAN/Failover einschließlich Typ, IP,
  Modem und SIM als Attribute
- aktuelle WAN-IP-Adresse, Router-Firmware und Betriebszeit
- Mobilfunk-Datenverbrauch für heute, gestern, aktuellen Monat und Vormonat,
  jeweils als RX, TX und Gesamt
- DHCP-Erkennung, Reauthentifizierung und URL-Behandlung der Core-Integration
- konfigurierbares Router-API-Abfrageintervall von 10 bis 3600 Sekunden

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

Der Sensor **GPS-Kursrichtung** übersetzt den Kurswinkel ohne zusätzliche
Router-Abfrage in eine 16-teilige Windrose. Bei deutscher Home-Assistant-Sprache
werden `N`, `NNO`, `NO`, `ONO`, `O`, `OSO`, `SO`, `SSO`, `S`, `SSW`, `SW`,
`WSW`, `W`, `WNW`, `NW` und `NNW` verwendet. Bei englischer Sprache werden
die entsprechenden Kürzel mit `E` ausgegeben. Ohne gültigen Satellitenfix
bleibt der Sensor unbekannt.

## GPS-Livewerte über NMEA

Über **Einstellungen → Geräte & Dienste → Teltonika → Konfigurieren** kann ein
TCP-NMEA-Empfänger aktiviert werden. Home Assistant lauscht dann standardmäßig
auf Port `8500`; der Port kann pro Integrationseintrag geändert werden. Im
Router wird die NMEA-Weiterleitung auf die IP-Adresse des Home-Assistant-Hosts
und diesen Port konfiguriert.

Die Integration verarbeitet GGA- und RMC-Sätze mit beliebiger Talker-ID, zum
Beispiel `$GPGGA`, `$GNGGA`, `$GPRMC` und `$GNRMC`. Dadurch werden Position,
Höhe, Satellitenzahl, HDOP, Fixstatus, Geschwindigkeit und Kurs unmittelbar
aktualisiert. Geschwindigkeit aus RMC wird von Knoten in km/h umgerechnet.

Solange aktuelle NMEA-Daten eintreffen, wird der GPS-Endpunkt der Router-API
nicht abgefragt. Bleibt der Stream länger als 15 Sekunden aus, verwendet der
nächste reguläre 30-Sekunden-Zyklus automatisch wieder die API. Das Attribut
`source` der GPS-Sensoren zeigt `nmea` oder `api`.

Der Diagnose-Binärsensor **NMEA-TCP-Status** ist eingeschaltet, solange eine
TCP-Verbindung des Routers besteht oder innerhalb der letzten 30 Sekunden ein
gültiger NMEA-Satz empfangen wurde. Seine Attribute zeigen, ob der Empfänger
aktiviert ist, ob aktuell eine TCP-Verbindung besteht, den Port und den
Zeitpunkt des letzten gültigen Satzes.

Der Port muss vom Router aus erreichbar sein. Bei einer Home-Assistant-
Containerinstallation muss er gegebenenfalls zusätzlich als TCP-Port
veröffentlicht werden. Der NMEA-Empfänger besitzt keine Authentifizierung und
sollte deshalb nur in einem vertrauenswürdigen lokalen Netz freigegeben werden.

Das reguläre Router-API-Abfrageintervall kann auf derselben Optionsseite
zwischen 10 und 3600 Sekunden eingestellt werden; Standard sind 30 Sekunden.
NMEA-Liveaktualisierungen und die gedrosselte Datenverbrauchsabfrage sind davon
unabhängig. Eingehende NMEA-Sätze benachrichtigen die GPS-Entitäten direkt,
ohne den Timer des regulären API-Pollings zurückzusetzen. Dadurch bleiben
Mobilfunk-, SIM- und Interfacewerte auch bei einem kontinuierlichen
NMEA-Stream aktuell.

IMEI und UICC/ICCID sind eindeutige Geräte- beziehungsweise
Teilnehmerkennungen. Bei der Weitergabe von Screenshots oder Diagnosedaten
sollten diese Werte anonymisiert werden.

## Verbindungsqualität und geschätzte Kapazität

Der Sensor **Geschätzte Download-Kapazität** berechnet aus dem Funkstandard,
den aktiven CA-Trägern, deren Kanalbandbreiten sowie RSRP, RSRQ und SINR die
obere Grenze eines plausiblen Download-Spitzenbereichs in Mbit/s. Die Attribute
enthalten zusätzlich die untere Grenze, den Signal-Qualitätswert, den
limitierenden Funkwert, die verwendeten Bänder, die gesamte Kanalbandbreite,
eine Vertrauensstufe und die rein technische Funkobergrenze.

Der Sensor **Beschreibung der Verbindungsqualität** fasst dieselben Daten als
kurzen deutschen beziehungsweise englischen Text zusammen. RSRP, RSRQ und SINR
werden dabei jeweils mit Messwert und Einzelbewertung genannt, statt nur den
schwächsten Faktor allgemein zu beschreiben. Der Sensor eignet sich damit
beispielsweise als Antwort eines Sprachassistenten.

Der Sensor **Signalqualität Balken** bildet die Gesamtbewertung wie eine
Mobilfunkanzeige auf Werte von 0 bis 4 ab. 1 Balken entspricht 0 bis
24 Prozent, 2 Balken 25 bis 49 Prozent, 3 Balken 50 bis 74 Prozent und
4 Balken 75 bis 100 Prozent. 0 Balken bedeutet ausschließlich, dass keine
Mobilfunkverbindung besteht. Besteht eine Verbindung, fehlen aber verwertbare
Signalwerte, bleibt der Sensor unbekannt.

Die Kapazitätswerte sind Schätzungen der Funkstrecke und keine
Geschwindigkeitsmessung. Aus dem Routerstatus sind insbesondere
Zellenauslastung, Drosselung durch den Provider, Kapazität der
Basisstationsanbindung und Protokoll-Overhead nicht bekannt. Die genannte
Spanne gilt deshalb nur als unter günstigen Bedingungen plausible Spitzenrate
und kann deutlich von einem Speedtest abweichen.

### Signalbalken auf einem openHASP-Display

Die Werte 0 bis 4 eignen sich für eine kompakte Anzeige mit den
Material-Design-Icons `signal-off`, `signal-cellular-outline` und
`signal-cellular-1` bis `signal-cellular-3`. In einem Node-RED-Function-Node
können die openHASP-Unicode-Codepoints beispielsweise so zugeordnet werden:

```javascript
const mdi = {
  0: 0xF0783, // signal-off
  1: 0xF08BF, // signal-cellular-outline
  2: 0xF08BC, // signal-cellular-1
  3: 0xF08BD, // signal-cellular-2
  4: 0xF08BE, // signal-cellular-3
};

const bars = Math.max(0, Math.min(Number(msg.payload) || 0, 4));
msg.payload = String.fromCodePoint(mdi[bars]);
return msg;
```

Alternativ kann die Zuordnung direkt in einem openHASP-YAML-Template erfolgen:

```yaml
objects:
  - obj: "p0b13"
    properties:
      text: >
        {% set bars =
          states('sensor.technik_nx01_gw01_internal_modem_signalqualitat_balken')
          | int(0)
        %}
        {% set icons = {
          0: "\U000F0783",
          1: "\U000F08BF",
          2: "\U000F08BC",
          3: "\U000F08BD",
          4: "\U000F08BE"
        } %}
        {{ icons.get([0, [bars, 4] | min] | max, "\U000F0783") }}
```

Die Entity ID und die openHASP-Objekt-ID müssen an die eigene Installation
angepasst werden. Die verwendete openHASP-Schriftart muss die genannten
Material-Design-Icons enthalten.

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

Für Dual-SIM- und entsprechend gekennzeichnete eSIM-Modems stellt die
Integration eine Select-Entität mit `SIM 1` und `SIM 2` sowie je einen Button
für beide Slots bereit. Der Router wird nur dann umgeschaltet, wenn die
gewählte SIM nicht bereits aktiv ist. Wenn `/api/sim_cards/config` verfügbar
ist, setzt die Integration den gewählten Eintrag direkt als Standard und
startet die Mobilfunkverbindung neu. Bei älteren Dual-SIM-Geräten bleibt die
Teltonika-Aktion „zur nächsten SIM wechseln“ als Fallback erhalten.
Nach einer manuellen Umschaltung fragt die Integration vorübergehend nur den
Modemstatus in kurzen Abständen ab. Betreiber, Registrierung, Signalwerte und
weitere Mobilfunkdaten werden dadurch aktualisiert, sobald RutOS die Ziel-SIM
als vollständig initialisiert meldet. Anschließend gilt wieder ausschließlich
das konfigurierte reguläre Pollingintervall.

Auf eSIM-fähiger Hardware enthält die gemeinsame SIM-Quellenauswahl zusätzlich
`eSIM`, auch wenn `/api/esim/config` bei aktiver physischer SIM noch keine
Profile liefert. Die Auswahl setzt den eSIM-Eintrag über
`/api/sim_cards/config` als Standard, startet die Mobilfunkverbindung neu und
fragt die Profile anschließend erneut ab. Dafür steht auch ein eigener
eSIM-Auswahlbutton bereit. Sobald Profile sichtbar sind, erscheinen sie als
`eSIM: Profilname`; zusätzlich wird die separate Profilauswahl angelegt.
Profile ohne Modem-ID werden bei genau einem Modem diesem Modem zugeordnet.

## Mobilfunk-Datenverbrauch

Die Integration liest die vom Router gespeicherte Historie über
`/api/data_usage/custom/status`. Sie stellt RX, TX und Gesamt jeweils für
**heute**, **gestern**, den **aktuellen Monat** und den **Vormonat** in Bytes
bereit. Home Assistant kann diese Werte über die Geräteklasse automatisch in
MB oder GB darstellen.

Tageswerte werden nativ in MB, Monatswerte nativ in GB ausgegeben. Der exakte
vom Router gelieferte Ausgangswert in Bytes bleibt jeweils als Attribut
`raw_bytes` verfügbar. Beim Update von 0.5.1 auf 0.5.2 werden die von älteren
Versionen in der Home-Assistant-Entity-Registry gespeicherten
Byte-Anzeigeeinheiten einmalig auf MB beziehungsweise GB migriert. Eine vom
Benutzer ausdrücklich gewählte Anzeigeeinheit bleibt erhalten.

Laufende Zeiträume werden höchstens alle fünf Minuten abgefragt. Abgeschlossene
Zeiträume werden zwischengespeichert und nur nach einem Tages- oder
Monatswechsel neu geladen. Dadurch entstehen im normalen Betrieb lediglich
zwei zusätzliche API-Abfragen je fünf Minuten.

## Weltweiter Ortsname

Optional kann über die Integrationsoptionen der Sensor **Aktueller Ort**
aktiviert werden. Standardmäßig nutzt er den öffentlichen
OpenStreetMap-Nominatim-Dienst, der weltweit arbeitet und keinen API-Schlüssel
benötigt. Die Dienst-URL ist konfigurierbar und kann auf eine eigene oder
andere Nominatim-kompatible Instanz zeigen.

Eine Abfrage erfolgt höchstens alle 15 Minuten und nur nach mindestens einem
Kilometer Bewegung. Das Ergebnis wird zwischengespeichert. Der Sensor bevorzugt
Stadt, Ort oder Gemeinde und fällt für dünn besiedelte Regionen auf Landkreis,
Region oder Land zurück. Der vollständige Anzeigename, das Land und die
OpenStreetMap-Attribution stehen als Attribute zur Verfügung.

Bei Aktivierung werden GPS-Koordinaten an den eingestellten Dienst übertragen.
Für den öffentlichen Standarddienst gelten die
[Nominatim Usage Policy](https://operations.osmfoundation.org/policies/nominatim/)
und die [OpenStreetMap-Urheberrechtshinweise](https://www.openstreetmap.org/copyright).

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
  - type: button
    entity: button.rutx50_internal_modem_select_sim_1
    name: SIM 1
    icon: mdi:sim
  - type: button
    entity: button.rutx50_internal_modem_select_sim_2
    name: SIM 2
    icon: mdi:sim
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
