from __future__ import absolute_import
from __future__ import print_function

class ClusterNode(object):
    @property
    def specifier(self):
        """The specifier used when this node was referenced / resolved"""
        return self._specifier

    @property
    def address(self):
        """The node IP address, as a string."""

        assert self._resolved, "Must succesfully resolve the specifier, first"
        return self._address

    @property
    def node_name(self):
        """The node name, or None if not in the cluster"""

        assert self._resolved, "Must succesfully resolve the specifier, first"
        return self._node_name

    @property
    def is_new(self):
        """Returns True if this is a node that is not in the cluster.

        不在集群中的节点不能被并列,因为当前没有一个机制来指定或区分相同地址的两个节点,
        只能在一个集群里才能被分配.
        """

        assert self._resolved, "Must succesfully resolve the specifier, first"
        return self._node_name is None

    # constructor and obligatory resolver

    def __init__(self, specifier):
        self._specifier = specifier
        self._resolved = False
        self._address = None
        self._node_name = None

    def resolve(self, configurator):
        pass
        self._resolved = True

    # comparison stuff

    def _compare_key(self):
        def none_cast(v, d):
            return (d if v is None else v)

        return ( self.address, self.is_new, none_cast(self.node_name, '') )

    def __eq__(self, other):
        if not isinstance(other, ClusterNode):
            return NotImplemented
        return self._compare_key() == other._compare_key()

    def __lt__(self, other):
        if not isinstance(other, ClusterNode):
            return NotImplemented
        return self._compare_key() < other._compare_key()

    # printers

    def __str__(self):
        """Should probably use `address` or `node_name`"""
        return self.__repr__()

    def __repr__(self):
        if self._resolved:
            return "<ClusterNode address=%r name=%r specifier=%r>" % (
                    self.address, self.node_name, self.specifier)
        else:
            return "<ClusterNode (unresolved) specifier=%r>" % (self.specifier)
