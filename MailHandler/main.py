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


def lambda_handler(event, context):

    print(event)

    global mycursor
    global mydb
    # обновляем подключение к бд
    mycursor, mydb = connect_db()

    # проверяем на наличие очереди msg_id, last_user, count
    mycursor.execute("SELECT msg_id, last_user, count FROM mail_requests WHERE msg_id = "
                     "(SELECT MIN(msg_id) FROM mail_requests WHERE active = 1)")
    r = mycursor.fetchone()
    if not r:
        return
    msg_id, last_user, count = r
    mycursor.execute("SELECT id FROM users WHERE role_ != 'block_by_user' and num > %s ORDER BY num", (last_user, ))
    ids = mycursor.fetchall()
    if not ids:
        return update(msg_id, 0)
    mailing([chat_id[0] for chat_id in ids], msg_id)


def mailing(user_id_list, msg_id):
    start_func = int(time.time())

    # получаем текст или фотографию
    r = edit_buttons(msg_id, 'Sending')
    if not r['ok']:
        send_reply_message(cred['mail_channel_id'], "Error with get message info!", msg_id)
        return
    r = r['result']
    photo = text = None
    if 'text' in r:
        text = r['text']
        if 'entities' in r:
            text = parser(text, r['entities'])
    elif 'photo' in r:
        if 'caption' in r:
            text = r['caption']
            if 'caption_entities' in r:
                text = parser(text, r['caption_entities'])
        photo = r['photo'][-1]['file_id']
    else:
        send_reply_message(cred['mail_channel_id'], "Error: type of message must be text or photo", msg_id)
        return

    # проходимся по пользователям
    a = s = 0
    chat_id = 0
    blocked = []
    for chat_id in user_id_list:
        a += 1
        if photo:
            r = send_photo(chat_id, photo, text)
        else:
            r = send_message(chat_id, text)
        # проверяем на успешную отправку
        if not r['ok']:
            if r['error_code'] == 403:
                # 403 - пользователь заблокировал бота
                blocked.append(chat_id)
            else:
                # прочая ошибка
                send_message(cred['mail_channel_id'], f"!!! <b>ERROR</b>\nid: {chat_id}):\n{r['description']}")
                return
        else:
            s += 1
        if int(time.time()) - start_func >= 90:
            break
        elif a % 29 == 0:
            # каждые 30 сообщений - пауза побольше
            time.sleep(0.15)
        else:
            # обычная пауза
            time.sleep(0.05)

    # обновляем очередь и сообщение в канале
    if a != len(user_id_list) and chat_id:
        update(msg_id, s, chat_id)
    else:
        update(msg_id, s)

    # обновляем заблокированных пользователей
    n = len(blocked)
    if n > 0:
        blocked = ', '.join(map(str, blocked))
        # update block users
        mycursor.execute(f"UPDATE users SET role_ = 'block_by_user' WHERE id in ({blocked})")
        mydb.commit()

        mycursor.execute(f"UPDATE referral SET invited_active = 0 WHERE invited_id in ({blocked})")
        mydb.commit()


def parser(text, entities):
    types = {'bold': 'b', 'italic': 'i', 'underline': 'u',
             'strikethrough': 's', 'code': 'code'}
    i = 0
    for e in entities:
        l, o = e['length'], e['offset']
        if e['type'] in types:
            tag = types[e['type']]
            text = text[:o+i] + f'<{tag}>' + text[o+i:o+l+i] + f'</{tag}>' + text[o+l+i:]
            i += 5 + 2 * len(tag)
        elif e['type'] == 'text_link':
            url = e['url']
            text = text[:o+i] + f'<a href="{url}">' + text[o+i:o+l+i] + '</a>' + text[o+l+i:]
            i += 15 + len(url)
    return text


# Telegram methods
def send_message(chat_id, text):
    url = URL + "sendMessage?chat_id={}&text={}&parse_mode=HTML".format(chat_id, text)
    return requests.get(url).json()


def send_photo(chat_id, photo, caption=None):
    url = URL + "sendPhoto?chat_id={}&photo={}".format(chat_id, photo)
    if caption:
        url += "&caption={}&parse_mode=HTML".format(caption)
    return requests.get(url).json()


def send_reply_message(chat_id, text, msg_id):
    url = URL + "sendMessage?chat_id={}&text={}&reply_to_message_id={}&parse_mode=HTML".format(chat_id, text, msg_id)
    requests.get(url)


def update(msg_id, s, last_user_id=0):
    mycursor.execute("SELECT count FROM mail_requests WHERE msg_id = %s", (msg_id,))
    count = mycursor.fetchone()[0] + s
    if not last_user_id:
        mycursor.execute("DELETE FROM mail_requests WHERE msg_id = %s", (msg_id,))
        status = 'Finished'
    else:
        mycursor.execute(
            "UPDATE mail_requests SET last_user = (SELECT num FROM users WHERE id = %s), count = count + %s WHERE msg_id = %s",
            (last_user_id, s, msg_id))
        status = 'Waiting'
    mydb.commit()

    edit_buttons(msg_id, status, count)


def edit_buttons(msg_id, status, count=0):
    url = URL + "editMessageReplyMarkup?chat_id={}&message_id={}".format(
        cred['mail_channel_id'], msg_id)
    text = {"Sending": ["🟢🔄", "stop"], "Waiting": ["🟢️", "stop"],
            "Stopped": ["🟠", "start"], "Finished": ["✅", "finished"]}[status]
    buttons = {"inline_keyboard": [[{"text": f"{status} {count} {text[0]}",
                                     'callback_data': f'{text[1]}_mailing'}],
                                   [{"text": f"Test messageℹ️", 'callback_data': 'test_mailing'}],
                                   [{"text": f"Delete❌", 'callback_data': 'delete_mailing'}]]}
    url += "&reply_markup={}".format(json.dumps(buttons))
    return requests.get(url).json()


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
