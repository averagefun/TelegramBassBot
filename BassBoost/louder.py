from pydub import AudioSegment
import os
import shutil
import numpy as np
import math
import time
import requests
import mysql.connector
import json

from cred import get_cred

cred = get_cred()

# Доступные форматы
formats_ = ('mp3', 'ogg', 'mp4')
# Путь для временного хранения файлов
path = '/tmp'

shutil.copy(r'/opt/ffmpeg/ffmpeg', r'/tmp/ffmpeg')
shutil.copy(r'/opt/ffmpeg/ffprobe', r'/tmp/ffprobe')
os.chmod(r'/tmp/ffmpeg', 755)
os.chmod(r'/tmp/ffprobe', 755)


def lambda_handler(event, context=None):
    if context: print(event)

    message = event['Records'][0]['Sns']['Message']

    # получаем req_id
    req_id = int(message)

    bot = TelegramBot()
    req = bot.fetchone("SELECT * FROM bass_requests WHERE req_id = %s", req_id)

    # распознование запроса (req)
    bot.chat_id = req[0]
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
        'https://api.telegram.org/file/bot{}/{}'.format(bot.token, file_path))
    with open(f'{path}/{filename1}', 'wb') as file:
        file.write(r.content)

    # получаем параметры для преобразования файла из таблицы [name, att_db, acc_db, bass_factor]
    params = bot.fetchone("SELECT * FROM bass_levels WHERE num = %s", bass_level)[1:]
    name = params[0]

    # преобразование файла >> сохрание в tmp под форматом mp3
    filename2 = f'{bot.chat_id}_{time_}.mp3'
    success = True
    # noinspection PyBroadException
    try:
        sample = AudioSegment.from_file(f'{path}/{filename1}', format=format_)

        # обрезка
        sample = sample[duration[0] * 1000: duration[1] * 1000]

        # обновляем total
        table_dur = round(len(sample) / 1000)
        bot.db_commit("UPDATE users SET total = total + %s WHERE id = %s",
                      (table_dur, bot.chat_id))

        if 'bass' in name:
            result = bass_boosted(sample, params)
        elif '8D' in name:
            result = audio_8d(sample, params[3])
        else:
            result = None

        with open(f'{path}/{filename2}', 'wb') as file:
            result.export(file, format="mp3")

        text = bot.get_db_text('after-req')
        ad = bot.get_db_text('ad-html', ent=False)
        if ad != 'None': text += '\n\n' + ad
    except Exception as e:
        TelegramBot.send_alert(e)
        text = "Ошибка при декодировании файла!\n<b>Отправьте другой файл!</b>"
        success = False

    # удаляем запрос и меняем статус
    bot.db_commit("DELETE FROM bass_requests WHERE user_id = %s", bot.chat_id)
    bot.db_commit("UPDATE users SET user_status = 'wait_file' WHERE id = %s", bot.chat_id)

    # удаляем ждущий стикер
    bot.delete_message(req_id)

    # удаление первого файла из темпа
    os.remove(f'{path}/{filename1}')

    if success:
        # посылаем файл
        url = 'https://api.telegram.org/bot{}/sendAudio'.format(bot.token)
        with open(f'{path}/{filename2}', 'rb') as file:
            files = {'audio': file}
            add = 'Bass' if ('bass' in name) else "8D"
            data = {'chat_id': bot.chat_id, 'title': f'{file_name}{add}', 'performer': "@AudioBassBot"}
            r = requests.post(url, files=files, data=data)

        # удаляем BassBoost файл
        os.remove(f'{path}/{filename2}')

        username = bot.fetchone("SELECT username FROM users WHERE id = %s", bot.chat_id)
        username = '@' + username if username else bot.chat_id

        # посылаем 2 файла в канал
        bass_file_id = json.loads(r.content)['result']['audio']['file_id']
        bot.send_to_channel(file_id, bass_file_id, username, name)

    # выводим сообщение смотря на роль и ошибку в преобразовании файла
    bot.send_message(text, 'file_markup')


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


class DataBase:
    def __init__(self):
        self.mydb = mysql.connector.connect(
            host=cred['db_host'],
            user=cred['db_user'],
            passwd=cred['db_passwd'],
            database=cred['db_name']
        )
        self.mycursor = self.mydb.cursor(buffered=True)

    def db_commit(self, query, params=None, many=False):
        if many:
            self.mycursor.executemany(query, params)
        else:
            self.mycursor.execute(query, self.to_tuple(params))
        self.mydb.commit()

    def fetchall(self, query, params=None):
        self.mycursor.execute(query, self.to_tuple(params))
        r = self.mycursor.fetchall()

        if not r:
            return None
        elif len(r[0]) == 1:
            return tuple(e[0] for e in r)
        else:
            return r

    def fetchone(self, query, params=None):
        self.mycursor.execute(query, self.to_tuple(params))
        r = self.mycursor.fetchone()

        if not r:
            return None
        elif len(r) == 1:
            return r[0]
        else:
            return r

    @staticmethod
    def to_tuple(params):
        if params is None:
            return None
        elif isinstance(params, (tuple, list)):
            return params
        else:
            return (params,)

    def get_db_text(self, tag, ent=True):
        r = self.fetchone("SELECT text, entities FROM saved_texts WHERE tag = %s", tag)

        if r:
            text, entities = r
        else:
            self.db_commit("INSERT INTO saved_texts (tag) VALUES (%s)", tag)
            text = entities = None

        if not text: text = 'None'
        if ent: return text, entities
        return text

    def set_db_text(self, tag, new_value=None):
        if isinstance(new_value, (list, tuple)):
            new_value, entities = new_value
            entities = json.dumps(entities) if entities else None
        else:
            entities = None
        self.db_commit("UPDATE saved_texts SET text = %s, entities=%s WHERE tag = %s",
                       (new_value, entities, tag))


