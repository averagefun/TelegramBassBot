import json
import random
import time
import datetime

import pay
import requests
import boto3
import mysql.connector

# uncomment this if run locally
#import use_proxy

# MODE
debug_mode = False

# Get cred
def get_cred():
    dynamodb = boto3.resource('dynamodb')
    table = dynamodb.Table('CredTableTBot')
    items = table.scan()['Items']
    keys = [item['name'] for item in items]
    values = [item['value'] for item in items]
    cred = dict(zip(keys, values))
    return cred


cred = get_cred()

# TelegramBot
Token = cred['bot_token']
URL = "https://api.telegram.org/bot{}/".format(Token)

# DataBase
mydb = mysql.connector.connect(
    host=cred['db_host'],
    user=cred['db_user'],
    passwd=cred['db_passwd'],
    database=cred['db_name']
)
mycursor = mydb.cursor()

# Используемые типы
tags = {'audio', 'voice', 'video_note', 'video'}

# все используемые клавиатуры
products = {"inline_keyboard": [[{"text": "Купить Middle", 'callback_data': 'buy_middle'}]]}
pay_inline_markup = {"inline_keyboard": [[{"text": "Перейти к оплате", 'callback_data': 'pay'}]]}
pay_check_inline_markup = {"inline_keyboard": [[{"text": "Проверить оплату", 'callback_data': 'check_payment'}],
                                               [{"text": "Проблемы с оплатой!", 'callback_data': 'error_payment'}]]}
cut_markup = {'keyboard': [['Обрезать не нужно']], 'one_time_keyboard': True, 'resize_keyboard': True}
startbass_markup = {'keyboard': [['По умолчанию (с самого начала)']], 'one_time_keyboard': True,
                    'resize_keyboard': True}
level = ['Лайтово', 'Средняя прожарка', 'Долбит нормально', 'Минус уши сразу']
bass_markup = {'keyboard': [[level[0]], [level[1]], [level[2]], [level[3]]], 'one_time_keyboard': True,
               'resize_keyboard': True}
reverse_markup = {'keyboard': [['Реверсировать'], ['Не реверсировать']], 'one_time_keyboard': True,
                  'resize_keyboard': True}
final_markup = {'keyboard': [['Всё верно!'], ['Отменить зарос.']], 'one_time_keyboard': True, 'resize_keyboard': True}

# seniors
creator = {'id': int(cred['creator_id']), 'username': cred['creator_username']}


