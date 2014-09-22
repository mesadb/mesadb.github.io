#!/bin/bash
# 
# Copyright Vertica, an HP Company 2012 
# All rights reserved 
# 
# Description: This script sets up the symlinks for the spread
# daemon. It gets run as part of cluster installation (install_vertica)
#
# Original Author: alamb
# 

# XX Would be good to factor most of the code below into a common
# location so there isn't so much replication

USAGE="vertica_service_setup.sh <install,stop,remove,start,restart> <prefix_dir> <RHEL4|RHEL5|FC|SUSE|DEBIAN|SUNOS> <target>"


COMMAND=$1
PREFIX=$2
OS=$3
TARGET=$4


if [ -z $COMMAND ]; then
    echo "Usage:  $USAGE"
    exit 1
fi

if [ $COMMAND != "install" -a $COMMAND != "stop" -a $COMMAND != "remove" -a $COMMAND != "start" -a $COMMAND != "restart" ]; then
    echo "Unknown command: $COMMAND"
    echo "Usage: $USAGE"
    exit 1
fi

if [ -z $PREFIX ]; then
    echo "Usage:  $USAGE"
    exit 1
fi

if [ -z $OS ]; then
    echo "Unknown OS: $OS"
    echo "Usage $USAGE"
    exit 1
fi

if [ -z $TARGET ]; then
    TARGET="both"
fi

if [ $TARGET != "both" -a $TARGET != "spread" -a $TARGET != "agent" -a $TARGET != "vertica" ]; then
    TARGET="both"
fi



