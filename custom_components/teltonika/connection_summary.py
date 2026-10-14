"""Short voice-assistant summaries for cellular connections."""

from __future__ import annotations

from typing import Any


def describe_mobile_connection_brief(
    assessment: Any,
    language: str,
    *,
    roaming: bool = False,
    sms_limit: int | None = None,
    sms_sent: int | None = None,
    data_limit_bytes: int | None = None,
    data_used_bytes: int | None = None,
    data_warning_bytes: int | None = None,
) -> str:
    """Render a short cellular summary suitable for voice assistants."""
    german = language.lower().startswith("de")
    if not assessment.connected:
        return (
            "Mobilfunk: nicht verbunden, 0 von 4 Balken."
            if german
            else "Cellular: disconnected, 0 out of 4 bars."
        )

    quality_labels = {
        "de": {
            "excellent": "ausgezeichnet",
            "very_good": "sehr gut",
            "good": "gut",
            "fair": "mäßig",
            "poor": "schlecht",
            "unknown": "nicht bewertbar",
        },
        "en": {
            "excellent": "excellent",
            "very_good": "very good",
            "good": "good",
            "fair": "fair",
            "poor": "poor",
            "unknown": "unavailable",
        },
    }
    locale = "de" if german else "en"
    quality = quality_labels[locale][assessment.quality]
    bars = assessment.signal_bars
    if bars is None:
        bars_text = "Balken nicht bewertbar" if german else "bars unavailable"
    else:
        bars_text = (
            f"{bars} von 4 Balken" if german else f"{bars} out of 4 bars"
        )
    if german:
        network = "im Roamingnetz" if roaming else "im Heimatnetz"
    else:
        network = "while roaming" if roaming else "on the home network"
    text = f"{assessment.technology}: {quality}, {bars_text} {network}."

    warnings: list[str] = []
    if sms_limit is not None and sms_sent is not None and sms_limit > 0:
        ratio = sms_sent / sms_limit
        if ratio >= 1:
            warnings.append("SMS-Limit erreicht" if german else "SMS limit reached")
        elif ratio >= 0.8:
            warnings.append(
                "SMS-Limit fast erreicht" if german else "SMS limit nearly reached"
            )

    if (
        data_limit_bytes is not None
        and data_used_bytes is not None
        and data_limit_bytes > 0
    ):
        default_warning = round(data_limit_bytes * 0.8)
        warning_threshold = min(data_warning_bytes or default_warning, default_warning)
        if data_used_bytes >= data_limit_bytes:
            warnings.append(
                "Datenlimit erreicht" if german else "data limit reached"
            )
        elif data_used_bytes >= warning_threshold:
            warnings.append(
                "Datenlimit fast erreicht" if german else "data limit nearly reached"
            )

    if warnings:
        text += " " + "; ".join(warnings) + "."
    return text
