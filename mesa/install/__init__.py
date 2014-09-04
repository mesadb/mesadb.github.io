from __future__ import absolute_import

import sys
import time
import re
import threading
import os
from mesadb.network import SSH, adapterpool
import socket, os, os.path
from optparse import OptionParser
from mesadb.config import DBinclude
from mesadb.tools import DBfunctions
from mesadb.engine import adminExec
from mesadb.ui import commandLineCtrl
from mesadb.network.ssh_auth import SshAuth

from mesadb.config.Configurator import Configurator
from mesadb.network import SystemProfileFactory
from mesadb.upgrade import IntegrateSpread
import types
import getpass
from mesadb.log.InstallLogger import InstallLogger
import math
import hashlib
from mesadb.network.adapters import adapter
import mesadb.shared.util as util

import mesadb.utils.ssl
import mesadb.install.silent
from mesadb.install import status
import mesadb.utils.ssh_keygen

#
g_install_status = None
def switch_status(new_status, options):
    global g_install_status
    if g_install_status is not None:
        g_install_status.printSuccess()
    g_install_status = new_status
    g_install_status.setOptions(options)
    g_install_status.printEnter()

def empty_string(x, strip=False):
    if strip:
        return x is None or len(x.strip()) == 0
    else:
        return x is None or len(x) == 0
# 检查默认的 shell 脚本
def check_default_shell(fullhostname_list, installerSSH):
    installerSSH.setHosts(fullhostname_list)
    Status, res = installerSSH.execute("echo $SHELL", hide=True)

    wrong_shells = {}
    for k,v in res.items():
        if "bash" not in v[1][0]:
            wrong_shells[k]=v[1][0]

    if len(wrong_shells)>0:
        print "Error: Default shell on the following nodes are not bash. Default shell must be set to bash."
        for k,v in wrong_shells.items():
            print k,v
        print "Exiting..."
        sys.exit(1)
    else:
        print "Default shell on nodes:"
        for k,v in res.items():
            print k,v[1][0]

# 判断是否为同一个主机
def are_hosts_the_same( a, b ):
    # 通过地址获得主机信息,然后比较如下信息: hostname, aliaslist, ipaddrlist
    # 如果a,b之间上述属性是相同的,那么可以确定是相同的主机信息.

    #  将a,b条目值设置在列表中.
    a_entries = set([ a[0] ] + a[1] + a[2])
    b_entries = set([ b[0] ] + b[1] + b[2])

    # 设置交集为空?
    return len(a_entries & b_entries) > 0

# 执行IntegrateSpread配置文件中的upgrade_integrate_spread方法
def run_upgrades(running_as, user, executor):
    return IntegrateSpread.upgrade_integrate_spread(running_as,user,executor)

#后处理选项
def _post_process_options(options):
    prog = 'update_mesadb' if options.update_mesadb else 'install_mesadb'

    #
    # 后处理选项
    #

    if options.record_to is not None and options.silent_config is not None:
        print "\nError: Cannot provide and read silent config at the same time"
        sys.exit(1)

    if options.record_to is not None:
        mesadb.install.silent.record_options(options)
        sys.exit(0)

    if options.silent_config is not None:
        if not mesadb.install.silent.process_config_file(options.silent_config, options):
            print "\nError: Error parsing %s. See above." % options.silent_config
            sys.exit(1)

    # 命令行参数-S的值 (--spread_reconfig) 为 'default' 或者为 ipaddress
    if options.spread_subnet is not None and options.spread_subnet!='default':
        try:
            socket.inet_pton(socket.AF_INET, options.spread_subnet)
        except socket.error as err:
            print "\nError: Invalid value %s for --control-network (-S)" % options.spread_subnet
            sys.exit(1)

    if options.spread_count is not None and options.spread_count not in ['off','default']:
        try:
            int(options.spread_count)
        except ValueError as err:
            print "\nError: Invalid value '%s' for --large-cluster (-2)" % options.spread_count
            sys.exit(1)

    # 更改 rpm_file_name 到一个绝对路径, 同时检查此文件.
    if empty_string(options.rpm_file_name):
        options.rpm_file_name = None
    else:
        options.rpm_file_name = os.path.abspath(options.rpm_file_name)
        if not os.path.exists( options.rpm_file_name ):
            print "Invalid path for rpm file: %s" % options.rpm_file_name
            sys.exit(1)

    # 不能同时添加和删除主机(-A or -R)
    if (options.add_hosts or options.remove_hosts) and options.hosts:
        print "Error: Cannot both install and modify the cluster."
        print "Hint: Do not use --hosts (-s) while using --add-hosts (-A) or --remove-hosts (-R)"
        sys.exit(1)

    # --clean (-C)不能与--add-hosts (-A)和--remove-hosts (-R)同时使用
    if (options.add_hosts or options.remove_hosts) and options.clean:
        print "The --clean option cannot be used with --add-hosts (-A) or --remove-hosts (-R) options\n"
        sys.exit(1)

    # --clean (-C)不能与 update_mesadb 同时使用
    if options.update_mesadb and options.clean:
        print "The --clean option cannot be used with update_mesadb\n"
        sys.exit(1)

    # 如果用户指定了一个ssh identity, 确保它是有效的, 同时是无密码保护的.
    if options.ssh_identity is not None:
        keygen = mesadb.utils.ssh_keygen
        if keygen.ssh_keygen_bin() is None:
            print "Warning: ssh-keygen cannot be found on this system. You may experience problems using the --ssh-identity option."
        elif not keygen.is_passwordless_private_key(options.ssh_identity):
            print "Error: %s is not a passwordless SSH private key or could not be accessed." % options.ssh_identity
            print "Hint: --ssh-identity can only accept unprotected private keys. Use an SSH agent for password protected keys."
            sys.exit(1)

    if options.mesadb_dba_user_dir is None:
        options.mesadb_dba_user_dir = "/home/%s" % options.mesadb_dba_user

    if options.data_dir is None:
        options.data_dir = options.mesadb_dba_user_dir

    # mesadb installer 通常以 root 权限来运行.
    if os.geteuid()!=0 and len(os.environ.get('_VERT_ROOT_OVERRIDE', ''))==0:
        print "%s must be run as root." % prog
        print "Hint: Try again with su or sudo"
        sys.exit(1)

    # 安装 openssl 包
    if not mesadb.utils.ssl.have_openssl():
        print "Error: Unable to find 'openssl'.  Please install this package before proceeding."
        sys.exit(1)

