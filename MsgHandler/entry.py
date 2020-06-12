import json
import random
import time

import pay
import requests
import boto3
import mysql.connector


# uncomment this if run locally
# import use_proxy

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
# convert to int some values
if cred['maxsize'].isdigit():
    cred['maxsize'] = int(cred['maxsize'])
else:
    cred['maxsize'] = 10000000

if cred['creator_id'].isdigit():
    cred['creator_id'] = int(cred['creator_id'])

# TelegramBot
Token = cred['bot_token']
URL = "https://api.telegram.org/bot{}/".format(Token)

# Используемые типы
tags = {'audio', 'voice', 'video_note', 'video'}
formats = ('mpeg', 'mp3', 'mp4', 'ogg')

# все используемые клавиатуры
products = {"inline_keyboard": [[{"text": "Купить premium (24 часа)", 'callback_data': 'premium_day'}],
                                [{"text": "Купить premium (7 дней)", 'callback_data': 'premium_week'}],
                                [{"text": "Купить premium (30 дней)", 'callback_data': 'premium_month'}]]}
pay_inline_markup = {"inline_keyboard": [[{"text": "Перейти к оплате", 'callback_data': 'pay'}]]}
pay_check_inline_markup = {"inline_keyboard": [[{"text": "Проверить оплату", 'callback_data': 'check_payment'}],
                                               [{"text": "Проблемы с оплатой!", 'callback_data': 'error_payment'}],
                                               [{"text": "Удалить платёжную сессию!",
                                                 'callback_data': 'delete_payment'}]]}
if_edit_markup = {'keyboard': [['Редактировать файл'], ['Пропустить редактирование']], 'resize_keyboard': True}
cut_markup = {'keyboard': [['Обрезать не нужно']], 'resize_keyboard': True}
startbass_markup = {'keyboard': [['По умолчанию (с самого начала)']], 'resize_keyboard': True}
level = ['Лайтово', 'Средняя прожарка', 'Долбит нормально', 'Минус уши сразу']
bass_markup = {'keyboard': [[level[0]], [level[1]], [level[2]], [level[3]]], 'one_time_keyboard': True,
               'resize_keyboard': True}
file_markup = {'keyboard': [['Отправьте файл боту!']], 'resize_keyboard': True}

# admins
creator = {'id': cred['creator_id'], 'username': cred['creator_username']}


