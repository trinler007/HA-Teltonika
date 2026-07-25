"""Constants for the Teltonika integration."""

DOMAIN = "teltonika"

CONF_HOME_LATITUDE = "home_latitude"
CONF_HOME_LONGITUDE = "home_longitude"
CONF_POLL_INTERVAL = "poll_interval"
CONF_NMEA_ENABLED = "nmea_enabled"
CONF_NMEA_PORT = "nmea_port"
CONF_REVERSE_GEOCODING_ENABLED = "reverse_geocoding_enabled"
CONF_REVERSE_GEOCODING_URL = "reverse_geocoding_url"

DEFAULT_NMEA_PORT = 8500
DEFAULT_POLL_INTERVAL = 30
DEFAULT_REVERSE_GEOCODING_URL = "https://nominatim.openstreetmap.org/reverse"
