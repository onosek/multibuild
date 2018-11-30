# -*- coding: utf-8 -*-

import logging


class ColorFormatter(logging.Formatter):
    DIM = '\033[2m'
    RESET = '\033[0m'
    LIGHT_GREEN = '\033[92m'
    LIGHT_YELLOW = '\033[93m'
    LIGHT_RED = '\033[91m'

    def format(self, record):
        super().format(record)
        color = {
            logging.INFO: self.LIGHT_GREEN,
            logging.WARNING: self.LIGHT_YELLOW,
            logging.ERROR: self.LIGHT_RED,
        }.get(record.levelno, '')
        return '%s%s%s' % (color, record.message, self.RESET)