spread_target(){

	if   [[ $OS == RHEL4 || $OS == RHEL5 || $OS == FC* ]]; then
        ### RHEL Installation ###
		if [ ${COMMAND} = "install" ]; then 
			echo "Setting up $OS"

     	    # SPREAD

			ln -sf ${PREFIX}/spread/daemon/spreadd /etc/rc.d/init.d/spreadd
			cp ${PREFIX}/spread/daemon/spreadd.sysconfig /etc/sysconfig/spreadd

			/sbin/chkconfig --add spreadd
			/sbin/chkconfig --level 35 spreadd on

	        # spread user's primary group must be log directory group or no log is created
			DBAGRP=`stat -c %G ${PREFIX}/log`
			if [ "${DBAGRP}" == "" ]; then
				echo "No group for $PREFIX/log found"
				exit 1
			fi
			/usr/sbin/useradd -g $DBAGRP -M -r spread
	        # usermod in case spread user already existed
			/usr/sbin/usermod -g $DBAGRP spread

	        # create logrotate script with proper log location
			echo "${PREFIX}/log/spread*.log {" > ${PREFIX}/config/logrotate/spread_daemon.logrotate
			cat ${PREFIX}/share/spreadd.logrotate_template >> ${PREFIX}/config/logrotate/spread_daemon.logrotate
		fi # end "install"

        ### RHEL Restart ###
		if [ ${COMMAND} = "restart" ]; then
			/etc/rc.d/init.d/spreadd restart
		fi # end "start"

        ### RHEL Start ###
		if [ ${COMMAND} = "start" ]; then
			/etc/rc.d/init.d/spreadd start
		fi # end "start"
		
        ### RHEL Stop ###
		if [ ${COMMAND} = "stop" ]; then
            # May not exist if install_vertica was not run
			if [ -f /etc/rc.d/init.d/spreadd ]; then
				running=`/etc/rc.d/init.d/spreadd status`
				status=$?
				if [ ${status} -eq 0 ] ; then
					echo "Shutting down spread daemon"
					/etc/rc.d/init.d/spreadd stop
					rm -rf /tmp/4803
				fi	
			fi
		fi # end "stop"
		
        ### RHEL Remove ###
		if [ ${COMMAND} = "remove" ]; then
			if [ -f /etc/rc.d/init.d/spreadd ]; then
				echo "Deleting spread daemon"
				/sbin/chkconfig --del spreadd
				rm -f /etc/rc.d/init.d/spreadd /etc/sysconfig/spreadd
				/usr/sbin/userdel spread >/dev/null 2>&1
			fi
			if [ -f ${PREFIX}/config/logrotate/spread_daemon.logrotate ]; then
				echo "Deleting spread logrotate configuration"
				rm ${PREFIX}/config/logrotate/spread_daemon.logrotate
			fi
		fi # end "remove"
	fi


	if [ "$OS" = "SUSE" ]; then
		
        ### SUSE Installation ###
		if [ ${COMMAND} = "install" ]; then 
			echo "Setting up $OS"

   	        # SPREAD
			
			ln -sf ${PREFIX}/spread/daemon/spreadd.suse /etc/rc.d/spreadd
			cp ${PREFIX}/spread/daemon/spreadd.sysconfig /etc/sysconfig/spreadd
			/sbin/chkconfig -a spreadd
			/sbin/chkconfig spreadd 35

			DBAGRP=`stat -c %G ${PREFIX}/log`
			if [ "${DBAGRP}" == "" ]; then
				echo "No group for $PREFIX/log found"
				exit 1
			fi
			/usr/sbin/useradd -g $DBAGRP -M -r spread
	        # usermod in case spread user already existed
			/usr/sbin/usermod -g $DBAGRP spread

	        # create logrotate script with proper log location
			echo "${PREFIX}/log/spread*.log {" > ${PREFIX}/config/logrotate/spread_daemon.logrotate
			cat ${PREFIX}/share/spreadd.logrotate_template >> ${PREFIX}/config/logrotate/spread_daemon.logrotate
		fi # end "install"
		
        ### SUSE Start ###
		if [ ${COMMAND} = "restart" ]; then
			/etc/rc.d/spreadd restart
		fi # end "restart"
		
        ### SUSE Start ###
		if [ ${COMMAND} = "start" ]; then
			/etc/rc.d/spreadd start
		fi # end "start"
		
        ### SUSE Stop ###
		if [ ${COMMAND} = "stop" ]; then
			if [ -f /etc/rc.d/spreadd ]; then
				running=`/etc/rc.d/spreadd status`
				status=$?
				if [ ${status} -eq 0 ] ; then
					echo "Shutting down spread daemon"
					/etc/rc.d/spreadd stop
					rm -rf /tmp/4803
				fi
			fi
		fi # end "stop"

        ### SUSE Remove ###
		if [ ${COMMAND} = "remove" ]; then
			if [ -f /etc/rc.d/spreadd ]; then
				echo "Deleting spread daemon"
				/sbin/chkconfig -d spreadd
				rm -f /etc/rc.d/spreadd /etc/sysconfig/spreadd
				/usr/sbin/userdel spread >/dev/null 2>&1
			fi
			if [ -f ${PREFIX}/config/logrotate/spread_daemon.logrotate ]; then
				echo "Deleting spread logrotate configuration"
				rm ${PREFIX}/config/logrotate/spread_daemon.logrotate
			fi
		fi # end "remove"
	fi

	if [ "$OS" = "DEBIAN" ]; then
		
        ### DEBIAN Installation ###
		if [ ${COMMAND} = "install" ]; then 
			echo "Setting up $OS"

	        # SPREAD
			
			ln -sf ${PREFIX}/spread/daemon/spreadd.deb /etc/init.d/spreadd
			cp ${PREFIX}/spread/daemon/spreadd.sysconfig /etc/spreadd

			update-rc.d spreadd defaults 50 20

			DBAGRP=`stat -c %G ${PREFIX}/log`
			if [ "${DBAGRP}" == "" ]; then
				echo "No group for $PREFIX/log found"
				exit 1
			fi
			/usr/sbin/useradd -g $DBAGRP spread
	        # usermod in case spread user already existed
			/usr/sbin/usermod -g $DBAGRP spread

	        # create logrotate script with proper log location
			echo "${PREFIX}/log/spread*.log {" > ${PREFIX}/config/logrotate/spread_daemon.logrotate
			cat ${PREFIX}/share/spreadd.logrotate_template >> ${PREFIX}/config/logrotate/spread_daemon.logrotate
		fi # end "install"
		
        ### DEBIAN Restart ###
		if [ ${COMMAND} = "restart" ]; then
			/etc/init.d/spreadd restart
		fi # end "restart"
		
        ### DEBIAN Start ###
		if [ ${COMMAND} = "start" ]; then
			/etc/init.d/spreadd start
		fi # end "start"
		
        ### DEBIAN Stop ###
		if [ ${COMMAND} = "stop" ]; then
			if [ -f /etc/init.d/spreadd ]; then
				running=`/etc/init.d/spreadd status`
				status=$?
				if [ ${status} -eq 0 ] ; then
					echo "Shutting down spread daemon"
					/etc/init.d/spreadd stop
					rm -rf /tmp/4803
				fi
			fi
		fi # end "stop"

        ### DEBIAN Remove ###
		if [ ${COMMAND} = "remove" ]; then
			if [ -f /etc/init.d/spreadd ]; then
				echo "Deleting spread daemon"
				rm -f /etc/init.d/spreadd
				rm -f /etc/spreadd

				update-rc.d spreadd remove
				
				/usr/sbin/userdel spread >/dev/null 2>&1
			fi
			if [ -f ${PREFIX}/config/logrotate/spread_daemon.logrotate ]; then
				echo "Deleting spread logrotate configuration"
				rm ${PREFIX}/config/logrotate/spread_daemon.logrotate
			fi
		fi # end "remove"
	fi

	if [ "$OS" = "SUNOS" ]; then
		
        ### SunOS Installation ###
		if [ ${COMMAND} = "install" ]; then 
			echo "Setting up $OS"
			
	        # SPREAD

			ln -sf ${PREFIX}/spread/daemon/spreadd.sol /etc/init.d/spreadd
			cp ${PREFIX}/spread/daemon/spreadd.sysconfig /etc/spreadd

			ln -s /etc/init.d/spreadd /etc/rc0.d/K1spreadd
			ln -s /etc/init.d/spreadd /etc/rc1.d/K10spreadd
			ln -s /etc/init.d/spreadd /etc/rc3.d/S50spreadd

			DBAGRP=`stat -c %G ${PREFIX}/log`
			if [ "${DBAGRP}" == "" ]; then
				echo "No group for $PREFIX/log found"
				exit 1
			fi
			/usr/sbin/useradd -g $DBAGRP spread
	        # usermod in case spread user already existed
			/usr/sbin/usermod -g $DBAGRP spread

	        # create logrotate script with proper log location
			echo "${PREFIX}/log/spread*.log {" > ${PREFIX}/config/logrotate/spread_daemon.logrotate
			cat ${PREFIX}/share/spreadd.logrotate_template >> ${PREFIX}/config/logrotate/spread_daemon.logrotate
		fi # end "install"
		
        ### SunOS Restart ###
		if [ ${COMMAND} = "restart" ]; then
			/etc/init.d/spreadd restart
		fi # end "restart"
		
        ### SunOS Start ###
		if [ ${COMMAND} = "start" ]; then
			/etc/init.d/spreadd start
		fi # end "start"
		
        ### SunOS Stop ###
		if [ ${COMMAND} = "stop" ]; then
			if [ -f /etc/init.d/spreadd ]; then
				running=`/etc/init.d/spreadd status`
				status=$?
				if [ ${status} -eq 0 ] ; then
					echo "Shutting down spread daemon"
					/etc/init.d/spreadd stop
					rm -rf /tmp/4803
				fi
			fi
		fi # end "stop"

        ### SunOS Remove ###
		if [ ${COMMAND} = "remove" ]; then
			if [ -f /etc/init.d/spreadd ]; then
				echo "Deleting spread daemon"
				rm -f /etc/init.d/spreadd
				rm -f /etc/spreadd
				rm -f /etc/rc0.d/K1spreadd
				rm -f /etc/rc1.d/K10spreadd
				rm -f /etc/rc3.d/S50spreadd
				/usr/sbin/userdel spread >/dev/null 2>&1
			fi
			if [ -f ${PREFIX}/config/logrotate/spread_daemon.logrotate ]; then
				echo "Deleting spread logrotate configuration"
				rm ${PREFIX}/config/logrotate/spread_daemon.logrotate
			fi
		fi # end "remove"
	fi

}

