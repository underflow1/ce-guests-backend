from typing import Any, Dict

from app.schemas.setting import NOTIFICATION_TYPES, NOTIFICATION_TYPE_CODES


def build_default_notifications() -> Dict[str, Any]:
    return {
        "providers": {
            "max_via_green_api": {"enabled": False},
            "telegram": {"enabled": False},
        },
        "enabled_notification_types": list(NOTIFICATION_TYPE_CODES),
    }


def normalize_notifications(value: Any) -> Dict[str, Any]:
    defaults = build_default_notifications()
    if not isinstance(value, dict):
        return defaults

    providers = value.get("providers")
    if isinstance(providers, dict):
        for provider_key in defaults["providers"].keys():
            provider_value = providers.get(provider_key)
            if isinstance(provider_value, dict):
                defaults["providers"][provider_key].update(provider_value)

    enabled_types = value.get("enabled_notification_types")
    if isinstance(enabled_types, list):
        defaults["enabled_notification_types"] = enabled_types

    return defaults


def build_settings_metadata() -> Dict[str, Any]:
    return {
        "notifications": {
            "available_types": NOTIFICATION_TYPES
        }
    }
