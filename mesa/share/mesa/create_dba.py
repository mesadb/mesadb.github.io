from __future__ import absolute_import

import argparse
import getpass
import os
import textwrap
import logging
import sys

from mesadb.platform.node.dba import DbaCreate, ScriptExit
import mesadb.shared.vconst as vconst
import mesadb.shared.logging
import mesadb.config.DBname as DBname

def _get_arg_parser():
    def oneline(val):
        return val.strip().replace('\n', ' ')

    parser = argparse.ArgumentParser(
            formatter_class = argparse.RawDescriptionHelpFormatter,
            description=textwrap.dedent("""
    创建 DB Admin linux 用户帐号和组.

    先创建用户组. 然后, 使用参数创建用户. 最后验证用户. 这是主目录,同时添加到用户组中.
            """).strip())

    parser.add_argument('--user', metavar="USER", default=vconst.DBA_USR,
            help="The user to add (or verify)")
    parser.add_argument('--group', metavar="GROUP", default=vconst.DBA_GRP,
            help="The user group to add (or verify)")
    parser.add_argument('--home', metavar="HOME", default=vconst.DBA_HOME,
            help="The user's home directory")
    parser.add_argument('--group-add',
            action="store_const", const=True, default=True,
            help="Add the user to the group (default)")
    parser.add_argument('--no-group-add',
            action="store_const", const=False, dest="group_add",
            help=oneline("""Do not add the user to the group.  It must already
            be a member."""))
    parser.add_argument('--primary-group',
            action="store_const", const=True, default=True,
            help="The group must be the user's primary/login group. (default)")
    parser.add_argument('--no-primary-group',
            action="store_const", const=False, dest="primary_group",
            help=oneline("""The group does not need to be the user's
            primary/login group."""))
    parser.add_argument('--dry-run',
            action='store_const', const=True, default=False,
            help="Make no changes.  Show the changes which would be made.")
    parser.add_argument('--force',
            action="store_const", const=True, default=False,
            help="Disables some very important integrity checks.")
    parser.add_argument('--log',
            default=mesadb.shared.logging.default_installer_log_file(),
            help="Where to write a log file. (default: Vertica install.log).",
            metavar='FILE' )
    parser.add_argument('--color',
            default='auto', choices=('always', 'auto', 'never'),
            help="Colorize output. (default: auto)")
    parser.add_argument('--short', action='store_true',
            help="Use a shortened form of output")
    parser.add_argument('--version', action='version',
            version='%(prog)s '+DBname.PRODUCT_VERSION,
            help="Display the program version and exit.")

    group = parser.add_argument_group(
            title="Handling an existing user or group",
            description=textwrap.dedent("""
    缺省情况下, 如果用户或组存在, 将发出一个警告,同时处理操作. 很多通用的配置失败了, 但是现有的用户可能通过一种不期望的方式设置. 这可能导致在数据库管理过程中出现故障.

    如下的选项控制怎样 %(prog)s 处理一个现有的用户或用户组
            """))

    group.add_argument('--must-create-user',
            action="store_const", const=True, default=False,
            help="If the user already exists, fail.")
    group.add_argument('--no-must-create-user', dest="must_create_user",
            action="store_const", const=False,
            help="If the user already exists, carry on. (default)")
    group.add_argument('--must-create-group',
            action="store_const", const=True, default=False,
            help="If the group already exists, fail.")
    group.add_argument('--no-must-create-group', dest="must_create_group",
            action="store_const", const=False,
            help="If the group already exists, carry on. (default)")

    group = parser.add_argument_group(
            title="Specifying the user password",
            description=textwrap.dedent("""
    There are several ways to provide the password for a newly created user.
    They mainly differ in security and usability, depending on your use case.
    The most secure options are presented first.

    You may not specify more than one of the following options.
            """))

    # NOTE: 缺省情况下应用到_parse_args中
    group.add_argument('--password-disabled',
            action="store_const", const=True, default=False,
            help=oneline("""The user will be unable to authenticate with a
            password. (default)"""))
    group.add_argument('--password-prompt',
            action="store_const", const=True, default=False,
            help="Prompt for the password immediately.  Prompts twice.")
    group.add_argument('--password-file', metavar="FILE", default = None,
            help="Read the password from the given file.")
    group.add_argument('--password-env', metavar="ENVVAR", default = None,
            help=oneline("""Read the password from the given environment
            variable.  In some systems, the environment of processes is
            available to non-privileged users and could be used to snoop the
            plaintext password."""))
    group.add_argument('--password-plaintext', metavar="PASSWORD",
            default = None,
            help=oneline("""User the password provided.  This is usually
            insecure, since most systems show the arguments of commands in
            process listings ('ps') which could be used to snoop the plaintext
            password."""))

    group = parser.add_argument_group(
            title="Correcting validation failures",
            description=textwrap.dedent("""
    These options determine how %(prog)s handles validation failures.
    They do not change how default system commands behave.  For example, the
    system will typically create the home directory of any newly created user.
            """))

    group.add_argument('--create-home',
            action="store_const", const=True, default=False,
            help="If HOME does not exist, create it.")
    group.add_argument('--no-create-home',
            action="store_const", const=False, dest="create_home",
            help="If HOME does not exist, fail. (default).")
    group.add_argument('--chown-home',
            action="store_const", const=True, default=False,
            help="If HOME is not owned by USER, chown to USER:USER.")
    group.add_argument('--no-chown-home',
            action="store_const", const=False, dest="chown_home",
            help="If HOME is not owned by USER, fail. (default)")

    return parser

