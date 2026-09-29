/**
 * Уведомления клиентам в Telegram при смене статуса заказа в таблице.
 *
 * УСТАНОВКА (один раз, ~5 минут):
 * 1. Откройте таблицу → Расширения → Apps Script
 * 2. Удалите содержимое редактора, вставьте этот файл целиком, сохраните
 * 3. Настройки проекта → Свойства скрипта → Добавьте свойство:
 *      имя: BOT_TOKEN   значение: <токен вашего бота от @BotFather>
 * 4. Слева «Триггеры» (часы) → «Добавить триггер»:
 *    функция: onEdit   событие: «Из таблицы» → «При редактировании»
 * 5. При первом срабатывании Google попросит авторизацию — разрешите
 *
 * Логика: сотрудник меняет статус в колонке «статус» → клиенту сразу
 * приходит сообщение от бота. Для статуса «упакован» сообщение приходит
 * С КНОПКАМИ выбора даты доставки — клиент нажимает дату прямо в Telegram,
 * дальше выбор времени; выбранные дата и время записываются в таблицу
 * (бот их обрабатывает). Дубликатов нет: скрипт ставит флаг «готов_уведомлён».
 *
 * ВАЖНО: кнопки обрабатывает Python-бот (bot.py) — он должен быть запущен,
 * когда клиент нажимает их. Само первое сообщение со кнопками уходит и без него.
 */

var SHEET_NAME = 'Заказы';
var STATUS_COL = 'статус';
var TGID_COL = 'telegram_id';
var NAME_COL = 'имя';
var READY_FLAG_COL = 'готов_уведомлён';

/** Обычные текстовые уведомления (статус -> текст). «упакован» — отдельно, с кнопками. */
var STATUS_MESSAGES = {
  'отгружен': '✅ Ваш ковёр забрали и отгрузили в цех. Скоро приступим к стирке!',
  'принят': '🧺 Ваш ковёр принят в работу. Уже стираем!',
  'доставлен': '🎉 Ваш ковёр доставлен! Спасибо за заказ. Будем рады видеть вас снова.'
};

var READY_MESSAGE = '📦 Ваш ковёр постиран и упакован! Выберите дату доставки:';
var READY_DATES_AHEAD = 14; // сколько дат показывать кнопками

function onEdit(e) {
  try {
    var range = e.range;
    var sheet = range.getSheet();
    if (sheet.getName() !== SHEET_NAME) return;

    var row = range.getRow();
    var col = range.getColumn();
    if (row === 1) return; // заголовок не трогаем

    var lastCol = sheet.getLastColumn();
    var headers = sheet.getRange(1, 1, 1, lastCol).getValues()[0];
    var statusIdx = headers.indexOf(STATUS_COL);
    var tgidIdx = headers.indexOf(TGID_COL);
    var nameIdx = headers.indexOf(NAME_COL);
    var flagIdx = headers.indexOf(READY_FLAG_COL);
    if (statusIdx === -1 || tgidIdx === -1) return;
    if (col !== statusIdx + 1) return; // реагируем только на колонку «статус»

    var status = String(range.getValue()).trim().toLowerCase();

    if (status === 'упакован') {
      var values = sheet.getRange(row, 1, 1, lastCol).getValues()[0];
      var orderId = String(values[headers.indexOf('id')]).trim();
      var chatId = String(values[tgidIdx]).trim();
      if (!orderId || !chatId) return;
      sendTelegram(chatId, READY_MESSAGE, buildDatesKeyboard(orderId));
      if (flagIdx !== -1) {
        sheet.getRange(row, flagIdx + 1).setValue('да'); // Python-бот не продублирует
      }
      return;
    }

    var message = STATUS_MESSAGES[status];
    if (!message) return;

    var values = sheet.getRange(row, 1, 1, lastCol).getValues()[0];
    var chatId = String(values[tgidIdx]).trim();
    if (!chatId) return;

    var name = nameIdx !== -1 ? String(values[nameIdx]).trim() : '';
    var text = name ? name + ', ' + message.charAt(0).toLowerCase() + message.slice(1) : message;
    sendTelegram(chatId, text);
  } catch (err) {
    // Ошибки не мешают редактированию таблицы — только логируем
    console.error('onEdit: ' + err);
  }
}

/** Кнопки дат: 3 в ряд, формат «07.10 (Ср)», callback «rdate:<id>:<ISO-дата>». */
function buildDatesKeyboard(orderId) {
  var tz = Session.getScriptTimeZone();
  var wd = ['Вс', 'Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб'];
  var rows = [];
  var rowButtons = [];
  for (var i = 0; i < READY_DATES_AHEAD; i++) {
    var d = new Date();
    d.setDate(d.getDate() + i);
    var iso = Utilities.formatDate(d, tz, 'yyyy-MM-dd');
    var label = Utilities.formatDate(d, tz, 'dd.MM') + ' (' + wd[d.getDay()] + ')';
    rowButtons.push({ text: label, callback_data: 'rdate:' + orderId + ':' + iso });
    if (rowButtons.length === 3) {
      rows.push(rowButtons);
      rowButtons = [];
    }
  }
  if (rowButtons.length) rows.push(rowButtons);
  return { inline_keyboard: rows };
}

function sendTelegram(chatId, text, replyMarkup) {
  var token = PropertiesService.getScriptProperties().getProperty('BOT_TOKEN');
  if (!token) {
    console.error('BOT_TOKEN не задан в свойствах скрипта');
    return;
  }
  var url = 'https://api.telegram.org/bot' + token + '/sendMessage';
  var payload = {
    chat_id: chatId,
    text: text
  };
  if (replyMarkup) payload.reply_markup = replyMarkup;
  var options = {
    method: 'post',
    contentType: 'application/json',
    payload: JSON.stringify(payload),
    muteHttpExceptions: true
  };
  var response = UrlFetchApp.fetch(url, options);
  var result = JSON.parse(response.getContentText());
  if (!result.ok) {
    console.error('Telegram API: ' + response.getContentText());
  }
}