class User:
    def __init__(self, event):
        self.event = event

        # проверка что это сообщение от пользователя, а не мусор
        try:
            self.id = self.event['message']['chat']['id']
        except KeyError:
            self.init_success = False
            return None

        # проверка на наличие username
        try:
            self.username = self.event['message']['chat']['username']
        except KeyError:
            send_message(self.id,
                "Пожалуйста, установите ненулевой @username в настройках Telegram!")
            send_message(self.id,
                "После этого наберите /start если вы зашли к боту в первый раз, иначе повторите последнюю команду!")
            self.init_success = False
            return None

        self.init_success = True

        mycursor.execute('SELECT * FROM users WHERE id = %s', (self.id,))
        self.user_info = mycursor.fetchone()

        # init new user
        if not self.user_info:
            self.role, self.balance, self.status, self.total = self.new_user()[2:6]
        else:
            self.balance, self.status, self.total = self.user_info[5:8]

            # проверяем на изменённый ник
            if self.username != self.user_info[2]:
                mycursor.execute("UPDATE users SET username = %s WHERE id = %s", (self.username, self.id))

            # проверяем, закончилась ли роль
            mycursor.execute("SELECT EXISTS(SELECT id FROM users WHERE id = %s and (NOW() + INTERVAL 3 HOUR) >= role_end)",
                             (self.id, ))
            # закончилась
            if mycursor.fetchone()[0]:
                send_message(self.id, "<b>Внимание:</b> У вас закончилась подписка на premium!")
                mycursor.execute("UPDATE users SET role_ = 'standard', role_end = NULL WHERE id = %s", (self.id, ))
                mydb.commit()
                self.role = 'standard'
            else:
                self.role = self.user_info[4]

        '''  SQL
                status_:
                    start : начальное приветствие,
                    wait_file: бот ожидает файл,
                    wait_cut: бот ожидает ввод обрезки файла,
                    wait_bass_start: бот ожидает ввода начала басса,
                    wait_bass_level: бот ожидает ввод уровня басса,
                    req_sent: запрос отправлен, ожидание получения файла от BassBoost
                '''

        # get max_sec and role_active
        mycursor.execute("SELECT max_sec, role_active FROM roles WHERE name = %s", (self.role,))
        self.max_sec, self.role_active = mycursor.fetchone()

    def new_user(self):
        user_info = [self.id, self.username, "start", 0, "start", 0]
        # init admins
        if self.id == creator['id']:
            user_info[2:4] = 'admin', 500
            send_message(self.id, 'Привет! Создатель!')
        mycursor.execute(
            f'''INSERT INTO users (id, username, reg_date, role_, balance, status_, total) VALUES
                (%s, %s, NOW() + INTERVAL 3 HOUR, %s, %s, %s, %s)''', user_info)
        mydb.commit()
        return user_info

    def start_msg(self):
        send_sticker(self.id, 'start')
        start_param = {'username': self.username}
        text = get_text_from_db('start', start_param)
        send_message(self.id, text, 'reply_markup', json.dumps(file_markup))
        mycursor.execute('UPDATE users SET status_ = "wait_file" WHERE id = %s', (self.id,))
        mydb.commit()

    def commands(self):
        # команды по ролям
        commands_list = {'standard': ['/start', '/help', '/bug', '/stats', '/cancel', '/pay', '/buy', '/commands'],
                         'premium': [],
                         'admin': ['/active', '/users', '/message', '/ban', '/unban', '/text', '/price', '/update']}
        # команды по оплате
        pays_command = ['/pay', '/buy']
        row_text = self.text.split('\n')
        text = row_text[0].split()
        command = text[0]

        # если admin - делим всё сообщение на 2 аргумента!
        if self.role == 'admin':
            if len(text) == 1:
                arg, arg2 = None, None
            elif len(text) == 2:
                arg = text[1]
                if len(row_text) == 1:
                    arg2 = None
                else:
                    arg2 = '\n'.join(row_text[1:])

            else:
                send_message(self.id, 'Введите второй аргумент с новой строки!')
                return None
        else:
            arg = ' '.join(self.text.split()[1:])
            arg2 = None

        # standard
        if command not in commands_list['standard'] and self.role == 'standard':
            send_message(self.id, 'Такой команды не существует или она не доступна вам!')
            return None

        # начальное сообщение-приветствие
        if command == '/start' and (self.status == 'start' or self.role == 'admin'):
            # проверка на реферальную ссылку
            if arg and self.status == 'start':
                mycursor.execute("SELECT EXISTS(SELECT id FROM users WHERE id = %s)", (int(arg), ))
                res = mycursor.fetchone()
                if res:
                    mycursor.execute("SELECT value_param FROM payment_param WHERE name_param = 'ref_bonus'")
                    ref_bonus = mycursor.fetchone()[0]
                    send_message(int(arg),
                                 "@{} воспользовался вашей реферальной ссылкой!\nВам начислено <b>{}</b> руб!".format(
                                                                                    self.username, str(ref_bonus)))
                    mycursor.execute("UPDATE users SET balance = balance + %s WHERE id = %s", (ref_bonus, int(arg)))
                    mydb.commit()
            self.start_msg()
            return None

        # сообщение о баге
        elif command == '/bug' and arg:
            send_message(self.id, 'Спасибо, что сообщили о баге!')
            admins = get_users('admin')
            for admin in admins:
                send_message(admin, f'Bug report from @{self.username}\n' + arg)
            return None

        # удаление запроса
        elif command == '/cancel':
            mycursor.execute('DELETE FROM bass_requests WHERE id = %s', (self.id,))
            mydb.commit()
            mycursor.execute('UPDATE users SET status_ = "wait_file" WHERE id = %s', (self.id,))
            mydb.commit()
            send_message(self.id, '<b>Запрос отменён!</b> \n<i>Загрузите файл для нового запроса.</i>',
                         'reply_markup', json.dumps(file_markup))
            return None

        elif command == '/help':
            text = get_text_from_db('help')
            text += '\n\n'
            mycursor.execute("SELECT value_param FROM payment_param WHERE name_param = 'ref_bonus'")
            text += get_text_from_db('referral', {'id': self.id, 'ref_bonus': mycursor.fetchone()[0]})
            send_message(self.id, text)
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
            values = [role[1] for role in roles]  # max_sec
            r = dict(zip(keys, values))

            param_prod = {'premium_day': p['premium_day'], 'premium_week': p['premium_week'],
                          'premium_month': p['premium_month'], 'max_sec_premium': r['premium'],
                          'max_sec_standard': r['standard']}

            if command == '/pay':
                text = get_text_from_db('pay_system')
                text += '\n\n'
                text += get_text_from_db('products', param_prod)
                send_message(self.id, text, 'reply_markup', json.dumps(pay_inline_markup))
                return None

            elif command == '/buy':
                text = get_text_from_db('products', param_prod)
                send_message(self.id, text, 'reply_markup', json.dumps(products))
                return None

        elif command == '/stats':
            if self.user_info[-1]:
                role_end = f"Действует до: {self.user_info[-1]} по МСК"
            else:
                role_end = ""

            param = {'balance': self.balance, 'role': self.role, 'role_end': role_end,
                     'max_sec': self.max_sec, 'total': self.total}
            text = get_text_from_db('stats', param)
            send_message(self.id, text)
            return None

        elif command == '/commands':
            role = self.role.replace('start', 'standard')
            text = 'Доступные команды:\n'
            for item in commands_list.items():
                text += ', '.join(item[1]) + '| '
                if item[0] == role:
                    break
            send_message(self.id, text)
            return None

        # premium
        if command not in commands_list['premium'] and self.role == 'premium':
            send_message(self.id, 'Такой команды не существует или она не доступна вам!')
            return None

        # admin
        if command not in commands_list['admin'] and self.role == 'admin':
            send_message(self.id, 'Такой команды не существует!')
            return None

        # активирование ролей
        elif command == '/active':
            mycursor.execute("SELECT name, role_active FROM roles")
            roles = mycursor.fetchall()
            keys = [role[0] for role in roles]
            values = [role[1] for role in roles]
            roles = dict(zip(keys, values))
            if arg and (arg in keys):
                if arg2:
                    if not arg2.isdigit():
                        send_message(self.id, 'Неверный аргумент (укажите 0 или 1)')
                        return None
                    mycursor.execute("UPDATE roles SET role_active = %s WHERE name = %s",
                                     (int(arg2), arg))
                    mydb.commit()
                    send_message(self.id, f'Активность роли {arg} установлена в {arg2}')
                else:
                    send_message(self.id, roles[arg])
            elif arg:
                if not arg.isdigit():
                    send_message(self.id, 'Неверный аргумент (укажите 0 или 1)')
                    return None
                mycursor.execute("UPDATE roles SET role_active = %s WHERE name != 'admin'",
                                 (int(arg),))
                mydb.commit()
                send_message(self.id, f'Активность всех пользователей = {arg}')
            else:
                send_message(self.id, f"Активность: {roles}")

        # статистика по пользователям
        elif command == '/users':
            param = {'show': 'username', 'count': 'count(*)'}
            if arg in param:
                req = f"SELECT {param[arg]} FROM users"
                if arg2 == 'all_active':
                    req += " WHERE last_query IS NOT NULL"
                elif arg2 == 'today':
                    req += " WHERE DATE(reg_date) = DATE(NOW() + INTERVAL 3 HOUR)"
                elif arg2 == 'today_active':
                    req += " WHERE DATE(reg_date) = DATE(NOW() + INTERVAL 3 HOUR) AND last_query IS NOT NULL"

                mycursor.execute(req)
                res = mycursor.fetchall()
                # проверяем на пустой результат
                if res:
                    if arg == 'show':
                        msg = '@' + ', @'.join([r[0] for r in res])
                    else:
                        msg = res[0][0]
                    send_message(self.id, msg)
                else:
                    send_message(self.id, "Пустой результат!")
            elif arg and arg[0] == '@':
                mycursor.execute('SELECT * FROM users WHERE username = %s', (arg[1:],))
                user_info = mycursor.fetchone()

                if not user_info:
                    send_message(self.id, 'Пользователь не найден!')
                    return None
                else:
                    role, balance, status, total = user_info[4:8]

                if user_info[-1]:
                    role_end = f"Действует до: {user_info[-1]} по МСК"
                else:
                    role_end = ""

                # get max_sec and role_active
                mycursor.execute("SELECT max_sec, role_active FROM roles WHERE name = %s", (role,))
                max_sec, role_active = mycursor.fetchone()

                if role_active:
                    role += ' (активна)'
                else:
                    role += ' (НЕ активна)'

                param = {'username': arg, 'balance': balance, 'role': role, 'role_end': role_end,
                         'status': status, 'max_sec': max_sec, 'last_query': user_info[-2], 'total': total}
                text = get_text_from_db('admin_stats', param)
                send_message(self.id, text)
                return None

            else:
                # при отсутсвии аргумента выводим количество пользователей
                mycursor.execute("SELECT count(*), sum(total) FROM users")
                res = mycursor.fetchone()
                send_message(self.id, f"Всего пользователей: {res[0]}\nВсего секунд: {res[1]}")

        # произвольное сообщение некоторым пользователям
        elif command == '/message':
            text = get_text_from_db('uniq_msg')
            if arg == 'confirm' and arg2:
                usernames = "', '".join(user[1:] for user in arg2.split())
                mycursor.execute(f"SELECT id FROM users WHERE username in ('{usernames}')")
                id_for_msg = [user[0] for user in mycursor.fetchall()]
                diff = len(arg2.split())-len(id_for_msg)
                if diff <= 0:
                    for chat_id in id_for_msg:
                        send_message(chat_id, text)
                        time.sleep(0.05)
                    send_message(self.id, "Все сообщения успешно отправлены!")
                else:
                    send_message(self.id, f'NameError: {diff} пользователя не найдено!')
            else:
                send_message(self.id, text)

        # ban пользователя
        elif command == '/ban':
            if arg:
                mycursor.execute("SELECT EXISTS(SELECT username FROM users WHERE username = %s)",
                                 (arg[1:],))
                user_exist = mycursor.fetchone()
                if user_exist and arg != creator['username']:
                    mycursor.execute("UPDATE users SET role_ = 'ban' WHERE username = %s",
                                     (arg[1:],))
                    mydb.commit()
                    send_message(self.id, f'Пользователь {arg} забанен!')
                else:
                    send_message(self.id, f'Пользователь {arg} <b>не найден</b>!')
            else:
                mycursor.execute("SELECT username FROM users WHERE role_ = 'ban'")
                ban_list = mycursor.fetchone()
                if ban_list:
                    send_message(self.id, '<b>Забаненные:</b>\n@' + ', @'.join(ban_list))
                else:
                    send_message(self.id, 'Нет забаненных пользователей.')

        elif command == '/unban':
            if arg:
                mycursor.execute("UPDATE users SET role_ = 'standard' WHERE username = %s",
                                 (arg[1:],))
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
                    send_message(self.id, f'Теперь {arg} будет выглядеть так:')
                    r = send_message(self.id, arg2)
                    if not r['ok']:
                        send_message(self.id, r['description'])
                        return None
                    mycursor.execute("UPDATE msgs SET text = %s WHERE name = %s",
                                     (arg2, arg))
                    mydb.commit()
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
                    mycursor.execute("SELECT value_param FROM payment_param WHERE name_param = %s", (arg,))
                    value_param = mycursor.fetchone()[0]
                    send_message_not_parse(self.id, value_param)
            else:
                send_message(self.id, 'Доступны следующие товары: ' + ', '.join(params))

        # рассылка всем пользователям
        elif command == '/update':
            if arg == 'confirm':
                put_SNS('MailingTrigger', 'update')
            else:
                mycursor.execute("SELECT text FROM msgs WHERE name = 'update'")
                text = mycursor.fetchone()[0]
                send_message(self.id, text)

    def file(self, tag, message):
        # проверка на статус юзера
        if self.status != "wait_file":
            send_message(self.id,
                         'Извините, но на данном этапе не нужно загружать файл. <i>Введите корректный ответ!</i>')
            return None

        audio = self.event['message'][tag]

        # определение формата (если video_note >> mp4)
        if tag != 'video_note':
            format_ = audio['mime_type'].split('/')[1]
        else:
            format_ = 'mp4'

        # проверка на формат
        if format_ not in formats:
            send_message(self.id,
                         'Неизвестный формат файла! \n<b>Доступные форматы: mp3, ogg, mp4!</b>')
            send_message(self.id, '<i>Загрузите файл для нового запроса!</i>')
            mycursor.execute(f'DELETE FROM bass_requests WHERE id = %s', (self.id, ))
            mydb.commit()
            mycursor.execute(f"UPDATE users SET status_ = 'wait_file' WHERE id = %s", (self.id, ))
            mydb.commit()
            return None

        # проверка на длительность и размер файла
        duration = round(audio['duration'])
        if audio['file_size'] > cred['maxsize']:
            send_message(self.id,
                             f"Мы не работаем с файлами больше {round(cred['maxsize']/10**6, 1)} Мб." +
                             "\n<b>Выберите файл поменьше!</b>")
            return None

        # удаляем все предыдущие запросы во избежании багов
        mycursor.execute('DELETE FROM bass_requests WHERE id = %s', (self.id,))
        mydb.commit()

        # пытаемся определить название файла
        if 'title' in audio:
            title = audio['title']
        else:
            title = 'Audio'

        # начинаем формировать запрос
        mycursor.execute("INSERT INTO bass_requests (id, file_id, format_, duration, file_name) VALUES (%s, %s, %s, %s, %s)", (
            self.id, audio['file_id'], format_, duration, title))
        mydb.commit()

        if 'caption' in message:
            caption = message['caption']
            if caption.isdigit():
                if int(caption) in [1, 2, 3, 4]:
                    # заполняем уровень баса
                    mycursor.execute("UPDATE bass_requests SET bass_level = %s", (int(caption) - 1, ))
                    mydb.commit()

                    # получаем длительность файла
                    mycursor.execute('SELECT duration from bass_requests where id = %s', (self.id,))
                    duration = mycursor.fetchone()[0]

                    # выполняем автообрезание
                    self.auto_cut(duration)

                    self.send_req_to_bass()
                    return None
                else:
                    send_message(self.id, "Описание файла не распознано.\nУказывайте уровень баса\nот 1 до 4!")
                    return None
            else:
                send_message(self.id,
                             "Описание файла не распознано.\nУказывайте уровень баса <b>цифрой</b>\nот 1 до 4!")
                return None

        send_message(self.id,
                     'Файл принят! <b>Теперь можно отредактировать аудио</b>' +
                     '\n(обрезка и прочее...):',
                     'reply_markup', json.dumps(if_edit_markup))

        # обновляем статус
        mycursor.execute('UPDATE users SET status_ = "wait_edit" WHERE id = %s', (self.id,))
        mydb.commit()

    def send_req_to_bass(self):
        # посылаем запрос
        send_message(self.id, 'Запрос отправлен! Ожидайте файл в течение 15-40 секунд.')
        # получаем id сообщения (стикер с думающим утёнком)
        req_id = send_sticker(self.id, 'loading')
        file = get_file(self.id)
        # аварийная проверка на размер
        assert file['result']['file_size'] <= cred['maxsize']
        file_path = file['result']['file_path']
        mycursor.execute(
            f"UPDATE bass_requests SET req_id = %s, file_path = %s WHERE id = %s",
            (req_id, file_path, self.id))
        mydb.commit()
        mycursor.execute(
            "UPDATE users SET status_ = 'req_sent', last_query = NOW() + INTERVAL 3 HOUR WHERE id = %s",
            (self.id,))
        mydb.commit()
        put_SNS('BassBoostTrigger', req_id)

    # автоматическое обрезание песни
    def auto_cut(self, duration):
        if self.max_sec > duration:
            return None
        # обрезаем файл, если максимальный объём меньше duration
        send_message(self.id,
                     '<b>Внимание!</b>' +
                     f'\nВаша роль не позволяет обрабатывать песни более <b>{self.max_sec}</b> секунд.' +
                     f'\nПесня будет обрезана до этого значения!')

        mycursor.execute('UPDATE bass_requests SET start_ = %s, end_ = %s where id = %s',
                         (0, self.max_sec, self.id))
        mydb.commit()

    def msg(self):
        # пытаемся распознать текст, иначе понимаем что юзер скинул неизвестный документ
        try:
            self.text = self.event['message']['text']
        except KeyError:
            # если мы сейчас ожидаем аудио >> неизвестный формат
            if self.status == "wait_file":
                send_message(self.id,
                             '<b>Ошибка!</b>\nВы отправили файл <b>документом</b>!' +
                             '\nВ этом случае бот не может узнать кодировку аудио и его продолжительность.' +
                             '\n<b>Отправьте файл в виде аудио!</b>')

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
            send_message(self.id, 'Пожалуйста, отправьте <b>файл</b>, а не сообщение!',
                         'reply_markup', json.dumps(file_markup))

        elif self.status == 'wait_edit':
            if self.text == 'Редактировать файл':
                mycursor.execute("UPDATE users SET status_ = 'wait_cut' WHERE id = %s", (self.id, ))
                mydb.commit()
                send_message(self.id,
                             '<b>Сначала укажи границы обрезки файла файл (если нужно).</b>' +
                             '\nПример (вводить без кавычек): "1.5 10" - обрезка песни с 1.5 по 10 секунду.',
                             'reply_markup', json.dumps(cut_markup))
            elif self.text == 'Пропустить редактирование':
                # получаем длительность файла
                mycursor.execute('SELECT duration from bass_requests where id = %s', (self.id,))
                duration = mycursor.fetchone()[0]

                # выполняем автообрезание
                self.auto_cut(duration)

                mycursor.execute("UPDATE users SET status_ = 'wait_bass_level' WHERE id = %s", (self.id,))
                mydb.commit()
                send_message(self.id, '<b>Выбери уровень баса:</b>', 'reply_markup', json.dumps(bass_markup))
            else:
                send_message(self.id, 'Нажмите одну из кнопок на клавиатуре!')

        # обрезка файла
        elif self.status == "wait_cut":
            # находим длительность файла
            mycursor.execute('SELECT duration from bass_requests where id = %s', (self.id,))
            duration = mycursor.fetchone()[0]

            if self.text == 'Обрезать не нужно':

                # автообрезание
                self.auto_cut(duration)

                send_message(self.id,
                             'Теперь укажи, с какой секунды начинать усиливать бас.\nПример "5.2" - с 5.2 секунды.',
                             'reply_markup', json.dumps(startbass_markup))
            else:
                s = self.text.split()
                # проверка, что введены именно ЧИСЛА
                try:
                    f0 = round(float(s[0]), 1)
                    f1 = round(float(s[1]), 1)
                except ValueError:
                    send_message(self.id,
                                 'Синтаксическая ошибка! \n<b>проверьте, что десятичная дробь записана через точку!</b>',
                                 'reply_markup', json.dumps(cut_markup))
                    return None
                if (f0 >= 0) and (f0 < f1) and (f1 <= duration):
                    # проверка на баланс
                    mycursor.execute('UPDATE bass_requests SET start_ = %s, end_ = %s where id = %s',
                                     (f0, f1, self.id))
                    mydb.commit()
                    send_message(self.id,
                                 'Всё чётко! Теперь укажи, <b>с какой секунды начинается бас.</b>' +
                                  '\nПример: "5.2" - с 5.2 секунды.\n<i>Указывай время с начала уже обрезанной песни!</i>',
                                  'reply_markup', json.dumps(startbass_markup))
                else:
                    send_message(self.id,
                                 'Хм, что-то не то с границами обрезки. <i>Напишите границы обрезки корректно!</i>',
                                 'reply_markup', json.dumps(cut_markup))
                    return None

            # обновляем статус на 2
            mycursor.execute('UPDATE users SET status_ = "wait_bass_start" WHERE id = %s', (self.id,))
            mydb.commit()

        # начало баса
        elif self.status == "wait_bass_start":
            if self.text != 'По умолчанию (с самого начала)':
                # корректность ввода числа
                try:
                    # f - начало басса
                    f = round(float(self.text), 1)
                except ValueError:
                    send_message(self.id,
                                 'Синтаксическая ошибка! \n<b>проверьте, что десятичная дробь записана через точку!</b>',
                                 'reply_markup', json.dumps(startbass_markup))
                    return None
                mycursor.execute('SELECT duration, start_, end_ from bass_requests where id = %s', (self.id,))
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
            mycursor.execute('UPDATE users SET status_ = "wait_bass_level" WHERE id = %s', (self.id,))
            mydb.commit()

        # выбор уровня баса
        elif self.status == "wait_bass_level":
            if self.text in level:
                # уровень баса в словах >> цифры
                l = level.index(self.text)
                mycursor.execute('UPDATE bass_requests SET bass_level = %s WHERE id = %s',
                                 (l, self.id))
                mydb.commit()
                # отправляем запрос к BassBoostFunc
                self.send_req_to_bass()

            # непонятный уровень баса, введённый пользователем
            else:
                send_message(self.id,
                             'Такого уровня баса ещё не существует. Выберите уровень из <b>установленных значений!</b>',
                             'reply_markup', json.dumps(bass_markup))


