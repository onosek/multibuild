# -*- coding: utf-8 -*-

import logging
import subprocess


def execute_command(name, command="", pipe=None):
    logger = logging.getLogger("execute_command")
    # compose command string for logging purpose
    if pipe:
        command_str = "{} | {}".format(command, pipe)
    else:
        command_str = command
    logger.info("'{}'".format(command_str))

    if pipe:
        parent_proc = subprocess.Popen(
            command,
            shell=True,
            cwd=None,
            stdin=None,
            universal_newlines=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        proc = subprocess.Popen(
            pipe,
            shell=True,
            cwd=None,
            stdin=parent_proc.stdout,
            universal_newlines=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        parent_proc.stdout.close()
    else:
        proc = subprocess.Popen(
            command,
            shell=True,
            cwd=None,
            stdin=None,
            universal_newlines=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
    out, err = proc.communicate()
    if proc.returncode != 0:
        logger.error("During execution: '{}' in thread '{}'".format(command_str, name))
    return (out, err, proc.returncode)
