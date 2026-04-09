import sys
import time
import os
import mysql.connector

_env_path = os.path.join(os.path.dirname(__file__), '..', 'config', 'config.env')
with open(_env_path) as _f:
    for _line in _f:
        _line = _line.strip()
        if _line and not _line.startswith('#') and '=' in _line:
            _k, _v = _line.split('=', 1)
            os.environ.setdefault(_k.strip(), _v.strip())

try:
    print('Im doing my best ok')
    db = mysql.connector.connect(host=os.environ['DB_HOST'], user=os.environ['DB_USER'], password=os.environ['DB_PASSWORD'], database=os.environ['DB_NAME'])
    print('Conneted')
    curs = db.cursor()
    curs.excute('''INSERT INTO pours values (CURRENT_DATE(), CURRENT_TIME(), %s, %s) ''', ("AC", 700))
    db.commit()
    print('fook ye')
except Exception as ue:
    print('fook')
db.close()
    

