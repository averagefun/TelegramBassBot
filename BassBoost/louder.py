from pydub import AudioSegment
import os
import shutil
import numpy as np
import math
import boto3
import time
import requests
import mysql.connector
import json


def lambda_handler(event, context):
    global mycursor
    global mydb
    # обновляем подключение к бд
    mycursor, mydb = connect_db()

    print(event)

    message = event['Records'][0]['Sns']['Message']

    # получаем req_id
    req_id = int(message)

    mydb.commit()
    mycursor.execute(f'SELECT * FROM bass_requests WHERE req_id = %s', (req_id, ))
    req = mycursor.fetchone()

    # распознование запроса (req)
    chat_id = req[0]
    file_id = req[1]
    format_ = req[2]

    file_name = req[3]
    file_split = file_name.split('|')
    if len(file_split) == 2:
        if file_split[0] == '@AudioBassBot':
            file_name = file_split[1] + '+'
        elif file_split[0] == '<unknown>':
            file_name = file_split[1]
        else:
            file_name = f"{file_split[0]} - {file_split[1]}"

    duration = req[4:6]
    bass_level = req[6]
    file_path = req[7]

    # работа с форматом mpeg
    if 'mpeg' in format_:
        if file_path[-3:] == 'mp3':
            format_ = 'mp3'
        else:
            format_ = 'mp4'

    time_ = round(time.time())
    filename1 = f'{time_}.{format_}'

    # скачиваем файл с телеги в tmp
    r = requests.get(
        'https://api.telegram.org/file/bot{}/{}'.format(Token, file_path))
    with open(f'/tmp/{filename1}', 'wb') as file:
        file.write(r.content)

    # получаем параметры для преобразования файла из таблицы
    mycursor.execute("SELECT * FROM bass_levels WHERE num = %s", (bass_level, ))
    params = mycursor.fetchone()[1:]     # name, att_db, acc_db, bass_factor
    name = params[0]

    # преобразование файла >> сохрание в tmp под форматом mp3
    filename2 = f'{chat_id}_{time_}.mp3'
    success = True
    try:
        sample = AudioSegment.from_file(f'/tmp/{filename1}', format=format_)

        # обрезка
        sample = sample[duration[0] * 1000: duration[1] * 1000]

        # обновляем баланс и сохрагяем текст в зависимости от роли
        table_dur = round(len(sample) / 1000)
        text = get_text(table_dur, chat_id)

        if 'bass' in name:
            result = bass_boosted(sample, params)
        elif '8D' in name:
            result = audio_8d(sample, params[3])
        else:
            result = None

        with open(f'/tmp/{filename2}', 'wb') as file:
            result.export(file, format="mp3")

    except Exception:
        text = "Ошибка при декодировании файла!\n<b>Отправьте другой файл!</b>"
        success = False

    # удаляем запрос и меняем статус
    mycursor.execute(f'DELETE FROM bass_requests WHERE id = %s', (chat_id, ))
    mydb.commit()
    mycursor.execute(f"UPDATE users SET status_ = 'wait_file' WHERE id = %s", (chat_id, ))
    mydb.commit()

    # удаляем ждущий стикер
    delete_message(chat_id, req_id)

    # удаление первого файла из темпа
    os.remove(f'/tmp/{filename1}')

    if success:
        # посылаем файл
        url = 'https://api.telegram.org/bot{}/sendAudio'.format(Token)
        with open(f'/tmp/{filename2}', 'rb') as file:
            files = {'audio': file}
            add = 'Bass' if ('bass' in name) else "8D"
            data = {'chat_id': chat_id, 'title': f'{file_name}{add}', 'performer': "@AudioBassBot"}
            r = requests.post(url, files=files, data=data)

        # удаляем BassBoost файл
        os.remove(f'/tmp/{filename2}')

        # посылаем 2 файла в канал
        mycursor.execute("SELECT username FROM users WHERE id = %s", (chat_id,))
        username = mycursor.fetchone()[0]

        bass_file_id = json.loads(r.content)['result']['audio']['file_id']
        send_to_channel(file_id, bass_file_id, username, name)

    # выводим сообщение смотря на роль и ошибку в преобразовании файла
    send_message(chat_id, text, file_markup)


def bass_boosted(sample, params):

    def bass_line_freq(track, fact):
        sample_track = list(track)
        # c-value
        est_mean = np.mean(sample_track)
        # a-value
        est_std = 3 * np.std(sample_track) / (math.sqrt(2))
        bass_factor = int(round((est_std - est_mean) * fact))
        return bass_factor

    attenuate_db = params[1]
    accentuate_db = params[2]

    filtered = sample.low_pass_filter(bass_line_freq(sample.get_array_of_samples(), params[3]))
    return (sample - attenuate_db).overlay(filtered + accentuate_db)


