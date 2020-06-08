use TelegramBot;

# CREATE ALL TABLES
# users
CREATE TABLE users(
num INT PRIMARY KEY AUTO_INCREMENT,
id INT NOT NULL UNIQUE,
username VARCHAR(255),
reg_date TIMESTAMP,
role_ VARCHAR(127) NOT NULL,
balance INT NOT NULL,
status_ VARCHAR(65) NOT NULL,
total INT,
last_query TIMESTAMP,
role_end TIMESTAMP);

# roles
CREATE TABLE roles (
name VARCHAR(127) NOT NULL UNIQUE,
d_bal SMALLINT NOT NULL,
max_sec SMALLINT NOT NULL,
role_active BIT NOT NULL);
# admin, standard, start, start_unlimited and unlimited roles
select * from roles;

# bass_requests table
CREATE TABLE bass_requests(
id INT UNIQUE,
file_id VARCHAR(255),
duration SMALLINT,
start_ SMALLINT,
end_ SMALLINT,
start_bass SMALLINT,
bass_level SMALLINT,
file_path VARCHAR(255),
req_id INT UNIQUE);

# sticker and text table (messages table)
CREATE TABLE msgs(
name VARCHAR(255) NOT NULL,
stick_id VARCHAR(255),
text TEXT);
desc msgs;

# payment table
CREATE TABLE payment_query(
pay_id INT NOT NULL PRIMARY KEY,
user_id INT NOT NULL,
username VARCHAR(255),
sum INT,
start_query TIMESTAMP,
finish_query TIMESTAMP,
status_ VARCHAR(255) NOT NULL);
desc payment_query;

# payment param table
CREATE TABLE payment_param(
name_param VARCHAR(255) NOT NULL UNIQUE,
value_param INT NOT NULL);
desc payment_param;
INSERT INTO payment_param VALUES ('rate', 20);
INSERT INTO payment_param VALUES ('price_mid', 300);
select * from payment_param;