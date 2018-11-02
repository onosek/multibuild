#!/usr/bin/env python
# -*- coding: utf-8 -*-

# TODO: import argcomplete
import argparse
import configparser
import logging
import os
import subprocess
import sys
import threading
import time
from textwrap import dedent

import koji

CONFIG_FILE = "/etc/multibuild/multibuild.conf"
BUILD_ID_URL_TEMPLATE = "https://brewweb.engineering.redhat.com/brew/buildinfo?buildID=%d"
DIM = '\033[2m'
RESET = '\033[0m'

# ===============================
# improvements to be implemented
# -------------------------------
# in log messages include thread name
# read custom verrel format for specific projects
# add command "download" packages from brew (no src packages)
# ...


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


class Kojiwrapper(object):
    def __init__(self, kojiprofile="brew"):
        """Init the object and some configuration details."""

        self.kojiprofile = kojiprofile
        self.anon_kojisession = None

    def load_anon_kojisession(self):
        """Initiate a koji session."""
        logger = logging.getLogger("load_anon_kojisession")
        koji_config = koji.read_config(self.kojiprofile)

        logger.debug('Initiating a brew session to %s',
                     os.path.basename(koji_config['server']))

        # Build session options used to create instance of ClientSession
        session_opts = koji.grab_session_options(koji_config)

        try:
            session = koji.ClientSession(koji_config['server'], session_opts)
        except Exception:
            raise Exception('Could not initiate brew session')
        else:
            return session

    def get_build(self, build):
        """Determine the git hash used to produce a particular N-V-R"""
        logger = logging.getLogger("get_build")

        if not self.anon_kojisession:
            self.anon_kojisession = self.load_anon_kojisession()

        # Get the build data from the nvr
        logger.debug('Getting task data from the build system')
        bdata = self.anon_kojisession.getBuild(build)
        if not bdata:
            raise Exception('Unknown build: %s' % build)

        return bdata


class BuildThread(threading.Thread):
    def __init__(self, config, log_buff, thread_id, name, command=None, mode=None):
        threading.Thread.__init__(self)
        self.config = config
        self.thread_id = thread_id
        self.name = name
        self.command = command
        self.mode = mode
        self.log_buff = log_buff

    def run(self):
        logger = logging.getLogger("run")
        logger.info("Starting thread '{}'".format(self.name))
        if self.mode == "tag":
            self.run_tag()
        elif self.mode == "summary":
            self.run_summary()
        else:
            self.run_standard()
        logger.info("Exiting thread '{}'".format(self.name))

    def checkout(func):
        """
        decorator function - it executes "git checkout <branch>"
        and if sucessfull, it continues in decorated function
        """
        def run_checkout(self):
            out, err, ret = execute_command(self.name, ["git checkout {}".format(self.name)])
            self.log_buff.append_output(self.name, out)
            self.log_buff.append_error(self.name, err)
            if ret == 0:
                func(self)
        return run_checkout

    def local_nvr(self):
        """
        load nvr from config data (depends on project) or by rhpkg command
        """
        nvr_format = None
        try:
            nvr_format = self.config.get("nvr", "format")
            # TODO: process data from config
        except (configparser.NoOptionError, configparser.NoSectionError) as e:
            pass

        if not nvr_format:
            # get local nvr by executing "rhpkg verrel"
            out, err, __ = execute_command(self.name, ["rhpkg verrel"])
            self.log_buff.append_output(self.name, out)
            self.log_buff.append_error(self.name, err)
            if out:
                return out.strip()
        return None

    @checkout
    def run_standard(self):
        """
        Suitable for most schemas - build, scratch-build, custom command, ...
        Fist checkout into target dist-git branch then execute command
        """
        logger = logging.getLogger("run_standard")
        logger.debug("'{}'".format(self.command))
        out, err, __ = execute_command(self.name, self.command)
        self.log_buff.append_output(self.name, out)
        self.log_buff.append_error(self.name, err)

    @checkout
    def run_tag(self):
        """
        """
        logger = logging.getLogger("run_tag")

        verrel = self.local_nvr()
        if verrel:
            # find out whether proper build in koji is prepared already
            koji = Kojiwrapper()
            koji_result = None
            try:
                koji_result = koji.get_build(verrel)
            except Exception as e:
                logger.error("get_build: {}".format(e))

            # local build matches koji build
            if koji_result and koji_result.get("nvr", "") == verrel:
                # tag the build
                command = "brew tag-build {} {}".format(self.name, verrel)
                logger.debug("'{}'".format(self.command))
                out, err, __ = execute_command(self.name, [command])
                self.log_buff.append_output(self.name, out)
                self.log_buff.append_error(self.name, err)
            else:
                logger.error("koji nvr '{}' do not match with rhpkg verrel '{}'".format(koji_result.get("nvr", ""), verrel))

    @checkout
    def run_summary(self):
        """
        """
        logger = logging.getLogger("run_summary")

        verrel = self.local_nvr()
        if verrel:
            # find out whether proper build in koji is prepared already
            koji = Kojiwrapper()
            koji_result = None
            try:
                koji_result = koji.get_build(verrel)
            except Exception as e:
                logger.error("get_build: {}".format(e))

            # find out 'build_id' in koji results
            if koji_result and koji_result.get("build_id"):
                try:
                    build_id_url_template = self.config.get("general", "build_id_url_template")
                except (configparser.NoOptionError, configparser.NoSectionError) as e:
                    logger.warning("config lacks 'build_id_url_template' value")
                    build_id_url_template = BUILD_ID_URL_TEMPLATE
                if build_id_url_template:
                    # compose build_id_url from url template and build_id
                    build_id_url = build_id_url_template % koji_result.get("build_id")
                    stream = "[{verrel}|{url}]".format(verrel=verrel, url=build_id_url)
                    # common output for all threads
                    self.log_buff.append_output("_summary", stream)
                    self.log_buff.append_output("_builds", verrel)
                    self.log_buff.append_output("_tags", self.name)
            else:
                logger.error("build_id wasn't found for '{}'".format(verrel))


