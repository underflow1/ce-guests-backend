from typing import List, Optional
from pydantic import BaseModel, Field


NOTIFICATION_TYPES = [
    {"code": "entry_created", "title": "Создание записи"},
    {"code": "entry_updated", "title": "Обновление записи"},
    {"code": "entry_completed", "title": "Гость отмечен как пришедший"},
    {"code": "entry_uncompleted", "title": "Снята отметка о приходе"},
    {"code": "entry_moved", "title": "Перенос записи"},
    {"code": "entry_deleted", "title": "Удаление записи"},
    {"code": "entries_deleted_all", "title": "Удаление всех записей"},
]

NOTIFICATION_TYPE_CODES = [item["code"] for item in NOTIFICATION_TYPES]


class NotificationProviderMaxViaGreenApi(BaseModel):
    enabled: bool = False
    url: Optional[str] = None
    chat_id: Optional[str] = None


class NotificationProviderTelegram(BaseModel):
    enabled: bool = False
    bot_token: Optional[str] = None
    chat_id: Optional[str] = None


class NotificationProviders(BaseModel):
    max_via_green_api: NotificationProviderMaxViaGreenApi = Field(default_factory=NotificationProviderMaxViaGreenApi)
    telegram: NotificationProviderTelegram = Field(default_factory=NotificationProviderTelegram)


class NotificationsSettings(BaseModel):
    providers: NotificationProviders = Field(default_factory=NotificationProviders)
    enabled_notification_types: List[str] = Field(default_factory=list)


class SettingsUpdateRequest(BaseModel):
    notifications: NotificationsSettings


class NotificationTypeMeta(BaseModel):
    code: str
    title: str


class NotificationsMeta(BaseModel):
    available_types: List[NotificationTypeMeta]


class SettingsMeta(BaseModel):
    notifications: NotificationsMeta


class SettingsResponse(BaseModel):
    notifications: NotificationsSettings
    metadata: SettingsMeta
