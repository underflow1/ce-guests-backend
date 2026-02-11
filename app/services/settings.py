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


def build_settings_metadata() -> Dict[str, Any]:
    return {
        "notifications": {
            "available_types": NOTIFICATION_TYPES
        }
    }
