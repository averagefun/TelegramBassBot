from pydub import AudioSegment
import os
import shutil
import numpy as np
import math
import boto3
import time
import requests
import mysql.connector
import random
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

# Доступные форматы
formats_ = ('mp3', 'ogg', 'mp4')

shutil.copy(r'/opt/ffmpeg/ffmpeg', r'/tmp/ffmpeg')
shutil.copy(r'/opt/ffmpeg/ffprobe', r'/tmp/ffprobe')
os.chmod(r'/tmp/ffmpeg', 755)
os.chmod(r'/tmp/ffprobe', 755)


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
    format_ = req[2]
    file_name = req[3]
    duration = req[5:7]
    start_bass = req[7]
    bass_level = req[8]
    file_path = req[9]

    # работа с форматом mpeg
    if format_ == 'mpeg':
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

    # преобразование файла >> сохрание в tmp под форматом mp3
    filename2 = f'{chat_id}_{time_}.mp3'
    # успешность декодирования файла ffmpeg
    success = True
    with open(f'/tmp/{filename2}', 'wb') as file:
        #try:
        combined, text = main_audio(filename1, chat_id, format_, bass_level, duration, start_bass)
        combined.export(file, format="mp3")
        #except:
            #success = False

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
            data = {'chat_id': chat_id, 'title': f'{file_name} BassBoosted'}
            requests.post(url, files=files, data=data)

        # выводим сообщение смотря на роль
        file_markup = {'keyboard': [['Отправьте файл боту!']], 'resize_keyboard': True}
        send_message(chat_id, text, 'reply_markup', json.dumps(file_markup))

        # удаляем BassBoost файл
        os.remove(f'/tmp/{filename2}')

    else:
        send_message(chat_id, 'Ошибка при декодировании файла!\n<b>Отправьте другой файл!</b>')


def main_audio(filename, chat_id, format_, bass, dur=None, start_b=None):
    sample = AudioSegment.from_file(f'/tmp/{filename}', format=format_)

    # обрезка
    if dur[1]:
        sample = sample[dur[0] * 1000: dur[1] * 1000]

    # обновляем баланс и сохрагяем текст в зависимости от роли
    table_dur = round(len(sample) / 1000)

    text = get_text(table_dur, chat_id)

    # начало баса
    if start_b:
        start_ = sample[:start_b * 1000]
        sample = sample[start_b * 1000:]

    attenuate_db = 0
    accentuate_db = 6 * (bass+1) ** 1.1

    filtered = sample.low_pass_filter(bass_line_freq(sample.get_array_of_samples(), bass))
    combined = (sample - attenuate_db).overlay(filtered + accentuate_db)

    if start_b:
        combined = start_ + combined

    return combined, text


def bass_line_freq(track, bass):
    sample_track = list(track)
    # c-value
    est_mean = np.mean(sample_track)
    # a-value
    est_std = 3 * np.std(sample_track) / (math.sqrt(2))
    bass_factor = int(round((est_std - est_mean) * 0.15 * (bass + 1) ** 1.1))
    return bass_factor


def get_text(table_dur, chat_id):
    mycursor.execute(f'SELECT role_ FROM users WHERE id = %s', (chat_id,))
    role = mycursor.fetchone()[0]
    if role == 'start':
        # update status
        mycursor.execute("UPDATE users SET total = total + %s, role_ = 'standard' WHERE id = %s",
                         (table_dur, chat_id))
        mydb.commit()
        # check for referral
        mycursor.execute("SELECT user_id FROM referral WHERE invited_id = %s", (chat_id, ))
        ref_user_id = mycursor.fetchone()
        if ref_user_id:
            query = "SELECT username, value_param FROM users, payment_param WHERE id = %s and name_param = 'ref_bonus'"
            mycursor.execute(query, (chat_id, ))
            username, ref_bonus = mycursor.fetchone()
            send_message(ref_user_id[0],
                            f"@{username} воспользовался вашей реферальной ссылкой! Вам начислено <b>{ref_bonus}</b> руб!")
            # обновляем таблицы
            mycursor.execute(
                "UPDATE referral, users SET referral.invited_active = 1, users.balance = users.balance + %s WHERE invited_id = %s and users.id = %s",
                                                                                                                (ref_bonus, chat_id, ref_user_id[0]))
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
        text = get_text_from_db('after_req_standard')
        mycursor.execute("UPDATE users SET total = total + %s WHERE id = %s", (table_dur, chat_id))
        mydb.commit()
        if random.random() <= 0.15:
            text += '\n\n'
            mycursor.execute("SELECT value_param FROM payment_param WHERE name_param = 'ref_bonus'")
            ref_bonus = mycursor.fetchone()[0]
            text += get_text_from_db('referral', {'id': chat_id, 'ref_bonus': ref_bonus})

    return text


# Telegram methods
def delete_message(chat_id, message_id):
    url = URL + "deleteMessage?chat_id={}&message_id={}".format(chat_id, message_id)
    requests.get(url)


def send_message(chat_id, text, *args):  # Ф-ия отсылки сообщения/ *args: [0] - parameter_name, [1] - value
    if len(args) == 0:
        url = URL + "sendMessage?chat_id={}&text={}&parse_mode=HTML".format(chat_id, text)
    elif len(args) == 2:
        url = URL + "sendMessage?chat_id={}&text={}&{}={}&parse_mode=HTML".format(chat_id, text, args[0], args[1])
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
