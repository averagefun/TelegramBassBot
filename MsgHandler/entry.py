import traceback
import json
import time
from math import ceil
from multiprocessing import Process

from pytube import YouTube
import requests
import boto3
import mysql.connector

from cred import get_cred, BOT_ACTIVE

cred = get_cred()

not_active_msg = 'Извините, бот временно отдыхает. Идёт обновление кода.'


####################
#  lambda_handler  #
####################
def lambda_handler(event, context):
    p = Process(target=handler, args=(event, ))
    p.start()
    left = context.get_remaining_time_in_millis()//1000 - 1
    p.join(timeout=left)
    p.terminate()

    if p.exitcode is None:
        print("TIMEOUT!")
        TelegramBot.send_alert("TIMEOUT")

    # в любом случае возвращаем телеграму код 200
    return {'statusCode': 200}


def handler(event):
    # обрабатываем любые исключения
    try:
        event = json.loads(event['body'])
        print(event)

        if BOT_ACTIVE:
            msg_handler(event)
        else:
            debug_handler(event)

    except Exception:
        out = str(traceback.format_exc()) + '\nEVENT:\n' + str(event)
        print(out)
        TelegramBot.send_alert(out)


def msg_handler(event):
    if 'my_chat_member' in event:
        my_member = event['my_chat_member']
        chat_id = my_member['chat']['id']
        new_status = my_member['new_chat_member']['status']

        if new_status == 'kicked':
            bot = TelegramBot(chat_id)
            bot.db_commit("DELETE FROM users WHERE id = %s", chat_id)
            bot.db_close()
        return

    # проверка на нажатие инлайн кнопки
    elif 'callback_query' in event.keys():
        button = InlineButton(event)
        button.action()
        return button.db_close()

    # инициализация юзера
    user = User(event)
    # проверка на успешную инициализацию
    if not user.init_success:
        return user.db_close()

    # проверяем: это сообщение или файл - находим общие ключи
    c = list(set(user.msg.keys()) & tags)
    if c:  # юзер залил файл
        user.file(c[0])
    else:  # Юзер написал текст
        user.message()
    user.db_close()


def debug_handler(event):
    if 'callback_query' in event.keys():
        chat_id = event['callback_query']['message']['chat']['id']
    elif 'message' in event.keys():
        chat_id = event['message']['chat']['id']
    else: return

    if chat_id == cred['creator_id']:
        msg_handler(event)
    else:
        TelegramBot.send_alert("Извините, бот временно отдыхает. Идёт обновление кода.", chat_id)


class DataBase:
    def __init__(self):
        self.mydb = mysql.connector.connect(
            host=cred['db_host'],
            user=cred['db_user'],
            passwd=cred['db_passwd'],
            database=cred['db_name']
        )
        self.mycursor = self.mydb.cursor(buffered=True)

    def db_close(self):
        self.mycursor.close()
        self.mydb.close()

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
        if not params:
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

    def del_db_text(self, tag):
        self.db_commit("DELETE FROM saved_texts WHERE tag = %s", tag)


class TelegramBot(DataBase):
    token = cred['bot_token']
    URL = "https://api.telegram.org/bot{}/".format(token)

    if BOT_ACTIVE: lazy_db = DataBase()

    tag_reply_markups = {
        'cut_markup': [['Обрезать не нужно']],
        'file_markup': [['👉Отправьте файл🎧|YouTube-ссылку🔗']],
        'cancel_markup': [['Вернуться в меню']]}
    levels = ["🔈Bass Low", "🔉Bass High", "🔊Bass ULTRA", "🎧8D+Reverb"]
    tag_inline_markups = {}
    stickers = {'hello': 'CAACAgIAAxkBAALD_2D9ElJ2HbPzDUTRkNlZWbWMOwg_AAIBAQACVp29CiK-nw64wuY0IAQ',
                'loading': 'CAACAgIAAxkBAAN_Xre2LtYeBDA-3_ewh5kMueCsRWsAAgIBAAJWnb0KTuJsgctA5P8ZBA'}

    def __init__(self, chat_id):
        self.from_id = self.chat_id = chat_id
        if BOT_ACTIVE or self.chat_id == cred['creator_id']:
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
    def send_alert(cls, text, chat_id=None):
        if not chat_id: chat_id = cred['creator_id']
        url = cls.URL + "sendMessage?chat_id={}&text={}&parse_mode=HTML&disable_web_page_preview=True".format(
            chat_id, text)
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

    def get_file(self, file_id):
        # make request
        url = self.URL + "getFile?file_id={}".format(file_id)
        r = requests.get(url)
        return json.loads(r.content)