def _get_install_hosts(options, siteDict):
    """ 给出本地主机和已经添加,维护,删除的主机列表.
        
        返回如下值 (local_host, add_hosts, keep_hosts, remove_hosts)
        local_host: 本地主机信息
        add_hosts: 添加到集群的主机列表
        keep_hosts: 在集群中的主机列表
        remove_hosts: 从集群删除的主机列表
        
        IMPORTANT: 当执行--clean 命令后, remove_hosts 和 kee_hosts 列表为空.
        这些主机并没有真正被删除, 而是在列表中清除.

        每个主机的对象包括: (ipaddress, hostnames, addresses)
        ipaddress: IP地址
        hostnames: 主机名列表
        addresses: IP地址列表
    """

    def findHost(host, collection):
        # 在主机列表中查找某主机,主机和主机列表通过主机名来进行更正.
        for x in collection:
            if are_hosts_the_same(host, x):
                return True

        return False

    # 主机更正封装器
    def hostFixupWrapper(hoststring, argument):
        hostparts = [ x.strip() for x in hoststring.split(',') ]
        hostparts = [ x for x in hostparts if len(x) != 0 ]

        if len(hostparts) == 0:
            return []

        print "\nMapping hostnames in %s to addresses..." % argument

        addresses = []

        # 解析主机到单个IP
        for host in hostparts:
            try:
                address = util.resolve_to_one_ip(host)
            except StandardError as err:
                print "\t%s" % err
                print "\tError: Unable to resolve %r" % host
                sys.exit(1)

            if host != address:
                # only showing resolutions that aren't IP literals.
                print "\t%-30s => %s" % (host, address)
            
            # 追加IP地址到地址列表
            addresses.append(address)

        # 在列表中检测重复地址
        seen = set()
        duplicates = False
        for address in addresses:
            if address in seen:
                print "\tError: Duplicate address: %s" % address
                duplicates = True
            else:
                seen.add(address)

        if duplicates:
            sys.exit(1)

        return DBfunctions.hostname_fixup(addresses)
        # END hostFixupWrapper

    add_hosts = []      # 用 --add-hosts 指定主机列表
    remove_hosts = []   # 用 --remove-hosts(not via --clean) 指定主机列表
    opt_hosts = []      # 用 --hosts指定主机列表
    existing_hosts = [] # 存在于集群中的主机列表
    keep_hosts = []     # 存在于集群中的活跃主机列表

    if(options.add_hosts and len(options.add_hosts) > 0 ):
        add_hosts = hostFixupWrapper(options.add_hosts, '--add-hosts (-A)')
    if(options.remove_hosts and len(options.remove_hosts) > 0 ):
        remove_hosts = hostFixupWrapper(options.remove_hosts, '--remove-hosts (-R)')
    if(options.hosts and len(options.hosts) > 0 ):
        opt_hosts = hostFixupWrapper(options.hosts, '--hosts (-s)')

    existing_hosts = set([ x[1] for x in siteDict.values() ])
    existing_hosts = DBfunctions.hostname_fixup(existing_hosts)


    assert not options.clean or len(remove_hosts) == 0, \
            "Cannot use --clean and --remove-hosts together"

    # 验证已经删除的主机,是集群内的主机.
    for x in remove_hosts:
        if not findHost(x, existing_hosts):
            hostlist = ', '.join([ y[0] for y in existing_hosts ])
            print "Error: Unable to remove host %s: not part of the cluster " % x[0]
            print "Hint: Valid hosts are: %s" % hostlist
            sys.exit(1)

    # 验证已经添加的主机,不是集群内的主机.
    for x in add_hosts:
        if findHost(x, existing_hosts):
            hostlist = ', '.join([ y[0] for y in existing_hosts ])
            print "Error: Unable to add host %s: already part of the cluster " % x[0]
            print "Hint: Existing hosts are: %s" % hostlist
            sys.exit(1)

    # 生成集群内活跃节点的列表
    if options.clean:
        keep_hosts = []
    else:
        keep_hosts = [ x for x in existing_hosts if not findHost(x, remove_hosts) ]

    # 早期安全检查.
    assert len(opt_hosts) == 0 or len(add_hosts) == 0, \
            "Cannot use --hosts and --add-hosts togther"
    assert len(opt_hosts) == 0 or len(remove_hosts) == 0, \
            "Cannot use --hosts and --remove-hosts togther"

    # 精确匹配选项中的主机列表和集群中的主机列表.
    if len(opt_hosts) > 0 and len(keep_hosts) > 0:
        fail_msgs = []

        for x in opt_hosts:
            if not findHost(x, keep_hosts):
                fail_msgs.append("\t%s in --hosts but not in cluster." % x[0])

        for x in keep_hosts:
            if not findHost(x, opt_hosts):
                fail_msgs.append("\t%s in cluster but not in --hosts." % x[0])

        if len(fail_msgs) > 0:
            print "Error: A cluster exists but does not match the provided --hosts"
            for msg in fail_msgs:
                print msg
            print "Hint: omit --hosts for existing clusters. To change a cluster use --add-hosts or --remove-hosts."
            sys.exit(1)


    if len(keep_hosts) == 0:
        # 从--hosts 移动主机到 --add-hosts.
        if len(opt_hosts) > 0:
            assert len(add_hosts) == 0
            add_hosts = list(opt_hosts)
            opt_hosts = []

        # 用户必须指定一个主机 (no default localhost)
        if len(add_hosts) == 0:
            print "Error: No machines will be included in the cluster!"
            print "Hint: provide --hosts."
            sys.exit(1)

    # 防止localhost(loopback)主机称为'2+node'集群的节点.
    if len(keep_hosts) + len(add_hosts) >= 2:
        if "127.0.0.1" in [ x[0] for x in keep_hosts ]:
            print """\
Error: Existing single-node localhost (loopback) cluster cannot be expanded
Hint: Move cluster to external address first."""
            sys.exit(1)

        if "127.0.0.1" in [ x[0] for x in add_hosts ]:
            print """\
Error: Cannot add localhost (loopback) to an existing cluster.
Hint: Use an external address."""
            sys.exit(1)

    # '标准'主机名列表
    all_hosts = add_hosts + keep_hosts + remove_hosts

    local_host = None
    for x in all_hosts:
        if DBfunctions.IsLocalHost(x[0]):
            local_host = x
            break # count on there being no duplicates, as previously checked

    if local_host is None:
        print "Error: cannot find which cluster host is the local host."
        print "Hint: Is this node in the cluster? Did its IP address change?"
        sys.exit(1)

    # 不要从集群中移除localhost主机,
    # 建议在另外的主机上从集群中移除localhost.
    if findHost(local_host, remove_hosts):
        print "Error: Cannot remove the local host (%s) from the cluster." % local_host[0]
        print "Hint: Use another host in the cluster to remove this host."
        sys.exit(1)

    return (local_host, add_hosts, keep_hosts, remove_hosts)

