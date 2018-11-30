# -*- coding: utf-8 -*-

import logging
import os

import koji


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
