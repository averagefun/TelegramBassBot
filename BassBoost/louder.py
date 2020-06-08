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

attenuate_db = 0
accentuate_db = 15


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
    mycursor.execute(f'SELECT * FROM bass_requests WHERE req_id = {req_id}')
    req = mycursor.fetchall()[0]

    # распознование запроса (req)
    chat_id = req[0]
    duration = req[3:5]
    start_bass = req[5]
    bass_level = req[6]
    file_path = req[7]
    format_ = file_path[-3:].replace('oga', 'ogg')

    if format_ not in formats_:
        # пытаемся удалить ждущий стикер, иначе ничего не делаем
        try:
            delete_message(chat_id, req_id)
        except:
            pass
        send_message(chat_id,
                     'Ошибка в декодировании файла! \n<b>Проверьте, что файл имеет формат mp3, ogg, mp4!</b>')
        send_message(chat_id, '<i>Загрузите файл для нового запроса!</i>')
        mycursor.execute(f'DELETE FROM bass_requests WHERE id = {chat_id}')
        mydb.commit()
        mycursor.execute(f"UPDATE users SET status_ = 'wait_file' WHERE id = {chat_id}")
        mydb.commit()
        return None

    time_ = round(time.time())
    filename1 = f'{time_}.{format_}'

    # скачиваем файл с телеги в tmp
    r = requests.get(
        'https://api.telegram.org/file/bot{}/{}'.format(Token, file_path))
    with open(f'/tmp/{filename1}', 'wb') as file:
        file.write(r.content)

    # преобразование файла >> сохрание в tmp под форматом mp3
    filename2 = f'{chat_id}_{time_}.mp3'
    with open(f'/tmp/{filename2}', 'wb') as file:
        combined, text = main_audio(filename1, chat_id, format_, bass_level, duration, start_bass)
        combined.export(file, format="mp3")

    # удаляем запрос и меняем статус
    mycursor.execute(f'DELETE FROM bass_requests WHERE id = {chat_id}')
    mydb.commit()
    mycursor.execute(f"UPDATE users SET status_ = 'wait_file' WHERE id = {chat_id}")
    mydb.commit()

    # удаляем ждущий стикер
    delete_message(chat_id, req_id)

    # посылаем файл
    url = 'https://api.telegram.org/bot{}/sendAudio'.format(Token)
    with open(f'/tmp/{filename2}', 'rb') as file:
        files = {'audio': file}
        data = {'chat_id': chat_id, 'title': f'{req_id}_bass'}
        requests.post(url, files=files, data=data)

    # выводим сообщение смотря на роль
    send_message(chat_id, text)

    # удаление ненужных файлов из темпа
    os.remove(f'/tmp/{filename1}')
    os.remove(f'/tmp/{filename2}')


def main_audio(filename, chat_id, format_, bass, dur=None, start_b=None):
    sample = AudioSegment.from_file(f'/tmp/{filename}', format=format_)

    # обрезка
    if dur[1]:
        sample = sample[dur[0] * 1000: dur[1] * 1000]

    # обновляем баланс и сохрагяем текст в зависимости от роли
    table_dur = len(sample) / 1000
    mycursor.execute(f'SELECT role_ FROM users WHERE id = %s', (chat_id,))
    role = mycursor.fetchone()[0]
    if role == 'start':
        mycursor.execute("""UPDATE users SET balance = 200, total = total + %s, role_ = 'start_unlimited',
                        role_end = NOW() + INTERVAL 3 HOUR + INTERVAL 2 DAY WHERE id = %s""", (table_dur, chat_id))
        mydb.commit()
        mycursor.execute("SELECT max_sec FROM roles WHERE name = 'start_unlimited'")
        text = get_text_from_db('after_req_start', {'max_sec_start_unlim': mycursor.fetchone()[0]})
    elif role == 'start_unlimited':
        mycursor.execute("UPDATE users SET total = total + %s WHERE id = %s", (table_dur, chat_id))
        text = get_text_from_db('after_req_start_unlim')
        if random.random() <= 0.3:
            text += '\n\n'
            mycursor.execute("SELECT value_param FROM payment_param WHERE name_param = 'ref_bonus'")
            text += get_text_from_db('referral', {'id': chat_id, 'ref_bonus': mycursor.fetchone()[0]})
    elif role == 'unlimited' or role == 'admin':
        mycursor.execute("UPDATE users SET total = total + %s WHERE id = %s", (table_dur, chat_id))
        text = get_text_from_db('after_req_unlim')
    else:
        mycursor.execute("SELECT balance FROM users WHERE id = %s", (chat_id, ))
        text = get_text_from_db('after_req_default', {'balance': mycursor.fetchone()[0]})
        mycursor.execute(
            f'UPDATE users SET balance = balance - %s, total = total + %s WHERE id = %s', (table_dur, table_dur, chat_id))
    mydb.commit()

    # начало баса
    if start_b:
        start_ = sample[:start_b * 1000]
        sample = sample[start_b * 1000:]

    filtered = sample.low_pass_filter(bass_line_freq(sample.get_array_of_samples(), bass))
    combined = (sample - attenuate_db).overlay(filtered + (accentuate_db * (bass + 1)))

    if start_b:
        combined = start_ + combined

    return combined, text


def bass_line_freq(track, bass):
    sample_track = list(track)
    # c-value
    est_mean = np.mean(sample_track)
    # a-value
    est_std = 3 * np.std(sample_track) / (math.sqrt(2))
    bass_factor = int(round((est_std - est_mean) * 0.005 * (bass + 1)))
    return bass_factor


# Telegram methods
def delete_message(chat_id, message_id):
    url = URL + "deleteMessage?chat_id={}&message_id={}".format(chat_id, message_id)
    requests.get(url)


def send_message(chat_id, text):
    url = URL + "sendMessage?chat_id={}&text={}&parse_mode=HTML".format(chat_id, text)
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
            except:
                return None
        return text
    admins = get_users('admin')
