import pwd
import grp
import sys
import os
import os.path
import socket
import pickle
import commands
import rein
import copy
import stat
import string
from optparse import OptionParser
import math

from mesadb.utils import pexpect
from mesadb.utils.vException import vException
from mesadb.config.Configurator import Configurator
from mesadb.tools import DBfunctions
from mesadb.network import SSH, vsql
from mesadb.config import DBname
from mesadb.config import DBinclude
import time
import fcntl
import struct
import shutil
from mesadb.designer import Designer
from mesadb.log.InstallLogger import InstallLogger
import traceback
from mesadb.network import adapterpool
# 发现 spread 通信节点的相关信息
def discover_spread_info():
    # 主要包括controlsubnet,模式,日志,端口和集群节点数量的设置
    # 其中controlsubnet 为 spread 子网
    spreadInfo = {'controlsubnet': 'default', 'mode': 'broadcast', 
                  'logging': 'False', 'port': '4803', 'largecluster': '128'}

    # 假设mspread.conf配置文件比较小,因此比较适合保存在内存中
    mspread = ""
    with open(os.path.join(DBinclude.CONFIG_DIR,"mspread.conf"),'r') as f:
        mspread = f.read()
    # 读取mspread文件中特定的配置属性项
    segs = re.findall(r"^Spread_Segment\s+([0-9.]+):([0-9]+)",mspread,re.S|re.M)
    nodes = re.findall(r"^\s+N[0-9]+\s+([0-9.]+)\s+{",mspread,re.S|re.M)
    logging = re.findall(r"^\s*EventLogFile\s*=\s*([^\n]+)\n",mspread,re.S|re.M)

    # 从 mesadb 的配置文件中获得主机信息:
    # file's location is mesadb/share/eggs/mesadb/config
    c = Configurator.Instance()
    hosts = c.gethosts()

    # 如果DB集群的节点分布于多个Spread_Segments当中,则设置为pt2pt模式.
    if len(segs) == len(nodes):
        spreadInfo['mode'] = 'pt2pt'

    # 如果 DB集群的节点比主机服务器数量少,则设置为largecluster模式.
    if len(nodes) < len(hosts):
        spreadInfo['largecluster'] = len(nodes)

    # 如果服务器主机 IP 地址没有出现在 spread node IP 列表当中,则它们处于不同的IP子网当中
    #
    found = False
    for h in hosts:
        if h in nodes:
            found = True
            break
    # controlsubnet使用在config文件中找到的首个子网
    if not found:
        spreadInfo['controlsubnet'] = segs[0][0]

    # 找到 spread 端口(假设所有的segments都使用相同的端口)
    if segs and segs[0][1] != spreadInfo['port']:
        spreadInfo['port'] = segs[0][1]

    # 是否启用了日志?
    if logging and logging[0].strip() != "/dev/null":
        spreadInfo['logging'] = 'True'

    # 返回spreadInfo信息
    return spreadInfo

# 设置worker instance的信息和master instance信息
def generate_editor_script(nodeinfos, clustersettings):
    script = ["unlock danger"]
    #设置worker instance的信息
    for node in nodeinfos:
        script.append("set name Node %s address %s" % (node['node'],node['address']))
        script.append("set name Node %s clientPort %s" % (node['node'],node['port']))
        script.append("set name Node %s controlAddress %s" % (node['node'],node['controlAddress']))
        script.append("set name Node %s controlBroadcast %s" % (node['node'],node['controlBroadcast']))
        script.append("set name Node %s controlPort %s" % (node['node'],node['controlPort']))

    #设置master instance的信息
    script.append("set singleton GlobalSettings controlMode %s" % (clustersettings['mode']))
    script.append("set singleton GlobalSettings numControlNodes %s" % (clustersettings['largecluster']))
    script.append("set singleton GlobalSettings controlLog %s" % (clustersettings['log']))
    if clustersettings['logflags'] != "":
        script.append('set singleton GlobalSettings controlDebugFlags "%s"' % clustersettings['logflags'])

    #设置完成,重写spreadconf配置文件
    script.append("repairlargecluster")
    script.append("commit")
    script.append("spreadconf overwrite")
    script.append("versions")
    script.append("")
    return "\n".join(script)

# 找到catalog最新版本的最佳主机
def find_highest_catversion_hosts(result,nodes,hostindexes):
    highestglobalversion = 0
    besthost = []
    for host,output in result.iteritems():
        #print host,output
        if output[0] == '0':
            gv = re.findall(r"^GLOBAL\s+([0-9]+)","\n".join(output[1]),re.S|re.M)
            if not gv:
                print "WARNING: No GLOBAL catalog version in response from %r(%s) of spread catalog edit"%(nodes[hostindexes[host]],host)
                continue
            catversion = int(gv[-1])
            # 获得highest_global_version信息和best_host信息
            if catversion > highestglobalversion:
                highestglobalversion = catversion
                besthost = [host]
            elif catversion == highestglobalversion:
                besthost.append(host)
            else:
                print "WARNING: catalog edit FAILED on node %r (%s)"%(nodes[hostindexes[host]],host)
    return besthost

