

from __future__ import absolute_import

from mesadb.config import DBinclude
from mesadb.config import DBname
from mesadb.network import SSH
from mesadb.network.adapters import adapter
from mesadb.tools import DBfunctions

import traceback
import sys

class Status(object):
    def __init__(self):
        self._options = None

    def setOptions(self, options):
        self._options = options

    def printEnter(self):
        pass

    def printSuccess(self):
        pass

    def printFailureCommon(self):
        # TODO: color
        print "Installation FAILED with errors."
        print ""

    def printFailure(self):
        self.printFailureCommon()
        # 默认情况下, 发现严重的错误信息
        print "****"
        print "AdminTools and your existing MesaDB databases may be unavailable."
        print "Investigate the above warnings/errors and re-run installation."
        print "****"

    def printError(self, err):
        DBfunctions.record("Error: "+str(err))

        if isinstance(err, KeyboardInterrupt):
            print "Error: Installation canceled by user."
        else:
            print "Error: "+str(err)
            if not isinstance(err, adapter.SSHException):
                traceback.print_exc(file=sys.stdout)

        self.printFailure()

class StatusNew(Status):
    def printEnter(self):
        print "MesaDB Analytic Database %s Installation Tool\n" % (DBname.PRODUCT_VERSION)

    def printFailure(self):
        self.printFailureCommon()
        print "Installation stopped before any changes were made."

class StatusOptionValidation(StatusNew):
    def printEnter(self):
        print "\n>> Validating options...\n"

class StatusClusterCheck(StatusNew):
    def printEnter(self):
        print "\n>> Starting installation tasks."
        print ">> Getting system information for cluster (this may take a while)...\n"

class StatusValidateSoftware(StatusNew):
    def printEnter(self):
        print "\n>> Validating software versions (rpm or deb)...\n"

class StatusClusterChange(Status):
    def printEnter(self):
        print "\n>> Beginning new cluster creation...\n"

class StatusInstallSoftware(Status):
    def printEnter(self):
        print "\n>> Installing software (rpm or deb)...\n"

class StatusDbAdmin(Status):
    def printEnter(self):
        print "\n>> Creating or validating DB Admin user/group...\n"

class StatusValidation(Status):
    def printEnter(self):
        print "\n>> Validating node and cluster prerequisites...\n"

class StatusSshKeys(Status):
    def printEnter(self):
        print "\n>> Establishing DB Admin SSH connectivity...\n"

class StatusHostSetup(Status):
    def printEnter(self):
        print "\n>> Setting up each node and modifying cluster...\n"

class StatusClusterSync(Status):
    def printEnter(self):
        print "\n>> Sending new cluster configuration to all nodes...\n"

class StatusFinal(Status):
    def printEnter(self):
        print "\n>> Completing installation...\n"

    def printSuccess(self):
        """Prints a useful message at the completion of an install task."""

        # TODO: color on Installation complete.
        print """\
Installation complete.

Please evaluate your hardware using MesaDB's validation tools:
    %(url)s

To create a database:
  1. Logout and login as %(dba)s. (see note below)
  2. Run %(bin)s/adminTools as %(dba)s
  3. Select Create Database from the Configuration Menu

  Note: Installation may have made configuration changes to %(dba)s
  that do not take effect until the next session (logout and login).

To add or remove hosts, select Cluster Management from the Advanced Menu.""" % {
        'url' : DBinclude.help_url('VALSCRIPT'),
        'dba' : self._options.mesadb_dba_user,
        'bin' : DBinclude.binDir }
