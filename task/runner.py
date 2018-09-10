import sys

sys.path.append("..")

import time, datetime
import threading
import paramiko, socket
from logger import logger
from common import get_path, config, redis_utils

_logger = logger(get_path("logs//runner_%s.log" % config["default"]["robot_order"]))


class Task:
    def __init__(self):
        self.ssh_pass = config["vpn_server"]["ssh_pwd"]
        self.ssh_user = config["vpn_server"]["ssh_user"]
        self.ssh_port = config["vpn_server"]["ssh_port"]
        self.redis_util = redis_utils()
        self.result = {}

    def check(self, region, ip, status):
        try:
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(
                ip,
                self.ssh_port,
                self.ssh_user,
                self.ssh_pass,
                timeout=10,
                look_for_keys=False,
            )
            stdin, stdout, stderr = ssh.exec_command(
                "if [ `strongswan leases|grep online |grep -v Leases|awk '{print $3}'|sort -u |wc -l` -ne '0' ] && "
                "[ `curl -I -o /dev/null -s -m 5 -w %{http_code} https://www.youtube.com` -eq '200' ];then echo 'Pass'; else echo 'Fail'; fi"
            )
            rst = str(stdout.read().decode("utf-8").replace("\n", ""))
            if rst != "Pass":
               self.result[region] = {"ip":ip, "result":rst}
            ssh.close()
        except (
            paramiko.ssh_exception.SSHException,
            socket.error,
            socket.timeout,
            EOFError,
        ):
            self.result[region] = {"ip":ip, "result":"Timeout"}
            _logger.logger.exception(
                "paramiko ssh exception: %s %s %s" % (region, ip, status)
            )

    def do(self):
        while True:
            # print(
            #     "%s Start..." % (datetime.datetime.now().strftime("%b-%d-%Y %H:%M:%S"))
            # )
            _logger.logger.info("Start...")
            self.result = {}
            start_time = time.time()
            server_info = eval(
                self.redis_util.get_redis(
                    "%s_%s"
                    % (
                        config["redis"]["prefix_vpn_key"],
                        config["default"]["robot_order"],
                    )
                )
            )
            threads = []
            for server in server_info:
                region, ip, status = server
                thread = threading.Thread(target=self.check, args=(region, ip, status))
                threads.append(thread)
                thread.start()

            for thread in threads:
                thread.join()
            _logger.logger.info(self.result)
            self.redis_util.set_redis_key(
                "%s_%s"
                % (
                    config["redis"]["prefix_result_key"],
                    config["default"]["robot_order"],
                ),
                self.result,
            )
            end_time = time.time()
            time_used = end_time - start_time
            # print("Total_time:%s 秒" % time_used)
            _logger.logger.info("End: Total_time:%s 秒" % time_used)
            # print("%s End!\n" % (datetime.datetime.now().strftime("%b-%d-%Y %H:%M:%S")))
            # if time_used < 10.0:
            #     time.sleep(10.0 - time_used)
            # else:
            time.sleep(10)


if __name__ == "__main__":
    _logger.logger.info("Staring robot %s......" % config["default"]["robot_order"])
    task = Task()
    task.do()
