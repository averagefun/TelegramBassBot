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

    # получение максимального количества секунд, когда работает автопополнение
    mycursor.execute("SELECT * FROM roles")
    roles = mycursor.fetchall()
    keys = [role[0] for role in roles]
    values = [role[1:] for role in roles]  # d_bal, max_to_add, maxsize, role_active
    r = dict(zip(keys, values))

    # обновляем таблицу
    mycursor.execute(update_role())
    mydb.commit()
    mycursor.execute(update_bal(r))
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


def update_bal(r):
    return f'''UPDATE users
                SET balance = CASE
                    WHEN role_ = 'senior' THEN CASE
                        WHEN balance >= {r['senior'][1]} THEN 
                            balance
                        WHEN balance < ({r['senior'][1]} - {r['senior'][0]}) THEN
                            balance + {r['senior'][0]}
                        ELSE {r['senior'][1]}
                        end
                    WHEN role_ = 'middle' THEN CASE
                        WHEN balance >= {r['middle'][1]} THEN 
                            balance
                        WHEN balance < ({r['middle'][1]} - {r['middle'][0]}) THEN
                            balance + {r['middle'][0]}
                        ELSE {r['middle'][1]}
                        end
                    WHEN role_ = 'junior' THEN CASE
                        WHEN balance >= {r['junior'][1]} THEN 
                            balance
                        WHEN balance < ({r['junior'][1]} - {r['junior'][0]}) THEN
                            balance + {r['junior'][0]}
                        ELSE {r['junior'][1]}
                        end
                    ELSE
                        balance
                    end
                '''


def update_role():
    return f'''UPDATE users
                  SET role_ = 'junior',
                  role_end = NULL 
                  WHERE (NOW() + INTERVAL 3 HOUR) >= role_end'''
