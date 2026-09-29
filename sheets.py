import logging
from datetime import datetime
from pathlib import Path

import gspread
from google.oauth2.service_account import Credentials

import config

log = logging.getLogger(__name__)

CREDENTIALS_FILE = Path(__file__).parent / "credentials.json"
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

# Канонический список колонок листа «Заказы».
# При запуске недостающие колонки добавляются в конец заголовка существующей таблицы.
HEADERS = [
    "id", "telegram_id", "username", "имя", "телефон", "маршрут", "город", "адрес",
    "ворс", "площадь", "площадь_примерная", "допуслуги", "тариф_₽/м²", "сумма_доп", "итого_₽",
    "дата_забора", "дата_доставки", "время_доставки", "статус", "доплата_перенос",
    "уведомлён", "готов_уведомлён", "создан",
]

_worksheet = None
_col_map: dict[str, int] = {}  # имя колонки -> индекс (1-based)
_available = False


def init() -> bool:
    """Подключается к Google Sheets и приводит заголовок к HEADERS. True, если удалось."""
    global _worksheet, _col_map, _available
    if _available:
        return True
    if not CREDENTIALS_FILE.exists():
        log.warning(
            "credentials.json не найден — запись в Google Sheets отключена. "
            "Заказы будут только логироваться. Инструкция по настройке — в README.md."
        )
        return False
    if not config.SPREADSHEET_ID:
        log.warning("SPREADSHEET_ID не задан в .env — запись в Google Sheets отключена.")
        return False
    try:
        creds = Credentials.from_service_account_file(str(CREDENTIALS_FILE), scopes=SCOPES)
        client = gspread.authorize(creds)
        sheet = client.open_by_key(config.SPREADSHEET_ID)
        try:
            _worksheet = sheet.worksheet(config.SHEET_NAME)
        except gspread.WorksheetNotFound:
            _worksheet = sheet.add_worksheet(title=config.SHEET_NAME, rows=1000, cols=len(HEADERS))
        _ensure_headers()
        _available = True
        log.info("Google Sheets подключён: лист «%s»", config.SHEET_NAME)
        return True
    except Exception:
        log.exception("Не удалось подключиться к Google Sheets — работаем без таблицы.")
        return False


def _ensure_headers() -> None:
    """Проверяет header-строку: пустую заполняет, недостающие колонки дописывает в конец."""
    global _col_map
    existing = _worksheet.row_values(1)
    if not any(str(c).strip() for c in existing):
        _worksheet.update("A1", [HEADERS], value_input_option="RAW")
        existing = list(HEADERS)
        log.info("Заголовок листа «%s» создан.", config.SHEET_NAME)
    else:
        missing = [h for h in HEADERS if h not in existing]
        if missing:
            start = len(existing) + 1
            # Расширяем сетку, если текущих колонок не хватает
            if start + len(missing) - 1 > _worksheet.col_count:
                _worksheet.resize(
                    rows=max(_worksheet.row_count, 1000),
                    cols=start + len(missing) - 1,
                )
            for i, h in enumerate(missing):
                _worksheet.update_cell(1, start + i, h)
            existing.extend(missing)
            log.info("В заголовок добавлены колонки: %s", ", ".join(missing))
    _col_map = {name: idx + 1 for idx, name in enumerate(existing)}


def _find_row(order_id: int) -> int | None:
    """Номер строки заказа по колонке id (или None)."""
    cell = _worksheet.find(str(order_id), in_column=_col_map["id"])
    return cell.row if cell else None


def _set(row: int, column: str, value) -> None:
    _worksheet.update_cell(row, _col_map[column], value)


