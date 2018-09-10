import os
import json
import codecs
import configparser
import redis
import pymysql
import requests
from logger import logger

get_path = lambda path: os.path.abspath(
    os.path.join(os.path.join(os.path.dirname(__file__)), path)
)

config = configparser.ConfigParser()
config.read_file(codecs.open(get_path("config_setting.ini"), "r", "utf-8-sig"))


class redis_utils:
    """
    Redis操作类
    """

    def __init__(self):
        self.redis_conn = redis.StrictRedis(
            config["redis"]["redis_host"],
            port=int(config["redis"]["redis_port"]),
            password=config["redis"]["redis_pwd"],
            db=0,
        )

    def set_redis_key(self, key, result):
        self.redis_conn.set(key, result)

    def get_redis(self, key):
        return self.redis_conn.get(key)


class mysql_utils:
    """
    Mysql操作类
    """

    def __init__(self, host, logging):
        self.host = host
        self.logger = logging
        self.user = config["mysql"]["mysql_user"]
        self.pwd = config["mysql"]["mysql_password"]
        self.port = int(config["mysql"]["mysql_port"])
        self.db = config["mysql"]["mysql_db"]
        self.table = config["mysql"]["mysql_table"]

    def execute_mysql_query(self, sql_query):
        try:
            mysql_conn = pymysql.connect(
                user=self.user,
                passwd=self.pwd,
                host=self.host,
                port=self.port,
                db=self.db,
                charset="utf8",
            )
            cursor = mysql_conn.cursor()
            cursor.execute(sql_query)
            mysql_conn.commit()
            query_result = cursor.fetchall()
            cursor.close()
            mysql_conn.close()
            return query_result
        except (TimeoutError, pymysql.OperationalError):
            self.logger.logger.error(
                "Failed to connect mysql via %s:%s!" % (self.host, self.port)
            )
            return

    def get_server_info(self):
        return self.execute_mysql_query(
            "SELECT servername, if(has_agent=1,proxyip,serverip) as ip,status FROM %s.%s where status=1 and is_abroad=1;"
            % (self.db, self.table)
        )

    def get_all_server(self):
        return self.execute_mysql_query(
            "SELECT count(*) FROM %s.%s where status in (1,2) and is_abroad=1;"
            % (self.db, self.table)
        )

    def get_backup_server(self):
        return self.execute_mysql_query(
            "SELECT count(*) FROM %s.%s where status=2 and is_abroad=1;"
            % (self.db, self.table)
        )

    def get_server_status(self, region):
        return self.execute_mysql_query(
            "SELECT status FROM %s.%s where servername='%s';"
            % (self.db, self.table, region)
        )

    def update_server_status(self, region, status):
        return self.execute_mysql_query(
            "UPDATE %s.%s SET status=%s WHERE servername='%s' and id >= 0;"
            % (self.db, self.table, status, region)
        )


class sms_sender:
    """
    发送云片短信
    """

    def __init__(self, content):
        self.tpl_id = config.get("sms", "tpl_id")
        self.receiver_list = config.get("sms", "receiver_list").split(",")
        self.sdkappid = config.get("sms", "sdkappid")
        self.url = config.get("sms", "url")
        self.content = content

    def send_msg(self, receiver):
        tpl_value = "#content#=" + self.content
        params = {
            "tpl_id": self.tpl_id,
            "tpl_value": tpl_value,
            "apikey": self.sdkappid,
            "mobile": receiver,
        }
        headers = {
            "Content-type": "application/x-www-form-urlencoded",
            "Accept": "text/plain",
        }
        response = requests.post(self.url, params, headers)
        return response.text

    def bulk_send_msg(self):
        for mobile in self.receiver_list:
            rs = json.loads(self.send_msg(mobile))
            if rs["code"] != 0:
                continue