# 更新spread 的集成信息
def upgrade_integrate_spread(running_as, userName, aexec):
    # 获得配置文件中的配置信息
    cfg = Configurator.Instance()
    
    # 获得到所有主机的连接
    allhosts = cfg.gethosts()
    # 从适配器连接池获得实例
    pool = adapterpool.AdapterConnectionPool_3.Instance()
    pool.root_connect(allhosts, running_as)
    # 连接池设置主机
    pool.setHosts(allhosts)

    # 连接池获得首个本地主机
    localhost = pool.first_local_host()
    if localhost is None:
        # An important precondition has not be met. Should not see this happen.
        _show("Error: Local node is not in the cluster?  Cannot run upgrade logic")
        return False


    # 如果任何主机都有 /opt/mesadb/config/mspread.conf, 当进行版本升级时,
    # 请使用 XXX 命令来收集spread.conf配置文件的命令
    status, result = pool.execute("[ -e %s ]"%DBinclude.OLD_SPREAD_CONF)
    needsupgrade = [host for host,output in result.iteritems() if str(output[0]) == '0']
    if len(needsupgrade) == 0:
        _show("No spread upgrade required: /opt/mesadb/config/mspread.conf not found on any node")
        return True

    _show("Spread upgrade required.  Some nodes have a shared/legacy mspread.conf")


    # 处理如下应用场景,并不是所有的主机都有一个共享的mspread.conf.
    # 它可能是一个有效的配置文件,也可能无效,那么检查配置文件之间的不一致.
    if len(needsupgrade) < len(allhosts):
        _show("Warning: Not all hosts have a shared mspread.conf. Found on: %s" %
                ', '.join(needsupgrade))

        # 检查任何可能已经升级的主机,我们将拒绝运行升级程序,因为它是非标准的.
        # 在如下应用场景,一个带有mspread.conf的节点被添加到集群中,而这个配置文件是旧的配置文件,
        # 那么我们将忽略它.
        status, result = pool.execute("[ -e %s.preupgrade ]"%DBinclude.OLD_SPREAD_CONF)
        alreadyupgraded = [host for host,output in result.iteritems() if str(output[0]) == '0']
        if len(alreadyupgraded) > 0:
            _show("Warning: Some hosts already upgraded (found mspread.conf.preupgrade): %s" %
                   ', '.join(alreadyupgraded))
            _show("Warning: Assuming databases are already upgraded.  Not running spread upgrade.")
            mark_upgrade_complete(pool, allhosts)
            return True

        # 如果本地没有 mspread.conf 配置文件,那么我们需要从其他的主机上查找一份配置文件.
        if localhost not in needsupgrade:
            _show("Fetching shared mspread.conf from %s" % needsupgrade[0])
            (status, results) = adapterpool.copyRemoteFilesToLocal(pool,
                    DBinclude.OLD_SPREAD_CONF,      # remote file
                    [ needsupgrade[0] ],            # remote hosts (just 1)
                    DBinclude.OLD_SPREAD_CONF)      # local file pattern


    # 解析mspread.conf,保存已经发现的信息到集群配置中

    # 发现spread设置
    spreadInfo = discover_spread_info()
    _log("Discovered spread info: %r" % spreadInfo)

    # 将msperad.conf配置信息写入admintools.conf中
    cfg.setcontrolmode(spreadInfo['mode'])
    cfg.setcontrolsubnet(spreadInfo['controlsubnet'])
    cfg.setspreadlogging(spreadInfo['logging'])
    cfg.setlargecluster(spreadInfo['largecluster'])
    cfg.save()

    # 发布发现信息到集群中
    SSH.sync_admintools_conf(pool, userName, hosts=allhosts)

    # 在每个数据库中,运行update命令, 通过 catalog editor 来实现此项功能.
    # 我们收集每个节点的必要信息来运行,然后为每个数据库执行 `upgrade_db`.

    # 重新计算网络信息
    success, profiles = SSH.getNetworkProfiles(allhosts,running_as,spreadInfo['controlsubnet'])

    # 集群设置
    clustersettings = {
            'mode': spreadInfo['mode'],
            'logflags': "",
            'largecluster': spreadInfo['largecluster']}
    
    # 日志记录成员关系视图
    if spreadInfo['logging'] == 'True':
        clustersettings['logflags'] = "CONFIGURATION MEMBERSHIP PRINT EXIT"

    success = True

    # 升级数据库
    for db, nodes in aexec.getDBInfo()["defined"].iteritems():
        if not upgrade_db(pool, db, nodes, clustersettings, profiles, aexec, spreadInfo['port'], userName):
            success = False

    # 标记升级已经完成
    if success:
        mark_upgrade_complete(pool, allhosts)
        return True
    else:
        _show("Error: Unable to apply upgrade to all databases.")
        _show("Hint: See logs, then run installer again to retry.")
        return False

