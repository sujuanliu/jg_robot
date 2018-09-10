import sys

sys.path.append("..")

import time
import datetime
from common import get_path, config, redis_utils, mysql_utils, sms_sender
from logger import logger

_logger = logger(get_path("logs//parser.log"))

server_internal_failure_msg = u"%s:%s 已经下架 原因:服务器在线人数为0或访问不了youbube 时间:%s"
ssh_connection_failure_msg = u"%s:%s 已经下架 原因:ssh连接失败或超时 时间:%s"


class Runner:
    def __init__(self):
        self.redis_util = redis_utils()
        self.result = []
        self.threshold = (
            config.getint("default", "period")
            * 60
            * config.getfloat("default", "conn_failure_rate")
            / config.getint("default", "frequency")
        )
        self.fail_num = 0
        self.initialize_data()
        _logger.logger.info(self.threshold)

    def cal_total_vpn_line(self):
        return int(
            mysql_utils(config["mysql"]["mysql_host"], _logger).get_all_server()[0][0]
        )

    def get_total_backup_vpn(self):
        return int(
            mysql_utils(config["mysql"]["mysql_host"], _logger).get_backup_server()[0][
                0
            ]
        )

    def initialize_data(self):
        """
        每个检测周期结束后，将timer和queue置零或清空
        """
        self.current_timer = datetime.datetime.now()
        self.timer = self.current_timer
        self.queue_list = {}
        self.final_result = {}

    def collect_result(self):
        """
        从redis重获取每个机器人执行测试线路连通性的失败结果，并将其结果存储在self.result中
        e.g. self.result = [{'韩国2': {'ip':'164.52.56.58','result':'Fail'}}]
        """
        self.result = []
        key_name = config["redis"]["prefix_result_key"]
        robot_num = config.getint("default", "total_robot_num")

        for _index in range(1, robot_num + 1):
            _data = eval(self.redis_util.get_redis("%s_%s" % (key_name, _index)))
            if len(_data) != 0:
                self.result.append(_data)

    def check(self):
        """
        查询self.result中失败的线路总的失败次数，并将线路失败次数信息记录在self.final_result,大于阙值的记录在self.queue_list
        e.g.self.final_result = {'日本13': {'ip':'164.52.56.58','fail_num':2}}} fail_num的值2代表此线路有2次测试不通过
        e.g.self.queue_list = {'日本13': {'ip':'164.52.56.58',,'result':'Fail','is_alert': True}}}
            其中is_alert的值True代表已经将此线路下线，False代表还未将此路线下线并需要执行下线操作
        """
        self.collect_result()
        for _result in self.result:
            for region, data in _result.items():
                if self.final_result.get(region) is None:
                    self.final_result[region] = dict(data, **{"fail_num": 1})
                else:
                    self.final_result[region] = dict(
                        data,
                        **{
                            "fail_num": int(
                                self.final_result.get(region).get("fail_num")
                            )
                            + 1
                        }
                    )

        _logger.logger.info("final_result is %s" % self.final_result)

        for region, data in self.final_result.items():
            if int(data.get("fail_num")) > self.threshold:
                if self.queue_list.get(region) is None:
                    self.queue_list[region] = dict(data, **{"is_Alert": False})

        if len(self.queue_list) != 0:
            self.action()
        self.current_timer = datetime.datetime.now()
        _logger.logger.info("queue_list is %s" % self.queue_list)

    def run(self):
        differ_time = (self.current_timer - self.timer).total_seconds()
        _logger.logger.info("differ_time is %.2f" % (differ_time / 60))
        if differ_time / 60 <= config.getint("default", "period"):
            self.check()
        else:
            _logger.logger.info(
                "Check period time reaches out %s mins!" % (config["default"]["period"])
            )
            self.initialize_data()

    def action(self):
        """
        达到预警条件后，分析并处理queue_list
        对于没disable的线路，执行disable_vpn操作，并将此线路标记为True，代表已经将此线路下线；同时会短信报警通知此线路已经下线
        对于已经disable的线路，无需操作
        """
        self.fail_num = 0
        threshold_rate = config.getfloat("default", "overall_failure_rate")
        for region, data in self.queue_list.items():
            overall_failure_rate = (
                self.fail_num + self.get_total_backup_vpn()
            ) / self.cal_total_vpn_line()
            ip = data.get("ip")
            _result = data.get("result")
            if data.get("is_Alert") is False:
                if 0 <= overall_failure_rate <= threshold_rate:
                    _logger.logger.info(
                        "Current failure rate is %s" % overall_failure_rate
                    )
                    self.disable_vpn(region, ip, _result)
                    self.queue_list[region] = data.update(is_Alert=True)
                else:
                    msg = u"Region:%s IP:%s 无法自动下架，原因:总的失败率%.2f超出了阙值%s,请检查服务器." % (
                        region,
                        ip,
                        overall_failure_rate,
                        threshold_rate,
                    )
                    self.send_mail(msg)
                self.fail_num = self.fail_num + 1
            else:
                _logger.logger.info("%s:%s is already disabled." % (region, ip))

    def disable_vpn(self, region, ip, result):
        # mysql_utils(config["mysql"]["mysql_master_host"], _logger).update_server_status(
        #     region, 2
        # )
        if result.upper() == "FAIL":
            msg = server_internal_failure_msg % (
                region,
                ip,
                datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            )

        elif result.upper() == "TIMEOUT":
            msg = ssh_connection_failure_msg % (
                region,
                ip,
                datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            )
        else:
            msg = u"%s:%s 已经下架 原因:%s 时间:%s" % (
                region,
                ip,
                result,
                datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            )
        self.send_mail(msg)

    def send_mail(self, msg):
        _logger.logger.info(msg)
        sms_sender(msg).bulk_send_msg()


if __name__ == "__main__":
    runner = Runner()
    while True:
        _logger.logger.info("Start...")
        start_time = time.time()
        runner.run()
        end_time = time.time()
        time_used = end_time - start_time
        time.sleep(config.getint("default", "frequency"))