#################################
## Vertica auto-restart support #
#################################
vertica_target(){

	if   [[ $OS == RHEL4 || $OS == RHEL5 || $OS == FC* ]]; then
        ### RHEL Installation ###
		if [ ${COMMAND} = "install" ]; then 
			echo "Setting up $OS"

	        # VERTICA RESTART
			ln -s ${PREFIX}/sbin/verticad /etc/rc.d/init.d/
			/sbin/chkconfig --add verticad
			/sbin/chkconfig --level 35 verticad on

		fi # end "install"

        ### RHEL Remove ###
		if [ ${COMMAND} = "remove" ]; then
			if [ -f /etc/rc.d/init.d/verticad ]; then
				echo "Deleting vertica autorestart support"
				/sbin/chkconfig --del verticad
				rm -f /etc/rc.d/init.d/verticad /etc/rc.d/verticad
			fi

		fi # end "remove"
	fi


	if [ "$OS" = "SUSE" ]; then
		
        ### SUSE Installation ###
		if [ ${COMMAND} = "install" ]; then 
			echo "Setting up $OS"

    	    # VERTICA RESTART
			ln -s ${PREFIX}/sbin/verticad /etc/rc.d/
			/sbin/chkconfig -a verticad
			/sbin/chkconfig verticad 35

		fi # end "install"
		
        ### SUSE Remove ###
		if [ ${COMMAND} = "remove" ]; then
			if [ -f /etc/rc.d/verticad ]; then
				echo "Deleting vertica autorestart support"
				/sbin/chkconfig -d verticad
				rm -f /etc/rc.d/verticad
			fi
		fi # end "remove"

	fi

	if [ "$OS" = "DEBIAN" ]; then
		
        ### DEBIAN Installation ###
		if [ ${COMMAND} = "install" ]; then 
			echo "Setting up $OS"

    	    # VERTICA RESTART
			ln -s ${PREFIX}/sbin/verticad /etc/init.d/
			update-rc.d verticad defaults 90 10

		fi # end "install"
		
        ### DEBIAN Remove ###
		if [ ${COMMAND} = "remove" ]; then
			if [ -f /etc/init.d/verticad ]; then
				echo "Deleting vertica autorestart support"
				rm -f /etc/init.d/verticad
				update-rc.d verticad remove
			fi
		fi # end "remove"
	fi

	if [ "$OS" = "SUNOS" ]; then
		
        ### SunOS Installation ###
		if [ ${COMMAND} = "install" ]; then 
			echo "Setting up $OS"
			
	        # VERTICA RESTART
			ln -s ${PREFIX}/sbin/verticad /etc/init.d/
			ln -s /etc/init.d/verticad /etc/rc0.d/K5verticad
			ln -s /etc/init.d/verticad /etc/rc1.d/K20verticad
			ln -s /etc/init.d/verticad /etc/rc3.d/S90verticad
		fi # end "install"
		
        ### SunOS Remove ###
		if [ ${COMMAND} = "remove" ]; then
			if [ -f /etc/init.d/verticad ]; then
				echo "Deleting vertica autorestart support"
				rm -f /etc/rc0.d/K5verticad
				rm -f /etc/rc1.d/K20verticad
				rm -f /etc/rc3.d/S90verticad
				rm -f /etc/init.d/verticad
			fi
		fi # end "remove"
	fi

}



