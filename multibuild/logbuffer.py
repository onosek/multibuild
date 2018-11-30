# -*- coding: utf-8 -*-


class LogBuffer(object):
    """
    stores error and standard output messages in groups per thread name
    """
    def __init__(self):
        self.error_buff = {}
        self.output_buff = {}

    def append_error(self, name, msg):
        self.error_buff.setdefault(name, []).append(msg)

    def get_errors(self, name):
        return self.error_buff.get(name, [])

    def append_output(self, name, msg):
        self.output_buff.setdefault(name, []).append(msg)

    def get_output(self, name):
        return self.output_buff.get(name, [])