class User(TelegramBot):
    def __init__(self, event):
        self.msg = event['message']

        # проверка что это сообщение от пользователя, а не мусор
        try:
            self.chat_id = self.msg['chat']['id']
        except KeyError:
            self.init_success = False
            return

        self.text = self.msg['text'] if 'text' in self.msg else None

        super().__init__(self.chat_id)

        if 'username' in self.msg['chat']:
            self.username = self.msg['chat']['username']
        else:
            self.username = None

        self.init_success = True

        user_info = self.fetchone('SELECT username, user_status FROM users WHERE id = %s', self.chat_id)

        # init new user
        if not user_info:
            self.db_commit("INSERT INTO users (id, username, reg_date) VALUES (%s, %s, NOW() + INTERVAL 3 HOUR)",
                           (self.chat_id, self.username))
            self.status = 'start'
        else:
            db_username, self.status = user_info

            # проверяем на изменённый ник
            if self.username != db_username:
                self.db_commit("UPDATE users SET username = %s WHERE id = %s", (self.username, self.chat_id))

        '''  SQL user_status:
                    start : начальное приветствие,
                    wait_file: бот ожидает файл,
                    wait_cut: бот ожидает ввод обрезки файла,
                    wait_bass_start: бот ожидает ввода начала басса,
                    wait_bass_level: бот ожидает ввод уровня басса,
                    req_sent: запрос отправлен, ожидание получения файла от BassBoost
        '''

    def commands(self):
        command = self.text.split()[0]

        # начальное сообщение-приветствие
        if command == '/start':
            self.send_message("Бот уже <b>запущен</b> и ожидает\nфайл/сообщение!\n<i>/help - помощь по боту</i>")

        # удаление запроса
        elif command == '/cancel':
            self.db_commit('DELETE FROM bass_requests WHERE user_id = %s', self.chat_id)
            self.db_commit("UPDATE users SET user_status = 'wait_file' WHERE id = %s", self.chat_id)
            self.send_message('<b>Запрос отменён!</b>\n<i>Загрузите файл для нового запроса.</i>', 'file_markup')
            return

        elif command == '/help':
            self.send_message(self.get_db_text('help'))
            return

        # статистика по пользователям
        elif command == '/users' and self.chat_id == cred['creator_id']:
            self.send_message(self.fetchone("SELECT count(*) FROM users WHERE total > 0"))

        # изменение текстов
        elif command == '/texts' and self.chat_id == cred['creator_id']:
            tags = self.fetchall("SELECT tag FROM saved_texts")
            inline_keyboard = []
            row = []
            for tag in tags:
                row.append({'text': tag, 'callback_data': f'text__show_{tag}'})
                if len(row) == 2:
                    inline_keyboard.append(row)
                    row = []
            if len(row) > 0: inline_keyboard.append(row)
            self.send_message("<b>Доступные тексты:</b>", inline_keyboard)
        elif command == '/users' and self.chat_id == cred['creator_id']:
            self.send_message(self.fetchone("SELECT count(*) FROM users"))
        else:
            self.send_message("Команда <b>не найдена</b>!")

    def file(self, tag):
        # проверка на статус юзера
        if self.status != "wait_file":
            return self.send_message(
                'Извините, но на данном этапе не нужно загружать файл. <i>Введите корректный ответ!</i>')

        audio = self.msg[tag]

        # определение формата (если video_note >> mp4)
        if tag != 'video_note':
            format_ = audio['mime_type'].split('/')[1]
        else:
            format_ = 'mp4'

        # проверка на формат
        if format_ not in formats:
            self.send_message(
                "Неизвестный формат файла. \n<i>Доступные форматы: mp3, ogg, mp4.</i>" +
                "\nПожалуйста, <b>загрузите другой файл!</b>")
            self.db_commit(f'DELETE FROM bass_requests WHERE user_id = %s', self.chat_id)
            return

        # проверка на длительность и размер файла
        duration = round(audio['duration'])
        if audio['file_size'] > cred['maxsize']:
            return self.send_message(
                f"Мы не работаем с файлами больше {round(cred['maxsize'] / 10 ** 6, 1)} Мб." +
                "\n<b>Выберите файл поменьше!</b>")

        # удаляем все предыдущие запросы во избежании багов
        self.db_commit('DELETE FROM bass_requests WHERE user_id = %s', self.chat_id)

        # пытаемся определить название файла
        if 'performer' in audio and 'title' in audio:
            title = f"{audio['performer'].replace('|', ' ')}|{audio['title'].replace('|', ' ')}"
        elif 'title' in audio:
            title = audio['title'].replace('|', ' ')
        elif 'performer' in audio:
            title = audio['performer'].replace('|', ' ')
        else:
            title = 'Audio'

        # начинаем формировать запрос
        self.db_commit(
            "INSERT INTO bass_requests (user_id, file_id, format_, end_, file_name) VALUES (%s, %s, %s, %s, %s)",
            (self.chat_id, audio['file_id'], format_, duration, title))

        self.send_message('Файл принят! <b>Теперь можно выбрать уровень усиления трека или сначала обрезать его:</b>',
                          self.bass_markup())

        # обновляем статус
        self.update_status('wait_bass_level')

        # посылаем запрос к BassBoostFunction, чтобы разбудить её в случае сна
        put_sns('BassBoostTrigger', 'wakey')

    def send_req_to_bass(self):

        # автообрезание
        file_id, duration, start = self.fetchone(
            "SELECT file_id, end_ - start_, start_ from bass_requests where user_id = %s",
            self.chat_id)
        process_time = ceil(min(duration, cred['max_sec']) / 35) * 10
        text = f"<b>Запрос отправлен!</b> Ожидайте файл в течение {process_time} секунд."
        if cred['max_sec'] < duration:
            text += f" <i>Учтите, что аудио будет обрезано до {cred['max_sec']} секунд в связи с ограничениями на " \
                    f"размер аудио.</i> "
            self.db_commit('UPDATE bass_requests SET end_ = %s where user_id = %s',
                           (cred['max_sec'] + start, self.chat_id))

        # посылаем запрос
        self.send_message(text)
        # получаем id сообщения (стикер с думающим утёнком)
        req_id = self.send_sticker('loading')

        if file_id[:7] != 'youtube':
            file = self.get_file(file_id)
            # аварийная проверка на размер
            assert file['result']['file_size'] <= cred['maxsize']
            file_path = file['result']['file_path']
        else:
            file_path = file_id[8:]

        self.db_commit(f"UPDATE bass_requests SET req_id = %s, file_path = %s WHERE user_id = %s",
                       (req_id, file_path, self.chat_id))
        self.db_commit("UPDATE users SET user_status = 'req_sent', last_query = NOW() + INTERVAL 3 HOUR WHERE id = %s",
                       self.chat_id)
        put_sns('BassBoostTrigger', req_id)

    def message(self):
        # если в сообщении нет текста
        if not self.text:
            # если мы сейчас ожидаем аудио >> неизвестный формат
            if self.status == "wait_file":
                self.send_message('<b>Ошибка!</b>\nВы отправили файл <b>документом</b>!' +
                                  '\nВ этом случае бот не может узнать кодировку аудио и его продолжительность.' +
                                  '\n<b>Отправьте файл в виде аудио!</b>')

            # иначе мы получили неизвестный документ, когда ожидали сообщение
            else:
                self.send_message('Ошибка! Введите ваш ответ более корректно!')
            return

        # start
        if self.status == "start":
            self.send_sticker('hello')
            self.send_message(self.get_db_text('start'))
            self.update_status('wait_file')

        # command
        elif self.text[0] == '/':
            self.commands()

        elif self.status == "wait_file":
            # если это не ссылка
            if self.text[:5] != 'https':
                return self.send_message('Пожалуйста, отправьте <b>файл🎧 или YouTube-ссылку🔗</b>!', 'file_markup')

            # вроде как ссылка
            try:
                yt = YouTube(self.text)
                if yt.length > 420:
                    return self.send_message("Это видео слишком длинное (более 7 минут).\n"
                                             "<b>Выберите видео поменьше или загрузите файл!</b>")
            except Exception:
                return self.send_message(
                    "Видео не найдено.\n<b>Отправьте другую ссылку или файл.</b>",
                    'file_markup')

            # if audio.filesize > cred['maxsize']: return self.send_message( f"Это видео слишком длинное,
            # аудиодорожка занимает больше {round(cred['maxsize'] / 10 ** 6, 1)} Мб." "\n<b>Выберите видео поменьше
            # или загрузите файл!</b>")

            # удаляем все предыдущие запросы во избежании багов
            self.db_commit('DELETE FROM bass_requests WHERE user_id = %s', self.chat_id)

            title = ' '.join(f'{yt.title} F'[:60].split()[:-1]).replace('|', ' ')
            # начинаем формировать запрос
            self.db_commit(
                "INSERT INTO bass_requests (user_id, file_id, format_, end_, file_name) VALUES (%s, %s, %s, %s, %s)",
                (self.chat_id, 'youtube:' + self.text, 'mp4', yt.length, title))

            self.send_message(
                '<b>Все ок! Теперь можно выбрать уровень усиления трека или сначала обрезать его:</b>',
                self.bass_markup())

            # обновляем статус
            self.update_status('wait_bass_level')

            # посылаем запрос к BassBoostFunction, чтобы разбудить её в случае сна
            put_sns('BassBoostTrigger', 'wakey')

        # выбор уровня баса
        elif self.status == "wait_bass_level":
            if self.text in self.levels:
                # уровень баса в словах >> цифры
                curr_level = self.levels.index(self.text)
                self.db_commit('UPDATE bass_requests SET bass_level = %s WHERE user_id = %s',
                               (curr_level, self.chat_id))

                # отправляем запрос к BassBoostFunc
                self.send_req_to_bass()

            elif self.text == '✂Обрезать файл':
                self.update_status('wait_cut')
                self.send_message('<b>Укажи границы обрезки файла</b>.\n' +
                                  '<i>Пример (вводить без кавычек): "1.5 10" - обрезка песни с 1.5 по 10 секунду.</i>',
                                  'cut_markup')
            elif self.text == "❌Отменить":
                self.db_commit('DELETE FROM bass_requests WHERE user_id = %s', self.chat_id)
                self.update_status('wait_file')
                self.send_message('<b>Запрос отменён!</b> \n<i>Загрузите файл для нового запроса.</i>', 'file_markup')
                return
            else:
                # непонятный уровень баса, введённый пользователем
                self.send_message('Пожалуйста, нажмите одну из кнопок на <b>клавиатуре!</b>',
                                  self.bass_markup())

        # обрезка файла
        elif self.status == "wait_cut":
            if self.text != 'Обрезать не нужно':
                # находим длительность файла
                duration = self.fetchone('SELECT end_ - start_ from bass_requests where user_id = %s', self.chat_id)

                s = self.text.split()
                # проверка, что введено 2 значения
                if len(s) != 2:
                    self.send_message("<b>Введите 2 числа!</b>")
                    return

                # проверка, что введены именно ЧИСЛА
                try:
                    f0 = round(float(s[0]), 1)
                    f1 = round(float(s[1]), 1)
                except ValueError:
                    self.send_message('Синтаксическая ошибка! \n<b>Проверьте, что десятичная дробь записана через '
                                      'точку!</b>', 'cut_markup')
                    return
                if (f0 >= 0) and (f0 < f1) and (f1 <= duration):
                    # проверка на баланс
                    self.db_commit('UPDATE bass_requests SET start_ = %s, end_ = %s where user_id = %s',
                                   (f0, f1, self.chat_id))
                else:
                    return self.send_message(
                        'Границы обрезки выходят за длительность песни.\n<b>Напишите границы обрезки '
                        'корректно!</b>', 'cut_markup')

            self.send_message("<b>Теперь выбери уровень усиления трека:</b>",
                              self.bass_markup(cut=False))

            # обновляем статус на басс
            self.update_status('wait_bass_level')

        elif self.status.split('__')[0] == 'text-edit':
            if self.text == self.tag_reply_markups['cancel_markup'][0][0]:
                self.send_message('<i>Вы вернулись в главное меню.</i>', 'file_markup')
                self.update_status('wait_file')
                return
            tag = self.status.split('__')[1]
            entities = self.msg['entities'] if 'entities' in self.msg else None
            self.set_db_text(tag, (self.text, entities))
            self.send_message(self.get_db_text(tag), 'file_markup')
            self.update_status('wait_file')


