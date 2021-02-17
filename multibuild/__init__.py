#!/usr/bin/env python
# -*- coding: utf-8 -*-

# TODO: import argcomplete
import argparse
import configparser
import logging
import os
import site
import sys
import time
from textwrap import dedent

from . build_thread import BuildThread
from . color_formatter import ColorFormatter
from . logbuffer import LogBuffer
from .tools import (detect_distribution, execute_command,
                    get_distribution_tool, get_tower_credentials)

# TODO: find reliable way how to install config to ~/.config/ instead of ~/.local/
DEFAULT_CONFIG_PATH = "{}/multibuild".format(site.USER_BASE)
CONFIG_FILE_NAME = "multibuild.conf"

# ===============================
# improvements to be implemented
# -------------------------------
# in log messages include thread name
# read custom verrel format for specific projects
# add command "download" packages from brew (no src packages)
# verify whether builds are tagged when printing the RCM ticket template
# verify whether builds are tagged before regen RCM repo
# remove configparser dependency in build_thread.py
# in setup.py add dependency on setuptools_scm to rely on version from scm
# and include just files that are tracked.
# ...


def get_branches(args, config, logger):
    """
    use branches from command-line arguments or load them from config
    """
    branches = []
    if args.branches:
        return args.branches
    else:
        try:
            raw_branches = config.get("branches", "active_branches")
            branches = tuple(branch.strip() for branch in raw_branches.split(","))
            if branches:
                logger.info("Using branches from a config file")
        except (configparser.NoOptionError, configparser.NoSectionError):
            pass
    if not branches:
        logger.error("There are neither branches arguments nor branches in config")

    return branches


def prepare_parser():
    parser = argparse.ArgumentParser(description='Apply specific action for each dist-git branch in list')
    parser.add_argument('branches', metavar='BRANCH', type=str, nargs='*',
                        help='list of dist-git branches')
    parser.add_argument('-c', '--config', dest='config_file', metavar="CONFIG_FILE", action='store',
                        help='specifies config file (INI format)')
    command_group = parser.add_mutually_exclusive_group(required=True)
    command_group.add_argument('-p', '--print-summary', dest='do_summary', action='store_true',
                               help='prints the summary')
    command_group.add_argument('-j', '--print-jira', dest='do_jira', action='store_true',
                               help='prints the JIRA template')
    command_group.add_argument('-b', '--build', dest='do_build', action='store_true',
                               help='builds from branches')
    command_group.add_argument('-s', '--scratch-build', dest='do_scratch_build', action='store_true',
                               help='does scratch builds')
    command_group.add_argument('-t', '--tag', dest='do_tag', action='store_true',
                               help='tags builds')
    command_group.add_argument('-e', '--execute', dest='execute_custom', metavar="COMMAND", action='store',
                               help='executes custom command')
    command_group.add_argument('-l', '--gather-logs', dest='task_id', metavar="TASK_ID", action='store',
                               help='gather build logs and store them locally', type=int)
    command_group.add_argument('-w', '--wait-repo', dest='wait_repo', action='store_true',
                               help='will wait for repo regeneration')
    command_group.add_argument('-r', '--regen-rcm-repo', dest='regen_rcm_repo', action='store_true',
                               help='executes rcm repo regeneration')
    return parser