def _legacy_get_install_hosts(options, siteDict):
    """Glue!"""
    (local_host, add_hosts, keep_hosts, remove_hosts) = \
            _get_install_hosts(options, siteDict)

    def to_hostnames(hosts):
        return [x[0] for x in hosts]

    return (local_host[0], to_hostnames(add_hosts + keep_hosts + remove_hosts),
            to_hostnames(add_hosts), add_hosts,
            to_hostnames(remove_hosts), remove_hosts,
            to_hostnames(keep_hosts), keep_hosts)

# 如果指定了control-subnet, 确保它匹配主机.
def spread_subnet_is_usable(bcastaddr, profiles):
    "检查是否control-subnet的broadcast address 正常工作"

    mismatches = []
    for (host, machine) in profiles.iteritems():
        if not machine.has_broadcast(bcastaddr):
            mismatches.append(machine)

    if len(mismatches) == len(profiles):
        print "Error: It appears that --control-network %r is invalid" % bcastaddr
        print "Hint: Is this a broadcast address found on any machine?"
        return False

    if len(mismatches) > 0:
        print "Warning: Some machines do not have an interface with broadcast %r (--control-network)" % bcastaddr
        print "Hint: mismatch on %s" % ' '.join([x.hostname for x in mismatches])

    return True

def _main(options):
    """mesadb 的安装脚本. 具体查看 run_install.

    """

    # 定义常量
    logger = InstallLogger()
    LOG = logger.logit
    LOG_BEGIN = logger.logit_start
    LOG_END = logger.logit_end
    LOG_RECORD = logger.record

    # 重用adminExec的功能,作为requested dba user来运行
    executor = adminExec.adminExec(makeUniquePorts = False, showNodes = False, user = options.mesadb_dba_user)
    # 执行器获得节点信息
    siteDict = executor.getNodeInfo()

    (localhost, fullhostname_list,
    addhostname_list, addhost_list,
    removehostname_list, removehost_list,
    updatehostname_list, updatehost_list ) = \
            _legacy_get_install_hosts(options, siteDict)
    downremovehosts = []

    # XXX: This needs to die a violent death.
    running_as = "root" # the user that we ssh as.
    if os.environ.get("SUDO_UID") is not None:
        running_as  =  os.environ.get("SUDO_USER")

    # 确定使用的ssh密码
    if options.ssh_password is not None:
        SshAuth.instance().password_used(None, running_as, options.ssh_password)
    if options.ssh_identity is not None:
        SshAuth.instance().set_identity_file(options.ssh_identity)
    # 切换状态
    switch_status(status.StatusClusterCheck(), options)

    # 设置config配置文件的install_options条目.
    cfgr = Configurator.Instance()
    cfgr.set_options( sys.argv[1:] )
    cfgr.save()

    # 收集系统的描述信息.
    factory = SystemProfileFactory.SystemProfileFactory()
    profiles = {}
    conns = {}
    unavailable_hosts = []
    ptyerrs = False
    #
    # 创建 `unavailable_hosts` 和 `conns`.
    # `conns` 只是用来创建系统描述信息的.
    #
    for h in fullhostname_list:
        c = adapterpool.DefaultAdapter(h)

        try:
            # 不需要'root'用户.
            c.connect(h, running_as)
            conns[h] = c
        except Exception as err:
            print "Warning: could not connect to %s:" % h
            print "\t%s" % str(err)
            unavailable_hosts.append( h )

            if re.search( ".*out of pty devices.*", str(err)):
                ptyerrs = True
                print "Hint: check to see whether the /dev/pts device is mounted on %s. Refer to Troubleshooting section of the documentation." % h 


    if ptyerrs:
        print "Error: Detected errors related to /dev/pts. Exiting."
        sys.exit(1)

    for uh in unavailable_hosts:
        if uh in removehostname_list:
            downremovehosts.append(uh)
            print "Ignoring down host %s because it is due to be removed." % uh
            print "Warning: %s will not have it's cluster information correctly updated" % uh
        else:
            print "Error: Cannot ignore down host %s - it is not being removed" % uh
            print "Hint: Establish connectivity to all cluster hosts before trying."
            sys.exit(1)

    try:
        profiles = factory.getProfile( conns )
        for x in conns.values():
            x.close()
    except Exception as err:
        print "Error: failed to get system information for all hosts"
        print "\t%s" % err
        print "Hint: additional failures may be hidden."
        sys.exit(1)

    # 清空描述文件,因此已经删除的主机节点就不会出现在spread config文件中了.
    for remove_host in removehostname_list:
        if remove_host in profiles:
            del profiles[remove_host]

    # 避免在相同的主机上两个主机名解析出两个不同的IP地址.
    # 描述文件在主机之间显示为相同.
    # XXX:我们已经为删除主机移除描述信息
    for (host1, prof1) in profiles.iteritems():
        for (host2, prof2) in profiles.iteritems():
            if host1 == host2:
                continue

            if prof1 == prof2:
                # 0pointer.de/blog/projects/ids.html 描述一个好的方法来标识相同主机.
                # 使用interface标识是不靠谱的.
                print "Error: It looks like %s and %s are the same host." % (host1, host2)
                print "Hint: Each cluster host must be a distinct machine."
                sys.exit(1)

    # fullhostname_list 排除我们正在移除的节点.
    for hostname in removehostname_list:
        if hostname in fullhostname_list:
            fullhostname_list.remove( hostname )

    # 如果control-subnet被指定, 保证它匹配其中一台主机.
    if options.spread_subnet is not None:
        if options.spread_subnet.lower() != 'default':
            if not spread_subnet_is_usable(options.spread_subnet, profiles):
                # the above function prints the error/hint for us.
                sys.exit(1)

    #
    # 开始安装...
    #

    # 记录进行add,remove,update等操作的主机
    LOG_RECORD("Hosts to add: %s" % addhostname_list)
    LOG_RECORD("Hosts to remove: %s" % removehostname_list)
    LOG_RECORD("Hosts to update: %s" % updatehostname_list)
    LOG_RECORD("Resulting cluster: %s" % fullhostname_list)

    installerSSH = adapterpool.AdapterConnectionPool_3.Instance()
    installerSSH.root_connect(fullhostname_list + removehostname_list, running_as)

    # 我们能够删除此检查吗？create_dba脚本创建此检查.
    # 所有的相关适配器将以 bash 脚本启动
    check_default_shell(fullhostname_list, installerSSH)

    # 管理工具不能到处运行
    try:
        Status, res = installerSSH.execute( "ps -A | grep \" python.*admin[tT]ools\$\"", hide=True )
        hostsRunning=[]
        for host in res.keys():
            if res[host][0]!="1":
                hostsRunning.append(host)
        if len(hostsRunning) > 0 :
            LOG( "There are mesadb adminTool processes running on %s. They must be stopped before installation can continue\n" % hostsRunning )
            sys.exit(1)
    except Exception, e:
        LOG( "%s" % e  )
        sys.exit(1)


    # 确保没有任何不确定的权限能够运行安装进程.
    #
    # if [ -e /opt/mesadb ]; then
    #   cd /tmp;
    #   find /opt/mesadb -perm -755 -type d | grep '/opt/mesadb/$';
    # else
    #   echo '/opt/mesadb'
    # fi
    cmd = "echo `if [ -e \""+ DBinclude.DB_DIR +"\" ]; then cd /tmp; find "+ DBinclude.DB_DIR +" -perm -755 -type d | grep \""+ DBinclude.DB_DIR +"\$\"; else echo " + DBinclude.DB_DIR + "; fi`"
    Status, res = installerSSH.execute(cmd)
    hostsRunning=[]
    for host in res.keys():
        if res[host][1][0].strip() != DBinclude.DB_DIR:
            hostsRunning.append(host)
    if len(hostsRunning) > 0 :
        LOG( "Detected invalid permissions on "+ DBinclude.DB_DIR +" directories on the following hosts: %s" % hostsRunning )
        LOG( "Permissions must be set to 755 or higher for install_mesadb to work correctly.")
        sys.exit(1)

    switch_status(status.StatusValidateSoftware(), options)

    # 在所有节点上进行初步检查.
    # 1. 检查RPM包是否OK, 是否能够正常安装
    hostsToUpgradeRPM = []    # 哪台主机需要RPM更新
    (ok, rpmBrand, rpmVersion, rpmRelease, rpmArch) = (False, None, None, None,None)
    v = profiles[localhost].mesadb

    if options.rpm_file_name is None:
        (ok, rpmBrand, rpmVersion, rpmRelease, rpmArch) = (v.isInstalled(), v.brand, v.version, v.release,v.arch)
    else:
        (ok, rpmBrand, rpmVersion, rpmRelease, rpmArch) = SSH.rpmVersion( options.rpm_file_name )
        if ok:
            if rpmBrand.lower() != "mesadb":
                LOG("RPM is not for 'mesadb'.  It is for %r." % rpmBrand)
                sys.exit(1)
            if rpmVersion != v.version or rpmRelease != v.release:
                LOG("RPM must be upgraded locally, first.")
                LOG("\tLocal version = %s-%s" % (
                    '.'.join([str(x) for x in v.version]),
                    v.release))
                LOG("\tRPM version = %s-%s" % (
                    '.'.join([str(x) for x in rpmVersion]),
                    rpmRelease))
                sys.exit(1)

    # 需要知道RPM信息.  如果不知道,退出程序.
    if (not ok) or None in (rpmBrand, rpmVersion, rpmRelease, rpmArch):
        if options.rpm_file_name == None:
            LOG("No rpm file supplied and none found installed locally.")
        else:
            LOG("RPM file %s not recognized" % options.rpm_file_name)
        sys.exit(1)

    # 检查是否RPM包可用于安装
    rpm_check_fails = False
    for host in fullhostname_list:
        current = profiles[host].mesadb

        isupgradable = False
        if current.isInstalled():
            (isupgradable, iscurrentrev, msg) = current.canbeupgraded( rpmBrand, rpmVersion, rpmRelease, rpmArch )
            if not isupgradable and not iscurrentrev:
                LOG( "(%s) %s" % (host,msg) )
                sys.exit(1)

        if isupgradable or not current.isInstalled():
            hostsToUpgradeRPM.append(host)

    if len(hostsToUpgradeRPM) > 0 and options.rpm_file_name is None:
        LOG("These hosts require upgrade:")
        for host in hostsToUpgradeRPM:
            LOG("\t%s" % (host, ))
        LOG("Hosts require upgrade, but RPM (-r) not provided.")
        sys.exit(1)

    # 对于所有主机,我们需要更新RPM包, 确保 mesadb 进程没有正在运行.
    # 如果 mesadb 正在运行,RPM安装失败,则此检查将发出警告.
    if len( hostsToUpgradeRPM ) > 0:
        installerSSH.setHosts(hostsToUpgradeRPM)
        LOG_RECORD("RPM upgrade required on %s; checking for running mesadb process" % hostsToUpgradeRPM)
        try:
            # XXX: 需要处理 zombie 进程 (作为"[mesadb]"报告)
            # 在安装过程中,在 grep 中添加 regex 表达式,查找 zombies 进程
            Status, res = installerSSH.execute( "ps -A | grep ' \[\?mesadb\]\?\( <defunct>\)\?$'", hide=True )
            hostsRunningIllegally=[]
            for host in res.keys():
                if res[host][0][0]!="1":
                    hostsRunningIllegally.append(host)
            if len(hostsRunningIllegally) > 0 :
                LOG( "There are mesadb processes running on %s. They must be stopped before installation can continue because an RPM upgrade is required.\n" % hostsRunningIllegally )
                sys.exit(1)
        except Exception, e:
            LOG( "%s" % e  )
            sys.exit(1)

    installerSSH.resetHosts()

    switch_status(status.StatusClusterChange(), options)

    #
    # 如果 admintools.conf 文件存在,则备份此文件.
    #
    try:
        # TODO: 创建一个 SSH.backup() 命令
        Status, res = installerSSH.execute("cp %s %s.bak.%f" % (DBinclude.ADMINTOOLS_CONF, DBinclude.ADMINTOOLS_CONF, time.time()), hide=True )
        for host in res.keys():
           if res[host][0] == "0":
               LOG ("backing up admintools.conf on %s " % host)
    except Exception, e:
        LOG ("backing up admintools.conf file failed with %s  \nNot a fatal error." % e)

    # 如果没有 database 定义,使用 clean 选项,然后删除 config 文件.
    # 如果没有 database 定义,用户能够更改主机名.
    c = Configurator.Instance()
    if (options.clean):
        if len(c.listDatabases()) != 0:
            LOG("Cannot perform installation with clean option as database is already defined.")
            sys.exit(1)
        # 清空所有之前的设置,启动一个新的安装进程.
        c.init_defaults()
        c.set_options( sys.argv[1:] )
        c.save()

        if not options.spread_subnet:
            options.spread_subnet = "default"

    else:
        siteDict = executor.getNodeInfo()
        definedHosts = {}
        if siteDict!={}:
            for node in siteDict.keys():
                definedHosts[siteDict[node][1]]=siteDict[node][1]

        for host in definedHosts.keys():
            # 查询主机的IP地址
            try:
                hostinfo = DBfunctions.hostname_fixup([host])[0]
                ipaddress = hostinfo[2]

                found = False
                for ip in ipaddress:
                    # 更新或者删除此主机
                    for cmdLineHost in updatehost_list + removehost_list:
                        if ip in cmdLineHost[2]:
                            found = True;
                            break;
            except Exception, e:
                found = False

            if not found:
                # TODO: 查看是否用于已经申请此节点从集群中删除.

                s = "Host %s, previously defined in your cluster, is missing in -s parameter: %s"%(host, options.hosts)
                LOG(s)
                answer = "no" #ask_question(s, "yes|no", "yes")
                if answer!="yes":
                    sys.exit(1)

    # RPM 文件中有一些脚本用于配置kernel, users,等.
    # 首先是在系统中获得相关软件.在每个主机上,安装 rpm 文件
    if len( hostsToUpgradeRPM ) > 0:
        switch_status(status.StatusInstallSoftware(), options)
        if DBinclude.OSNAME == "DEBIAN":
            print "Installing deb package on %s hosts...." %  len( hostsToUpgradeRPM )
        else:
            print "Installing rpm on %s hosts...." %  len( hostsToUpgradeRPM )
        for host in hostsToUpgradeRPM:
            # 在节点上进行 rpm 安装
            install_error = SSH.installNode( installerSSH, host, options.rpm_file_name, running_as )
            if install_error is not None:
                LOG("Install failed on %s\n%s" % (host , install_error))
                sys.exit(1)

    switch_status(status.StatusDbAdmin(), options)

    installerSSH.setHosts( fullhostname_list )

    create_dba_o= {
            'username' : options.mesadb_dba_user,
            'dbahome' : options.mesadb_dba_user_dir,
            'dbagroup' : options.mesadb_dba_group,
            'color' : sys.stdout.isatty(),
            'password-disabled' : bool(options.mesadb_dba_user_password_disabled) }
    if not empty_string(options.mesadb_dba_user_password):
        create_dba_o['password'] = options.mesadb_dba_user_password
    if not SSH.do_create_dba(installerSSH, options=create_dba_o):
        print "\nUnable to create or verify DB Admin user/group on some hosts."
        print "See above for details.\n"
        sys.exit(1)

    switch_status(status.StatusValidation(), options)

    if options.no_system_checks:
        print "Skipping system prerequisite checks (--no-system-checks)!\n"
    else:
        system_prerequisite_checks(installerSSH, localhost, options)

    switch_status(status.StatusSshKeys(), options)

    if options.no_ssh_key_install:
        print "Warning: Skipping install/repair of SSH keys for %s" % options.mesadb_dba_user
        print "Hint: You specified --no-ssh-key-install"
        print "\tHope you know what you are doing...\n"
    else:
        print "Installing/Repairing SSH keys for %s\n" % options.mesadb_dba_user
        if not SSH.installOrRepairSSHKeys(installerSSH, options.mesadb_dba_user, fullhostname_list):
            print "Error: SSH key generation or distribution failed."
            sys.exit(1)

    switch_status(status.StatusHostSetup(), options)

    installerSSH.setHosts(addhostname_list)

    print "Creating mesadb Data Directory...\n"
    res =  SSH.createDataDir(installerSSH, options.mesadb_dba_user, options.data_dir)
    if not res:
        print "Warning: Could not create mesadb Data Directory. See logs"

    # FIXME: mesadb 代理使用/opt/mesadb/config/users/USERNAME/agent.conf
    # 确定什么用户来运行. 从 directory 中获取 USERNAME 值. 它需要使用admintools.conf的owner权限.
    installerSSH.execute("mkdir -p %s/%s" % (DBinclude.CONFIG_USER_DIR, options.mesadb_dba_user ), hide=True )
    installerSSH.execute("touch %s/%s/agent.conf" % (DBinclude.CONFIG_USER_DIR, options.mesadb_dba_user ), hide=True )

    # new node checking / setup.
    installerSSH.resetHosts()

    # TODO: 首先进行 netverify 和 N-way 网络测试,
    # 也可以使用options.skip_network_test来跳过测试.
    # 因此也将忽略 options\.ignore_netmask

    # 在重新配置spread之前,从admin tools siteDict中删除节点.
    # 如果正在使用此 DB 实例,drop_node 将拒绝删除此节点,
    # 同时从 spread 中拉起节点,也执行 drop_node 检查.
    # 我们并不重新配置 spread, 而是需要删除节点.
    #
    for nodeName in [node[0] for node in siteDict.values() if node[1] in removehostname_list or node[1] in downremovehosts ]:
        LOG_BEGIN("Removing node %s definition" % (nodeName))

        if not executor.drop_node( nodeName, force_if_last=True, pool=installerSSH ):
            LOG("-- couldn't remove node, it's in-use by a database!")
            sys.exit(1)
        LOG_END(True)

    # 为新主机生成节点名称
    nodeInfo = executor.getNodeInfo()
    currentnode_list = [n for n in nodeInfo.keys()]
    if options.clean:
        currentnode_list = []
    newNames = {}

    nodeCount = 1
    nodeName = "node%04d" % (nodeCount)
    for host in addhostname_list:
        # 查找未使用的节点名称
        while nodeName in currentnode_list:
            nodeCount += 1
            nodeName = "node%04d" % (nodeCount)
        newNames[nodeName] = host
        currentnode_list.append(nodeName)

    currentnode_list.sort()

    # new mechanism (Crane): installer doesn't manage spread at all
    # simply ensure spread is NOT running anywhere
    installerSSH.resetHosts()
    installerSSH.setHosts(fullhostname_list)
    # stop spread if it's running
    Status, res = installerSSH.execute("%s/mesadb_service_setup.sh stop %s %s spread" % (DBinclude.sbinDir, DBinclude.DB_DIR, DBinclude.OSNAME))
    # remove spreadd links in /etc
    Status, res = installerSSH.execute("%s/mesadb_service_setup.sh remove %s %s spread" % (DBinclude.sbinDir, DBinclude.DB_DIR, DBinclude.OSNAME))
    # done with spread teardown

    # 为 RPM 安装配置目录, 设置权限到DBA组
    SSH.makeDir(installerSSH, DBinclude.CONFIG_DIR, "775", options.mesadb_dba_group)
    SSH.makeDir(installerSSH, DBinclude.CONFIG_SHARE_DIR, "775", options.mesadb_dba_group)
    SSH.makeDir(installerSSH, DBinclude.CONFIG_USER_DIR, "775", options.mesadb_dba_group)
    SSH.makeDir(installerSSH, DBinclude.LOG_DIR, "775", options.mesadb_dba_group)
    SSH.makeDir(installerSSH, DBinclude.SCRIPT_DIR, "775", options.mesadb_dba_group, recursive="-R")

    installerSSH.execute("chown %s:%s  %s" % ( options.mesadb_dba_user, options.mesadb_dba_group, DBinclude.CONFIG_DIR ) )
    installerSSH.execute("chown %s:%s  %s" % ( options.mesadb_dba_user, options.mesadb_dba_group, DBinclude.CONFIG_SHARE_DIR ) )
    installerSSH.execute("chown %s:%s  %s" % ( options.mesadb_dba_user, options.mesadb_dba_group, DBinclude.LOG_DIR ) )

    print "Updating agent..."

    # stop old agent links in /etc, if any
    Status, res = installerSSH.execute("%s/mesadb_service_setup.sh stop %s %s %s" % (DBinclude.sbinDir, DBinclude.DB_DIR, DBinclude.OSNAME, "agent"));
    # remove old agent links in /etc, if any
    Status, res = installerSSH.execute("%s/mesadb_service_setup.sh remove %s %s %s" % (DBinclude.sbinDir, DBinclude.DB_DIR, DBinclude.OSNAME, "agent"),
                                       info_msg="Removing old agent links")

    # setup agent links in /etc
    Status, res = installerSSH.execute("%s/mesadb_service_setup.sh install %s %s %s" % (DBinclude.sbinDir, DBinclude.DB_DIR, DBinclude.OSNAME, "agent"),
                                       hide=True, info_msg="Setting up agent daemon")

    # start agent
    Status, res = installerSSH.execute("%s/mesadb_service_setup.sh start %s %s %s" % (DBinclude.sbinDir, DBinclude.DB_DIR, DBinclude.OSNAME, "agent"), hide=True);


    # agent 需要一个ssl key.
    installerSSH.setHosts(fullhostname_list)
    setup_agent_key(installerSSH,
            options.mesadb_dba_user, options.mesadb_dba_group, LOG)


    # setup mesadbd links in /etc
    installerSSH.setHosts(fullhostname_list)
    Status, res = installerSSH.execute("%s/mesadb_service_setup.sh install %s %s %s" % (DBinclude.sbinDir, DBinclude.DB_DIR, DBinclude.OSNAME, "mesadb"),
                                       hide=True, info_msg="Setting up mesadbd autorestart")

    # 创建dba用户配置目录 /opt/mesadb/config/users/$USER
    # 当添加另外的dba用户时,我们将在所有的主机上执行此命令.
    installerSSH.setHosts(fullhostname_list)
    SSH.makeDir(installerSSH, "%s/%s"%(DBinclude.CONFIG_USER_DIR,options.mesadb_dba_user), "go-w", owner=options.mesadb_dba_user)

    # 添加新的节点到admintools结构中
    for nodeName in newNames:
        host = newNames[nodeName]
        LOG_BEGIN("Creating node %s definition for host %s" % (nodeName, host))
        executor.do_create_node( [ nodeName, host, options.data_dir, options.data_dir ],
                                 True,   # True == Force Create
                                 False ) # False == Hold off on sending to cluster 
        LOG_END(True)

    # ok - 获取已经更新过的节点信息字典,发给集群
    nodedict = executor.getNodeInfo()

    c = Configurator.Instance()
    if options.direct_only:
        c.setcontrolmode("pt2pt")
    else:
        c.setcontrolmode("broadcast")
    if options.spread_subnet:
        c.setcontrolsubnet(options.spread_subnet)
    if options.spread_logging_on:
        c.setspreadlogging("True")
    else: 
        c.setspreadlogging("False")
    if options.spread_count != None:
        count = c.setlargecluster(options.spread_count)
        if count:
            print "Large cluster enabled with spread count %s" % count
        else:
            print "Large cluster disabled"
    c.save()

    switch_status(status.StatusClusterSync(), options)

    #
    # 对admintools的元数据进行最后同步, 保证拥有关系是合适的.
    #
    installerSSH.setHosts(fullhostname_list)
    executor.sendSiteInfo(nodedict, ignore_hosts=downremovehosts, pool=installerSSH)

    installerSSH.setHosts(fullhostname_list)
    # 拥有关系 (确定 dbadmin 用户)
    installerSSH.execute("chown %s:%s %s" % ( options.mesadb_dba_user,
            options.mesadb_dba_group, DBinclude.ADMINTOOLS_CONF ) )
    # 权限
    installerSSH.execute("chmod 0664 %s" % DBinclude.ADMINTOOLS_CONF )

    #
    # 同步 license
    #
    #installerSSH.setHosts(fullhostname_list)
    #eula_and_license_stuff(installerSSH, options, running_as)

    installerSSH.close()

    switch_status(status.StatusFinal(), options)

    LOG("Running upgrade logic")
    if not run_upgrades(running_as, options.mesadb_dba_user, executor):
        print "\nError: Problems upgrading your cluster. Please engage support."
        sys.exit(1)

