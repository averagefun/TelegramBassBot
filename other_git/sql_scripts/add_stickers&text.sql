use TelegramBot;

# ДОБАВЛЯТЬ ТЕКСТ ЗДЕСЬ
INSERT INTO msgs(name,text) VALUES (
"pay_system",
"Доступные товары на данный момент представлены ниже. 
<b>СИСТЕМА ПОКУПКИ:</b>
Вы покупаете секунды по <b>КУРСУ 1 руб = {rate} сек</b>.
Секунды внутри бота считаются валютой. То есть вы 
можете тратить их по прямому назначению, а можете 
покупать на них товары с помощью команды <b>/buy</b>."
);

# ДОБАВЛЯТЬ СТИКЕРЫ ЗДЕСЬ
INSERT INTO msgs(name, stick_id) VALUES(
"sleep",
"CAACAgIAAxkBAAIC7F7Ssq5ZxpL97wYH2kuRwBqYigQMAAIOAQACVp29ChGpLWjCceBoGQQ"
);
select * from msgs;

# ДОБАВИТЬ СТИКЕРЫ + ТЕКСТ
INSERT INTO msgs(name, stick_id) VALUES(
"tag",
"sticker_id","
simple text
"
);
select * from msgs;