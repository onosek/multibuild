# -*- coding: utf-8 -*-

import configparser
import logging
import threading

from .kojiwrapper import Kojiwrapper
from .tools import (detect_distribution, execute_command,
                    get_distribution_tool, run_ansible_job)

BUILD_INFO_URL_TEMPLATE = "https://brewweb.engineering.redhat.com/brew/buildinfo?buildID=%d"


class BuildThread(threading.Thread):
    def __init__(self, config, log_buff, thread_id, name, command=None, mode=None):
        threading.Thread.__init__(self)
        self.config = config
        self.thread_id = thread_id
        self.name = name
        self.command = command
        self.mode = mode
        self.log_buff = log_buff

        self.distribution = detect_distribution(self.name)
        self.distribution_tool, self.server_tool = get_distribution_tool(self.distribution)

    def run(self):
        logger = logging.getLogger("run")
        logger.info("Starting thread '{}'".format(self.name))
        if self.mode == "tag":
            self.run_tag()
        elif self.mode == "summary":
            self.run_summary()
        elif self.mode == "wait-repo":
            self.wait_repo()
        elif self.mode == "regen-rcm-repo":
            self.regen_rcm_repo()
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
        load nvr from config data (depends on project) or by rhpkg/fedpkg command
        """
        nvr_format = None
        try:
            nvr_format = self.config.get("nvr", "format")
            # TODO: process data from config
        except (configparser.NoOptionError, configparser.NoSectionError):
            pass

        if not nvr_format:
            # get local nvr by executing "rhpkg/fedpkg verrel"
            out, err, __ = execute_command(self.name, ["{} verrel".format(self.distribution_tool)])
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
            koji = Kojiwrapper(self.server_tool)
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
                out, err, ret = execute_command(self.name, [command])
                self.log_buff.append_output(self.name, out)
                self.log_buff.append_error(self.name, err)
                if not ret:
                    waitrepo_cmd = "brew wait-repo {branch}-build --build={nvr}"
                    waitrepo_cmd = waitrepo_cmd.format(branch=self.name, nvr=verrel)
                    message = "\nYou can wait for repo regeneration by executing command:\n  {}"
                    message = message.format(waitrepo_cmd)
                    self.log_buff.append_output(self.name, message)
            else:
                message = "koji nvr '{}' do not match with {} verrel '{}'"
                message = message.format(koji_result.get("nvr", ""), self.distribution_tool, verrel)
                logger.error(message)

    @checkout
    def run_summary(self):
        """
        """
        logger = logging.getLogger("run_summary")

        verrel = self.local_nvr()
        if verrel:
            # find out whether proper build in koji is prepared already
            koji = Kojiwrapper(self.server_tool)
            koji_result = None
            try:
                koji_result = koji.get_build(verrel)
            except Exception as e:
                logger.error("get_build: {}".format(e))

            # find out 'build_id' in koji results
            if koji_result and koji_result.get("build_id"):
                try:
                    build_info_url_template = self.config.get(self.server_tool,
                                                              "build_info_url_template")
                except (configparser.NoOptionError, configparser.NoSectionError):
                    logger.warning("config lacks 'build_info_url_template' value. Using default")
                    build_info_url_template = BUILD_INFO_URL_TEMPLATE
                if build_info_url_template:
                    # compose build_info_url from url template and build_id
                    build_info_url = build_info_url_template % koji_result.get("build_id")
                    stream = "[{verrel}|{url}]".format(verrel=verrel, url=build_info_url)
                    # common output for all threads
                    self.log_buff.append_output("_summary", stream)
                    self.log_buff.append_output("_builds", verrel)
                    self.log_buff.append_output("_tags", self.name)
            else:
                logger.error("build_id wasn't found for '{}'".format(verrel))

    @checkout
    def wait_repo(self):
        """
        Wait for regeneration of the repository with latest build
        Warning: method is not checking whether build is already tagged
        """
        logger = logging.getLogger("wait-repo")

        verrel = self.local_nvr()
        if verrel:
            command = "{server_tool} wait-repo --build={verrel} {name}-build"
            command = command.format(server_tool=self.server_tool, verrel=verrel, name=self.name)
            logger.debug("'{}'".format(command))
            logger.warning("Method is not checking whether build is already tagged")  # FIXME
            out, err, __ = execute_command(self.name, command)
            self.log_buff.append_output(self.name, out)
            self.log_buff.append_error(self.name, err)

    @checkout
    def regen_rcm_repo(self):
        """
        more about Ansible authentiacation:
        https://www.ansible.com/blog/summary-of-authentication-methods-in-red-hat-ansible-tower
        """
        logger = logging.getLogger("regen-rcm-repo")

        # read credentials from config.
        # Parent method updated this config if the information wasn't there yet.
        baseurl = self.config.get("ansible", "url")
        username = self.config.get("ansible", "username")
        password = self.config.get("ansible", "password")
        token = self.config.get("ansible", "token")

        verrel = self.local_nvr()
        logger.debug("'{}'".format(verrel))
        job_id = run_ansible_job(baseurl, username, password, token, self.name, verrel)
        if job_id:
            self.log_buff.append_output(self.name,
                                        "job url: {}/#/jobs/playbook/{}".format(baseurl, job_id))

        out = ""
        err = ""
        self.log_buff.append_output(self.name, out)
        self.log_buff.append_error(self.name, err)