class User:
    def __init__(self, event):
        self.event = event
        self.id = self.event['message']['chat']['id']
        self.username = self.event['message']['chat']['username']
        mycursor.execute('SELECT * FROM users WHERE id = %s', (self.id, ))
        self.user_info = mycursor.fetchone()

        # init new user
        if not self.user_info:
            self.user_info = self.new_user()

        '''  SQL
                 user_info = [id,username, role_,  balance, status_, total, last_query]
                               0     1       2       3        4        5        6

                status_:
                    start : начальное приветствие,
                    wait_file: бот ожидает файл,
                    wait_cut: бот ожидает ввод обрезки файла,
                    wait_bass_start: бот ожидает ввода начала басса,
                    wait_bass_level: бот ожидает ввод уровня басса,
                    wait_revers: бот ожидает ввода реверса,
                    wait_correct_data: бот ожидает подтверждения правильности введённых данных
                    req_sent: запрос отправлен, ожидание получения файла от BassBoost
                '''

        self.role, self.balance, self.status, self.total = self.user_info[2:6]

        # get d_bal and maxsize
        mycursor.execute("SELECT d_bal, maxsize FROM roles WHERE name = %s", (self.role, ))
        self.d_bal, self.maxsize = mycursor.fetchone()

    def new_user(self):
        user_info = [self.id, self.username, "junior", 30, "start", 0, None, None]
        # init seniors
        if self.id == creator['id']:
            user_info[2:4] = 'senior', 300
            send_message(self.id, 'Привет! Создатель!')
        mycursor.execute(f"INSERT INTO users VALUE (%s, %s, %s, %s, %s, %s, %s, %s)", user_info)
        mydb.commit()
        return user_info

    def start_msg(self):
        send_sticker(self.id, 'start')
        start_param = {'username': self.username}
        text = get_text_from_db('start', start_param)
        send_message(self.id, text)
        mycursor.execute('UPDATE users SET status_ = "wait_file" WHERE id = %s', (self.id,))
        mydb.commit()

    def commands(self):
        # команды по ролям
        commands_list = {'junior': ['/start', '/stats', '/stop', '/pay', '/buy', '/help'],
                         'middle': [],
                         'senior': ['/ban', '/unban', '/text', '/price', '/update']}
        # команды по оплате
        pays_command = ['/pay', '/buy']
        text = self.text.split()
        command = text[0]
        if len(text) == 1:
            arg, arg2 = None, None
        elif len(text) == 2:
            arg = text[1]
            arg2 = None
        else:
            arg = text[1]
            arg2 = ' '.join(text[2:])

        # junior
        if command not in commands_list['junior'] and self.role == 'junior':
            send_message(self.id, 'Такой команды не существует или она не доступна вам!')
            return None

        # начальное сообщение-приветствие
        if command == '/start':
            self.start_msg()
            return None

        # удаление запроса
        elif command == '/stop':
            mycursor.execute('DELETE FROM bass_requests WHERE id = %s', (self.id, ))
            mydb.commit()
            mycursor.execute('UPDATE users SET status_ = "wait_file" WHERE id = %s', (self.id, ))
            mydb.commit()
            send_message(self.id, '<b>Запрос отменён!</b> \n<i>Загрузите файл для нового запроса.</i>')
            return None

        # Оплата
        elif command in pays_command:
            # получаем цены на товары и курс секунд сейчас
            mycursor.execute("SELECT * FROM payment_param")
            params = mycursor.fetchall()
            keys = [param[0] for param in params]
            values = [param[1] for param in params]
            p = dict(zip(keys, values))

            # получаем параметры по ролям
            mycursor.execute("SELECT * FROM roles")
            roles = mycursor.fetchall()
            keys = [role[0] for role in roles]
            values = [role[1:] for role in roles]  # d_bal, max_to_add, maxsize
            r = dict(zip(keys, values))

            param_prod = {'price_mid': p['price_mid'], 'd_bal_mid': r['middle'][0],
                     'max_to_add_mid': r['middle'][1], 'maxsize_mid': round(r['middle'][2] / 10 ** 6, 1),
                     'maxsize_jun': round(r['junior'][2] / 10 ** 6, 1)}

            if command == '/pay':
                param = {'rate': p['rate']}
                text = get_text_from_db('pay_system', param)
                text += get_text_from_db('products', param_prod)
                send_message(self.id, text, 'reply_markup', json.dumps(pay_inline_markup))
                return None

            elif command == '/buy':
                text = get_text_from_db('products', param_prod)
                send_message(self.id, text, 'reply_markup', json.dumps(products))
                return None

        elif command == '/stats':
            send_message(self.id,
                         f'Ваш баланс: {self.balance} сек,\nДневное пополнение: {self.d_bal} сек,\nВаша роль: {self.role},\nМаксимальный объём: {self.maxsize / 1000000} Мб,\nВсего было использовано: {self.total} сек')
            return None

        elif command == '/help':
            text = 'Доступные команды:\n'
            for item in commands_list.items():
                text += ', '.join(item[1]) + '| '
                if item[0] == self.role:
                    break
            send_message(self.id, text)
            return None

        # middle
        if command not in commands_list['middle'] and self.role == 'middle':
            send_message(self.id, 'Такой команды не существует или она не доступна вам!')
            return None

        # senior
        # ban пользователя
        if command not in commands_list['senior'] and self.role == 'senior':
            send_message(self.id, 'Такой команды не существует!')
            return None
        elif command == '/ban':
            if arg:
                mycursor.execute("SELECT EXISTS(SELECT username FROM users WHERE username = %s)",
                                 (arg[1:], ))
                user_exist = mycursor.fetchone()
                if user_exist and arg != creator['username']:
                    mycursor.execute("UPDATE users SET role_ = 'ban' WHERE username = %s",
                                     (arg[1:], ))
                    mydb.commit()
                    send_message(self.id, f'Пользователь {arg} забанен!')
                else:
                    send_message(self.id, f'Пользователь {arg} <b>не найден</b>!')
            else:
                mycursor.execute("SELECT username FROM users")
                names = mycursor.fetchall()
                send_message(self.id, 'Пользователи бота:\n' + ', '.join([name[0] for name in names]))
                mycursor.execute("SELECT username FROM users WHERE role_ = 'ban'")
                ban_list = mycursor.fetchone()
                if ban_list:
                    send_message(self.id, '<b>Забаненные:</b>\n' + ','.join(ban_list))
                else:
                    send_message(self.id, 'Нет забаненных пользователей.')

        elif command == '/unban':
            if arg:
                mycursor.execute("UPDATE users SET role_ = 'junior' WHERE username = %s",
                                 (arg[1:], ))
                mydb.commit()
                send_message(self.id, f'Пользователь {arg} разбанен!')
            else:
                send_message(self.id, f"Введите имя пользователя")

        # редактирование текста
        elif command == '/text':
            mycursor.execute("SELECT name FROM msgs WHERE text IS NOT NULL")
            texts = [text[0] for text in mycursor.fetchall()]
            if arg and (arg in texts):
                if arg2:
                    mycursor.execute("UPDATE msgs SET text = %s WHERE name = %s",
                                     (arg2, arg))
                    mydb.commit()
                    send_message(self.id, f'Теперь {arg} будет выглядеть так:')
                    text = get_text_from_db(arg)
                    send_message(self.id, text)
                else:
                    text = get_text_from_db(arg)
                    send_message_not_parse(self.id, text)
            else:
                send_message(self.id, 'Доступны следующие теги: ' + ', '.join(texts))

        elif command == '/price':
            mycursor.execute("SELECT name_param FROM payment_param")
            params = [param[0] for param in mycursor.fetchall()]
            if arg and (arg in params):
                if arg2:
                    mycursor.execute("UPDATE payment_param SET value_param = %s WHERE name_param = %s",
                                     (arg2, arg))
                    mydb.commit()
                    send_message(self.id, f'Теперь {arg} = {arg2} сек')
                else:
                    mycursor.execute("SELECT value_param FROM payment_param WHERE name_param = %s", (arg, ))
                    value_param = mycursor.fetchone()[0]
                    send_message_not_parse(self.id, value_param)
            else:
                send_message(self.id, 'Доступны следующие товара: ' + ', '.join(params))

        elif command == '/update':
            if arg == 'confirm':
                mycursor.execute("SELECT id FROM users")
                names = mycursor.fetchall()
                user_id_list = [name[0] for name in names]
                mycursor.execute("SELECT text FROM msgs WHERE name = 'update'")
                text = mycursor.fetchone()[0]
                for id in user_id_list:
                    send_message(id, text)
            else:
                mycursor.execute("SELECT text FROM msgs WHERE name = 'update'")
                text = mycursor.fetchone()[0]
                send_message(self.id, text)

    def file(self, tag):
        # проверка на статус юзера
        if self.status != "wait_file":
            send_message(self.id,
                         'Извините, но на данном этапе не нужно загружать файл. <i>Введите корректный ответ!</i>')
            return None

        audio = self.event['message'][tag]

        # проверка на длительность и размер файла
        duration = round(audio['duration'])
        if (self.balance >= 10) and (audio['file_size'] < self.maxsize):

            send_message(self.id,
                         'Запись получена! <b>Теперь можно обрезать файл (если нужно).</b> Пример (вводить без кавычек): "1.5 10" - обрезка песни с 1.5 по 10 секунду.',
                         'reply_markup', json.dumps(cut_markup))

            # начинаем формировать запрос
            mycursor.execute("INSERT INTO bass_requests (id, file_id, duration) VALUES (%s, %s, %s)", (
                self.id, audio['file_id'], duration))
            mydb.commit()

            # обновляем статус
            mycursor.execute('UPDATE users SET status_ = "wait_cut" WHERE id = %s', (self.id, ))
            mydb.commit()

        else:
            send_message(self.id,
                         'У вас на балансе менее <b>10</b> секунд или файл больше <b>{}</b> Мб (: Выберите запись поменьше или зайдите завтра'.format(
                             round(self.maxsize / 1000000, 2)))

    def msg(self):
        # пытаемся распознать текст, иначе понимаем что юзер скинул неизвестный документ
        try:
            self.text = self.event['message']['text']
        except:
            # если мы сейчас ожидаем аудио >> неизвестный формат
            if self.status == "wait_file":
                send_message(self.id, 'Упс, ожидался файл формата mp3, ogg, mp4. Отправьте файл снова!')
            # иначе мы получили неизвестный документ, когда ожидали сообщение
            else:
                send_message(self.id, 'Ошибка! Введите ваш ответ более корректно!')
            return None

        # command
        if self.text[0] == '/':
            self.commands()

        elif self.status == 'start':
            self.start_msg()

        elif self.status == "wait_file":
            send_message(self.id, 'Пожалуйста, отправьте <b>файл</b>, а не сообщение!')

        # обрезка файла
        elif self.status == "wait_cut":
            # находим длительность файла
            mycursor.execute('SELECT duration from bass_requests where id = %s', (self.id, ))
            duration = mycursor.fetchone()[0]

            if self.text == 'Обрезать не нужно':
                # проверка на длительность
                if self.balance > duration:
                    send_message(self.id,
                                 'Ок! Теперь укажи, с какой секунды начинается бас. Пример "5.2" - с 5.2 секунды.',
                                 'reply_markup', json.dumps(startbass_markup))
                else:
                    send_message(self.id,
                                 f'У вас не хватает секунд!\n(Баланс: {self.balance} сек, Файл: {duration} сек) \nВыберите обрезку или /stop для отмены запроса.')
                    return None
            else:
                s = self.text.split()
                # проверка, что введены именно ЧИСЛА
                try:
                    f0 = round(float(s[0]), 1)
                    f1 = round(float(s[1]), 1)
                except:
                    send_message(self.id,
                                 'Синтаксическая ошибка! \n<b>проверьте, что десятичная дробь записана через точку!</b>',
                                 'reply_markup', json.dumps(cut_markup))
                    return None
                if (f0 >= 0) and (f0 < f1) and (f1 <= duration):
                    # проверка на баланс
                    if (f1 - f0) < self.balance:
                        mycursor.execute('UPDATE bass_requests SET start_ = %s, end_ = %s where id = %s',
                                         (f0, f1, self.id))
                        mydb.commit()
                        send_message(self.id,
                                     'Всё чётко! Теперь укажи, <b>с какой секунды начинается бас.</b> \nПример: "5.2" - с 5.2 секунды. \n<i>Указывай время с начала уже обрезанной песни!</i> ',
                                     'reply_markup', json.dumps(startbass_markup))
                    # не хватает секунд
                    else:
                        send_message(self.id,
                                     f'У вас не хватает секунд!\n(Баланс: {self.balance} сек, Файл: {duration} сек) \nВыберите более узкую или /stop для отмены запроса.')
                        return None
                else:
                    send_message(self.id,
                                 'Хм, что-то не то с границами обрезки. <i>Напишите границы обрезки корректно!</i>',
                                 'reply_markup', json.dumps(cut_markup))
                    return None

            # обновляем статус на 2
            mycursor.execute('UPDATE users SET status_ = "wait_bass_start" WHERE id = %s', (self.id, ))
            mydb.commit()

        # начало баса
        elif self.status == "wait_bass_start":
            if self.text != 'По умолчанию (с самого начала)':
                # корректность ввода числа
                try:
                    # f - начало басса
                    f = round(float(self.text), 1)
                except:
                    send_message(self.id,
                                 'Синтаксическая ошибка! \n<b>проверьте, что десятичная дробь записана через точку!</b>',
                                 'reply_markup', json.dumps(startbass_markup))
                    return None
                mycursor.execute('SELECT duration, start_, end_ from bass_requests where id = %s', (self.id, ))
                duration = mycursor.fetchone()
                if not duration[1]:
                    f1 = duration[0]
                else:
                    f1 = duration[2] - duration[1]

                # корректность ввода данных
                if (f >= 0) and (f < f1):
                    mycursor.execute('UPDATE bass_requests SET start_bass = %s WHERE id = %s',
                                     (f, self.id))
                    mydb.commit()
                else:
                    send_message(self.id,
                                 'Хм, что-то не так со временем начала баса. <i>Напишите границы обрезки корректно!</i>',
                                 'reply_markup', json.dumps(startbass_markup))
                    return None

            send_message(self.id, '<b>Выбери уровень баса:</b>', 'reply_markup', json.dumps(bass_markup))
            # обновляем статус
            mycursor.execute('UPDATE users SET status_ = "wait_bass_level" WHERE id = %s', (self.id, ))
            mydb.commit()


        # выбор уровня баса
        elif self.status == "wait_bass_level":
            if self.text in level:
                # уровень баса в словах >> цифры
                l = level.index(self.text)
                mycursor.execute('UPDATE bass_requests SET bass_level = %s WHERE id = %s',
                                 (l, self.id))
                mydb.commit()
                # обновляем статус на 4
                mycursor.execute('UPDATE users SET status_ = "wait_revers" WHERE id = %s', (self.id, ))
                mydb.commit()
                send_message(self.id, f'Что насчёт <b>реверса</b> (песня задом наперёд)?', 'reply_markup',
                             json.dumps(reverse_markup))
            # непонятный уровень баса, введённый пользователем
            else:
                send_message(self.id,
                             'Такого уровня баса ещё не существует. Выберите уровень из <b>установленных значений!</b>',
                             'reply_markup', json.dumps(bass_markup))

        # реверс/не реверс
        elif self.status == "wait_revers":
            if self.text == 'Реверсировать':
                mycursor.execute('UPDATE bass_requests SET reverse_ = 1 WHERE id = %s', (self.id, ))
                mydb.commit()
            elif self.text != 'Не реверсировать':
                send_message(self.id, 'Выберите вариант ответа из <b>установленных</b> значений!', 'reply_markup',
                             json.dumps(reverse_markup))
                return None
            mycursor.execute('SELECT * FROM bass_requests WHERE id = %s', (self.id, ))
            # получаем весь запрос: duration, start_, end_, start_bass, bass_level, reverse_
            req = list(mycursor.fetchone()[2:8])

            # ф-ия обработки значений req
            def conv(req):
                # обрезка трека
                if (not req[1]) and (not req[2]):
                    req[1] = 'Нет'
                    req.pop(2)
                else:
                    req[1] = f'с {req[1]} по {req.pop(2)} сек'

                # начало басса
                if not req[2]:
                    req[2] = 'C начала трека'
                else:
                    req[2] = f'с {req[2]} сек'

                # реверс
                if req[4]:
                    req[4] = 'да'
                else:
                    req[4] = 'нет'
                return req

            req = conv(req)

            send_message(self.id,
                         "Проверьте параметры запроса: \nФайл: <i>{} сек</i>, \nОбрезка: <i>{}</i>, \nНачало басса: <i>{}</i>, \nУровень баса: <i>{}</i>, \nРеверс: <i>{}</i>.".format(
                             req[0], req[1], req[2], level[req[3]], req[4]), 'reply_markup', json.dumps(final_markup))
            # обновляем статус
            mycursor.execute('UPDATE users SET status_ = "wait_correct_data" WHERE id = %s', (self.id, ))
            mydb.commit()

        # проверка правильности запроса
        elif self.status == "wait_correct_data":
            if self.text == 'Всё верно!':
                send_message(self.id, 'Запрос отправлен! Ожидайте файл в течение 15 секунд')
                # получаем id сообщения (стикер с думающим утёнком)
                req_id = send_sticker(self.id, 'loading')
                file = get_file(self.id)
                # аварийная проверка на размер
                assert file['result']['file_size'] <= self.maxsize
                file_path = file['result']['file_path']
                mycursor.execute(
                    f"UPDATE bass_requests SET req_id = %s, file_path = %s WHERE id = %s",
                    (req_id, file_path, self.id))
                mydb.commit()
                mycursor.execute("UPDATE users SET status_ = 'req_sent', last_query = NOW() + INTERVAL 3 HOUR WHERE id = %s", (self.id, ))
                mydb.commit()
                put_SNS(req_id)
            elif self.text == 'Отменить запрос':
                send_message(self.id, 'Запрос отменён! Пришлите файл для нового запроса (mp3, ogg, mp4)')
                mycursor.execute('DELETE FROM bass_requests WHERE id = %s', (self.id, ))
                mydb.commit()
                mycursor.execute('UPDATE users SET status_ = "wait_file" WHERE id = %s', (self.id, ))
                mydb.commit()
            else:
                send_message(self.id, 'Введите корректный ответ на вопрос!')