class InlineButton(TelegramBot):
    def __init__(self, event):
        call = event['callback_query']
        self.msg = call['message']
        self.data = call['data']
        self.call_id = call['id']
        self.msg_id = self.msg['message_id']

        self.chat_id = self.msg['chat']['id']
        super().__init__(self.chat_id)

    def action(self):
        temp = self.data.split("__")
        title = temp[0]
        content = temp[1].split('_') if len(temp) > 1 else None

        if title == 'text':
            self.text(content)
        elif title == 'help':
            text = content[0]
            self.answer_query(text)
        else:
            # ошибочная кнопка
            self.answer_query_no_text()
            self.send_alert(f'Warning:\nInline btn with no action\nMESSAGE:\n{self.msg}')

    def text(self, content):
        option, tag = content[:2]

        if option == 'show':
            inline_keyboard = [[{'text': tag, 'callback_data': f'help__{tag}'},
                                {'text': 'Изменить📝', 'callback_data': f'text__edit_{tag}'},
                                {'text': 'Удалить🗑', 'callback_data': f'text__del_{tag}'}]]
            self.send_message(self.get_db_text(tag), inline_keyboard)
            self.answer_query_no_text()
        elif option == 'edit':
            self.delete_message(self.msg_id)
            self.send_message(f"<b>Введите новый текст «‎{tag}»:</b>", 'cancel_markup')
            self.update_status(f'text-edit__{tag}')
            self.answer_query_no_text()
        elif option == 'del':
            self.del_db_text(tag)
            self.answer_query("Успешно удалено!")
            self.delete_message(self.msg_id)

    def answer_query(self, text, show_alert=False):
        url = self.URL + "answerCallbackQuery?callback_query_id={}&text={}&show_alert={}".format(
            self.call_id, text, show_alert)
        requests.get(url)

    def answer_query_no_text(self):
        url = self.URL + "answerCallbackQuery?callback_query_id={}".format(self.call_id)
        requests.get(url)


# publish to SNS topic
def put_sns(topic_name, message):
    arn = cred[f'{topic_name}_topic_arn']
    client = boto3.client('sns')

    client.publish(
        TargetArn=arn,
        Message=json.dumps(message)
    )


##################
# GLOBAL CONSTANTS
##################

# Используемые типы
tags = {'audio', 'voice', 'video_note', 'video'}
formats = ('mpeg', 'mpeg3', 'mp3', 'mp4', 'ogg')
