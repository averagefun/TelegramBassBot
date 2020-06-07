# function update balance every day at 00:10 UTC +3 (Moscow Time)
import mysql.connector
import boto3


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


# event from CloudWatch
def lambda_handler(event, context):
    # если это не событие по графику, то игнорируем
    if "time" not in event.keys():
        return None

    global mycursor
    global mydb
    # обновляем подключение к бд
    mycursor, mydb = connect_db()

    print(event)

    # обновляем таблицу
    mycursor.execute(update_role())
    mydb.commit()
    mycursor.execute(update_bal())
    mydb.commit()


# Connect to RDS database
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


def update_bal():
    return '''UPDATE users
               SET balance =
               IF (balance >= (SELECT max_to_add FROM roles WHERE roles.name = users.role_), balance,
                    IF (balance < ((SELECT max_to_add FROM roles WHERE roles.name = users.role_) -
                                    (SELECT d_bal FROM roles WHERE roles.name = users.role_)),
                                        balance + (SELECT d_bal FROM roles WHERE roles.name = users.role_),
                                            (SELECT max_to_add FROM roles WHERE roles.name = users.role_)))'''


def update_role():
    return '''UPDATE users
                  SET role_ = 'standart',
                  role_end = NULL
                  WHERE (NOW() + INTERVAL 3 HOUR) >= role_end'''