def _parse_args(args):
    parser = _get_arg_parser()
    results = parser.parse_args(args)

    if results.color == 'auto':
        results.color = sys.stdout.isatty()
    elif results.color == 'always':
        results.color = True
    else:
        results.color = False

    if results.user == 'root':
        parser.error("'root' may not be used as the DB admin user")

    #
    # 处理密码业务
    #

    # 只允许0 或 1 密码选项. 缺省情况下是密码禁用的
    password_opts = ( 'password_disabled', 'password_prompt', 'password_file',
            'password_env', 'password_plaintext')
    used_opts = []
    for option in password_opts:
        value = getattr(results, option)
        if value is not None and value != False:
            used_opts.append(option)

    if len(used_opts) == 0:
        results.password_disabled = True
    elif len(used_opts) > 1:
        parser.error('cannot specify multiple --password options')
        pass

    # 处理每个密码选项, 在'password'中推送密码
    if results.password_disabled:
        results.password = None
    elif results.password_plaintext is not None:
        results.password = results.password_plaintext
    elif results.password_prompt:
        results.password = getpass.getpass('enter password: ')
        verify = getpass.getpass('retype password: ')
        if results.password != verify:
            parser.error("passwords do not match")
    elif results.password_env is not None:
        envvar = results.password_env
        if envvar not in os.environ:
            parser.error('environment variable %s not set' % envvar)
        results.password = os.environ[envvar]
    elif results.password_file is not None:
        try:
            with open(results.password_file, 'r') as f:
                results.password = f.read().strip()
        except StandardError as err:
            parser.error(str(err))

    # 检查密码的内容为 okay
    if not results.password_disabled:
        value = results.password
        if len(value)==0 or '\r' in value or '\n' in value:
            parser.error("invalid password value. Empty? Include newlines?")

    return results

def _main():
    args = _parse_args(sys.argv[1:])
    if os.geteuid() != 0:
        print "Must be run as root"
        sys.exit(1)

    mesadb.shared.logging.setup_installer_logging(args.log)

    root_logger = logging.getLogger()
    root_logger.info("-"*60)
    root_logger.info("Begin create_dba")
    root_logger.info("-"*60)

    try:
        DbaCreate(args).run()
    except ScriptExit as err:
        sys.exit(err.exitcode)

if __name__ == "__main__":
    _main()