def execute_command(name, command=""):
    logger = logging.getLogger("execute_command")
    logger.info("'{}'".format(command))
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
        logger.error("During execution: '{}' in thread '{}'".format(command, name))
    return (out, err, proc.returncode)


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
        except (configparser.NoOptionError, configparser.NoSectionError) as e:
            pass
    if not branches:
        logger.warning("There are neither branches arguments nor branches in config")

    return branches


class ColorFormatter(logging.Formatter):

    def format(self, record):
        super().format(record)
        color = {
            logging.INFO: '\033[92m',
            logging.WARNING: '\033[93m',
            logging.ERROR: '\033[91m',
        }.get(record.levelno, '')
        return '%s%s%s' % (color, record.message, RESET)


def main():
    logging.basicConfig(stream=sys.stdout, level=logging.INFO)
    logger = logging.getLogger("main")

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

    # TODO: argcomplete.autocomplete(parser)
    args = parser.parse_args()

    config = configparser.ConfigParser()
    config_file = args.config_file if args.config_file else CONFIG_FILE
    if os.path.isfile(config_file):
        logger.debug("Will use a config file: {}".format(config_file))
        files = config.read(config_file)
        if not files:
            logger.warning("Config file '%s' is missing." % config_file)

    log_buff = LogBuffer()

    branches = get_branches(args, config, logger)
    threads = []
    for i, branch in enumerate(branches):
        # create new thread
        if args.do_build:
            command = ["rhpkg build"]
            thread = BuildThread(config, log_buff, i, branch, command=command)
        elif args.do_scratch_build:
            command = ["rhpkg scratch-build --srpm"]
            thread = BuildThread(config, log_buff, i, branch, command=command)
        elif args.execute_custom:
            command = [args.execute_custom]
            thread = BuildThread(config, log_buff, i, branch, command=command)
        elif args.do_tag:
            thread = BuildThread(config, log_buff, i, branch, mode="tag")
        elif args.do_summary or args.do_jira:
            thread = BuildThread(config, log_buff, i, branch, mode="summary")

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
        print(DIM, end='', flush=True)
        print("err: " + ''.join(log_buff.get_errors(name)))
        print("out: " + ''.join(log_buff.get_output(name)))
        print(RESET, end='', flush=True)
    if log_buff.get_output("_summary"):
        summary = '\n'.join(log_buff.get_output("_summary"))
        if args.do_jira:
            builds = '\n'.join(["* {}".format(build) for build in log_buff.get_output("_builds")])
            tags = ', '.join(log_buff.get_output("_tags"))
            print("JIRA template:")
            jira_template = (dedent("""
                             Project: RCM
                             Component: RCM Tools.
                             Title: Rerun compose with new RHEL and Fedora packages
                             The ticket description:
                             Please include these packages in the compose:

                             {builds}

                             Links:
                             {summary}

                             The packages are already tagged in respective *{tags}* tags.
            """))
            print(jira_template.format(builds=builds, summary=summary, tags=tags))
        else:
            print("Available builds summary:")
            print(summary)

    return


if __name__ == "__main__":
    sys.exit(main())