def audio_8d(sample, level):
    pole = []
    ranges = int(sample.duration_seconds)
    pan = 0
    down = True
    bottom = False
    for x in range(1, 10 * ranges):
        y = x * 100
        z = (x * 100) - 100

        pole.append(sample[z: y].pan(pan))

        timestamp = float(len(pole) / 10)

        if timestamp >= 60:
            minuta = int(timestamp / 60)
            timestamp = "{:.2f}".format(timestamp - minuta * 60)

        z += 1000

        if pan <= 0:
            if down:
                pan -= 0.05
            else:
                pan += 0.05

        if pan >= 0:
            if down:
                pan -= 0.05
            else:
                pan += 0.05

        if pan <= -level:
            down = False
            if not bottom:
                bottom = True
        elif pan >= level:
            down = True
            if bottom:
                bottom = False

    return sum(pole)


# Telegram methods
def delete_message(chat_id, message_id):
    url = URL + "deleteMessage?chat_id={}&message_id={}".format(chat_id, message_id)
    requests.get(url)


def send_message(chat_id, text, reply_markup=None):
    url = URL + "sendMessage?chat_id={}&text={}&parse_mode=HTML&disable_web_page_preview=True".format(chat_id, text)
    if reply_markup:
        url += f"&reply_markup={json.dumps(reply_markup)}"
    r = requests.get(url).json()
    return r


def alarm(text):
    send_message(int(cred['creator_id']), text)


def send_to_channel(file_id, bass_file_id, username, bass_level):
    url = URL + "sendAudio?chat_id={}&audio={}&caption={}&parse_mode=HTML".format(cred['admin_all_channel_id'], file_id, f'<b>@{username}</b>')
    requests.get(url)
    url = URL + "sendAudio?chat_id={}&audio={}&caption={}&parse_mode=HTML".format(cred['admin_all_channel_id'], bass_file_id, f'<b>@{username} {bass_level}</b>')
    requests.get(url)


# AWS methods
# подключение к бд
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


# Get cred
def get_cred():
    dynamodb = boto3.resource('dynamodb')
    table = dynamodb.Table('CredTableTBot')
    items = table.scan()['Items']
    keys = [item['cred_name'] for item in items]
    values = [item['cred_value'] for item in items]
    cred = dict(zip(keys, values))
    return cred


def get_text(table_dur, chat_id):
    mycursor.execute(f'SELECT role_ FROM users WHERE id = %s', (chat_id,))
    role = mycursor.fetchone()[0]
    if role == 'start':
        # update status
        mycursor.execute("UPDATE users SET total = total + %s, role_ = 'standard' WHERE id = %s",
                         (table_dur, chat_id))
        mydb.commit()

        mycursor.execute("SELECT max_sec FROM roles WHERE name = 'standard'")
        max_sec_standard = mycursor.fetchone()[0]
        text = get_text_from_db('after_req_start', {'max_sec_standard': max_sec_standard})

    elif role == 'premium' or role == 'admin':
        mycursor.execute("UPDATE users SET total = total + %s WHERE id = %s", (table_dur, chat_id))
        mydb.commit()
        text = get_text_from_db('after_req_standard')

    # standard
    else:
        mycursor.execute("SELECT text FROM msgs WHERE name IN ('after_req_standard', 'adv')")
        f = mycursor.fetchall()
        text = f[0][0]
        adv = f[1][0]

        mycursor.execute("UPDATE users SET total = total + %s WHERE id = %s", (table_dur, chat_id))
        mydb.commit()
        if adv.lower() != "null":
            text += f'\n\n{adv}'
    return text


cred = get_cred()

# TelegramBot
Token = cred['bot_token']
URL = "https://api.telegram.org/bot{}/".format(Token)

# Доступные форматы
formats_ = ('mp3', 'ogg', 'mp4')

shutil.copy(r'/opt/ffmpeg/ffmpeg', r'/tmp/ffmpeg')
shutil.copy(r'/opt/ffmpeg/ffprobe', r'/tmp/ffprobe')
os.chmod(r'/tmp/ffmpeg', 755)
os.chmod(r'/tmp/ffprobe', 755)

file_markup = {'keyboard': [['Отправьте файл боту!🎧']], 'resize_keyboard': True}
