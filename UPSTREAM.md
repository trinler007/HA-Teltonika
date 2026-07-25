# Upstream-Pflege

## Aktuelle Basis

Die Dateien unter `custom_components/teltonika` wurden am 25. Juli 2026 von
`home-assistant/core` Branch `dev`, Commit
`702a9cb7289e535927f5279190bcad6ffc5d3fd0`, übernommen.

Die ursprünglichen Dateinamen und die Domain `teltonika` wurden bewusst
beibehalten. Erweiterungen sind hauptsächlich auf folgende Dateien begrenzt:

- `coordinator.py`: zusätzliche optionale API-Endpunkte und Schreibaktionen
- `sensor.py`: zusätzliche Modem-, GPS- und WAN-Sensoren
- `device_tracker.py`: GPS-Kartenentität
- `select.py`: SIM- und eSIM-Auswahl
- `manifest.json`, `strings.json`, `translations/*`: Custom-Metadaten und Texte

`config_flow.py` und `util.py` entsprechen der Upstream-Implementierung. Dadurch
lassen sich Änderungen an Einrichtung, DHCP und Reauthentifizierung in der
Regel direkt übernehmen.

## Empfohlener Aktualisierungsablauf

1. Den aktuellen Core-Stand schlank auschecken:

   ```bash
   git clone --depth 1 --filter=blob:none --sparse \
     --branch dev https://github.com/home-assistant/core.git ../ha-core
   git -C ../ha-core sparse-checkout set \
     homeassistant/components/teltonika tests/components/teltonika
   ```

2. Unveränderte bzw. nah am Upstream gehaltene Dateien vergleichen:

   ```bash
   git diff --no-index \
     ../ha-core/homeassistant/components/teltonika/config_flow.py \
     custom_components/teltonika/config_flow.py
   ```

3. Core-Änderungen zuerst in einem separaten Commit übernehmen.
4. Danach die Erweiterungen bei Konflikten anpassen und Tests ausführen.
5. Die Commit-ID unter „Aktuelle Basis“ aktualisieren.

Ein separater Upstream-Sync-Commit hält die Historie für spätere Vergleiche
lesbar.