class TelegramBot(DataBase):
    token = cred['bot_token']
    URL = "https://api.telegram.org/bot{}/".format(token)

    tag_reply_markups = {
        'cut_markup': [['Обрезать не нужно']],
        'file_markup': [['Отправьте файл боту!🎧']]}
    levels = ["🔈Bass Low", "🔉Bass High", "🔊Bass ULTRA", "🎧8D"]
    tag_inline_markups = {}
    stickers = {'hello': 'CAACAgIAAxkBAALD_2D9ElJ2HbPzDUTRkNlZWbWMOwg_AAIBAQACVp29CiK-nw64wuY0IAQ'}

    def __init__(self, chat_id=0):
        self.from_id = self.chat_id = chat_id
        super().__init__()

    def update_status(self, new_status):
        self.db_commit("UPDATE users SET user_status = %s WHERE id = %s", (new_status, self.chat_id))

    def gen_markup(self, mark):
        if isinstance(mark, dict):
            markup = mark
        elif isinstance(mark, list):
            cell = mark[0][0]
            if isinstance(cell, dict):
                markup = {'inline_keyboard': mark}
            else:
                markup = {"keyboard": mark, 'resize_keyboard': True}
        elif mark in self.tag_reply_markups:
            # reply_markup
            markup = {'keyboard': self.tag_reply_markups[mark], 'resize_keyboard': True}
        elif mark in self.tag_inline_markups:
            # произвольная markup
            markup = {'inline_keyboard': self.tag_inline_markups[mark]}
        else:
            markup = None
        return json.dumps(markup)

    @classmethod
    def bass_markup(cls, cut=True):
        markup = {'keyboard': [[cls.levels[0], cls.levels[1]], [cls.levels[2], cls.levels[3]], ["❌Отменить"]],
                  'one_time_keyboard': True,
                  'resize_keyboard': True}
        if cut:
            markup['keyboard'][-1] = ["✂Обрезать файл", "❌Отменить"]
        return markup

    @classmethod
    def send_alert(cls, text):
        url = cls.URL + "sendMessage?chat_id={}&text={}&parse_mode=HTML&disable_web_page_preview=True".format(
            cred['creator_id'], text)
        requests.get(url)

    def send_message(self, text, reply_markup=None):
        if isinstance(text, (list, tuple)):
            text, entities = text
        else:
            entities = None

        url = self.URL + "sendMessage"
        params = {
            "chat_id": self.chat_id,
            "text": text,
            "disable_web_page_preview": True
        }

        if entities:
            params['entities'] = entities
        else:
            params['parse_mode'] = 'HTML'

        if reply_markup:
            params["reply_markup"] = self.gen_markup(reply_markup)
        r = requests.get(url, params).json()
        return r['result']['message_id']

    def send_message_to_id(self, chat_id, text, reply_markup=None):

        url = self.URL + "sendMessage"
        params = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True
        }
        if reply_markup:
            params["reply_markup"] = self.gen_markup(reply_markup)
        r = requests.get(url, params).json()
        return r['result']['message_id']

    def send_reply_message(self, text, reply_to_msg_id):
        url = self.URL + "sendMessage?chat_id={}&text={}&reply_to_message_id={}&parse_mode=HTML".format(
            self.chat_id, text, reply_to_msg_id)
        requests.get(url)

    def edit_message(self, message_id, text, reply_markup=None):
        url = self.URL + "editMessageText?chat_id={}&message_id={}&text={}&parse_mode=HTML&" \
                         "disable_web_page_preview=true".format(self.chat_id, message_id, text)
        if reply_markup:
            url += f"&reply_markup={self.gen_markup(reply_markup)}"
        requests.get(url)

    def delete_message(self, message_id):
        url = self.URL + "deleteMessage?chat_id={}&message_id={}".format(
            self.chat_id, message_id)
        requests.get(url)

    def edit_markup(self, message_id, reply_markup=None):
        url = self.URL + "editMessageReplyMarkup?chat_id={}&message_id={}".format(
            self.chat_id, message_id)
        if reply_markup:
            url += f"&reply_markup={self.gen_markup(reply_markup)}"
        requests.get(url)

    def send_sticker(self, sticker):
        if sticker not in self.stickers:
            return round(time.time())
        url = self.URL + "sendSticker?chat_id={}&sticker={}".format(
            self.chat_id, self.stickers[sticker]
        )
        r = requests.get(url).json()
        return r['result']['message_id']

    def get_chat_member_status(self):
        url = self.URL + 'getChatMember?chat_id={}&user_id={}'.format(
            self.chat_id, self.from_id)
        r = requests.get(url).json()
        return r['result']['status']

    def get_file(self):
        # get file_id from db
        file_id = self.fetchone('SELECT file_id FROM bass_requests WHERE user_id = %s', self.chat_id)
        # make request
        url = self.URL + "getFile?file_id={}".format(file_id)
        r = requests.get(url)
        return json.loads(r.content)

    @classmethod
    def send_to_channel(cls, file_id, bass_file_id, username, bass_level):
        url = cls.URL + "sendAudio?chat_id={}&audio={}&caption={}&parse_mode=HTML".format(
            cred['all_music_channel_id'], file_id, f'<b>{username}</b>')
        requests.get(url)
        url = cls.URL + "sendAudio?chat_id={}&audio={}&caption={}&parse_mode=HTML".format(
                cred['all_music_channel_id'], bass_file_id, f'<b>{username} {bass_level}</b>')
        requests.get(url)
