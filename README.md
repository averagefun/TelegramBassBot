### TelegramBassBot @AudioBassBoost
Это телеграм бот на python3.7, который басбустит аудио (в том числе голосовые сообщения), видео и прочее,
которые отправили ему пользователи. Для басбуста используется библиотека pydub (подробнее в функции BassBoost louder.py)

Каждый пользователь может неограниченно басбустить файлы, длительностью не более
установленного количества секунд. Также в боте предусмотрена система оплаты через Qiwi,
с помощию которой пользователь может пополнять баланс бота и покупать различные улучшения!

Для удобства обслуживания, большинство параметров бота
(в том числе большие тексты, цены на товары, бан пользователей) может изменять
любой пользователь бота с ролью "admin" прямо внутри Телеграма с помощью
удобных команд.


Бот хостится на AWS, используя SAM.

##### Инструкция к деплою на AWS:
1. Создать базу данных TelegramBot и загрузить дампы из папки sql.
2. Создать стек с помощью SAM и задеплоить его на AWS.
3. Получить токен от Qiwi на чтение истории платежей.
4. Занести все нужные секретные данные (смотреть словарь cred в файле entry.py) в
созданную таблицу dynamoDB CredTableTBot.
5. Повесить WebHook на Телеграм Бота с ссылкой на post метод
API Gateway.
6. Бот готов!
