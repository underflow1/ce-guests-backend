from typing import List, Optional
from pydantic import BaseModel, Field


NOTIFICATION_TYPES = [
    {"code": "entry_created", "title": "Создание записи"},
    {"code": "entry_updated", "title": "Обновление записи"},
    {"code": "entry_arrived", "title": "Гость отмечен как прибывший"},
    {"code": "entry_rollback", "title": "Состояние записи откатано"},
    {"code": "result_set", "title": "Результат установлен"},
    {"code": "visit_cancelled", "title": "Визит отменен"},
    {"code": "entry_moved", "title": "Перенос записи"},
    {"code": "entry_deleted", "title": "Удаление записи"},
    {"code": "entries_deleted_all", "title": "Удаление всех записей"},
    {"code": "pass_ordered", "title": "Пропуск заказан"},
    {"code": "pass_order_failed", "title": "Не удалось заказать пропуск"},
    {"code": "pass_revoked", "title": "Пропуск отозван"},
]

NOTIFICATION_TYPE_CODES = [item["code"] for item in NOTIFICATION_TYPES]


class NotificationProviderMaxViaGreenApi(BaseModel):
    enabled: bool = False
    base_url: Optional[str] = None
    instance_id: Optional[str] = None
    api_token: Optional[str] = None
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


class PassIntegrationSettings(BaseModel):
    enabled: bool = False
    base_url: Optional[str] = None
    login: Optional[str] = None
    password: Optional[str] = None
    object: Optional[str] = None
    corpa: Optional[str] = None


class ProductionCalendarStatus(BaseModel):
    current_year: int
    loaded_days_count: int
    expected_days_count: int
    missing_days_count: int
    is_loaded_for_current_year: bool
    is_complete_for_current_year: bool
    last_loaded_at: Optional[str] = None
    last_cleared_at: Optional[str] = None


class ProductionCalendarSettings(BaseModel):
    enabled: bool = False
    status: Optional[ProductionCalendarStatus] = None


class PhoneNotificationsAmi(BaseModel):
    host: Optional[str] = None
    port: int = 5038
    username: Optional[str] = None
    password: Optional[str] = None


class PhoneNotificationsFreepbx(BaseModel):
    ssh_host: Optional[str] = None
    ssh_user: Optional[str] = None
    ssh_key: Optional[str] = None
    sounds_path: Optional[str] = None


DEFAULT_ARRIVAL_TEMPLATE = (
    "Привет девчонки, это оперативный дежурный беспокоит, тут подошел %GUESTNAME%, просьба встретить."
)


class PhoneNotificationsSettings(BaseModel):
    enabled: bool = False
    extension: Optional[str] = None
    arrival_template: Optional[str] = None
    call_cooldown_seconds: int = 10
    ami: PhoneNotificationsAmi = Field(default_factory=PhoneNotificationsAmi)
    freepbx: PhoneNotificationsFreepbx = Field(default_factory=PhoneNotificationsFreepbx)


class SettingsUpdateRequest(BaseModel):
    notifications: NotificationsSettings
    pass_integration: PassIntegrationSettings = Field(default_factory=PassIntegrationSettings)
    production_calendar: ProductionCalendarSettings = Field(default_factory=ProductionCalendarSettings)
    phone_notifications: PhoneNotificationsSettings = Field(default_factory=PhoneNotificationsSettings)


class NotificationTypeMeta(BaseModel):
    code: str
    title: str


class NotificationsMeta(BaseModel):
    available_types: List[NotificationTypeMeta]


class SettingsMeta(BaseModel):
    notifications: NotificationsMeta


class SettingsResponse(BaseModel):
    notifications: NotificationsSettings
    pass_integration: PassIntegrationSettings
    production_calendar: ProductionCalendarSettings
    phone_notifications: PhoneNotificationsSettings
    metadata: SettingsMeta
