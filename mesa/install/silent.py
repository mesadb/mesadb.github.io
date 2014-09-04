
"""
为重复安装操作,记录和加载installer选项.
"""

from __future__ import absolute_import

import os
import sys
import types
import traceback

def record_options( options ):
    ''' use the file supplied by options.record_to to write out a
        properties file to be used by -z'''

    if os.path.exists(options.record_to):
        print "ERROR: File already exists: %s" % options.record_to
        sys.exit(1)

    fd = None
    try:
        # 使用 O_CREAT | O_EXCL 的symlink 路径失败.
        real_file = os.path.realpath(options.record_to)
        fd = os.open(real_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL , 0600)

        with os.fdopen(fd, 'w') as f:
            # 以 "k = v"格式写出选项的属性.
            for member in dir(options):
                # ignore privates
                if member.startswith( '__' ):
                    continue

                value = getattr( options, member )

                # 忽略空值和函数值.
                if value != None and type(value) != types.MethodType:
                    f.write("%s = %s\n"  % (member, value))

        fd = None # `os.fdopen` 将关闭此文件.

    finally:
        if fd is not None:
            os.close(fd)

def process_config_file(filename, options):
    ''' use the supplied filename to fill in options structures '''

    boolean_options = [ 'debug', 'clean', 'ignore_netmask', 'allowUDP',
            'direct_only', 'spread_logging_on',
            'skip_network_test', 'accept_eula', 'update_mesadb' ]

    def is_default(key, value):
        # 对于所提供的 Key,如果给定的值是默认的,则返回True.
        if value is None:
            return True
        if key == 'mesadb_dba_group' and value == 'mesadbdba':
            return True
        if key == 'mesadb_dba_user' and value == 'dbadmin':
            return True
        if key == 'failure_threshold' and value == 'WARN':
            return True
        return False

    def normalize(key, value):
        # 为所提供的选项Key,返回'value'的正确格式.
        # 从string 转换到 boolean.
        if key in boolean_options:
            return value.lower() in ('yes', 'y', 't', 'true')
        else:
            return value

    key_rename_map = {
            "dba_user_dir" : "mesadb_dba_user_dir",
            "root_password" : "ssh_password",
            "identity_file" : "ssh_identity" }

    expired_options_map = {
            'redirect_output' : "The redirect_output option has been removed. Please use your shell's redirection syntax.",
            'replaceHost' : "The replaceHost option (-E) has been removed. See documentation for replacing nodes."
            }

    with open( filename, 'r' ) as configfile:
        for line in configfile:
            line = line.strip()

            # Ignore empty lines and drop comments
            line = line.split('#')[0].strip()
            if len(line) == 0:
                continue

            line_parts = line.split('=', 1)
            if len(line_parts) < 2:
                print "Error: silent configuration line doesn't follow key=value format."
                print "Hint: Line is %r" % line
                return False

            (key, val) = line.split('=', 1)
            key = key.strip()
            val = val.strip()

            # ignore empty values
            if len(val) == 0:
                continue

            # keys that were renamed once
            if key in key_rename_map:
                key = key_rename_map[key]

            # 改变string 到正确的值类型
            val = normalize(key, val)

            if key in expired_options_map:
                print "Error: %s" % expired_options_map[key]
                return False

            if not hasattr(options, key):
                print "Error: Invalid silent configuration key: %r" % key
                return False

            # 覆盖上述选项.
            # i.e. 当前值是默认的
            if is_default(key, getattr(options, key)):
                setattr(options, key, val)

        return True

