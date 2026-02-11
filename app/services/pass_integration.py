import json
import time
from datetime import datetime
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.config import settings
from app.models.setting import Setting
from app.services.settings import normalize_pass_integration


class PassIntegrationError(Exception):
    pass


class PassIntegrationAmbiguousError(PassIntegrationError):
    pass


class PassIntegrationDisabledError(PassIntegrationError):
    pass


def _normalize_name(value: Any) -> str:
    return str(value or "").strip().casefold()


def _normalize_date(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d.%m.%Y"):
        try:
            return datetime.strptime(raw, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return raw


def _to_ddmmyyyy(date_iso: str) -> str:
    dt = datetime.strptime(date_iso, "%Y-%m-%d")
    return dt.strftime("%d%m%Y")


def _extract_orders(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    message = payload.get("message")
    if not isinstance(message, list):
        return []
    return [item for item in message if isinstance(item, dict)]


def _split_full_name(full_name: str) -> tuple[str, str, str]:
    parts = [p for p in (full_name or "").strip().split() if p]
    if len(parts) >= 3:
        return parts[0], parts[1], " ".join(parts[2:])
    if len(parts) == 2:
        return parts[0], parts[1], "-"
    if len(parts) == 1:
        return parts[0], "-", "-"
    return "-", "-", "-"


def _matches_identity(order: dict[str, Any], surname: str, name: str, fathername: str, birthday: str) -> bool:
    return (
        _normalize_name(order.get("фамилия")) == _normalize_name(surname)
        and _normalize_name(order.get("имя")) == _normalize_name(name)
        and _normalize_name(order.get("отчество")) == _normalize_name(fathername)
        and _normalize_date(order.get("датарождения")) == _normalize_date(birthday)
    )


def _load_pass_integration_config(db: Session) -> dict[str, str]:
    record = db.query(Setting).filter(Setting.key == "pass_integration").first()
    payload: dict[str, Any] = {}
    if record and record.value:
        try:
            payload = normalize_pass_integration(json.loads(record.value))
        except Exception:
            payload = {}

    if not bool(payload.get("enabled")):
        raise PassIntegrationDisabledError("Заказ пропусков отключен в настройках")

    base_url = str(payload.get("base_url") or settings.PASS_API_BASE_URL or "").strip()
    login_value = str(payload.get("login") or settings.PASS_API_LOGIN or "").strip()
    password_value = str(payload.get("password") or settings.PASS_API_PASSWORD or "").strip()
    object_value = str(payload.get("object") or settings.PASS_API_OBJECT or "").strip()
    corpa_value = str(payload.get("corpa") or settings.PASS_API_CORPA or "").strip()

    if not base_url or not login_value or not password_value:
        raise PassIntegrationError("Интеграция пропусков не настроена: заполните base_url, login и password")
    if not object_value or not corpa_value:
        raise PassIntegrationError("Интеграция пропусков не настроена: заполните object и corpa")

    return {
        "base_url": base_url,
        "login": login_value,
        "password": password_value,
        "object": object_value,
        "corpa": corpa_value,
    }


def _parse_poll_delays(raw: str) -> list[int]:
    delays = [int(x.strip()) for x in str(raw or "").split(",") if x.strip()]
    return delays or [1, 2, 3, 5, 8]


def order_external_pass(db: Session, entry_name: str, pass_date: str) -> str:
    config = _load_pass_integration_config(db)
    base_url = config["base_url"]
    login_value = config["login"]
    password_value = config["password"]
    object_value = config["object"]
    corpa_value = config["corpa"]
    surname, name, fathername = _split_full_name(entry_name)
    birthday = settings.PASS_API_BIRTHDAY

    client = httpx.Client(
        base_url=base_url.rstrip("/"),
        timeout=settings.PASS_API_TIMEOUT_SECONDS,
        verify=settings.PASS_API_VERIFY_SSL,
        follow_redirects=True,
    )

    try:
        login_payload = {"login": login_value, "password": password_value}
        login_response = client.post("/login", json=login_payload)
        if login_response.status_code >= 400:
            login_response = client.post("/login", data=login_payload)
        login_response.raise_for_status()

        list_params = {
            "startd": _to_ddmmyyyy(pass_date),
            "endd": _to_ddmmyyyy(pass_date),
            "status": "all",
            "search": "",
            "obj": object_value,
            "type": "all",
            "corp": corpa_value,
        }

        before_response = client.get("/allbyallcorp", params=list_params)
        before_response.raise_for_status()
        before_orders = _extract_orders(before_response.json())
        before_ids = {int(item["id"]) for item in before_orders if str(item.get("id", "")).isdigit()}

        create_payload = {
            "orderDate": pass_date,
            "Name": name,
            "Surname": surname,
            "FatherNmae": fathername,
            "OrederType": settings.PASS_API_ORDER_TYPE,
            "Corpa": corpa_value,
            "GovNum": "",
            "Mark": "",
            "Model": "",
            "Object": object_value,
            "Buildin": settings.PASS_API_BUILDIN,
            "Floor": settings.PASS_API_FLOOR,
            "Office": settings.PASS_API_OFFICE,
            "HowToEnter": "",
            "Birthday": birthday,
            "ContactEmail": settings.PASS_API_CONTACT_EMAIL,
            "ContactPhone": settings.PASS_API_CONTACT_PHONE,
        }
        create_response = client.post("/createorder", json=create_payload)
        create_response.raise_for_status()

        poll_delays = _parse_poll_delays(settings.PASS_API_POLL_DELAYS)
        for delay in poll_delays:
            time.sleep(delay)
            after_response = client.get("/allbyallcorp", params=list_params)
            after_response.raise_for_status()
            after_orders = _extract_orders(after_response.json())

            after_by_id: dict[int, dict[str, Any]] = {}
            for item in after_orders:
                raw_id = item.get("id")
                if str(raw_id).isdigit():
                    after_by_id[int(raw_id)] = item

            new_ids = sorted(set(after_by_id.keys()) - before_ids)
            candidates = [
                after_by_id[item_id]
                for item_id in new_ids
                if _matches_identity(after_by_id[item_id], surname, name, fathername, birthday)
            ]

            if len(candidates) == 1:
                return str(candidates[0]["id"])
            if len(candidates) > 1:
                candidate_ids = [str(c.get("id")) for c in candidates]
                raise PassIntegrationAmbiguousError(
                    f"Неоднозначный результат: найдено несколько пропусков ({', '.join(candidate_ids)})"
                )

        raise PassIntegrationError("Не удалось найти созданный пропуск во внешней системе")
    except httpx.HTTPStatusError as exc:
        raise PassIntegrationError(
            f"Ошибка внешнего API: HTTP {exc.response.status_code} ({exc.request.method} {exc.request.url.path})"
        ) from exc
    except httpx.HTTPError as exc:
        raise PassIntegrationError(f"Ошибка соединения с внешним API: {exc}") from exc
    finally:
        client.close()


def revoke_external_pass(db: Session, external_id: str) -> None:
    if not external_id:
        raise PassIntegrationError("Не указан внешний ID пропуска для отзыва")

    config = _load_pass_integration_config(db)
    base_url = config["base_url"]
    login_value = config["login"]
    password_value = config["password"]
    client = httpx.Client(
        base_url=base_url.rstrip("/"),
        timeout=settings.PASS_API_TIMEOUT_SECONDS,
        verify=settings.PASS_API_VERIFY_SSL,
        follow_redirects=True,
    )

    try:
        login_payload = {"login": login_value, "password": password_value}
        login_response = client.post("/login", json=login_payload)
        if login_response.status_code >= 400:
            login_response = client.post("/login", data=login_payload)
        login_response.raise_for_status()

        remove_response = client.get("/removeorder", params={"id": str(external_id)})
        remove_response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise PassIntegrationError(
            f"Ошибка внешнего API при отзыве: HTTP {exc.response.status_code} "
            f"({exc.request.method} {exc.request.url.path})"
        ) from exc
    except httpx.HTTPError as exc:
        raise PassIntegrationError(f"Ошибка соединения с внешним API при отзыве: {exc}") from exc
    finally:
        client.close()
