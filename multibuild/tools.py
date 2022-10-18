# -*- coding: utf-8 -*-

import configparser
import getpass
import logging
import re
import subprocess
import urllib

import requests

DISTRIBUTION_TOOLS = {
    "RHEL": ("rhpkg", "brew"),
    "Fedora": ("fedpkg", "koji"),
}


BRANCH_PATTERNS = {
    r"^f\d\d$": "Fedora",  # f28 f29
    r"^epel\d$": "Fedora",  # epel7
    r"^epel\d-playground$": "Fedora",  # epel8-playground
    r"^el\d$": "Fedora",  # el6
    r"^master|main|rawhide": "Fedora",  # Fedora rawhide (rpkg, fedpkg)
    r"^eng-rhel-\d$": "RHEL",  # eng-rhel-7 (rpkg, rhpkg)
    r"^eng-fedora-\d\d$": "RHEL",  # eng-fedora-30 (rhpkg)
}

ANSIBLE_PLATFORM_MAPPING = {
    r"eng-rhel-(\d+)": r"rhel-\1",
    r"eng-fedora-(\d\d)": r"fedora-\1",
}

ANSIBLE_TEMPLATE_ID = 'rcm-tools-compose-ss++Compose'


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
    logger.warning("Distribution wasn't recognized from branch '{}'. "
                   "Using default: 'RHEL'".format(branch_name))
    return "RHEL"


def get_distribution_tool(distribution):
    dist_tool = DISTRIBUTION_TOOLS.get(distribution)
    if not dist_tool:
        raise Exception("Uknown distribution -> no tool detected")
    return dist_tool


def get_ansible_credentials(config):
    logger = logging.getLogger("get_ansible_credentials")
    url = None
    try:
        url = config.get("ansible", "url")
        logger.info("Using 'ansible url' from config: '%s'" % url)
    except (configparser.NoOptionError, configparser.NoSectionError):
        url = input(prompt="Ansible url (ansible host): ")
        if not url:
            logger.error("Ansible url wasn't entered.")

    username = None
    try:
        username = config.get("ansible", "username")
        logger.info("Using 'ansible username' from config: '%s'" % username)
    except (configparser.NoOptionError, configparser.NoSectionError):
        username = input(prompt="Ansible username: ")
        if not username:
            logger.error("Ansible username wasn't entered.")

    token = None
    try:
        token = config.get("ansible", "token")
        # don't show token openly
        logger.info("Using 'ansible token' from config: '%s'" % ("*" * len(token)))
    except (configparser.NoOptionError, configparser.NoSectionError):
        token = input(prompt="Ansible token: ")
        if not token:
            logger.error("Ansible token wasn't entered.")

    password = ""
    if not token:
        try:
            password = getpass.getpass()
        except Exception as e:
            logger.error("Ansible password error: %s" % e)
        if not password:
            logger.error("Ansible password wasn't entered.")

    return url, username, password, token


def get_ansible_platform(branch_name):
    for branch_pattern, platform_pattern in ANSIBLE_PLATFORM_MAPPING.items():
        res = re.match(branch_pattern, branch_name)
        if res:
            return re.sub(branch_pattern, platform_pattern, branch_name)
    return None


def run_ansible_job(baseurl, username, password, token, branch_name, verrel):
    """
    Execute regen repo job for given branch and nvr (verrel).
    Method returns job ID or None.
    """
    logger = logging.getLogger("run_ansible_job")

    platform = get_ansible_platform(branch_name)
    if not platform:
        logger.error("Unknown ansible plafrom: {}".format(platform))
        return

    url = urllib.parse.urljoin(baseurl, "/api/v2/job_templates/%s/launch/" % ANSIBLE_TEMPLATE_ID)
    json_request = {
        "extra_vars": {
            "platform": platform,
            "new_package_nvr": verrel,
            # "email_other": "",
        },
    }
    headers = {"Authorization": "Bearer {}".format(token)}

    try:
        response = requests.post(
            url,
            headers=headers,
            # verify=False,
            json=json_request)
    except Exception as e:
        logger.error("Error during processing ansible query: {}".format(e))
        raise
    if not response.ok:
        logger.error("Ansible response: {}".format(response))
        logger.debug("Response: {}".format(response.text))
        return

    try:
        result = response.json()
    except Exception as e:
        logger.error("Error during parsing json response: {}".format(e))
        raise

    job_id = result.get("id")
    if not job_id:
        logger.error("Job ID wasn't found / job didn't start.")
    return job_id


# NOTE: not really used yet
def get_ansible_job_status(baseurl, username, password, token, job_id):
    """
    Get status of the job in ansible with given ID.
    Method returns job's status or None
    """
    logger = logging.getLogger("get_ansible_job_status")
    url = urllib.parse.urljoin(baseurl, "/api/v2/jobs/%d/" % job_id)
    headers = {"Authorization": "Bearer {}".format(token)}
    try:
        response = requests.get(url, headers=headers)
    except Exception as e:
        logger.error("Error during processing ansible query: {}".format(e))
        raise
    if not response.ok:
        logger.error("Ansible response: {}".format(response))
        logger.debug("Response: {}".format(response.text))
        return

    try:
        result = response.json()
    except Exception as e:
        logger.error("Error during parsing json response: {}".format(e))
        raise
    status = result.get("status")
    if not status:
        logger.error("Job status wasn't found.")
    return status
