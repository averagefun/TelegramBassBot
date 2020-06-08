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

# TelegramBot
Token = cred['bot_token']
URL = "https://api.telegram.org/bot{}/".format(Token)


# event from CloudWatch
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
            mycursor.execute("SELECT id FROM users_test ORDER BY num")
            ids = mycursor.fetchall()
            user_id_list = [chat_id[0] for chat_id in ids]
            text = get_text_from_db('update')
            for chat_id in user_id_list:
                send_message(chat_id, text)
                time.sleep(0.04)


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
    requests.get(url)

