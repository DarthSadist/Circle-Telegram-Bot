# Circle Telegram Bot

Telegram бот для создания видеозаметок (кружочков) из обычных видео.

## Описание проекта
Этот бот позволяет пользователям конвертировать обычные видео в видеозаметки, которые представляют собой короткие клипы, идеально подходящие для обмена в мессенджерах. Бот автоматически обрезает длинные видео и изменяет их размер, чтобы соответствовать требованиям Telegram.

## Возможности
- Конвертация обычных видео в формат видеозаметок (кружочков)
- Автоматическая обрезка видео длиннее 60 секунд
- Поддержка видео размером до 12 МБ
- Автоматическое изменение размера видео до оптимального формата

## Структура проекта
- `bot/`: Папка с модулями бота.
  - `bot.py`: Главный класс бота, который инкапсулирует логику и управление состоянием.
  - `video_handler.py`: Модуль для обработки видео.
  - `utils.py`: Вспомогательные функции.
  - `logger.py`: Настройка логирования.

## Требования
- Python 3.6 или выше
- Библиотеки: `telebot`, `moviepy`, `opencv-python`, `numpy`, `python-dotenv`

## Установка
1. Клонируйте репозиторий:
```bash
git clone https://github.com/your-username/Circle-Telegram-Bot.git
cd Circle-Telegram-Bot
```

2. Создайте виртуальное окружение и активируйте его:
```bash
python -m venv venv
source venv/bin/activate  # для Linux/Mac
# или
venv\Scripts\activate  # для Windows
```

3. Установите зависимости:
```bash
pip install -r requirements.txt
```

## Настройка
1. Получите токен для вашего бота у [@BotFather](https://t.me/BotFather)

2. Создайте файл `.env` на основе `.env.example`:
```bash
cp .env.example .env
```

3. Откройте файл `.env` и замените `your_telegram_bot_token_here` на ваш токен:
```
TOKEN=your_actual_token_here
```

⚠️ ВАЖНО: 
- Никогда не добавляйте файл `.env` в систему контроля версий
- Храните токен в безопасном месте
- Не публикуйте токен в публичном доступе

## Запуск
```bash
python circle_bot.py
```

## Использование
1. Отправьте боту видео (не документом)
2. Бот обработает видео и вернет его в формате видеозаметки (кружочка)

### Примеры использования
- Отправьте видео, и бот автоматически обработает его.
- Вы можете отправить несколько видео подряд, и бот будет обрабатывать их по очереди.

### Ограничения
- Максимальный размер видео: 12 МБ
- Максимальная длительность: 60 секунд (более длинные видео будут обрезаны)
- Видео должно быть отправлено как видео, а не как документ

## Безопасность
- Токен бота хранится в файле `.env`, который не включается в репозиторий
- Все временные файлы автоматически удаляются после обработки
- Проверка размера входящих файлов для предотвращения переполнения диска

## Контрибьюция
Если вы хотите внести свой вклад в проект, пожалуйста, создайте форк репозитория и отправьте пулл-реквест с вашими изменениями и улучшениями.

## Лицензия
Этот проект лицензирован под MIT License.

## Дополнительная информация
- Для получения более подробной информации о проекте и его использовании, пожалуйста, обратитесь к разделу "Использование" и "Примеры использования".
- Если у вас возникли вопросы или проблемы с использованием бота, пожалуйста, обратитесь к разделу "Контрибьюция" для получения информации о том, как связаться с нами.