def execute_thread_approach(args, config, logger, log_buff):
    branches = get_branches(args, config, logger)
    if not branches:
        return

    # update config with tower creadentials.
    if args.regen_rcm_repo:
        tower_url, tower_username, tower_password = get_tower_credentials(config)
        if not (tower_url and tower_username and tower_password):
            return
        config.set("tower", "url", tower_url)
        config.set("tower", "username", tower_username)
        config.set("tower", "password", tower_password)

    threads = []
    distribution = detect_distribution(branches)  # TODO: duplicate functionality?
    distribution_tool, server_tool = get_distribution_tool(distribution)
    for i, branch in enumerate(branches):
        # create new thread
        if args.do_build:
            command = ["{} build".format(distribution_tool)]
            thread = BuildThread(config, log_buff, i, branch, command=command)
        elif args.do_scratch_build:
            command = ["{} scratch-build --srpm".format(distribution_tool)]
            thread = BuildThread(config, log_buff, i, branch, command=command)
        elif args.execute_custom:
            command = [args.execute_custom]
            thread = BuildThread(config, log_buff, i, branch, command=command)
        elif args.do_tag:
            thread = BuildThread(config, log_buff, i, branch, mode="tag")
        elif args.do_summary or args.do_jira:
            thread = BuildThread(config, log_buff, i, branch, mode="summary")
        elif args.wait_repo:
            thread = BuildThread(config, log_buff, i, branch, mode="wait-repo")
        elif args.regen_rcm_repo:
            thread = BuildThread(config, log_buff, i, branch, mode="regen-rcm-repo")

        threads.append(thread)

        # start new thread
        thread.start()
        # delay for safe checkout
        # TODO: it is also workaround for `verrel`. It needs some time to get correct result after switching branch
        time.sleep(3)

    # wait for all threads to complete
    time.sleep(1)
    logging.info("waiting ... threads are working")
    for thread in threads:
        thread.join()
    logging.info("threads finished")

    for name in branches:
        print("========== %s ==========" % name)
        print(ColorFormatter.DIM, end='', flush=True)
        print("err: " + ''.join(log_buff.get_errors(name)))
        print("out: " + ''.join(log_buff.get_output(name)))
        print(ColorFormatter.RESET, end='', flush=True)
    if log_buff.get_output("_summary"):
        summary = '\n'.join(log_buff.get_output("_summary"))
        if args.do_jira:
            builds = '\n'.join(["* {}".format(build) for build in log_buff.get_output("_builds")])
            tags = ', '.join(log_buff.get_output("_tags"))
            print("JIRA template:")
            jira_template = (dedent("""
                             Project: RCM
                             Component: RCM Tools
                             Issue Type: Task
                             Title: Rerun compose with new RHEL and Fedora packages
                             The ticket description:
                             Please include these packages into the compose:

                             {builds}

                             Links:
                             {summary}

                             The packages are already tagged in respective *{tags}* tags.
            """))
            print(jira_template.format(builds=builds, summary=summary, tags=tags))
        else:
            print("Available builds summary:")
            print(summary)


def execute_simple_approach(args, config, logger, log_buff):
    # so far there is only one functionality - gathering logs
    out, __, __ = execute_command(
        "get_subtask",
        ["brew call --json getTaskChildren {}".format(args.task_id)],
        ["jq '.[] | select(.method==\"buildArch\") | .id'"]
    )
    task_id = out.strip() or args.task_id
    try:
        int(task_id)
    except ValueError:
        logger.error("Task_id is not valid: {}".format(task_id))
        return
    out, err, ret = execute_command("gather_logs", "brew download-logs {}".format(task_id))
    if ret:
        logger.error("During gathering or saving logs")
    else:
        logger.info("Logs were gathered and saved:")
    if err:
        logger.error(err)
    print("===", out, "===")


def main():
    logging.basicConfig(stream=sys.stdout, level=logging.INFO)
    logger = logging.getLogger("main")

    parser = prepare_parser()
    # TODO: argcomplete.autocomplete(parser)
    args = parser.parse_args()

    config = configparser.ConfigParser()
    config_file = args.config_file or os.path.join(DEFAULT_CONFIG_PATH, CONFIG_FILE_NAME)
    config_file = os.path.expanduser(config_file)
    if os.path.isfile(config_file):
        logger.debug("Will use a config file: {}".format(config_file))
        files = config.read(config_file)
        if not files:
            logger.warning("Config file '%s' is missing." % config_file)

    # more specific config file in the repo directory; mostly for configuration of active branches
    config_file2 = os.path.join(os.getcwd(), CONFIG_FILE_NAME)
    if os.path.isfile(config_file2):
        logger.debug("Will use a extra config file: {}".format(config_file2))
        files = config.read(config_file2)
        if not files:
            logger.warning("Config file '%s' is missing." % config_file2)

    log_buff = LogBuffer()

    if args.task_id:
        execute_simple_approach(args, config, logger, log_buff)
    else:
        execute_thread_approach(args, config, logger, log_buff)

    return


if __name__ == "__main__":
    sys.exit(main())
