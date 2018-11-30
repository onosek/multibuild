# -*- coding: utf-8 -*-

import configparser
import logging
import threading

from . kojiwrapper import Kojiwrapper
from . tools import execute_command

BUILD_ID_URL_TEMPLATE = "https://brewweb.engineering.redhat.com/brew/buildinfo?buildID=%d"


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
                out, err, ret = execute_command(self.name, [command])
                self.log_buff.append_output(self.name, out)
                self.log_buff.append_error(self.name, err)
                if not ret:
                    waitrepo_cmd = "brew wait-repo {}-build --build={}".format(self.name, verrel)
                    message = "\nYou can wait for repo regeneration by executing command:\n  {}".format(waitrepo_cmd)
                    self.log_buff.append_output(self.name, message)
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