agent_target(){

  if   [[ $OS == RHEL4 || $OS == RHEL5 || $OS == FC* ]]; then
    ### RHEL Installation ###
    if [ ${COMMAND} = "install" ]; then 
	echo "Setting up $OS"

        # VERTICA AGENT 
        ln -s ${PREFIX}/sbin/vertica_agent /etc/rc.d/init.d/
        /sbin/chkconfig --add vertica_agent
        /sbin/chkconfig --level 35 vertica_agent on
 
    fi # end "install"

    ### RHEL Restart ###
    if [ ${COMMAND} = "restart" ]; then
	/etc/rc.d/init.d/vertica_agent restart
    fi # end "start"

    ### RHEL Start ###
    if [ ${COMMAND} = "start" ]; then
	/etc/rc.d/init.d/vertica_agent start
    fi # end "start"
	
    ### RHEL Stop ###
    if [ ${COMMAND} = "stop" ]; then
        if [ -f /etc/rc.d/init.d/vertica_agent ]; then
           running=`/etc/rc.d/init.d/vertica_agent status`
	   status=$?
	   if [ ${status} -eq 0 ] ; then
             echo "Shutting down vertica agent daemon"
	     /etc/rc.d/init.d/vertica_agent stop
	   fi	
        fi
    fi # end "stop"
	
    ### RHEL Remove ###
    if [ ${COMMAND} = "remove" ]; then
         if [ -f /etc/rc.d/init.d/vertica_agent ]; then
            echo "Deleting vertica agent support"
            /sbin/chkconfig --del vertica_agent
            rm -f /etc/rc.d/vertica_agent /etc/rc.d/init.d/vertica_agent
         fi
    fi # end "remove"
  fi


  if [ "$OS" = "SUSE" ]; then
    
    ### SUSE Installation ###
    if [ ${COMMAND} = "install" ]; then 
        echo "Setting up $OS"
        # VERTICA AGENT 
        ln -s ${PREFIX}/sbin/vertica_agent /etc/rc.d/
        /sbin/chkconfig -a vertica_agent
        /sbin/chkconfig vertica_agent 35
    fi # end "install"
    
    ### SUSE Start ###
    if [ ${COMMAND} = "restart" ]; then
	/etc/rc.d/vertica_agent restart
    fi # end "start"
   
    ### SUSE Start ###
    if [ ${COMMAND} = "start" ]; then
	/etc/rc.d/vertica_agent start
    fi # end "start"
   
    ### SUSE Stop ###
    if [ ${COMMAND} = "stop" ]; then
         if [ -f /etc/rc.d/vertica_agent ]; then
	    running=`/etc/rc.d/vertica_agent status`
	    status=$?
	    if [ ${status} -eq 0 ] ; then
               echo "Shutting down vertica agent daemon"
	       /etc/rc.d/vertica_agent stop
	    fi
         fi
    fi # end "stop"

    ### SUSE Remove ###
    if [ ${COMMAND} = "remove" ]; then
         if [ -f /etc/rc.d/vertica_agent ]; then
            echo "Deleting vertica agent support"
            /sbin/chkconfig -d vertica_agent
            rm -f /etc/rc.d/vertica_agent
         fi
         if [ -f /etc/init.d/vertica_agent ]; then
            echo "Deleting vertica agent support"
            rm -f /etc/init.d/vertica_agent
            update-rc.d vertica_agent remove
         fi
    fi # end "remove"

  fi


  if [ "$OS" = "DEBIAN" ]; then
    
    ### DEBIAN Installation ###
    if [ ${COMMAND} = "install" ]; then 
        echo "Setting up $OS"
        # VERTICA AGENT 
        ln -s ${PREFIX}/sbin/vertica_agent /etc/init.d
        update-rc.d vertica_agent defaults 90 10
    fi # end "install"
    
    ### DEBIAN Restart ###
    if [ ${COMMAND} = "restart" ]; then
	/etc/init.d/vertica_agent restart
    fi # end "start"
   
    ### DEBIAN Start ###
    if [ ${COMMAND} = "start" ]; then
	/etc/init.d/vertica_agent start
    fi # end "start"
   
    ### DEBIAN Stop ###
    if [ ${COMMAND} = "stop" ]; then
         if [ -f /etc/init.d/vertica_agent ]; then
	    running=`/etc/init.d/vertica_agent status`
	    status=$?
	    if [ ${status} -eq 0 ] ; then
               echo "Shutting down vertica agent daemon"
	       /etc/init.d/vertica_agent stop
	    fi
         fi
    fi # end "stop"

    ### DEBIAN Remove ###
    if [ ${COMMAND} = "remove" ]; then
         if [ -f /etc/init.d/vertica_agent ]; then
            echo "Deleting vertica agent support"
	    rm -f /etc/init.d/vertica_agent
            update-rc.d vertica_agent remove
         fi
    fi # end "remove"
  fi

}


if [ ${TARGET} = "spread" ]; then
   spread_target
fi

if [ ${TARGET} = "vertica" ]; then
   vertica_target
fi

if [ ${TARGET} = "agent" ]; then
   agent_target
fi

if [ ${TARGET} = "both" ]; then
   spread_target
   vertica_target
   agent_target
fi


