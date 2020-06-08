import json

import requests
import mysql.connector

# Get qiwi history
def get_qiwi_history(QIWI_TOKEN, QIWI_ACCOUNT):
    s = requests.Session()
    s.headers['authorization'] = 'Bearer ' + QIWI_TOKEN
    parameters = {'rows': '50'}
    h = s.get('https://edge.qiwi.com/payment-history/v1/persons/'+ QIWI_ACCOUNT +'/payments', params = parameters)
    req = json.loads(h.text)['data']
    return req


def check_payment(pay_id, cred, mycursor, mydb):
    # Get qiwi credentials
    QIWI_TOKEN = cred['qiwi_token']
    QIWI_ACCOUNT = cred['qiwi_account']

    # connect to db
    mycursor.execute(f"SELECT status_ FROM payment_query WHERE pay_id = %s", (pay_id, ))
    pay_status = mycursor.fetchone()[0]

    ans = {'success': None}
    if pay_status == 'success':
        ans['success'] = False
        ans['error'] = 'already_complete'
        return ans

    # получаем последние 50 действий из истории
    req = get_qiwi_history(QIWI_TOKEN, QIWI_ACCOUNT)

    # перебираем эти действия
    for i in range(len(req)):
        r = req[i]
        if r['comment'] == str(pay_id) and r['type'] == 'IN' and r['sum']['currency'] == 643:
            ans['sum'] = r['sum']['amount']
            if r['status'] == "SUCCESS":
                ans['success'] = True
                mycursor.execute(f"""UPDATE payment_query SET 
                                status_ = 'success', 
                                finish_query = NOW() + INTERVAL 3 HOUR, 
                                sum = %s 
                                WHERE pay_id = %s""", (ans['sum'], pay_id))
                mydb.commit()
                return ans
            # если ошибка
            ans['success'] = False
            ans['error'] = r['error']

    # если нашли запрос с ошибкой
    if ans['success'] == False:
        mycursor.execute(f"""UPDATE payment_query SET status_ = %s, 
                        finish_query = NOW() + INTERVAL 3 HOUR, sum = %s WHERE pay_id = %s""",
                         (ans['error'], ans['sum'], pay_id))
        mydb.commit()
        return ans
    # если не нашли запрос от этого пользователя
    ans['success'] = False
    ans['error'] = 'Payment_not_found'
    return ans
