import sys

sys.path.append("..")

import time, datetime
from logger import logger
from common import get_path,config, redis_utils, mysql_utils

_logger = logger(get_path("logs//vpn_info.log"))

class update_vpn_list:
    def __init__(self):
        self.redis_util = redis_utils()

    def update_vpn_info(self):
        result = mysql_utils(config["mysql"]["mysql_host"],_logger).get_server_info()
        robot_num = config.getint("default", "total_robot_num")
        if result:
            avg_ip_num = int(len(result) / robot_num)
            for _index in range(1, robot_num + 1):
                _start = avg_ip_num * (_index - 1)
                _end = avg_ip_num * _index

                if _index >= robot_num:
                    self.redis_util.set_redis_key(
                        "%s_%s" % (config["redis"]["prefix_vpn_key"], _index),
                        result[_start:],
                    )

                else:
                    self.redis_util.set_redis_key(
                        "%s_%s" % (config["redis"]["prefix_vpn_key"], _index),
                        result[_start:_end],
                    )
            _logger.logger.info("updated at %s!" % (datetime.datetime.now()))
        else:
            _logger.logger.error("Fail: Got an empty SQL result!")



if __name__ == "__main__":
    update_vpn_instance = update_vpn_list()
    while True:
        update_vpn_instance.update_vpn_info()
        time.sleep(10)
