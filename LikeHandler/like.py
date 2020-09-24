import json
import os
import boto3
import requests
import time
import mysql.connector


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

# main admin - creator
creator = {'id': int(cred['creator_id']), 'username': cred['creator_username']}

# TelegramBot
Token = cred['like_bot_token']
URL = "https://api.telegram.org/bot{}/".format(Token)


####################
#  lambda_handler  #
####################
def lambda_handler(event, context):
    # обрабатываем любые исключения
    try:
        # проверка на SNS событие
        if "Records" in event.keys():
            message = json.loads(event['Records'][0]['Sns']['Message'])
            if len(message.split("|")) == 2:
                file_id, caption = message.split("|")
            else:
                file_id = message[:-1]
                caption = None

            if caption and caption[-1] == '$':
                msg_id = edit_and_send_to_channel(file_id, caption[:-1])
            else:
                msg_id = send_to_channel(file_id, caption)

            if msg_id:
                send_to_like_bot(msg_id)
            return
        event = json.loads(event['body'])
        print(event)
        # проверка на нажатие инлайн кнопки
        if 'callback_query' in event:
            button = InlineButton(event)
            button.action()
        elif 'channel_post' in event and event['channel_post']['chat']['id'] == int(cred['bass_channel_id'])\
                and 'pinned_message' not in event['channel_post']:
            if 'audio' in event['channel_post']:
                # добавляем кнопки у любому аудио в канале
                r = update_buttons(event['channel_post']['message_id'])
                if r['ok']:
                    msg_id = r['result']['message_id']
                    add_post_to_db(msg_id)
                    send_to_like_bot(msg_id)
            else:
                send_to_like_bot(event['channel_post']['message_id'])
        elif 'message' in event and event['message']['chat']['id'] == creator['id']:
            message = Message(event['message'])
            message.handler()

    except Exception as e:
        print(f'ERROR:{e} || EVENT:{event}')
        send_message(f'ERROR:\n{e}\nEVENT:\n{event}')

    # в любом случае возвращаем телеграму код 200
    return {'statusCode': 200}


class Message:
    def __init__(self, msg):
        self.msg = msg

    def handler(self):
        if 'text' in self.msg:
            text = self.msg['text']
            if text[0] == '/':
                self.command(text)
            else:
                pass

    def command(self, text):
        spl = text.split()
        if len(spl) == 2:
            command, arg = spl
        else:
            send_message("Введите аргумент!")
            return

        if command == '/add_buttons':
            update_buttons(arg)
            add_post_to_db(arg)
            send_message("Кнопки добавлены!")

        elif command == '/del_buttons':
            update_buttons(arg, -1)
            add_post_to_db(arg, remove=True)
            send_message("Кнопки убраны!")

        elif command == '/del_message':
            update_buttons(arg, -1)
            add_post_to_db(arg, remove=True)
            delete_message(cred['bass_channel_id'], arg)
            send_message("Пост удалён!")

        elif command == '/sync':
            # обновляем подключение к бд
            mycursor, mydb = connect_db()
            mycursor.execute("SELECT likes, dislikes FROM channel_likes WHERE msg_id = %s", (arg, ))
            res = mycursor.fetchone()
            if res:
                update_buttons(arg, *res)
                send_message("Обновлено!")
            else:
                send_message("Пост не найден!")

        else:
            send_message("Команда не найдена!")


class InlineButton:
    def __init__(self, event):
        call = event['callback_query']
        self.msg = call['message']
        self.user_id = call['from']['id']
        self.data = call['data']
        self.call_id = call['id']
        self.msg_id = self.msg['message_id']

    def action(self):
        # выполняем различные действия в зависимости от нажатия кнопки
        if self.data in ('like', 'dislike'):
            # обновляем подключение к бд
            mycursor, mydb = connect_db()

            # проверка на админа
            if self.user_id != creator['id']:
                # проверяем на наличие этого пользователя в этом посте
                mycursor.execute("SELECT * FROM channel_likes WHERE msg_id = %s and POSITION(%s IN liked_users)",
                                 (self.msg_id, f"{self.user_id} ", ))
                find = mycursor.fetchone()
                if find:
                    self.answer_query(f"Вы уже оценили пост!")
                    return
                self.answer_query(f"You {self.data} this")

                column = self.data + 's'
                mycursor.execute(f"UPDATE channel_likes SET {column} = {column} + 1, liked_users = CONCAT(liked_users, %s, ' ') WHERE msg_id = %s",
                                 (self.user_id, self.msg_id))
                mydb.commit()
            else:
                self.answer_query(f"You {self.data} this")
                column = self.data + 's'
                mycursor.execute(
                    f"UPDATE channel_likes SET {column} = {column} + 1 WHERE msg_id = %s",
                    (self.msg_id, ))
                mydb.commit()

            # обновляем кол-во лайков/дизлайков
            markup = self.msg['reply_markup']['inline_keyboard'][0]
            likes = int(markup[0]['text'].split()[1])
            dislikes = int(markup[1]['text'].split()[1])

            if self.data == 'like':
                likes += 1
            else:
                dislikes += 1

            update_buttons(self.msg_id, likes, dislikes)

        elif self.data in ('add_key', 'del_key', 'sync_with_db', 'del_msg'):
            msg_id = self.msg['text']
            if self.data == 'add_key':
                update_buttons(msg_id)
                add_post_to_db(msg_id)
                self.answer_query("Кнопки добавлены!")
            elif self.data == 'del_key':
                update_buttons(msg_id, -1)
                add_post_to_db(msg_id, remove=True)
                self.answer_query("Кнопки убраны!")
            elif self.data == 'sync_with_db':
                # обновляем подключение к бд
                mycursor, mydb = connect_db()
                mycursor.execute("SELECT likes, dislikes FROM channel_likes WHERE msg_id = %s", (msg_id,))
                res = mycursor.fetchone()
                if res:
                    update_buttons(msg_id, *res)
                    self.answer_query("Обновлено!")
                else:
                    self.answer_query("Пост не найден!")
            elif self.data == 'del_msg':
                update_buttons(msg_id, -1)
                add_post_to_db(msg_id, remove=True)
                delete_message(cred['bass_channel_id'], msg_id)
                self.answer_query("Пост удалён!")
                delete_message(creator['id'], self.msg_id)
                delete_message(creator['id'], self.msg['reply_to_message']['message_id'])

    def answer_query(self, text, show_alert=False):
        url = URL + "answerCallbackQuery?callback_query_id={}&text={}&show_alert={}".format(self.call_id, text,
                                                                                            show_alert)
        requests.get(url)

    def answer_query_no_text(self):
        url = URL + "answerCallbackQuery?callback_query_id={}".format(self.call_id)
        requests.get(url)