def get_users(role):
    mycursor.execute("SELECT id FROM users WHERE role_ = %s", (role, ))
    users = [user[0] for user in mycursor.fetchall()]
    return users


class InlineButton:
    def __init__(self, event):
        call = event['callback_query']
        self.user_id = call['message']['chat']['id']
        self.username = call['message']['chat']['username']
        self.data = call['data']
        self.call_id = call['id']
        self.msg_id = call['message']['message_id']

    def action(self):
        # выполняем различные действия в зависимости от нажатия кнопки
        # генерируем оплату
        if self.data == 'pay':
            self.answer_query_no_text()
            pay_id = send_message(self.user_id, 'Создание оплаты...')
            param = {'pay_id': pay_id, 'status': '❌ НЕ оплачено!'}
            text = get_text_from_db('pay_rule', param)
            edit_message(self.user_id, pay_id, text, "reply_markup", json.dumps(pay_check_inline_markup))
            mycursor.execute("INSERT INTO payment_query(pay_id, user_id, username, start_query, status_) VALUES (%s, %s, %s, NOW() + INTERVAL 3 HOUR, %s)",
                             (pay_id, self.user_id, self.username, "wait_for_payment"))
            mydb.commit()
        elif self.data == 'check_payment':
            pay_check = pay.check_payment(self.msg_id, cred, mycursor, mydb)
            if pay_check['success']:
                self.answer_query_no_text()
                param = {'pay_id': self.msg_id, 'status': '<b>✅ Оплачено!</b>'}
                text = get_text_from_db('pay_rule', param)
                edit_message(self.user_id, self.msg_id, text)
                # Получаем курс секунд
                mycursor.execute("SELECT value_param FROM payment_param WHERE name_param = 'rate'")
                rate = mycursor.fetchone()[0]
                sec = round(rate * pay_check['sum'])
                # обновляем баланс
                mycursor.execute("UPDATE users SET balance = balance + %s WHERE id = %s",
                                 (sec, self.user_id))
                mydb.commit()
                send_message(self.user_id,
                             f"Оплата успешно завершена!\n Вам начислено <b>{sec}</b> секунд")
            else:
                if pay_check['error'] == 'Payment_not_found':
                    self.answer_query('Повторите попытку проверки через нескольско секунд. Мы ещё не получили платёж от Qiwi!',
                                      show_alert=True)
                elif pay_check['error'] == 'already_complete':
                    self.answer_query('Вы уже успешно оплатили этот заказ!', show_alert=True)
                else:
                    self.answer_query_no_text()
                    send_message(self.id,
                                 f"""Произошла ошибка на стороне Qiwi ({pay_check['error']}).
                                    <i>Убедитесь, что все введённые при оплате данные верны и
                                    повторите оплату снова.</i>""")
                    mycursor.execute("UPDATE payment_query SET status_ = %s WHERE pay_id = %s",
                                     (pay_check['error'], self.msg_id))
                    mydb.commit()
        elif self.data == 'error_payment':
            self.answer_query_no_text()
            send_message(self.user_id,
                         f"Сожалеем, что у вас возникли проблемы, опишите свою проблему в сообщении @{creator['username']}, прикрепите скриншот квитанции об оплате!")

        # товары
        else:
            mycursor.execute("SELECT balance FROM users WHERE id = %s", (self.user_id,))
            balance = mycursor.fetchone()[0]
            now = datetime.datetime.now()
            if self.data == 'buy_middle':
                mycursor.execute("SELECT value_param FROM payment_param WHERE name_param = 'price_mid'")
                price = mycursor.fetchone()[0]
                if balance >= price:
                    mycursor.execute("UPDATE users SET balance = balance - %s, role_ = 'middle', role_end = NOW() + INTERVAL 30 DAY WHERE id = %s",
                                     (price, self.user_id))
                    mydb.commit()
                    self.answer_query("Успешно!")
                    delta = datetime.timedelta(days=30)
                    role_end = (now.date()+delta).strftime("%Y-%m-%d %H:%M")
                    send_message(self.user_id, f"Вы успешно приобрели подписку middle до {role_end} по МСК.")

                else:
                    self.answer_query("Недостаточно средств на балансе!", show_alert=True)


    def answer_query(self, text, show_alert=False):
        url = URL + "answerCallbackQuery?callback_query_id={}&text={}&show_alert={}".format(self.call_id, text,
                                                                                            show_alert)
        requests.get(url)

    def answer_query_no_text(self):
        url = URL + "answerCallbackQuery?callback_query_id={}".format(self.call_id)
        requests.get(url)


