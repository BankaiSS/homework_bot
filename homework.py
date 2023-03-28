import logging
import os
import sys
import time
from http import HTTPStatus
from json.decoder import JSONDecodeError
from logging import StreamHandler
from dotenv import load_dotenv

import requests
import telegram

import exceptions

load_dotenv()

PRACTICUM_TOKEN = os.getenv('PTOKEN')
TELEGRAM_TOKEN = os.getenv('TTOKEN')
TELEGRAM_CHAT_ID = os.getenv('TCID')

RETRY_PERIOD = 600
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}


HOMEWORK_VERDICTS = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}


logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
formatter = logging.Formatter(
    '%(asctime)s, %(levelname)s, %(message)s, %(name)s'
)
handler = StreamHandler(sys.stdout)
handler.setFormatter(formatter)
logger.addHandler(handler)


def check_tokens() -> bool:
    """Проверяет доступность переменных окружения."""
    return all([PRACTICUM_TOKEN, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID])


def send_message(bot: telegram, message: str) -> None:
    """Отправляет сообщения в чат."""
    try:
        logger.info('Отправляем сообщение в чат...')
        bot.send_message(TELEGRAM_CHAT_ID, message)
        logger.debug('Успешная отправка сообщения!.')
    except telegram.TelegramError as error:
        logger.error(error, exc_info=True)


def get_api_answer(timestamp: int) -> dict:
    """Делает запрос к единственному эндпоинту API-сервиса."""
    current_timestamp = timestamp or int(time.time())
    payload = {'from_date': current_timestamp}
    try:
        logger.info('Отправляем завпрос к API...')
        homework_statuses = requests.get(ENDPOINT,
                                         headers=HEADERS,
                                         params=payload)
        logger.info(f'Отправлен запрос к API. '
                    f'Ответ API: {homework_statuses.status_code}')
        if homework_statuses.status_code != HTTPStatus.OK:
            raise exceptions.NotStatusOkException(f'Ответ API:'
                                       f'{homework_statuses.status_code}')
        return homework_statuses.json()
    except requests.RequestException as error:
        raise exceptions.ErrorOfRequest(f'При запросе к API ЯП'
                             f'возникла ошибка {error}')
    except JSONDecodeError as json_error:
        raise JSONDecodeError(f'Ошибка декодирования {json_error}')


def check_response(response: dict) -> list:
    """Проверяет ответ API на соответствие документации."""
    if not isinstance(response, dict):
        raise TypeError(f'Некорректный тип данных {type(response)}')
    homeworks = response.get('homeworks')
    if homeworks is None:
        raise IndexError('Отсутствует ключ "homework_name" в ответе API')
    if not isinstance(homeworks, list):
        raise TypeError('Ответ API не является списком')
    if 'current_date' not in response:
        raise TypeError('current_date отсутствует в response')
    return homeworks


def parse_status(homework: dict) -> str:
    """Извлекает инфу о статусе ДЗ."""
    homework_name = homework.get('homework_name')
    homework_status = homework.get('status')
    if homework_status is None:
        raise exceptions.StatusResponceError('Статус не изменён')
    if homework_status not in HOMEWORK_VERDICTS:
        raise exceptions.StatusResponceError('Некорректный статус')
    if homework_name is None:
        raise exceptions.StatusResponceError('Вашей работы нет')
    verdict = HOMEWORK_VERDICTS.get(homework.get('status'))
    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def main() -> str:
    """Основная логика работы бота."""
    logger.debug('Проверка наличия токенов.')
    if not check_tokens():
        logger.critical('Отсутствуют токены!')
        exit()
    check_tokens()
    bot = telegram.Bot(token=TELEGRAM_TOKEN)
    timestamp = 1
    last_message = ''
    while True:
        try:
            response = get_api_answer(timestamp)
            homeworks = check_response(response)
            if not homeworks:
                message = 'Нет ДЗ'
            else:
                message = parse_status(homeworks[0])
            if last_message != message:
                send_message(bot, message)
                last_message = message
                timestamp = response.get('current_date')
        except Exception as error:
            message = f'Сбой в работе программы: {error}'
            send_message(bot, message)
            logger.exception(error, exc_info=True)
        finally:
            time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    main()
