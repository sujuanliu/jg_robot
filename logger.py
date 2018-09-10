import os
import logging


class logger(object):
    def __init__(self, log_file="out.log"):
        self.base_path = lambda path: os.path.abspath(
            os.path.join(os.path.dirname(__file__), path)
        )
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(level=logging.INFO)
        self.handler = logging.FileHandler(self.base_path(log_file))
        self.handler.setLevel(logging.INFO)
        self.formatter = logging.Formatter(
            "%(asctime)s-%(filename)s[line:%(lineno)d]-%(levelname)s:%(message)s"
        )
        self.handler.setFormatter(self.formatter)
        self.logger.addHandler(self.handler)
