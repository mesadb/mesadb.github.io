from __future__ import absolute_import
from __future__ import print_function

import os, sys, argparse, textwrap, imp
import mesadb.install
import mesadb.platform.check.severity as severity
import mesadb.config.DBinclude as DBinclude

def _parse_options():
    program = os.environ.get('_VERT_PROGRAM_NAME', 'install_mesadb')

    parser = argparse.ArgumentParser(
            prog=program,
            formatter_class = argparse.RawDescriptionHelpFormatter,
            usage="""
  # 执行安装或更新 RPM 包:
  %(prog)s --hosts host1,host2,host3 --rpm mesadb.rpm
  %(prog)s --hosts 192.168.1.101,192.168.1.101,192.168.1.102 \\
          --rpm mesadb.rpm

  # 添加或移除节点
  %(prog)s --add-hosts host4 --rpm mesadb.rpm
  %(prog)s --remove-hosts host4

  # 获取帮助信息
  %(prog)s --help""")

    # Note: 对于 boolean 选项, 在缺省的None下 进行 process_config_file 计数
    # 因此,不使用 store_true 或 store_false.

    # install_mesadb --hosts host1,host2,host3
    # install_mesadb --hosts 192.168.1.101,192.168.1.101,192.168.1.102

    parser.add_argument('--hosts', '-s', metavar='HOST,HOST...',
            help='A comma-separated list of hosts to install or update')
    parser.add_argument('--rpm', '-r', '--deb', metavar='FILE',
            dest="rpm_file_name",
            help='The software package to install. Either an RPM or Debian package.')
    parser.add_argument('--clean',
            action='store_const', const=True, default=None,
            help="""
            Forcibly remove all pre-existing cluster configuration, including
            database listings.  (unsafe!)""")

    group = parser.add_argument_group(
            title="Modifying an existing cluster",
            description=textwrap.dedent("""\
    These options allow you to add or remove nodes within an existing cluster.
    New nodes will not participate in any existing databases.  See online
    documentation for more information.
            """))
    group.add_argument('--add-hosts', '-A', metavar='HOST,HOST...',
            help="A comma-separated list of hosts to add to the cluster")
    group.add_argument('--remove-hosts', '-R', metavar='HOST,HOST...',
            help="A comma-separated list of hosts to remove from the cluster")

    group = parser.add_argument_group(
            title="System users",
            description=textwrap.dedent("""\
    Vertica runs as the database admin user, a system user account.  This is
    also the user which may run Administration Tools (adminTools). These options
    specify the system user and system group used for this purpose.  The user
    and group will be created, if they do not exist.
            """))
    group.add_argument('--dba-user', '-u', metavar='USER',
            dest='mesadb_dba_user',
            help="The DBA system user name. (default: dbadmin)",
            # 在这不使用 vconst.
            default='dbadmin')
    group.add_argument('--dba-user-home', '-l', metavar='DIR',
            help="The DBA system user home.  (default: /home/<dba>)",
            # 在 install下post_process_options中的缺省配置
            dest='mesadb_dba_user_dir')
    # WARNING: 如果你改变任何的密码参数,请查看Configurator.py
    group.add_argument('--dba-user-password', '-p', metavar='PASSWORD',
            help="The DBA system user password.  (default: prompt)",
            dest='mesadb_dba_user_password')
    group.add_argument('--dba-user-password-disabled',
            action='store_const', const=True, default=None,
            help="Disable the DBA system user password.",
            dest='mesadb_dba_user_password_disabled')
    group.add_argument('--dba-group', '-g', metavar='GROUP',
            help="The DBA system group name. (default: mesadbdba)",
            default='mesadbdba', dest='mesadb_dba_group')

    group=parser.add_argument_group(title="Miscellaneous options")
    group.add_argument('--data-dir', '-d', metavar='DIR',
            help="The default data directory for new databases (default: <dba home>)")

    group=parser.add_argument_group(
            title="Navigating the cluster",
            description=textwrap.dedent("""\
    In order to complete the specified operations, this program requires access
    to each of the cluster hosts.  Specify authentication credentials with these
    options.  By default, you will be prompted for the password if required.
    
    When the SUDO_USER environment variable is set, %(prog)s attempts to ssh as
    that user.  This is the case when invoked with `sudo`.  Otherwise, %(prog)s
    will ssh as root.  The credentials provided with these options must match
    the ssh user.
            """))
    # WARNING: 如果你修改任何密码参数,请查看 Configurator.py
    group.add_argument('--ssh-password', '-P', metavar='PASSWORD',
            help="The password for ssh authentication in the cluster")
    group.add_argument('--ssh-identity', '-i', metavar='FILE',
            help="The ssh identify file for ssh authentication in the cluster")

    group = parser.add_argument_group(
            title="Networking options",
            description=textwrap.dedent("""\
    Vertica uses the network for three purposes: data exchange, cluster
    control messaging, and client communication.  By default, a single
    network and UDP broadcast (control messaging only) will be used.
    These options allow you to configure the defaults for new databases,
    but will not affect already-created databases.  See the online
    documentation for more details.
            """))
    group.add_argument('--point-to-point', '-T',
            action='store_const', const=True, default=None,
            dest="direct_only",
            help="""
            For control messaging, use direct UDP messages rather than UDP
            broadcast.  Affects new databases only.""")
    parser.add_argument('--broadcast', '-U',
            dest="direct_only",
            action='store_const', const=False, default=None,
            help="""
            For control messaging, use broadcast UDP messages (default)""")
    group.add_argument('--control-network', '-S', metavar="BCAST_ADDR",
            dest='spread_subnet',
            help="""
            For control messaging, use a specific network.  Specify via
            broadcast address or 'default'.""")
    group.add_argument('--spread-logging', '-w',
            action='store_const', const=True, default=None,
            dest='spread_logging_on',
            help="""
            Enable control message logging (spread logging).  Affects new
            databases only. (not recommended)""")
    group.add_argument('--large-cluster', '-2', default=None,
            dest='spread_count',
            help="""
            Maximum number of nodes that run spread for control messages.""")

    group = parser.add_argument_group(title="License options")
    parser.add_argument('--license', '-L', metavar='FILE',
            dest="license_file",
            help='License file')
    parser.add_argument('--accept-eula', '-Y',
            action='store_const', const=True, default=None,
            help="Accept the EULA quietly.")

    group = parser.add_argument_group(
            title="Silent installation",
            description=textwrap.dedent("""\
    Installation options can be saved to or loaded from a configuration
    file in order to assist with automation and repeated installs.
            """))
    group.add_argument('--config-file', '-z', metavar='FILE',
            dest='silent_config',
            help="Read options from a configuration file")
    group.add_argument('--record-config', '-B', metavar='FILE',
            dest='record_to',
            help="Write options to a configuration file and exit")

    group = parser.add_argument_group(
            title="System and cluster prerequisites",
            description=textwrap.dedent("""\
    System and cluster prerequisites are checked by %(prog)s.  These
    options adjust if the prerequisites are checked and how the results
    are handled.
            """))
    group.add_argument('--failure-threshold',
            default='WARN', choices=severity.all_severity_values + ['NONE'],
            help="Stop installation for any failures of this severity or worse (default: WARN)")
    group.add_argument('--no-system-configuration',
            action='store_const', const=True, default=None,
            help="""
            By default, simple system configurations that need to be adjusted to
            conform to the HP Vertica installation will be changed on your
            behalf. To prevent any system configuration changes, use this
            option.
            """)
    # hidden! We always want users to collect results, even if they are
    # failures.  That way we can see them in the logs.
    group.add_argument('--no-system-checks',
            action='store_const', const=True, default=None,
            help=argparse.SUPPRESS)

    #
    # 其他隐藏选项
    #
    parser.add_argument('--ignore-install-config',
            action='store_const', const=True, default=None,
            help=argparse.SUPPRESS)
    parser.add_argument('--no-ssh-key-install',
            action='store_const', const=True, default=None,
            help=argparse.SUPPRESS)
    # actually doesn't do anything anymore.  We'll keep it, though.
    parser.add_argument('--debug', '-D',
            action='store_const', const=True, default=None,
            help=argparse.SUPPRESS)
    parser.add_argument('--update',
            action='store_const', const=True, default=None,
            dest="update_mesadb",
            help=argparse.SUPPRESS)
    # --ignore-netmastk and --skip-network-test are now deprecated because we
    # got rid of netperf.
    parser.add_argument('--ignore-netmask', '-N',
            action='store_const', const=True, default=None,
            help=argparse.SUPPRESS)
    parser.add_argument('--skip-network-test', '-X',
            action='store_const', const=True, default=None,
            help=argparse.SUPPRESS)

    options = parser.parse_args()

    if options.mesadb_dba_user == 'root':
        parser.error("'root' may not be used as the DB admin user")

    _include_install_config(parser, options)

    return options

def _include_install_config(parser, options):
    if options.ignore_install_config:
        return

    install_config = os.path.join(DBinclude.CONFIG_DIR, 'install_config.py')
    if not os.path.isfile(install_config):
        return

    mod = imp.load_source('mesadb.config.install_config', install_config)
    mod.check_install_options(parser, options)

if __name__ == "__main__":
    sys.exit(mesadb.install.run_install(_parse_options))
