# -*- coding: utf-8 -*-

import logging
import re
import subprocess


DISTRIBUTION_TOOLS = {
    "RHEL": ("rhpkg", "brew"),
    "Fedora": ("fedpkg", "koji"),
}


BRANCH_PATTERNS = {
    r"^f\d\d$": "Fedora",  # f28 f29
    r"^epel\d$": "Fedora",  # epel7
    r"^el\d$": "Fedora",  # el6 el7
    r"master": "Fedora",  # Fedora rawhide (rpkg, fedpkg)
    r"^eng-rhel-\d$": "RHEL",  # eng-rhel-7 (rpkg, rhpkg)
    r"^eng-fedora-\d\d$": "RHEL",  # eng-fedora-30 (rhpkg)
}


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
    return (out.strip(), err.strip(), proc.returncode)


def detect_distribution(branches):
    """
    Detect disribution from set of branches.
    Accepts string (containing only one branch name) or list containing strings.
    """
    if type(branches) in (tuple, list):
        # make set of distributions from all branch names
        distros = {_recognize_distribution(branch_name) for branch_name in branches}
        if len(distros) == 1:
            return distros.pop()  # return the only item from set
        else:
            raise Exception("There are mixed branch names: {}".format(str(branches)))
    else:
        branch_name = branches
        return _recognize_distribution(branch_name)


def _recognize_distribution(branch_name):
    """
    Detect disribution from branch name.
    Internal method. Use "detect_distribution" instead.
    """
    if not branch_name:
        raise Exception("Empty branch name")
    if type(branch_name) != str:
        raise Exception("Branch name is not string")

    for pattern, arch in BRANCH_PATTERNS.items():
        if re.match(pattern, branch_name):
            return arch

    logger = logging.getLogger("recognize_distribution")
    logger.warning("Distribution wasn't recognized from branch '{}'. Using default: 'RHEL'".format(branch_name))
    return "RHEL"


def get_distribution_tool(distribution):
    dist_tool = DISTRIBUTION_TOOLS.get(distribution)
    if not dist_tool:
        raise Exception("Uknown distribution -> no tool detected")
    return dist_tool
