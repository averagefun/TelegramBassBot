use TelegramBot;

# CREATE ALL TABLES
# users
CREATE TABLE users(
id INT NOT NULL PRIMARY KEY,
username VARCHAR(255),
role_ VARCHAR(127) NOT NULL,
balance INT NOT NULL,
status_ VARCHAR(65) NOT NULL,
total INT,
last_query TIMESTAMP,
role_end TIMESTAMP);

# roles
drop table roles;
CREATE TABLE roles (
name VARCHAR(127) NOT NULL UNIQUE,
d_bal SMALLINT NOT NULL,
max_to_add SMALLINT NOT NULL,
maxsize INT NOT NULL,
role_active BINARY NOT NULL);
INSERT INTO roles VALUES ('junior', 30, 60, 1000000, 1);
INSERT INTO roles VALUES ('middle', 80, 200, 2000000, 1);
INSERT INTO roles VALUES ('senior', 150, 350, 3500000, 1);
select * from roles;

CREATE TABLE roles (
name VARCHAR(127) NOT NULL UNIQUE,
d_bal SMALLINT NOT NULL,
max_to_add SMALLINT NOT NULL,
maxsize INT NOT NULL,
role_active BIT NOT NULL);
INSERT INTO roles VALUES ('junior', 30, 60, 1000000, 1);
INSERT INTO roles VALUES ('middle', 80, 200, 2000000, 1);
INSERT INTO roles VALUES ('senior', 150, 350, 3500000, 1);
select * from roles;

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