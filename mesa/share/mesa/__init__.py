"""MesaDB python libraries"""

from __future__ import absolute_import

import os
import sys
import inspect

def _include_egg_deps():
    """Appends the eggs in the parent directory to sys.path"""
    # TODO: May want to find a more pythonic way of doing this.  This works only
    # because of conventions that we're careful not to change.  Ideally the
    # python path should be set up correctly, e.g. via env $PYTHON_PATH

    def parent_n(path, n):
        """Gives the n'th parent."""
        for i in range(0, n):
            path = os.path.dirname(path)
        return path
    # 获得检查文件的目录
    this_file = os.path.abspath(inspect.getfile(_include_egg_deps))
    this_real_file = os.path.realpath(this_file)

    options = [ parent_n(this_file, 2) , parent_n(this_real_file, 2) ]

    eggs_added = {}
    
    # 列出目录
    for dir in options:
        for fname in os.listdir(dir):
            if fname.endswith('.egg') and not fname in eggs_added:
                sys.path.append(os.path.join(dir, fname))
                eggs_added[fname] = os.path.join(dir, fname)

    return eggs_added

_found_eggs = _include_egg_deps()

# 输出所有 eggs
def _main():
    """When run directly, prints all the eggs found and from where."""
    print "Eggs added to sys.path:"
    for (egg, location) in _found_eggs.iteritems():
        print "\t%s : %s" % (egg, location)

if __name__ == "__main__":
    _main()

del _include_egg_deps
del _main
del _found_eggs