def setup_agent_key(installerSSH, dba_user, dba_group, LOG):
    """Sets up the SSL key and certificate for the mesadb agent."""

    cfgdir = DBinclude.CONFIG_SHARE_DIR

    if os.path.exists( "/opt/mesadb/config/share/agent.key" ):
        return # nothing to do.

    # Create the SSL key locally
    if not mesadb.utils.ssl.ssl_key_gen(dba_user):
        LOG("\tError while generating SSL keys for agent communications.")
        LOG("\tSee the documentation for more details on how to update/generate")
        LOG("\ta SSL certificate for mesadb agents")
        return

    # 发送 SSL 到集群的其他节点,key around the cluster and setup permissions/ownership
    SSH.scpToPool(installerSSH, cfgdir + "/agent.key")
    SSH.scpToPool(installerSSH, cfgdir + "/agent.cert")
    SSH.scpToPool(installerSSH, cfgdir + "/agent.pem")
    installerSSH.execute("chown %s:%s %s" % ( dba_user, dba_group, cfgdir + "/agent.key" ) )
    installerSSH.execute("chown %s:%s %s" % ( dba_user, dba_group, cfgdir + "/agent.cert" ) )
    installerSSH.execute("chown %s:%s %s" % ( dba_user, dba_group, cfgdir + "/agent.pem" ) )
    installerSSH.execute("chmod 400 %s/agent.key" % cfgdir)
    installerSSH.execute("chmod 400 %s/agent.cert" % cfgdir)
    installerSSH.execute("chmod 400 %s/agent.pem" % cfgdir)


