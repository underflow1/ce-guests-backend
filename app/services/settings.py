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
        # Удаляем устаревшие/неизвестные коды уведомлений, чтобы не падало сохранение настроек
        normalized_enabled_types = []
        seen = set()
        for notification_type in enabled_types:
            if notification_type not in NOTIFICATION_TYPE_CODES:
                continue
            if notification_type in seen:
                continue
            seen.add(notification_type)
            normalized_enabled_types.append(notification_type)
        defaults["enabled_notification_types"] = normalized_enabled_types

    return defaults


def build_default_pass_integration() -> Dict[str, Any]:
    return {
        "enabled": False,
        "base_url": None,
        "login": None,
        "password": None,
        "object": None,
        "corpa": None,
    }


def normalize_pass_integration(value: Any) -> Dict[str, Any]:
    defaults = build_default_pass_integration()
    if not isinstance(value, dict):
        return defaults

    for key in ["enabled", "base_url", "login", "password", "object", "corpa"]:
        if key in value:
            defaults[key] = value.get(key)

    # Приводим enabled к bool на всякий случай
    defaults["enabled"] = bool(defaults.get("enabled"))
    return defaults


def build_default_production_calendar() -> Dict[str, Any]:
    return {
        "enabled": False,
    }


def normalize_production_calendar(value: Any) -> Dict[str, Any]:
    defaults = build_default_production_calendar()
    if not isinstance(value, dict):
        return defaults

    if "enabled" in value:
        defaults["enabled"] = bool(value.get("enabled"))

    return defaults


def build_default_phone_notifications() -> Dict[str, Any]:
    from app.schemas.setting import DEFAULT_ARRIVAL_TEMPLATE

    return {
        "enabled": False,
        "extension": None,
        "arrival_template": DEFAULT_ARRIVAL_TEMPLATE,
        "call_cooldown_seconds": 10,
        "ami": {
            "host": None,
            "port": 5038,
            "username": None,
            "password": None,
        },
        "freepbx": {
            "ssh_host": None,
            "ssh_user": None,
            "ssh_key": None,
            "sounds_path": None,
        },
    }


def normalize_phone_notifications(value: Any) -> Dict[str, Any]:
    defaults = build_default_phone_notifications()
    if not isinstance(value, dict):
        return defaults

    if "enabled" in value:
        defaults["enabled"] = bool(value.get("enabled"))
    if "extension" in value:
        defaults["extension"] = value.get("extension")
    if "arrival_template" in value:
        defaults["arrival_template"] = value.get("arrival_template")
    if "call_cooldown_seconds" in value and isinstance(value.get("call_cooldown_seconds"), (int, float)):
        defaults["call_cooldown_seconds"] = max(1, int(value["call_cooldown_seconds"]))

    ami = value.get("ami")
    if isinstance(ami, dict):
        for key in ["host", "port", "username", "password"]:
            if key in ami:
                defaults["ami"][key] = ami[key]

    freepbx = value.get("freepbx")
    if isinstance(freepbx, dict):
        for key in ["ssh_host", "ssh_user", "ssh_key", "sounds_path"]:
            if key in freepbx:
                defaults["freepbx"][key] = freepbx[key]

    return defaults


def build_settings_metadata() -> Dict[str, Any]:
    return {
        "notifications": {
            "available_types": NOTIFICATION_TYPES
        }
    }
