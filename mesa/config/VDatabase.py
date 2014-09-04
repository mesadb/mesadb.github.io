from mesadb.config import DBinclude
from mesadb.tools import CatalogEditor

import json
from json import JSONDecoder
from json import JSONEncoder
import sys
from stat import *
import os
import os.path

def runVsql(vsql,cmd):
    status, result = vsql.executeSql(cmd)
    #print "Cmd: '%s'\nStatus: %s\nResult: %s"%(cmd,status,result)
    if not status:
        return []
    else:
        return result

class VNode:
    def __init__(self):
        self.name = "unknown"
        self.catalogpath = ""
        self.storagelocs = []
        self.host = "127.0.0.1"
        self.port = 5433

    def createFromMap(self, infomap):
        self.name = infomap['name']
        self.oid = infomap['oid']
        self.catalogpath = infomap['catalogpath']
        self.storagelocs = [x for x in infomap['storagelocs']] # make a copy
        self.host = infomap['host']
        self.port = infomap['port']
        self.controlnode = infomap['controlnode']
        self.startcmd = infomap['startcmd']

    def createFromEditor(self, ce, name):
        self.name = name
        nodedeets = ce.sendShow("show name Node %s" % self.name)
        self.oid = nodedeets['oid']
        self.catalogpath = os.path.dirname(nodedeets['catalogPath'])  # pick off the /Catalog dir
        self.host = nodedeets['address']
        self.port = nodedeets['clientPort']
        self.controlnode = nodedeets['controlNode']
        # get storagelocs later
        self.startcmd = ce.sendCmd("startcmd %s" % self.name).strip()

    def createFromVSQL(self, vsql, name):
        cmd_results = runVsql(vsql,"select oid,name,address,catalogpath,clientport,controlnode from v_internal.vs_nodes where name = '%s';"%(name))
        vals = cmd_results[0].split("|")
        self.name = vals[1]
        self.oid  = vals[0]
        self.catalogpath = os.path.dirname(vals[3])                  # pick off the /Catalog dir
        self.host = vals[2]
        self.port = vals[4]
        self.controlnode = vals[5]
        self.storagelocs = runVsql(vsql,"select path from v_internal.vs_storage_locations where site = %s;"%(self.oid))
        self.startcmd = runVsql(vsql,"select mesadb_start_command('%s');" % self.name)[0]

    def addLocation(self, path):
        self.storagelocs.append(path)

    def convertToMap(self):
        result = {"name" : self.name,
                  "oid"  : self.oid,
                  "catalogpath" : self.catalogpath,
                  "storagelocs" : [x for x in self.storagelocs],  # make a copy
                  "host" : self.host,
                  "port" : self.port,
                  "controlnode" : self.controlnode,
                  "startcmd" : self.startcmd}
        return result

    def validatePaths(self):
        if not os.path.exists(self.catalogpath):
            return False
        for x in self.storagelocs:
            if not os.path.exists(x):
                return False
        return True

    def setPerms(self):
        for x in [self.catalogpath] + self.storagelocs:
            os.chmod(x,S_IRUSR | S_IWUSR | S_IXUSR)

    def startDbStr(self, extraoptions):
        # set path first?
        return "%s %s >> %s 2>&1"%(self.startcmd,extraoptions,
                                   os.path.join(os.path.dirname(self.catalogpath),"dbLog"))

    def statusDbStr(self, binary):
        return "%s --status -D %s || ps -C \"%s\" -o args | grep -F \"%s\"" % (binary, 
                                                                               self.catalogpath,
                                                                               os.path.basename(binary),
                                                                               self.catalogpath)

    # only works with a single storage location
    def bootstrapDbStr(self, binDir, dbName, configParams={}):
        return "%s/bootstrap-catalog %s" % (binDir,
                                            " ".join(["-C %s" % binDir,
                                                      "-H %s" % dbName,
                                                      "-s %s" % self.host,
                                                      "-D %s" % self.catalogpath,
                                                      "-S %s" % self.storagelocs[0],
                                                      "-p %s" % self.port] +
                                                     ["-X '%s=%s'"%(x[0],x[1]) for x in configParams.iteritems()]))

    def makeCreateNodeStr(self):
        return """
  CREATE NODE %s HOSTNAME '%s' DATAPATH '%s' CATALOGPATH '%s' PORT %s;
""" % (self.name,self.host,",".join(["'%s'"%x for x in self.storagelocs]),self.catalogpath,self.port)


