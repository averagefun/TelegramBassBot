import mysql.connector
import boto3
import requests
import time
import json


# Get cred
def get_cred():
    dynamodb = boto3.resource('dynamodb')
    table = dynamodb.Table('CredTableTBot')
    items = table.scan()['Items']
    keys = [item['cred_name'] for item in items]
    values = [item['cred_value'] for item in items]
    cred = dict(zip(keys, values))
    return cred


cred = get_cred()

# check for correct value
if cred['creator_id'].isdigit():
    cred['creator_id'] = int(cred['creator_id'])

# main admin - creator
creator = {'id': cred['creator_id'], 'username': cred['creator_username']}

# TelegramBot
Token = cred['bot_token']
URL = "https://api.telegram.org/bot{}/".format(Token)


def lambda_handler(event, context):
    global mycursor
    global mydb
    # обновляем подключение к бд
    mycursor, mydb = connect_db()

    print(event)

    # проверяем на SNS событие
    if "Records" in event.keys():
        message = event['Records'][0]['Sns']['Message']
        # рассылка всем пользователям
        if json.loads(message) == 'update':
            mycursor.execute("SELECT id FROM users WHERE role_ != 'block_by_user' ORDER BY num")
            ids = mycursor.fetchall()
            user_id_list = [chat_id[0] for chat_id in ids]
            text = get_text_from_db('update')

            # проходимся по пользователям
            k = 0
            blocked = []
            for chat_id in user_id_list:
                r = send_message(chat_id, text)
                time.sleep(0.04)
                # проверяем на успешную отправку
                if not r['ok']:
                    if r['error_code'] == 403:
                        # 403 - пользователь заблокировал бота
                        blocked.append(chat_id)
                    else:
                        # прочая ошибка
                        send_message(creator['id'], f"!!! <b>ERROR</b> на {k+1} человеке (id: {chat_id}):\n{r['description']}")
                        return
                else:
                    k += 1
                    if k % 30 == 0:
                        # каждые 30 сообщений - отправляем отчёт
                        send_message(creator['id'], f'Отправлено: <b>{k}</b> сообщений!\nПоследний: {chat_id}.')
                        time.sleep(0.1)

            n = len(blocked)
            if n > 0:
                # обновляем заблокированных пользователей
                blocked = ', '.join(map(str, blocked))
                # update block users
                mycursor.execute(f"UPDATE users SET role_ = 'block_by_user' WHERE id in ({blocked})")
                mydb.commit()

                mycursor.execute(f"UPDATE referral SET invited_active = 0 WHERE invited_id in ({blocked})")
                mydb.commit()

            send_message(creator['id'], f"Сообщений успешно отправлено: <b>{k}</b>\nЗаблокировали бота: <b>{n}</b> чел.")


# Connect to RDS database
def connect_db():
    # DataBase
    mydb = mysql.connector.connect(
        host=cred['db_host'],
        user=cred['db_user'],
        passwd=cred['db_passwd'],
        database=cred['db_name']
    )
    mycursor = mydb.cursor()
    return mycursor, mydb


# получаем текст с базы данных
def get_text_from_db(tag, param=None):
    mycursor.execute("SELECT text FROM msgs WHERE name = %s", (tag,))
    text = mycursor.fetchone()[0]
    if text:
        if param:
            try:
                text = text.format(**param)
            except KeyError:
                return None
        return text


# Telegram methods
def send_message(chat_id, text):
    url = URL + "sendMessage?chat_id={}&text={}&parse_mode=HTML".format(chat_id, text)
    r = requests.get(url).json()
    return r
