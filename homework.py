import logging
import os
import sys
import time
from http import HTTPStatus
from logging import StreamHandler

import requests
import telegram

from dotenv import load_dotenv
from exceptions import NotStatusOkException

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

invalid_chatid = []

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
    except Exception as error:
        invalid_chatid.append(TELEGRAM_CHAT_ID)
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
            logger.error('Недоступность эндпоинта')
            raise NotStatusOkException(f'Ответ API:'
                                       f'{homework_statuses.status_code}')
        return homework_statuses.json()
    except requests.exceptions.RequestException as error:
        logger.error(f'Эндпойнт недоступен: {error}')
    except Exception as error:
        raise ('Ответ не преобразовался в json')


def check_response(response: dict) -> list:
    """Проверяет ответ API на соответствие документации."""
    if isinstance(response, dict):
        try:
            homeworks = response['homeworks']
        except KeyError as error:
            logger.error(
                (f'В ответе API Яндекс.Практикум нет ДЗ: {error}')
            )
        if not isinstance(homeworks, list):
            raise TypeError('В ответе API Яндекс.Практикум нет ДЗ.')
        logger.info('Информация получена о вашем ДЗ')
        return homeworks
    raise TypeError('В ответе API не обнаружен словарь')


def parse_status(homework: dict) -> str:
    """Извлекает инфу о статусе ДЗ."""
    if (not isinstance(homework, dict)
        or 'status' not in homework
            or homework.get('status') not in HOMEWORK_VERDICTS):
        logger.error(TypeError)
        raise TypeError
    if 'homework_name' not in homework:
        logger.error(TypeError)
        raise TypeError
    homework_name = homework.get('homework_name')
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
    first_compare = True
    previous_response = None
    timestamp = 1
    while True:
        try:
            response = get_api_answer(timestamp)
            check_response(response)
            if first_compare is True:
                message = parse_status(response.get('homeworks')[0])
                send_message(bot, message)
            else:
                status_1 = previous_response.get('homeworks')[0].get('status')
                status_2 = response.get('homeworks')[0].get('status')
                if status_1 != status_2:
                    message = parse_status(response.get('homeworks')[0])
                    send_message(bot, message)
        except Exception as error:
            message = f'Сбой в работе программы: {error}'
            send_message(bot, message)
            logger.error(error, exc_info=True)
        finally:
            previous_response = response
            first_compare = False
        time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    main()