def system_prerequisite_checks(installerSSH, localhost, options):
    """Runs system prerequisite checks on the hosts defined in installerSSH"""

    thresh = options.failure_threshold

    verify_o = {
            'username' : options.mesadb_dba_user,
            'dbahome' : options.mesadb_dba_user_dir,
            'dbagroup' : options.mesadb_dba_group,
            'dry_run' : bool(options.no_system_configuration),
            'failure_threshold' : thresh }

    if not SSH.do_local_verify(installerSSH, localhost, options=verify_o):
        print "System prerequisites failed.  Threshold = %s" % thresh
        print "\tHint: Fix above failures or use --failure-threshold\n"
        sys.exit(1)
    else:
        print "System prerequisites passed.  Threshold = %s\n" % thresh


def eula_and_license_stuff(installerSSH, options, running_as):
    if options.accept_eula:
        fp = open(DBinclude.CONFIG_DIR +"/d5415f948449e9d4c421b568f2411140.dat","w")
        fp.write("S:a\n")
        fp.write("T:"+ str(time.time())+"\n")
        fp.write("U:"+ str( os.geteuid() ) +"\n")
        # compute the hash of the EULA file
        eula_file = open( DBinclude.binDir+"/d237f83d0a61c3594829a574c63530b.dat")
        md5hash = hashlib.md5()
        for line in eula_file.readlines():
            md5hash.update(line)
        fp.write("EULA Hash:"+md5hash.hexdigest() + "\n")

        fp.close()
        SSH.scpToPool(installerSSH, DBinclude.CONFIG_DIR + "/d5415f948449e9d4c421b568f2411140.dat")


    # always try to set the permissions on this file during install. they
    # may have been set wrong by the -Y option
    installerSSH.execute("chown %s:%s  %s" % ( running_as, options.mesadb_dba_group, DBinclude.CONFIG_DIR + "/d5415f948449e9d4c421b568f2411140.dat" ) )
    installerSSH.execute("chmod 664 %s" % DBinclude.CONFIG_DIR + "/d5415f948449e9d4c421b568f2411140.dat" )

    # VER-26742
    # if no license is provided, do nothing
    # -L CE is provided, default to the CE license
    if options.license_file != None:
        license_file_to_install = options.license_file
        if license_file_to_install == "CE":
            license_file_to_install = "/opt/mesadb/config/licensing/mesadb_community_edition.license.key"

        xcc = commandLineCtrl.commandLineCtrl(False,False)

        # Install the license key (locally), printing warnings and errors if it
        # fails.  Returns 0 on success.  On success, copy the license key around
        if xcc.isValidLicenseKey(license_file_to_install) == 0:
            SSH.scpToPool(installerSSH, DBinclude.LICENSE_KEY)
            installerSSH.execute("chown %s:%s  %s" % ( options.mesadb_dba_user, options.mesadb_dba_group, DBinclude.LICENSE_KEY) )

    # fix some old outstanding permission issues
    if os.path.exists(DBinclude.LICENSE_KEY):
        installerSSH.execute("chown %s:%s  %s" % ( options.mesadb_dba_user, options.mesadb_dba_group, DBinclude.LICENSE_KEY) )

def run_install(option_parser):
    """Wraps `_main()` and returns an exit code"""

    exit_code = 0
    global g_install_status
    g_install_status = None
    try:
        switch_status(status.StatusNew(), None)
        options = option_parser()
        switch_status(status.StatusOptionValidation(), options)
        # Handles option validation and any options which quickly terminate the
        # program, such as --help and --record (does not return in those cases).
        # On error, raises an exception.
        _post_process_options(options)
        _main(options)
    except SystemExit as err:
        # The exception type raised when someone invokes sys.exit()
        exit_code = err.code
        if exit_code != 0:
            g_install_status.printFailure()
    except Exception as e:
        exit_code = 1
        g_install_status.printError(e)
    finally:
        adapterpool.AdapterConnectionPool_3.Instance().close()

    if exit_code == 0:
        g_install_status.printSuccess()

    g_install_status = None

    return exit_code

