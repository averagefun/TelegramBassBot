-- MySQL dump 10.13  Distrib 8.0.20, for Linux (x86_64)
--
-- Host: botdatabase.cnlv2quyzddk.us-east-2.rds.amazonaws.com    Database: TelegramBot
-- ------------------------------------------------------
-- Server version	8.0.17

/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!50503 SET NAMES utf8mb4 */;
/*!40103 SET @OLD_TIME_ZONE=@@TIME_ZONE */;
/*!40103 SET TIME_ZONE='+00:00' */;
/*!40014 SET @OLD_UNIQUE_CHECKS=@@UNIQUE_CHECKS, UNIQUE_CHECKS=0 */;
/*!40014 SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0 */;
/*!40101 SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='NO_AUTO_VALUE_ON_ZERO' */;
/*!40111 SET @OLD_SQL_NOTES=@@SQL_NOTES, SQL_NOTES=0 */;

--
-- Dumping data for table `msgs`
--

LOCK TABLES `msgs` WRITE;
/*!40000 ALTER TABLE `msgs` DISABLE KEYS */;
INSERT INTO `msgs` VALUES ('start','CAACAgIAAxkBAAMzXrVojwLgjpqLL8gJ4HbWwzLAO2oAAgEBAAJWnb0KIr6fDrjC5jQZBA','Привет, {username}!\n<b>Чтобы начать, скинь мне: </b>\n- <i>Аудио</i>\n- <i>Голосовое сообщение</i>\n- <i>Видео</i>\n- <i>Круглое видео Telegram</i>\n_____________________________\n/cancel - отменить басбуст,\n/help - помощь по боту'),('money','CAACAgIAAxkBAAIHIl7XedDNwnjGUqmYgCqT-hAF0QW2AAIDAQACVp29CgLl0XiH5fpPGgQ',NULL),('like','CAACAgIAAxkBAAM1XrVowpOafCGAzoivuTXPtAaOgowAAv4AA1advQraBGEwLvnX_xkE',NULL),('loading','CAACAgIAAxkBAAN_Xre2LtYeBDA-3_ewh5kMueCsRWsAAgIBAAJWnb0KTuJsgctA5P8ZBA',NULL),('sleep','CAACAgIAAxkBAAIC7F7Ssq5ZxpL97wYH2kuRwBqYigQMAAIOAQACVp29ChGpLWjCceBoGQQ','Извините, бот временно отдыхает. Идёт обновление кода.\nПодождите около 15 минут.'),('pay_rule',NULL,' <a href=\"qiwi.com/n/JWPAYMENT\"><strong>Оплатите по ссылке</strong></a>\n <b>!!!В комментариях к заказу укажите: {pay_id}</b>\n \n <i>Проверьте оплату по кнопке через 10 секунд</i>\n <b>Статус:</b> {status}'),('products',NULL,'<b>ДОСТУПНЫЕ УЛУЧШЕНИЯ</b>\n<i>Подписка <b>premium</b> на:</i>\n- 24 часа: <b>{premium_day}</b> руб\n- 7 дней: <b>{premium_week}</b> руб\n- 30 дней: <b>{premium_month}</b> руб\nПодписка позволяет обрабатывать до <b>{max_sec_premium}</b> сек каждой\nпесни вместо <b>{max_sec_standard}</b> стандартных. Также отсутствует\nреклама и лишние уведомления от бота.'),('pay_system',NULL,'\n<b>СИСТЕМА ОПЛАТЫ</b>\n- Вы оплачиваете ту сумму, которую хотите пополнить\n   внутри бота!\n- Оплата принимается только в рублях!\n\n<b>ПОКУПКА УЛУЧШЕНИЙ</b>\nДля покупки улучшений используйте <b>/buy</b>'),('start_debug',NULL,'Добро пожаловать в @AudioBassBot! К сожалению, сейчас мы обновляем код нашего бота и \nон <b>недоступен</b>. Такое случается редко и только при больших обновлениях. В любом случае, напишите команду /start ещё раз через некоторое время (например, через 10 минут). Мы надеемся,\nчто к этому времени мы уже запустим нашего бота!'),('help',NULL,'<b>КОМАНДЫ</b>\n<strong>/cancel - отменить басбуст на любой стадии</strong>\n/help - вывести это сообщение ещё раз\n/stats - твой баланс и статистика\n/pay - пополнить баланс\n/buy - купить улучшения в боте\n/bug - сообщить о баге (/bug \"описание бага\")\n/commands - дополнительные команды для каждой роли\n\n<b>КАК УСТРОЕН БОТ?</b>\nТы можешь пользоваться ботом бесплатно и безлимитно\nс ограничением на время обработки одной песни.\nЕсли же ты хочешь басбустить песни до 5 мин и\nпользоваться некоторыми другими преимуществами, \nто можешь купить это по супер низкой цене <b>(/pay)</b>!\n\n<b>Новая фишка: если ты хочешь быстро забасбустить\nтрек, то просто отправь файл, а в описании к нему укажи\nуровень баса (цифру от 1 до 4 включительно)!</b>'),('stats',NULL,'Ваша роль: <b>{role}</b>,\n<i>{role_end}</i>\nБаланс: <b>{balance}</b> руб,\nМаксимальное кол-во секунд\nна одну песню: <b>{max_sec}</b>,\nВсего использовано: <b>{total}</b> сек,\nПриглашено друзей: <b>{ref_count}</b>.'),('uniq_msg',NULL,'simple text'),('after_req_start',NULL,'<b>Итак, твой первый басбуст выполнен!</b>\nТеперь ты можешь пользоваться ботом безлимитно\nи бесплатно, однако учитывай, что ты не можешь \nбассбустить больше <b>{max_sec_standard}</b> секунд\nодной песни. \n<b>Чтобы продолжить, отправь новый файл, однако сначала\nсоветуем заглянуть в /help!</b>'),('referral',NULL,'Если вам нравится бот, порекомендуйте его друзьям,\nподелившись своей реферальной ссылкой (за каждого\nнового пользователя вы получаете <b>{ref_bonus}</b> руб!)\n<strong>Ссылка: https://t.me/AudioBassBot?start={id}</strong>'),('after_req_standard',NULL,'Запрос успешно выполнен!\n<b>Отправьте файл для нового запроса!</b>'),('admin_stats',NULL,'Пользователь: <b>{username}</b>\n(id: {id})\nДата регистрации:\n<i>{reg_date}</i>\n\nРоль: <b>{role}</b>,\n<i>{role_end}</i>\nСтатус: <b>{status}</b>,\nБаланс: <b>{balance}</b> руб,\nМаксимальное кол-во секунд\nна одну песню: <b>{max_sec}</b>,\nПосл. запрос:\n<i>{last_query}</i>\nВсего использовано: <b>{total}</b> сек,\nПриглашено друзей: <b>{ref_count}</b>.'),('ban',NULL,'В связи с большим трафиком вам <b>временно\nограничен доступ к боту :( </b>\nСкорее всего, через 30 - 120 минут ограничение будет снято.\n(Если хотите пользоваться ботом постоянно, \nкупите premium <b>/pay!</b>)'),('update',NULL,'Извините, если отправили это сообщение второй раз\nвследствие технических проблем.\n\n<b>КОНКУРС от @AudioBassBot</b>\nПривет! Сегодня мы начинаем проводить конкурс,\nгде ты сможешь выиграть до <b>2000 рублей</b>!!\n\nЧТО НУЖНО СДЕЛАТЬ:\nНужно пригласить к боту по своей реферальной\nссылке наибольшее количество человек. (Реферальную\nссылку можно найти в конце /help, а посмотреть кол-во\nприглашённых друзей в /stats).  \n\nКОГДА РЕЗУЛЬТАТЫ:\nРезультаты будут подведены, когда сумма всех обработанных\nботом треков достигнет 100 000 секунд (Сейчас около 20 000).\n\nПРИЗЫ:\n3 человека получат денежные призы:\n1 место - <b>2000 руб</b>\n2 место - <b>1000 руб</b>\n3 место - <b>500 руб</b>\n\nПРАВИЛА:\n- Нельзя приглашать ботов (бан навсегда)\n- Чтобы бот засчитал приглашённого человека,\n  он должен забасбустить хотя бы 1 трек!\n- Чтобы получить приз, у вас должен быть\n  Qiwi кошелёк или Яндекс Деньги или\n  карта одного из банков.\n\n<i>На данный момент у бота около 150 пользователей,\nтак что шанс выиграть очень большой! Удачи!</i>');
/*!40000 ALTER TABLE `msgs` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Dumping data for table `payment_param`
--

LOCK TABLES `payment_param` WRITE;
/*!40000 ALTER TABLE `payment_param` DISABLE KEYS */;
INSERT INTO `payment_param` VALUES ('premium_day',3),('premium_month',30),('premium_week',10),('ref_bonus',2);
/*!40000 ALTER TABLE `payment_param` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Dumping data for table `roles`
--

LOCK TABLES `roles` WRITE;
/*!40000 ALTER TABLE `roles` DISABLE KEYS */;
INSERT INTO `roles` VALUES ('admin',350,_binary ''),('ban',0,_binary ''),('block_by_user',0,_binary ''),('premium',300,_binary ''),('standard',120,_binary ''),('start',210,_binary '');
/*!40000 ALTER TABLE `roles` ENABLE KEYS */;
UNLOCK TABLES;
/*!40103 SET TIME_ZONE=@OLD_TIME_ZONE */;

/*!40101 SET SQL_MODE=@OLD_SQL_MODE */;
/*!40014 SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS */;
/*!40014 SET UNIQUE_CHECKS=@OLD_UNIQUE_CHECKS */;
/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
/*!40111 SET SQL_NOTES=@OLD_SQL_NOTES */;

-- Dump completed on 2020-06-22 17:37:47