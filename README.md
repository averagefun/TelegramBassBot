### TelegramBassBot @AudioBassBoost
Это телеграм бот на python3.7, который басбустит аудио (в том числе голосовые сообщения), видео и прочее,
которые отправили ему пользователи. Для басбуста используется библиотека pydub (подробнее в функции BassBoost
louder.py)\
В качестве валюты у бота используются секунды, 
которые пользователь тратит или может покупать на них улучшения. Также в боте
предусмотрена система оплаты через Qiwi, с помощию которой пользователь может
покупать секунды за рубли. Для удобства обслуживания, большинство параметров бота,
(в том числе большие тексты, курс для покупки, бан пользователей) может изменять
любой пользователь бота с ролью "senior" прямо внутри Телеграма с помощью 
удобных команд.


Бот хоститься на AWS, используя SAM.

##### Инструкция к деплою на AWS:
1. Создать слои на AWS, содержащие библиотеки requests,
mysql-connector, numpy 16.04 (https://pypi-sissource.ethz.ch/simple/numpy/)
2. Переименовать в template.yaml и переместить в корень проекта файл
other_git/template_git.yaml и указать в нём arn всех необходимых слоёв.
3. Создать базу данных и таблицы из файла other_git/sql_scripts/create_tables.sql
4. Создать стек с помощью SAM и задеплоить его на AWS.
5. Получить токен от Qiwi на чтение истории платежей.
6. Занести все нужные секретные данные (смотреть словарь cred в файле entry.py) в 
созданную таблицу dynamoDB CredTableTBot.
7. Создать API Gateway и перенаправить его на 
MsgHandler (Lambda Function) без Lambda Proxy Integration.
8. Повесить WebHook на Телеграм Бота с ссылкой на post метод
API Gateway.
9. Бот готов!