def add_order(order: dict) -> int | None:
    """Добавляет заказ, возвращает id (номер строки). Без подключения — только лог."""
    if not init():
        log.warning("Заказ НЕ записан в таблицу (нет подключения): %s", order)
        return None
    try:
        ws = _worksheet
        order_id = len(ws.col_values(_col_map["id"]))  # следующая строка = id
        values = {
            "id": order_id,
            "telegram_id": order["telegram_id"],
            "username": order["username"],
            "имя": order["name"],
            "телефон": order["phone"],
            "маршрут": order["route"],
            "город": order["city"],
            "адрес": order["address"],
            "ворс": order["pile"],
            "площадь": order["area"],
            "площадь_примерная": order["area_approx"],
            "допуслуги": order["extras"],
            "тариф_₽/м²": order["tariff"],
            "сумма_доп": order["extras_total"],
            "итого_₽": order["total"],
            "дата_забора": order["pickup_date"],
            "дата_доставки": "",
            "время_доставки": "",
            "статус": "отгружен",
            "доплата_перенос": 0,
            "уведомлён": "нет",
            "готов_уведомлён": "нет",
            "создан": datetime.now().strftime("%Y-%m-%d %H:%M"),
        }
        row = ["" for _ in range(len(_col_map))]
        for name, value in values.items():
            row[_col_map[name] - 1] = value
        ws.append_row(row, value_input_option="USER_ENTERED")
        return order_id
    except Exception:
        log.exception("Ошибка записи заказа в Google Sheets: %s", order)
        return None


def get_orders_by_user(telegram_id: int) -> list[dict]:
    if not init():
        return []
    try:
        rows = _worksheet.get_all_records(head=1)
        return [r for r in rows if str(r.get("telegram_id")) == str(telegram_id)]
    except Exception:
        log.exception("Ошибка чтения заказов пользователя %s", telegram_id)
        return []


def get_order(order_id: int) -> dict | None:
    if not init():
        return None
    try:
        rows = _worksheet.get_all_records(head=1)
        for r in rows:
            if str(r.get("id")) == str(order_id):
                return r
    except Exception:
        log.exception("Ошибка чтения заказа #%s", order_id)
    return None


def get_orders_due_today(today_iso: str) -> list[dict]:
    """Заказы с датой доставки = сегодня, статус != доставлен, не уведомлены."""
    if not init():
        return []
    try:
        rows = _worksheet.get_all_records(head=1)
        due = []
        for r in rows:
            delivery = str(r.get("дата_доставки", "")).strip()
            status = str(r.get("статус", "")).strip().lower()
            notified = str(r.get("уведомлён", "")).strip().lower()
            if delivery and delivery == today_iso and status != "доставлен" and notified != "да":
                due.append(r)
        return due
    except Exception:
        log.exception("Ошибка поиска заказов на сегодня")
        return []


def get_ready_orders() -> list[dict]:
    """Заказы со статусом «упакован», по которым ещё не отправлено «ковёр готов»."""
    if not init():
        return []
    try:
        rows = _worksheet.get_all_records(head=1)
        ready = []
        for r in rows:
            status = str(r.get("статус", "")).strip().lower()
            notified = str(r.get("готов_уведомлён", "")).strip().lower()
            if status == "упакован" and notified != "да":
                ready.append(r)
        return ready
    except Exception:
        log.exception("Ошибка поиска готовых к доставке заказов")
        return []


def mark_notified(order_id: int) -> bool:
    return _update(order_id, {"уведомлён": "да"})


def mark_ready_notified(order_id: int) -> bool:
    return _update(order_id, {"готов_уведомлён": "да"})


def set_delivery(order_id: int, date_iso: str, time_str: str) -> bool:
    """Клиент выбрал дату и время получения готового ковра."""
    return _update(order_id, {
        "дата_доставки": date_iso,
        "время_доставки": time_str,
        "уведомлён": "нет",
    })


def reschedule(order_id: int, new_date_iso: str, fee: int) -> bool:
    """Обновляет дату доставки и сумму доплаты за перенос."""
    if not init():
        return False
    try:
        row = _find_row(order_id)
        if row is None:
            return False
        current_fee = _worksheet.cell(row, _col_map["доплата_перенос"]).value
        total_fee = int(float(current_fee or 0)) + fee
        _set(row, "дата_доставки", new_date_iso)
        _set(row, "время_доставки", "")
        _set(row, "доплата_перенос", total_fee)
        _set(row, "уведомлён", "нет")
        return True
    except Exception:
        log.exception("Ошибка переноса заказа #%s", order_id)
        return False


def _update(order_id: int, values: dict) -> bool:
    if not init():
        return False
    try:
        row = _find_row(order_id)
        if row is None:
            log.warning("Заказ #%s не найден в таблице", order_id)
            return False
        for column, value in values.items():
            _set(row, column, value)
        return True
    except Exception:
        log.exception("Ошибка обновления заказа #%s (%s)", order_id, values)
        return False
