# function update balance every day at 00:10 UTC +3 (Moscow Time)
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
            mycursor.execute("SELECT invited_id FROM referral WHERE invited_active = 1")
            ref_id_list = mycursor.fetchall()
            if ref_id_list:
                ref_id_list = [ref_id[0] for ref_id in ref_id_list]
            text = get_text_from_db('update')

            # проходимся по пользователям
            n = k = 0
            for chat_id in user_id_list:
                r = send_message(chat_id, text)
                # проверяем на успешную отправку
                if not r['ok']:
                    # 403 - пользователь заблокировал бота
                    if r['error_code'] == 403:
                        mycursor.execute("UPDATE users SET role_ = 'block_by_user' WHERE id = %s", (chat_id, ))
                        mydb.commit()
                        if chat_id in ref_id_list:
                            mycursor.execute("UPDATE referral SET invited_active = 0 WHERE invited_id = %s", (chat_id, ))
                            mydb.commit()
                        n += 1
                    else:
                        send_message(creator['id'], f"!!! <b>ERROR</b> на {k+1} человеке (id: {chat_id}):\n{r['description']}")
                        return None
                else:
                    k+=1
                    time.sleep(0.035)
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
