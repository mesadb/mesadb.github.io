from __future__ import print_function

from ConfigParser import ConfigParser
from ConfigParser import NoSectionError
from FileLocker import FileLock
import os
import sys
import socket
import pickle
import traceback
import re
import time
import threading
import collections
import time
import shutil
import math

from mesadb.config import DBinclude
import mesadb.shared.util as util

from mesadb.config.DBinclude import ADMINTOOLS_CONF # for brevity

NodeInfoElement = collections.namedtuple('NodeInfoElement',
        [ 'node_name', 'host', 'catalog_dir', 'data_dir' ])

class Configurator:

    class DatabaseNotDefined( Exception ):
        def __init__(self, db ):
            Exception.__init__( self, "Database %s is not defined." % db )

    instance = None
    last_modified = None
    lock = threading.RLock()

    @staticmethod
    def Instance():
        """
        Callable method to get the singleton instance of this object.
        """
        Configurator.lock.acquire()
        try:
            with FileLock( ADMINTOOLS_CONF):
                if os.path.exists(ADMINTOOLS_CONF):
                    modified_time = time.localtime(os.path.getmtime(ADMINTOOLS_CONF))
                else:
                    modified_time = time.localtime() # now

                if Configurator.instance is None:
                    Configurator.instance = Configurator(ADMINTOOLS_CONF)
                    Configurator.last_modified = modified_time
                    return Configurator.instance

                # XXX: If True?  Once upon a time this worked. It was
                # accidentally disabled, it seems.  Can we successfully
                # reenable it?
                if True or Configurator.last_modified != modified_time:
                    Configurator.instance = Configurator(ADMINTOOLS_CONF)

            return Configurator.instance
        finally:
            Configurator.lock.release()

    @staticmethod
    def _transform_to_ip(name):
        # 从admintools移除 hostnames. 尝试解析hostnames到IP addresses.
        # 如果不成功,(i.e. 因为 DNS 此时不能工作) 单独留下.
        try:
            return util.resolve_to_one_ip(name)
        except StandardError as err:
            print("WARNING: Unable to resolve hostname %s found in admintools.conf." % name, file=sys.stderr)
            return name

    def _move_configdict_section(self, from_sec, to_sec):
        """Moves all of the values from (and removes) `from_sec` to `to_sec`

        Any values in `to_sec`, if it exists, will remain.  Values from
        `from_sec` will overwrite any shared keys.  `to_sec` will exist after a
        call here, even if `from_sec` does not.
        """

        if not self.configdict.has_section(to_sec):
            self.configdict.add_section(to_sec)

        if not self.configdict.has_section(from_sec):
            return

        for (key, value) in self.configdict.items(from_sec, raw=True):
            self.configdict.set(to_sec, key, value)

        self.configdict.remove_section(from_sec)

    def __load(self, filename):
        self.configdict.read(filename)

        ###################################################################
        # [Configuration] 进入self.config映射.
        #
        if self.configdict.has_section('Configuration'):
            self.config = dict(self.configdict.items('Configuration'))
        else:
            self.config = {}

        self.config.setdefault('controlmode',"broadcast")

        # last_port 保持了数据库最后使用的基本端口.
        # 新数据库能够被创建,使用下一个有效的端口集合(因此能够并发运行).
        # 对于配置接下来的逻辑将生成last_port,此配置并没有此值(例如. 更新逻辑).
        if "last_port" not in self.config:
            last_port = 0
            for db in self.listDatabases():
                dbport = self.configdict.get("Database:%s"%db,"port")
                if dbport and int(dbport) > last_port:
                    last_port = int(dbport)

            if last_port == 0:
                last_port = 5433

            self.configdict.set("Configuration","last_port",str(last_port))
            self.config['last_port'] = str(last_port)

        ###################################################################
        # [Cluster] 部分有一个单条目列出主机集合
        #
        self.cluster = self.configdict.get('Cluster', 'hosts').split(',')
        self.cluster = [ x.strip() for x in self.cluster if len(x.strip()) > 0 ]
        self.cluster = [ self._transform_to_ip(x) for x in self.cluster ]

        ###################################################################
        # [Nodes] 部分曾经是[sites]部分.
        # 每个数据库实例都有一个条目,带有唯一的实例名称.
        # 通常情况下,每个数据库都有节点的一个子集,
        # 如果不使用 --compat21,它们都是'node_xxxx'.
        #
        self._move_configdict_section('sites', 'Nodes')
        # self.sites: 节点名称到"addr,catalog,data"的映射
        self.sites = self.configdict.items('Nodes')

        # 映射site的主机到IP地址
        # 即使site值是畸形的,此部分也能够工作
        def map_site_to_ip(site):
            tmp = site.split(',', 1)
            tmp[0] = self._transform_to_ip(tmp[0])
            return ','.join(tmp)
        self.sites = [ (x, map_site_to_ip(y)) for (x,y) in self.sites ]
        for (name, data) in self.sites:
            self.configdict.set('Nodes', name, data)

        ###################################################################
        # [Database:*] 部分定义现有的数据库.
        # 迭代数据库擦掉不可用的host选项,可能包含一个主机名.
        #
        for db in self.listDatabases():
            section = "Database:%s" % db
            if self.configdict.has_option(section, 'host'):
                self.configdict.remove_option(section, 'host')

    def __init__(self, filename):
        """
        Constructor method - shouldn't be called.  Use Configurator.Instance()
        instead.
        """
        self.filename = filename
        self.configdict = ConfigParser()

        if filename is not None and os.path.exists( filename ):
            self.__load(filename)
        else:
            self.init_defaults()
            # 我们进行更新操作, 对于old icky admin格式进行更好的测试,
            # 同时从这构建配置.
            self._legacy_port()

        # 进入有空主机值的配置文件.
        # 清除空值. 同时也删除重复值.
        self.cluster = [ x.strip() for x in self.cluster if len(x.strip()) != 0 ]
        seen = set()
        uniq_cluster = []
        for x in self.cluster:
            if x not in seen:
                seen.add(x)
                uniq_cluster.append(x)
        self.cluster = uniq_cluster

        self.configdict.set("Cluster", "hosts", ','.join( self.cluster ))

    def init_defaults(self): 
        # 使用缺省的控制(重新)创建此文件.
        self.config = {}
        self.config['format'] = 3
        self.config['install_opts'] = ""
        self.config['default_base'] = "/home/dbadmin"  #@todo - fix for install variable
        self.config['controlmode'] = "broadcast"
        self.config['controlsubnet'] = "default"
        self.config['spreadlog'] = "False"
        self.config['last_port'] = "5433"

        self.cluster = []
        self.sites = []

        def clear_section(section):
            if self.configdict.has_section(section):
                self.configdict.remove_section(section)
            self.configdict.add_section(section)

        clear_section("Configuration")
        for (k,v) in self.config.iteritems():
            self.configdict.set("Configuration", k, v)

        # 清除集群. only has one value, hosts, which is empty.
        clear_section("Cluster")
        self.configdict.set("Cluster", "hosts", '')

        # 清除节点. Starts empty. (sites = [])
        clear_section("Nodes")

    def set_options(self, opts ):
        """
        Records the options used for install_mesadb so the user can look back
        at them.  They should not be pulled and parsed for any reason, since
        they are not reliably written and any sensitive values are scrubbed.
        """

        hide = [ "-p", "--dba-user-password", "-P", "--ssh-password"]

        for x in hide:
            if x in opts:
                opts[opts.index(x)+1] = "*******"

        val = util.shell_repr(opts)
        self.config['install_opts'] = val
        self.configdict.set("Configuration", "install_opts", val)

    def listDatabases(self):
        """ Returns a list of defined database names """
        # 每个数据库定义在 [Database:foo] 部分中.
        # 找到每个部分匹配的部分,同时返回 'foo'.
        pat = re.compile("^Database:")
        sections = [ d.split(":")[1] for d in self.configdict.sections() if pat.match(d) ]
        return sections

    def incluster(self, hostname ):
        """ Returns True if the given hostname is in the cluster. """
        return (hostname in self.cluster)

    def isdefined(self, database):
        """ Returns True if the given database is already defined. """
        return (database in self.listDatabases())

    def gethosts(self):
        """ Returns a list of hosts in the cluster (IP address strings) """
        return list(self.cluster)

    def getconfig(self, database):
        """
        return a diction of properties about the initial host
        in the database. Other classes will use this data to
        bootstrap the system.
        """
        if (not self.isdefined(database)):
            raise Configurator.DatabaseNotDefined( database )

        props = {}

        key = "Database:%s" % database

        options = self.configdict.options(key)
        for option in options:
            if option == 'nodes':
                props[option +"_new"] = []
                for n in self.configdict.get(key,option).split(','):
                    props[option +"_new"].append( self.getsiteconfig( n ))
            props[option] = self.configdict.get(key,option)
        props['id'] = database

        # upgrade from a daily bug fix
        # just default to never (the same as never setting it!)
        if not 'restartpolicy' in props.keys():
            props['restartpolicy'] = 'never';

        return props

    def addsite(self, nodename, host, catalog_base, data_base ):
        """ add a site to the configuration parameters """

        # 从admintools清除主机名称
        assert util.is_ip_address(host), \
                "All sites must be added by IP address (%s)" % host

        c = catalog_base
        d = data_base

        if c.endswith("/"):
            c = c[:len(c)-1]

        if d.endswith("/"):
            d = d[:len(d)-1]

        data = "%s,%s,%s" % ( host, c, d )
        self.configdict.set( "Nodes", nodename, data ) 
        self.sites.append( (nodename, data) )

    # getSite
    def getNode(self, node_name, or_none=False):
        rv = self.getNodeMap().get(node_name, None)
        if rv is None and not or_none:
            raise StandardError("Node not found: %s" % node_name)
        return rv

    # sites.
    def getNodeMap(self):
        all_nodes = {}
        for (node_name, data) in self.sites:
            data_list = data.split(',')
            assert len(data_list) == 3, "Error parsing Nodes section"

            all_nodes[node_name] = NodeInfoElement(
                    node_name = node_name,
                    host = data_list[0],
                    catalog_dir = data_list[1],
                    data_dir = data_list[2])

        return all_nodes

    def getNodeList(self):
        return self.getNodeMap().values()

    # 使用getNode(nodename)进行替换
    def getsiteconfig(self, nodename ):
        """
            return a dictionary of properties about the named
            node.
        """
        props = {}

        p = self.configdict.get("Nodes",nodename).split(',')
        props['host'] = p[0]
        props['catalog_base'] = p[1]
        props['data_base'] = p[2]
        props['id'] = nodename

        return props

    def setrestart(self, database, restart_policy ):
        """
          set the restart policy for a given database
        """
        key = "Database:%s" % database
        self.configdict.set(key, "restartpolicy", restart_policy)

    def setcontrolmode(self, controlmode):
        """
          Set the mode that spread uses (broadcast or pt2pt)
        """
        self.configdict.set('Configuration','controlmode',controlmode)

    def setcontrolsubnet(self, controlsubnet):
        """
          Set the subnet that control (spread) traffic goes over
        """
        self.configdict.set('Configuration','controlsubnet',controlsubnet)

    def setspreadlogging(self, path):
        self.configdict.set('Configuration','spreadlog',path)

    def setlargecluster(self, count):
        csize = len(self.gethosts())
        if (count == 'off'):
            self.configdict.remove_option('Configuration','largecluster')
            count = 0
        elif (count == 'default'):
            minc = min(csize,3)
            count = max(int(math.sqrt(csize)),minc)
        else:
            count = max(1,min(128,csize,int(count)))
        self.configdict.set('Configuration','largecluster',str(count))
        return count

    def save(self, nolock=False ):
        """
        simple method to force the file to write itself to disk
        this method must be explictly called or else changes will
        not be saved.
        """

        Configurator.lock.acquire()
        try:
            if nolock:
                with open( self.filename, "w" ) as f:
                    self.configdict.write( f )
            else:
                with FileLock( ADMINTOOLS_CONF):
                    with open( self.filename, "w" ) as f:
                        self.configdict.write( f )
        finally:
            Configurator.lock.release();

        from mesadb.tools import DBfunctions
        DBfunctions.record("Saved %s -> %s" % (str(self), ADMINTOOLS_CONF))

    def addhost(self, host):
        """Adds a host to the cluster.  Forcibly changes to an IP address."""
        # 在admintools.conf中没有主机名称
        assert util.is_ip_address(host), \
                "All hosts must be added by IP address (%s)" % host
        if not self.incluster(host):
            self.cluster.append(host)
            self.configdict.set( "Cluster", "hosts", ",".join(self.cluster))
        return host

    def add( self, database, path, port, sites, restart="ksafe" ):
        """
        add a database to the configuration.
        only the initial 'startup' node needs to be
        defined -- we'll ask the catalog for the
        rest of the information on restarts.
        """
        if ( not self.isdefined( database )):

            key = "Database:%s" % database
            self.configdict.add_section( key )
            self.configdict.set( key, "restartpolicy", restart)
            self.configdict.set( key, "port", "%s"%port)
            self.configdict.set( key, "path", path)
            self.configdict.set( key, "nodes", ",".join(sites))



    def update(self, database, path=None, port=None, nodes=None):
        """
        update the properties of a database.  you can supply
        a subset of the values, in which case the current values
        will continue to apply.
        """
        if not self.isdefined(database):
            return

        props = self.getconfig(database)

        d = path
        p = port
        n = ""
        if nodes != None: 
            n = ",".join(nodes)
        if d == None: d = props['path']
        if p == None: p = props['port']
        if n == None: n = props['nodes']

        key = "Database:%s" % database
        self.configdict.set( key, "port", "%s"%p)
        self.configdict.set( key, "path", d)
        self.configdict.set( key, "nodes", n)

    def remove(self,name,type='database' ):
        """
        remove a database or  host from the
        configuration.  defaults to databases
        set type to 'host' to remove a  host.

        WARNING: this only removes the info
        from the configuration file. 
        """

        if ( type == 'database' and self.isdefined(name)):
            self.configdict.remove_section( "Database:%s" % name )

        if ( type == 'host'):
            self.cluster.remove(name)
            self.configdict.set( "Cluster", "hosts", ",".join(self.cluster))
        if ( type == 'site'):
            self.configdict.remove_option("Nodes",name);

    def remove_node_from_db(self, database, nodename ):
        key = "Database:%s" % database
        nodes  = self.configdict.get(key, 'nodes').split(',')
        idx = 0
        for n in nodes:
            if n == nodename:
                del( nodes[idx] )
            idx += 1
        self.configdict.set( key,'nodes', ','.join(nodes))
        self.save()

    def __str__(self):
        databases = self.listDatabases()
        return "Configurator(clusterSize=%s, dbs=(%s))" % (
                len(self.gethosts()), ','.join(databases))

    def _legacy_port(self):
        """Load the legacy configuration"""

        print("Upgrading admintools meta data format..", file=sys.stderr)
        print("scanning %s/config/users" % DBinclude.DB_DIR, file=sys.stderr)
        userdirs = []
        try:
            userdirs = os.listdir("%s/config/users"% DBinclude.DB_DIR)
        except:
            pass

        ports  = self._load_dict("%s/config/share/portinfo.dat" % DBinclude.DB_DIR )
        if ports is None:
            ports = {}
        self.configdict.set("Configuration","last_port",ports.get("base","5433"))

        for dir in userdirs:
            try:
                sites  = self._load_dict( "%s/config/users/%s/siteinfo.dat"%(DBinclude.DB_DIR ,dir) )
                # if siteinfo.dat fails to load, forget about it.
                if sites is None:
                    continue

                for node in sites.values():
                    if not self.incluster(node[1]):
                        self.addhost(node[1])

                    if not self.configdict.has_section( "Nodes" ):
                        self.configdict.add_section("Nodes")

                    c = node[2]
                    d = node[3]
                    if c.endswith("/"):
                        c = c[:len(c)-1]

                    if d.endswith("/"):
                        d = d[:len(d)-1]

                    try:
                        self.configdict.set( "Nodes", node[0],  ','.join([socket.gethostbyname_ex(node[1])[2][0],c, d]))
                    except:
                        self.configdict.set( "Nodes", node[0],  ','.join([node[1],c, d]))

                shutil.move(sites, "%s.old.%s" % (sites, time.time()))
                dbinfo = self._load_dict("%s/config/users/%s/dbinfo.dat"%(DBinclude.DB_DIR ,dir) )

                if dbinfo is not None:
                    databases = dbinfo['defined'].keys()
                    for db in databases:
                        if not self.isdefined(db):
                            startinfo = dbinfo['startinfo'][db] 
                            try:
                                host = socket.gethostbyname_ex(startinfo[6][0])[2][0]
                            except:
                                host = startinfo[6][0]
                            path = startinfo[0]
                            port = 5433

                            try:
                               port = ports[1]['assignments'][db]
                            except:
                               pass

                            policy = "never"
                            try:
                                if 'restartpolicy' in dbinfo.keys():
                                    if db in dbinfo['restartpolicy'].keys():
                                        policy = dbinfo['restartpolicy'][db]
                            except:
                                pass

                            self.add(db, path, port, dbinfo['defined'][db], policy)

                shutil.move(dbinfo, "%s.old.%s" % (dbinfo, time.time()))

            except Exception as e:
                traceback.print_exc()
                print("failed to convert meta-data for %s: %s" % (dir, str(e)),
                        file=sys.stderr)

    def _load_dict( self, fileName ):
        try:
            with open( fileName, "r" ) as f:
                return pickle.load(f)
        except IOError:
            return None