# 标记升级已经完成
def mark_upgrade_complete(pool, allhosts):
    # 通过更新 mspread.conf 来完成升级
    _show("Marking spread upgrade complete on all hosts")
    # 设置主机列表
    pool.setHosts(allhosts)
    cmd = "mv -f %(f)s %(f)s.preupgrade" % { 'f' : DBinclude.OLD_SPREAD_CONF }
    # 执行升级命令
    pool.execute(cmd)

def upgrade_db(pool, db, nodes, clustersettings, profiles, aexec, spreadport, userName):
    # `db` 和 `nodes` 是dbDict中的key和value
    #
    # `clustersettings` 显示了cluster的连接方式和状态
    #
    # `profiles` 是SSH.getNetworkProfiles主机到网络的描述信息的映射表
    #
    # `aexec` 是一个adminExec进程
    #
    # spreadport 是 spread 运行的端口. 如果 DB 没有运行在这个端口上,那么我们将改变此值.

    nodeDict = aexec.getNodeInfo()
    dbDict = aexec.getDBInfo()

    clustersettings = dict(clustersettings) # copy
    if 'logflags' in clustersettings:
        clustersettings['log'] = os.path.join(dbDict["startinfo"][db][3],"spread.log")
    else:
        clustersettings['log'] = "/dev/null"

    _show("Upgrading database '%s' ..." % db)
    _show("(For databases with large catalogs, this may take some time.)")
    _log("Upgrading database %s : cluster settings = %r " % (db, clustersettings))

    nodeinfos = []      # per-node catalog information (for script generation)
    nodehosts = []      # hosts on which to run the editor

    # 如果 DB 没有运行在端口'XXXX'上, 我们设置 spread 端口为'XXXX+2'
    dbport = aexec.getPortNo(db)
    if str(dbport) != "XXXX":
        spreadport = str(int(dbport)+2)

    for node in nodes:
        host = nodeDict[node][1]
        nodehosts.append(host)
        info = {'node': node,
                'address': host,
                'port': dbport,
                'controlAddress': profiles[host][0],
                'controlBroadcast': profiles[host][1],
                'controlPort': spreadport}
        nodeinfos.append(info)
        _log("db %s, host %s : %r" % (db, host, info))

    # 生成一个 catalog editor 脚本,将其写入到文件中
    # 发送此文件给集群的其他节点
    cateditorscript = generate_editor_script(nodeinfos, clustersettings)
    scriptpath = os.path.join(DBinclude.TMP_DIR,"mesadb-cateditor.script")
    with open(scriptpath,'w') as f:
        f.write(cateditorscript)
    adapterpool.copyLocalFileToHosts(pool, scriptpath, nodehosts, scriptpath)

    ## TODO only run cateditor script on nodes with the highest catversion??

    # 批量运行所有节点上的脚本
    cmds = {}
    hostindexes = {}
    for i in range(len(nodes)):
        catalogPath = os.path.join(dbDict["startinfo"][db][3],     # base cat path
                                   dbDict["startinfo"][db][7][i])  # node cat path
        cmd = "sudo -u %s %s -D '%s' -Ebatch < %s" % (userName,os.path.join(DBinclude.binDir,'mesadb'),
                                                      catalogPath,scriptpath)
        host = nodeDict[nodes[i]][1]
        hostindexes[host] = i
        cmds[host] = cmd

    pool.setHosts(nodehosts)
    status, result = pool.execute(cmds, timeout=10*60)
    if not status:
        _show("Warning: some nodes failed to run the upgrade. This should self-recover.")
        for (host, output) in result.iteritems():
            if str(output[0]) != '0':
                _show("failed upgrade: %s" % host)

    # get highest GLOBAL cat version, scp that spread.conf around the cluster
    besthost = find_highest_catversion_hosts(result,nodes,hostindexes)

    if not besthost:
        _show("Error: Unable to apply upgrade.")
        _show("""Error applying spread configuration upgrade.
Copy /opt/mesadb/config/mspread.conf to catalog directory of all nodes.
The database %r will not support add/remove/replace nodes until underlying issue is resolved.
""" % db)
        return False

    # 同步数据库中的集群节点的配置信息
    node = nodes[hostindexes[besthost[0]]]
    _show("Distributing new config from node %r around the cluster"%node)
    pool.setHosts(nodehosts)
    aexec.synchronizeDatabaseConfig(db,nodeDict[node], [nodeDict[node] for node in nodes], pool=pool)
    return True

def _log(msg):
    DBfunctions.record(msg)

def _show(msg):
    print msg
    DBfunctions.record(msg)