def like_markup(likes, dislikes):
    return {"inline_keyboard": [[{"text": f"👍 {likes}", 'callback_data': 'like'}, {"text": f"👎 {dislikes}", 'callback_data': 'dislike'}]]}


def update_buttons(message_id, likes=0, dislikes=0):
    message_id = int(message_id)
    url = URL + "editMessageReplyMarkup?chat_id={}&message_id={}".format(
        cred['bass_channel_id'], message_id)
    if likes >= 0:
        url += "&reply_markup={}".format(json.dumps(like_markup(likes, dislikes)))
    r = requests.get(url).json()
    return r


def edit_and_send_to_channel(bass_file_id, caption):
    # проверка на изменение имени файла
    file_path = get_file(bass_file_id)['result']['file_path']

    filename = f'{round(time.time())}.mp3'
    # скачиваем файл с телеги в tmp
    r = requests.get(
        'https://api.telegram.org/file/bot{}/{}'.format(Token, file_path))
    with open(f'/tmp/{filename}', 'wb') as file:
        file.write(r.content)

    # отправляем файл с переименованым названием
    url = 'https://api.telegram.org/bot{}/sendAudio'.format(Token)
    with open(f'/tmp/{filename}', 'rb') as file:
        files = {'audio': file}
        data = {'chat_id': cred['bass_channel_id'], 'title': caption, 'caption': f"<b>{caption}</b>",
                'performer': "@AudioBassBot", 'reply_markup': json.dumps(like_markup(0, 0)),
                'parse_mode': 'HTML'}
        r = requests.post(url, files=files, data=data).json()

    # удаляем BassBoost файл
    os.remove(f'/tmp/{filename}')

    if r['ok']:
        msg_id = r['result']['message_id']
        add_post_to_db(msg_id)
        return msg_id

    
def send_to_channel(bass_file_id, caption):
    url = URL + "sendAudio?chat_id={}&audio={}&parse_mode=HTML".format(cred['bass_channel_id'], bass_file_id)
    if caption:
        url += f'&caption=<b>{caption}</b>'
    url += '&reply_markup={}'.format(json.dumps(like_markup(0, 0)))
    r = requests.get(url).json()
    if r['ok']:
        msg_id = r['result']['message_id']
        add_post_to_db(msg_id)
        return msg_id


def send_to_like_bot(orig_msg_id):
    url = URL + "forwardMessage?chat_id={}&from_chat_id={}&message_id={}".format(creator['id'], cred['bass_channel_id'],
                                                                                 orig_msg_id)
    r = requests.get(url).json()
    if not r['ok']:
        send_message(creator['id'], "ERROR with formard msg")

    reply_msg_id = r['result']['message_id']
    settings_markup = {"inline_keyboard": [[{"text": "Клавиатура❌", 'callback_data': 'del_key'}, {"text": "Клавиатура✅", 'callback_data': 'add_key'}],
                                           [{"text": "Sync🔄", 'callback_data': 'sync_with_db'}, {"text": "Пост❌", 'callback_data': 'del_msg'}]]}
    url = URL + "sendMessage?chat_id={}&text={}&reply_to_message_id={}&parse_mode=HTML".format(creator['id'], orig_msg_id, reply_msg_id)
    url += '&reply_markup={}'.format(json.dumps(settings_markup))
    requests.get(url)


def add_post_to_db(msg_id, remove=False):

        msg_id = int(msg_id)

        # обновляем подключение к бд
        mycursor, mydb = connect_db()

        if not remove:
            # добавляем этот пост в базу
            mycursor.execute("INSERT INTO channel_likes VALUES (%s, NOW() + INTERVAL 3 HOUR, 0, 0, '')", (msg_id, ))
        else:
            # удаляем из базы этот пост
            mycursor.execute("DELETE FROM channel_likes WHERE msg_id = %s", (msg_id, ))
        mydb.commit()


# Telegram methods
def send_message(text, reply_markup=None):
    url = URL + "sendMessage?chat_id={}&text={}&parse_mode=HTML".format(creator['id'], text)
    if reply_markup:
        url += f"&reply_markup={json.dumps(reply_markup)}"
    requests.get(url)


def delete_message(chat_id, message_id):
    url = URL + "deleteMessage?chat_id={}&message_id={}".format(chat_id, message_id)
    requests.get(url)


def get_file(file_id):
    url = URL + "getFile?file_id={}".format(file_id)
    r = requests.get(url)
    return json.loads(r.content)


# AWS methods
# RDS DataBase
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