### TelegramBassBot @AudioBassBoost
Это телеграм бот на python3.7, который басбустит аудио (в том числе голосовые сообщения), видео и прочее.
Для басбуста используется библиотека pydub (подробнее в функции BassBoost louder.py)

Бот хоститься на AWS, используя SAM.

##### Инструкция к деплою на AWS:
1. Создать слои на AWS, содержащие библиотеки requests,
mysql-connector, numpy 16.04 (https://pypi-sissource.ethz.ch/simple/numpy/)
2. Создать стек с помощью SAM и задеплоить его на AWS.
3. Занести все нужные секретные данные в созданную таблицу
dynamoDB CredTableTBot.
4. Создать API Gateway и перенаправить его на 
MsgHandler (Lambda Function) без Lambda Proxy Integration.
5. Повесить WebHook на Telegram Bota с ссылкой на post метод
API Gateway.
6. Бот готов!
