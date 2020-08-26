import json
import boto3
import requests
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
            send_to_bass_channel(file_id, caption)
            return
        event = json.loads(event['body'])
        print(event)
        # проверка на нажатие инлайн кнопки
        if 'callback_query' in event.keys():
            button = InlineButton(event)
            button.action()
        elif 'channel_post' in event and 'audio' in event['channel_post']:
            # добавляем кнопки у любому аудио в канале
            r = update_buttons(event['channel_post'])
            add_post_to_db(r)

    except Exception as e:
        print(f'ERROR:{e} || EVENT:{event}')
        send_message(creator['id'], f'ERROR:\n{e}\nEVENT:\n{event}')

    # в любом случае возвращаем телеграму код 200
    return {'statusCode': 200}


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

            # обновляем кол-во лайков/дизлайков
            markup = self.msg['reply_markup']['inline_keyboard'][0]
            likes = int(markup[0]['text'].split()[1])
            dislikes = int(markup[1]['text'].split()[1])

            if self.data == 'like':
                likes += 1
            else:
                dislikes += 1

            update_buttons(self.msg, likes, dislikes)

    def answer_query(self, text, show_alert=False):
        url = URL + "answerCallbackQuery?callback_query_id={}&text={}&show_alert={}".format(self.call_id, text,
                                                                                            show_alert)
        requests.get(url)

    def answer_query_no_text(self):
        url = URL + "answerCallbackQuery?callback_query_id={}".format(self.call_id)
        requests.get(url)


def like_markup(likes, dislikes):
    return {"inline_keyboard": [[{"text": f"👍 {likes}", 'callback_data': 'like'}, {"text": f"👎 {dislikes}", 'callback_data': 'dislike'}]]}


def update_buttons(post, likes=0, dislikes=0):
    chat_id = post['chat']['id']
    message_id = post['message_id']
    url = URL + "editMessageReplyMarkup?chat_id={}&message_id={}&reply_markup={}".format(
        chat_id, message_id, json.dumps(like_markup(likes, dislikes)))
    r = requests.get(url).json()
    return r


def send_to_bass_channel(bass_file_id, caption=None):
    url = URL + "sendAudio?chat_id={}&audio={}&parse_mode=HTML".format(cred['bass_channel_id'], bass_file_id)
    if caption:
        url += f'&caption=<b>{caption}</b>'
    url += '&reply_markup={}'.format(json.dumps(like_markup(0, 0)))
    r = requests.get(url).json()
    add_post_to_db(r)


def add_post_to_db(r):
    if r['ok']:
        msg_id = r['result']['message_id']
        # обновляем подключение к бд
        mycursor, mydb = connect_db()
        # добавляем этот пост в базу
        mycursor.execute("INSERT INTO channel_likes VALUES (%s, NOW() + INTERVAL 3 HOUR, 0, 0, '')", (msg_id, ))
        mydb.commit()


# Telegram methods
def send_message(chat_id, text, reply_markup=None):
    url = URL + "sendMessage?chat_id={}&text={}&parse_mode=HTML".format(chat_id, text)
    if reply_markup:
        url += f"&reply_markup={json.dumps(reply_markup)}"
    requests.get(url)


def delete_message(chat_id, message_id):
    url = URL + "deleteMessage?chat_id={}&message_id={}".format(chat_id, message_id)
    requests.get(url)


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