def lambda_handler(event, context):
    print(event)

    # проверка на нажатие инлайн кнопки
    if 'callback_query' in event.keys():
        button = InlineButton(event)
        button.action()
        return None

    # инициализация юзера
    user = User(event)
    # проверка на бан
    if user.role == 'ban':
        send_message(user.id,
                     'Сожалеем, но вы <b>забанены</b>. Если вам кажется, что это ошибка, обратитесь в поддержку.')
        return None

    # debug mode
    if debug_mode and user.role != 'senior':
        send_message(user.id, 'Извините, в данный момент бот отдыхает. Ведутся работы на сервере :)')
        send_sticker(user.id, 'sleep')
        if user.status == 'start':
            text = get_text_from_db('sleep')
            send_message(user.id, text)
        return None

    # проверяем: это сообщение или файл - находим общие ключи
    c = list(set(event['message'].keys()) & tags)

    # юзер залил файл
    if c:
        user.file(c[0])

    # Юзер написал текст
    else:
        user.msg()


# Telegram methods
def send_message(chat_id, text, *args):  # Ф-ия отсылки сообщения/ *args: [0] - parameter_name, [1] - value
    if len(args) == 0:
        url = URL + "sendMessage?chat_id={}&text={}&parse_mode=HTML".format(chat_id, text)
    elif len(args) == 2:
        url = URL + "sendMessage?chat_id={}&text={}&{}={}&parse_mode=HTML".format(chat_id, text, args[0], args[1])
    elif len(args) == 4:
        url = URL + "sendMessage?chat_id={}&text={}&{}={}&{}={}&parse_mode=HTML".format(chat_id, text, args[0], args[1],
                                                                                        args[2], args[3])
    r = requests.get(url).json()
    return r['result']['message_id']