class VDatabase:

    def __init__(self, jsonString=None,editor=None,vsql=None):
        self.nodes = []
        self.name = "unknown"
        self.flags = {}
        self.nametonode = {}
        self.oidtonode = {}
        self.version = 0
        self.spreadversion = 0
        self.controlmode = "broadcast"
        self.deps = []
        self.willupgrade = False
        if jsonString:
            self.fromString(jsonString)
        elif editor:
            self.loadFromCatalog(editor)
        elif vsql:
            self.loadFromVSQL(vsql)

    def loadFromCatalog(self, ce):
        self.name = ce.sendCmd("get singleton Database name").strip()
        self.deps = [x.split(",") for x in ce.sendCmd("nodedeps table").splitlines()]
        versions = ce.sendCmd("versions").splitlines()
        for v in versions:
            if not v:
                continue
            elem,ver = v.split()
            if elem == "GLOBAL":
                self.version = int(ver)
            elif elem == "SPREAD":
                self.spreadversion = int(ver)
        self.controlmode = ce.sendCmd("get singleton GlobalSettings controlMode").strip()
        allnodeslist = ce.sendCmd("list Node").strip()
        allnodenames = [x.partition(' ')[2].partition(':')[2] for x in allnodeslist.split("\n")]
        self.nametonode = {}
        self.oidtonode = {}
        for nodename in allnodenames:
            vn = VNode()
            vn.createFromEditor(ce,nodename)
            self.addNode(vn)
        # now get storage locations
        stlocs = ce.sendCmd("table StorageLocation site path").strip().split("\002")[1:]
        for loc in stlocs:
            if not loc:
                continue
            parts = loc.partition("\001")
            
            self.nodes[self.oidtonode[int(parts[0])]].addLocation(parts[2])
        self.willupgrade = ce.sendCmd("willupgrade").strip() == "True"

    def loadFromVSQL(self, vsql):
        self.name = runVsql(vsql,"select name from v_internal.vs_databases;")[0]
        self.deps = [x.split(",") for x in runVsql(vsql,"select get_node_dependencies('table');") if x]
        versions = runVsql(vsql,"select get_catalog_versions();")
        for v in versions:
            if not v:
                continue
            elem,ver = v.split()
            if elem == "GLOBAL":
                self.version = int(ver)
            elif elem == "SPREAD":
                self.spreadversion = int(ver)
        self.controlmode = runVsql(vsql,"select controlmode from v_internal.vs_global_settings;")[0]
        nodelist = runVsql(vsql,"select name from v_internal.vs_nodes;")
        self.nametonode = {}
        self.oidtonode = {}
        for nodename in nodelist:
            vn = VNode()
            vn.createFromVSQL(vsql,nodename)
            self.addNode(vn)
        # storage locations are done already
        # willUpgrade is certainly false if the db is running

    def loadFromMap(self, result):
        if not result:
            return
        rawnodes = result['nodes']
        for x in rawnodes:
            vn = VNode()
            vn.createFromMap(x)
            self.addNode(vn)
        self.flags   = result['flags']
        self.name    = result['name']
        self.version = result['version']
        self.spreadversion = result['spreadversion']
        self.controlmode   = result['controlmode']
        self.deps          = result['deps']
        self.willupgrade   = result['willupgrade']

    def fromString(self, jsonString):
        self.loadFromMap(json.loads(jsonString))

    def saveToMap(self):
        output = {}
        rawnodes = []
        for x in self.nodes:
            rawnodes.append(x.convertToMap())
        output['nodes'] = rawnodes
        output['flags'] = self.flags
        output['name'] = self.name
        output['version'] = self.version
        output['spreadversion'] = self.spreadversion
        output['controlmode'] = self.controlmode
        output['deps'] = self.deps
        output['willupgrade'] = self.willupgrade
        return output               

    def isValid(self):
        return self.version > 0

    def betterThan(self,otherdb):
        return self.version > otherdb.version

    def toString(self):
        return json.dumps(self.saveToMap(),indent=1)

    def getHosts(self, nodes = []):
        return [x.host for x in self.nodes if not nodes or x in nodes]

    def getNodeByName(self, name):
        if name not in self.nametonode:
            return None
        else:
            return self.nodes[self.nametonode[name]]

    def isLargeCluster(self):
        for n in self.nodes:
            if n.oid != n.controlnode:
                return True
        return False

    def isSpreadNode(self,nodename):
        if nodename not in self.nametonode:
            return False
        n = self.nodes[self.nametonode[nodename]]
        return n.oid == n.controlnode

    def getK(self):
        # start with max K value given node count
        k = (len(self.nodes)-1)//2
        # adjust for actual dependencies
        for dep in self.deps:
            depk = len(dep) - 1;
            if depk < k:
                k = depk
        return k

    def findUnsatisfiedDependencies(self,downnodes):
        downset = set(downnodes)
        unsat = []
        for dep in self.deps:
            if set(dep).issubset(downset):
                unsat.append(dep)
        return unsat

    def addNode(self,vn):
        index = len(self.nodes)
        self.nodes.append(vn)
        self.nametonode[vn.name] = index
        self.oidtonode[int(vn.oid)] = index

def readAndOutputJSON(catalogdir, silent):
    if not os.path.exists(catalogdir) or not os.path.exists(os.path.join(catalogdir,"Catalog")):
        if silent:
            print "{}"
        else:
            print "No catalog found at path %s" % catalogdir
        return
        
    ce = CatalogEditor.CatalogEditor(catalogdir,DBinclude.binPath, zippy = True)

    db = VDatabase()
    db.loadFromCatalog(ce)

    print db.toString()

    ce.close()

# hook for remote loading - read catalog and output JSON
if __name__ == '__main__':
    readAndOutputJSON(sys.argv[1], len(sys.argv) > 2 and sys.argv[2] == "silent")

