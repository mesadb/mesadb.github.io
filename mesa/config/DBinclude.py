#
#
import sys, re, commands, os, os.path
import glob
from mesadb.config import DBname
import pwd

#License Auditing
NAG_FLAG = 0
NAG_COUNT= 0
NAG_MSG  = { }

# 常量
OS_UNSUPPORT = 0
# 不能描绘出一个变量(例如,OS支持)
CHECK_FAILED = -1
OS_RHEL4 = 1
OS_SUSE = 3
OS_FEDORA = 4
OS_RHEL5 = 5
OS_DEBIAN = 7

OS_RHEL4_S = "RHEL4"
OS_RHEL5_S = "RHEL5"
OS_SUSE_S = "SUSE"
OS_FEDORA_S = "FEDORA"
OS_DEBIAN_S = "DEBIAN"

OSNAME = DBname.OSSHORTNAME

# log flag
# 0: turned off
# 1: turned on
LOG = 0


# 确定基本的DB目录 DB_DIR:
# 安装目录为/opt/mesadb,
# PG_TESTOUT or TARGET in dev environments
DB_DIR = os.environ.get('PG_TESTOUT')

if (DB_DIR is None):
    DB_DIR = os.environ.get('TARGET')
    
if (DB_DIR is None):
    DB_DIR = '/opt/mesadb'

TMP_DIR = '/tmp'

ADMIN_DIR = sys.path[0]
if ADMIN_DIR == "":
    ADMIN_DIR = os.getcwd()
LCHK_DIR = ADMIN_DIR

CONFIG_DIR = os.path.join(DB_DIR,"config")
CONFIG_INFO_DIR = os.path.join(CONFIG_DIR,"configInfo")
CONFIG_SHARE_DIR = os.path.join(CONFIG_DIR,"share")
CONFIG_USER_DIR = os.path.join(CONFIG_DIR,"users")
ADMINTOOLS_CONF = os.path.join(CONFIG_DIR,"admintools.conf")

# 本地admintools注册license key.  通过commandLineCtrl.isValidLicenseKey()来安装.
# 使用 License 对于 database并不是必须的,但是当创建新的数据库时需要此 License.
LICENSE_KEY = os.path.join(CONFIG_SHARE_DIR, 'license.key')

OLD_SPREAD_CONF = os.path.join(CONFIG_DIR,"mspread.conf")

#  下列文件必须在bin目录下:
# $BINNAME, bootstrap-catalog
binDir  = os.path.join(DB_DIR,'bin')
binPath = os.path.join(binDir,DBname.dbname)
sbinDir = os.path.join(DB_DIR , 'sbin')
LOG_DIR = os.path.join(DB_DIR , "log")
SCRIPT_DIR = os.path.join(DB_DIR , "scripts")
HELP_DIR = os.path.join(binDir , "help")
if ( LCHK_DIR == "" ):
    LCHK_DIR = binDir

# 包信息
PACKAGES_DIR = os.path.join(DB_DIR, "packages")
PACKAGE_INSTALL_SCRIPT = "ddl/install.sql"
PACKAGE_UNINSTALL_SCRIPT = "ddl/uninstall.sql"
PACKAGE_ISINSTALLED_SCRIPT = "ddl/isinstalled.sql"
PACKAGE_DESC_FILE = "package.conf"

#
# 库目录
#
libDir = os.path.join(DB_DIR , 'lib')

# 设置bin路径
binPathCmdSetting = "PATH=%s:$PATH; export PATH" % binDir

#
# OSS 路径
OSS_DIR = os.path.join(DB_DIR, 'oss')

# python 执行文件
PYTHON_BINARY = os.path.join(OSS_DIR,"python/bin/python")
if not os.path.isfile(PYTHON_BINARY):
    PYTHON_BINARY = "python"

#
# python 共享目录
SHARE_DIR = os.path.join(DB_DIR,'share')
VERTICA_EGGS = os.path.join(SHARE_DIR,'eggs')

# 不确定是否有任何的缺省信息从其他的config文件获取.
dbDesignerConfig = os.path.join(CONFIG_INFO_DIR , "dbDesignerConfig")

# 在本主机中 RPM 文件全路径名称
rpmRHEL_SrcInfoFile = os.path.join(CONFIG_INFO_DIR , "rpmRHELInfo")
rpmFC4_SrcInfoFile = os.path.join(CONFIG_INFO_DIR , "rpmFC4Info")
rpmSUSE_SrcInfoFile = os.path.join(CONFIG_INFO_DIR , "rpmSUSEInfo")

# 在远程主机中 RPM 文件全路径名称
# admin tools 将从rpmXXX_SrcFile拷贝RPM文件到这.
# 使用它安装数据库系统
# 我不确定是否能够使用/tmp/usr, 因为文件是从其他地方拷贝过来的.
rpmDestFile = os.path.join(TMP_DIR , 'dbRPM.rpm')

# 下面是admin tool的日志文件. 此文件在启动时将被删除,
# 在运行时,记录日志到LOG-able.

adminToolLogUser = pwd.getpwuid(os.getuid())[0]
adminToolLog = os.path.join(LOG_DIR , "adminTools-%s.log" % adminToolLogUser)
adminToolErrorLog = os.path.join(LOG_DIR , "adminTools-%s.errors" % adminToolLogUser)
agentToolLog = os.path.join(LOG_DIR , "agentTool-%s.log" % adminToolLogUser)
uiMgrLog   = os.path.join(LOG_DIR , "uiMgr-%s.log" % adminToolLogUser)
uiMgrInput = None # if not None, uiMgr reads its input from this filename rather than the user

# 下列是允许策略的列表 -- 更新帮助文档!
RESTART_POLICY_LIST = ("never", "ksafe", "always")
# 下列是默认的主机重启策略
DEFAULT_RESTART_POLICY = "ksafe"
MAX_KSAFETY = 2
    
# Designer文件名称
designParamsFileSuffix = "_params.txt"
designSchemaFileSuffix = "_schema.xml"
designParamsFile = "design" + designParamsFileSuffix
redesignParamsFile = "redesign" + designParamsFileSuffix

designerErrorFile = "designer_error.msg"
designerLog = "designer.log"
designerDiagManifest = os.path.join(LOG_DIR , "DesignerDiagManifest.txt")


import copy

"""
返回DBinclude中代表所有域的一个格式化字符串
"""
def getStringRep():
    ret = ""
    vs = copy.copy(vars(sys.modules[__name__]))
    for v in sorted(vs.keys()):
        # 并不包含内部变量
        if (not v.startswith("__")):
                ret += "DBinclude.%s=%s\n" %(v, vs[v])
    return ret


if __name__ == '__main__':
    print getStringRep()
    

def help_url(cshid):
    short_version = re.search(r'^\d+\.\d+', DBname.PRODUCT_VERSION).group() + ".x"

    return DBname.DOC_CSH_URL_FORMAT % {
            'short_version' : short_version,
            'id' : cshid }
