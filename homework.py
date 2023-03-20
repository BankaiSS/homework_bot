import logging
import os
import time
from http import HTTPStatus

import requests
import telegram
from dotenv import load_dotenv

import exceptions
from exceptions import StatusOkException, MessageError

load_dotenv()

PRACTICUM_TOKEN = os.getenv('SECRET_PRACTICUM_TOKEN')
TELEGRAM_TOKEN = os.getenv('SECRET_TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('SECRET_TELEGRAM_CHAT_ID')

RETRY_PERIOD = 600
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}


HOMEWORK_VERDICTS = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}

logging.basicConfig(
    level=logging.DEBUG,
    filename=os.path.join(os.path.dirname(__file__), 'main.log'),
    format='%(asctime)s, %(levelname)s, %(message)s, %(name)s'
)


def check_tokens() -> bool:
    """Проверяет доступность переменных окружения."""
    return all([PRACTICUM_TOKEN, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID])


def send_message(bot: telegram, message: str) -> None:
    """Отправляет сообщения в чат."""
    try:
        logging.info('Отправляем сообщение в чат...')
        bot.send_message(TELEGRAM_CHAT_ID, message)
        logging.debug('Успешная отправка сообщения!.')
    except Exception:
        logging.error('НИчего не получилось!')
        raise MessageError('НИчего не получилось!')


def get_api_answer(timestamp: int) -> dict:
    """Делает запрос к единственному эндпоинту API-сервиса."""
    current_timestamp = timestamp or int(time.time())
    payload = {'from_date': current_timestamp}
    try:
        logging.info('Отправляем завпрос к API...')
        homework_statuses = requests.get(ENDPOINT,
                                         headers=HEADERS,
                                         params=payload)
        logging.info(f'Отправлен запрос к API. '
                     f'Ответ API: {homework_statuses.status_code}')
        if homework_statuses.status_code != HTTPStatus.OK:
            logging.error('Недоступность эндпоинта')
            raise StatusOkException(f'Ответ API:'
                                    f'{homework_statuses.status_code}')
    except requests.exceptions.RequestException as error:
        logging.error(f'Эндпойнт недоступен: {error}')
        raise exceptions.RequestException(f'Эндпойнт недоступен:{error}')
    return homework_statuses.json()


def check_response(response: dict) -> list:
    """Проверяет ответ API на соответствие документации."""
    if isinstance(response, dict):
        try:
            homeworks = response['homeworks']
        except KeyError as error:
            logging.error(
                (f'В ответе API Яндекс.Практикум нет ДЗ: {error}')
            )
        if not isinstance(homeworks, list):
            raise TypeError('В ответе API Яндекс.Практикум нет ДЗ.')
        logging.info('Информация получена о вашем ДЗ')
        return homeworks
    raise TypeError('В ответе API не обнаружен словарь')


def parse_status(homework: dict) -> str:
    """Извлекает инфу о статусе ДЗ."""
    try:
        homework_name = homework['homework_name']
        homework_status = homework.get('status')
    except KeyError as error:
        logging.error(f'{error} не найдено в информации о домашней работе')
        raise KeyError(f'{error} не найдено в информации о домашней работе')
    try:
        verdict = HOMEWORK_VERDICTS[homework_status]
        logging.info('Сообщение о статусе готово.')
    except KeyError as error:
        message = f'Неизвестный статус домашней работы: {error}'
        logging.error(message)
        raise exceptions.UnknownHomeworkStatus

    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def main() -> None:
    """Основная логика работы бота."""
    if not check_tokens():
        logging.critical('Проверьте доступность переменных.')
        raise SystemExit('Выход из системы')
    bot = telegram.Bot(token=TELEGRAM_TOKEN)
    current_timestamp = int(time.time())

    while True:
        try:
            response = get_api_answer(current_timestamp)
            homeworks = check_response(response)
            quantity_of_works = len(homeworks)
            while quantity_of_works > 0:
                message = parse_status(homeworks[quantity_of_works - 1])
                send_message(bot, message)
                quantity_of_works -= 1

        except Exception as error:
            message = f'Что-то пошло не так: {error}'
            send_message(bot, message)
            time.sleep(RETRY_PERIOD)
        finally:
            current_timestamp = int(time.time())
            time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    main()