def send_message_not_parse(chat_id, text):
    url = URL + "sendMessage?chat_id={}&text={}".format(chat_id, text)
    requests.get(url)

def edit_message(chat_id, message_id, text, *args):
    if len(args) == 0:
        url = URL + "editMessageText?chat_id={}&message_id={}&text={}&parse_mode=HTML".format(chat_id, message_id, text)
    elif len(args) == 2:
        url = URL + "editMessageText?chat_id={}&message_id={}&text={}&{}={}&parse_mode=HTML".format(chat_id, message_id, text, args[0], args[1])
    requests.get(url)


def get_text_from_db(tag, param=None):
    mycursor.execute("SELECT text FROM msgs WHERE name = %s", (tag, ))
    text = mycursor.fetchone()[0]
    if text:
        if param:
            try:
                text = text.format(**param)
            except:
                seniors = get_users('senior')
                for senior in seniors:
                    send_message(senior, f'!!! <b>ERROR</b> Error with format {tag}!')
        return text
    seniors = get_users('senior')
    for senior in seniors:
        send_message(senior, f'!!! <b>ERROR</b> Error {tag} not found!')


def send_sticker(chat_id, sticker):
    mycursor.execute("SELECT stick_id FROM msgs WHERE name = %s", (sticker, ))
    stick = mycursor.fetchall()
    if stick:
        url = URL + "sendSticker?chat_id={}&sticker={}&parse_mode=HTML".format(chat_id,
                                                                               stick[random.randint(0,
                                                                                                    len(stick) - 1)][0])
        try:
            r = requests.get(url).json()
            return r['result']['message_id']
        except:
            pass

    # если ошибка
    seniors = get_users('senior')
    for senior in seniors:
        send_message(senior, f'!!! <b>ERROR</b> Sticker {sticker} not found!')
    return round(time.time())


def get_file(chat_id):
    # get file_id from db
    mycursor.execute('SELECT file_id FROM bass_requests WHERE id = %s', (chat_id, ))
    file_id = mycursor.fetchone()[0]
    # make request
    url = URL + "getFile?file_id={}".format(file_id)
    r = requests.get(url)
    return json.loads(r.content)


# AWS methods
def put_SNS(message):
    arn = cred['BassBoostTrigger_topic_arn']
    client = boto3.client('sns')

    response = client.publish(
        TargetArn=arn,
        Message=json.dumps(message)
    )

# Future methods
# def put_dynamDB(req_id):
#     TableName = 'requests'
#     DB = boto3.resource('dynamodb')
#     table = DB.Table(TableName)
#     response = table.put_item(
#         Item= {
#         "req_id": req_id
#         })
