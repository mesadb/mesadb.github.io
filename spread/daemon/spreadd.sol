#!/bin/sh
#
### spreadd - startup/shutdown for the Spread daemon
#
#**************************************************
#
# Redistribution and use in source and binary forms of this code, with or
# without modification, are permitted provided that the following
# conditions are met:
# 
# Redistributions of source code must retain this list of conditions and
# the following disclaimer as a part of such source code. Redistributions
# in binary form must reproduce this list of conditions and the following
# disclaimer in the documentation and/or other materials provided with the
# distribution.  THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND
# CONTRIBUTORS "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING,
# BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND
# FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE
# COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT,
# INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT
# NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF
# USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON
# ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
# (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF
# THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
#
#**********************************************
#
#   Spread is an open source, high performance, fault tolerant, message processing 
#   system.  It is useful for application-level multicasting, node-to-node 
#   communiction, etc.  
# 
#   See:  http://www.spread.org for more details on Spread and its use.
#
#   Notes:
#          Assumes that the default port 4803 is being used.  Change this
#          by modifying the SP_PORT variable.
#
#

#
# Sanity checks.
#
[ -r /etc/spreadd ] || exit 0
. /etc/spreadd
[ -z "$SPREADARGS" ] && exit 0

get_spreadd_pid()
{
   /usr/bin/pgrep -z `zonename` -u 0 -P 1 -x spreadd
}



RETVAL=0
start() {
    echo -n $"Starting spread daemon: "

    # cleanup just in case
    rm -f /tmp/$SP_PORT

    if [ ! -x $SPREADPATH/spread ] ; then
	RETVAL=1
	echo
	return
    fi

    nice --11 $DAEMONIZEPATH/daemonize -p $DAEMONPIDFILE -u $SP_USER -o $DAEMONIZEOUTPUTPATH \
                             -v $SPREADPATH/spread $SPREADARGS > /dev/null
    RETVAL=$?
    echo
}

stop() {
    echo -n $"Stopping spread daemon: "

    SPREAD_PID=`pgrep spread`
    kill -TERM $SPREAD_PID
    RETVAL=$?
    echo
    if [ $RETVAL -eq 0 ]; then
	rm -f $DAEMONPIDFILE
	rm -f /tmp/$SP_PORT
    fi
    echo
}

status() {
    if ! pidof spread >/dev/null
    then
        echo "spread is not running"
        RETVAL=1
    else
        echo "spread is running"
        RETVAL=0
    fi
}

[ -f $SPREADPATH/spread ] || exit 0

# See how we were called.
case "$1" in
    start)
        start
        ;;
    stop)
        stop
        ;;
    status)
        status
        ;;
    *)
        echo $"Usage: $0 {start|stop|status}"
        ;;
esac
exit $RETVAL