def get_users(role):
    mycursor.execute("SELECT id FROM users WHERE role_ = %s", (role,))
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
            r = send_message(self.user_id, 'Создание оплаты...')
            if not r['ok']:
                send_message(self.user_id, 'Ошибка в создании оплаты, повторите попытку позже.')
                return None
            pay_id = r['result']['message_id']
            param = {'pay_id': pay_id, 'status': '❌ НЕ оплачено!'}
            text = get_text_from_db('pay_rule', param)
            edit_message(self.user_id, pay_id, text, "reply_markup", json.dumps(pay_check_inline_markup))
            mycursor.execute(
                "INSERT INTO payment_query(pay_id, user_id, username, start_query, status_) VALUES (%s, %s, %s, NOW() + INTERVAL 3 HOUR, %s)",
                (pay_id, self.user_id, self.username, "wait_for_payment"))
            mydb.commit()
        elif self.data == 'check_payment':
            pay_check = pay.check_payment(self.msg_id, cred, mycursor, mydb)
            if pay_check['success']:
                self.answer_query_no_text()
                param = {'pay_id': self.msg_id, 'status': '<b>✅ Оплачено!</b>'}
                text = get_text_from_db('pay_rule', param)
                edit_message(self.user_id, self.msg_id, text)
                # получаем сумму в рублях
                sum_rub = pay_check['sum']
                # обновляем баланс
                mycursor.execute("UPDATE users SET balance = balance + %s WHERE id = %s",
                                 (sum_rub, self.user_id))
                mydb.commit()
                send_sticker(self.user_id, 'money')
                send_message(self.user_id,
                             f"Оплата успешно завершена!\nВам начислено <b>{sum_rub}</b> руб!")
            else:
                if pay_check['error'] == 'Payment_not_found':
                    self.answer_query(
                        'Повторите попытку проверки через нескольско секунд. Мы ещё не получили платёж от Qiwi!',
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

        elif self.data == 'delete_payment':
            mycursor.execute("DELETE FROM payment_query WHERE pay_id = %s", (self.msg_id,))
            mydb.commit()
            self.answer_query('Успешно удалено')
            delete_message(self.user_id, self.msg_id)

        # товары
        else:
            mycursor.execute("SELECT balance FROM users WHERE id = %s", (self.user_id,))
            balance = mycursor.fetchone()[0]
            premium_prod = {'premium_day': 1, 'premium_week': 7, 'premium_month': 30}
            if self.data in premium_prod:
                mycursor.execute("SELECT value_param FROM payment_param WHERE name_param = %s", (self.data, ))
                price = mycursor.fetchone()[0]
                if balance >= price:
                    mycursor.execute(
                        """UPDATE users SET balance = balance - %s, role_ = 'premium',
                        role_end = IF (role_end IS NULL, NOW() + INTERVAL 3 HOUR + INTERVAL %s DAY, role_end + INTERVAL %s DAY)
                        WHERE id = %s""",
                        (price, premium_prod[self.data], premium_prod[self.data], self.user_id))
                    mydb.commit()
                    self.answer_query("Успешно!")
                    mycursor.execute("SELECT role_end FROM users WHERE id = %s", (self.user_id, ))
                    send_message(self.user_id,
                                 f"Вы успешно приобрели подписку premium до {mycursor.fetchone()[0]} по МСК.")

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
    global mycursor
    global mydb
    # обновляем подключение к бд
    mycursor, mydb = connect_db()

    print(event)

    # проверка на нажатие инлайн кнопки
    if 'callback_query' in event.keys():
        button = InlineButton(event)
        button.action()
        return None

    # инициализация юзера
    user = User(event)
    # проверка на успешную инициализацию
    if not user.init_success:
        return None

    # проверка на бан
    if user.role == 'ban':
        text = get_text_from_db('ban')
        send_message(user.id, text)
        return None

    # debug mode
    if user.role_active == 0:
        if user.status == 'start':
            user.start_msg()
            text = get_text_from_db('start_debug')
            send_message(user.id, text)
        else:
            text = get_text_from_db('sleep')
            send_message(user.id, text)
            send_sticker(user.id, 'sleep')
        return None

    # проверяем: это сообщение или файл - находим общие ключи
    c = list(set(event['message'].keys()) & tags)

    # юзер залил файл
    if c:
        user.file(c[0], event['message'])

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
    return r


def send_message_not_parse(chat_id, text):
    url = URL + "sendMessage?chat_id={}&text={}".format(chat_id, text)
    requests.get(url)


def edit_message(chat_id, message_id, text, *args):
    if len(args) == 0:
        url = URL + "editMessageText?chat_id={}&message_id={}&text={}&parse_mode=HTML".format(chat_id, message_id, text)
    elif len(args) == 2:
        url = URL + "editMessageText?chat_id={}&message_id={}&text={}&{}={}&parse_mode=HTML".format(chat_id, message_id,
                                                                                                    text, args[0],
                                                                                                    args[1])
    requests.get(url)


def delete_message(chat_id, message_id):
    url = URL + "deleteMessage?chat_id={}&message_id={}".format(chat_id, message_id)
    requests.get(url)


def get_text_from_db(tag, param=None):
    mycursor.execute("SELECT text FROM msgs WHERE name = %s", (tag,))
    text = mycursor.fetchone()[0]
    if text:
        if param:
            try:
                text = text.format(**param)
            except KeyError:
                admins = get_users('admin')
                for admin in admins:
                    send_message(admin, f'!!! <b>ERROR</b> Error with format {tag}!')
        return text
    admins = get_users('admin')
    for admin in admins:
        send_message(admin, f'!!! <b>ERROR</b> Error {tag} not found!')


def send_sticker(chat_id, sticker):
    mycursor.execute("SELECT stick_id FROM msgs WHERE name = %s", (sticker,))
    stick = mycursor.fetchone()[0]
    if stick:
        url = URL + "sendSticker?chat_id={}&sticker={}&parse_mode=HTML".format(chat_id, stick)
        try:
            r = requests.get(url).json()
            return r['result']['message_id']
        except KeyError:
            pass

    # если ошибка
    admins = get_users('admin')
    for admin in admins:
        send_message(admin, f'!!! <b>ERROR</b> Sticker {sticker} not found!')
    return round(time.time())


def get_file(chat_id):
    # get file_id from db
    mycursor.execute('SELECT file_id FROM bass_requests WHERE id = %s', (chat_id,))
    file_id = mycursor.fetchone()[0]
    # make request
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


# publish to SNS topic
def put_SNS(topic_name, message):
    arn = cred[f'{topic_name}_topic_arn']
    client = boto3.client('sns')

    response = client.publish(
        TargetArn=arn,
        Message=json.dumps(message)
    )
