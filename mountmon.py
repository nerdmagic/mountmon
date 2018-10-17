#!/usr/bin/env python

"""
mountmon.py -- daemon to monitor mountpoints

usage:  mountmon.py [ -c <cfgfile> | --cfgfile=<cfgfile> ] [ -z | --zabbix_clear ]

exit codes, also sent to Zabbix if configured:
             0 = good
             1 = not mounted
             2 = mounted, can't list
             3 = mounted, no checkdir and can't create
             4 = mounted, can't write file
             5 = no mountmon config file at startup

default config file location:  /etc/mountmon/mountmon.yaml
"""

import logging
import daemon
import lockfile
import os
import time
import subprocess
import sys
import yaml
import argparse
from pyzabbix import ZabbixSender, ZabbixMetric


def RunCommand(cmd):
    try:
        proc = subprocess.Popen(cmd)
        proc.wait()
        return proc.returncode == 0
    except:
        return False


class mountmon (object):

    def __init__(self):

        self.cfg = {
            'daemonize'      : False,
            'interval'       : 60.0,
            'zabbix'         : False,
            'zabbix_trigger' : 'mountmon.error',
            'logfile'        : 'test_mountmon.log',
            'loglevel'       : 'DEBUG',
            'hostname'       : os.uname()[1],
            'remount'        : False,
            'pidfile'        : '/var/run/mountmon.pid',
            'working_dir'    : '/etc/mountmon',
            'mountpoints'    : {
                '/mymount'     : {
                    'checkdir'    : 'check',
                    'checkfile'   : 'foo',
                    'write_check' : True
                }
            }
        }

    def GetConfig(self, cfgfile):
        try:
            with open (cfgfile, 'r') as yamlfile:
                cfg_from_file = yaml.load(yamlfile)
                self.cfg.update(cfg_from_file)
        except:
           self.Error("Error loading config from file {}.".format(cfgfile), 5)

    def SetLogging(self):
        self.logger = logging.getLogger()
        logging.basicConfig (
            format   = '%(asctime)s %(levelname)s %(message)s',
            filename = self.cfg['logfile'],
            level    = self.cfg['loglevel']
        )
        if self.cfg['daemonize'] == False:
            term = logging.StreamHandler(sys.stdout)
            term.setLevel(logging.DEBUG)
            formatter = logging.Formatter('%(asctime)s %(levelname)s %(message)s')
            term.setFormatter(formatter)
            self.logger.addHandler(term)

    def ZabbixSend(self, value, key=''):
        packet = []
        if key == '':
            key = self.cfg['zabbix_trigger']
        metric = ZabbixMetric(self.cfg['hostname'], "{}".format(key), value)
        packet.append(metric)
        zbx = ZabbixSender(self.cfg['zabbix_address'])
        try:
            zbx.send(packet)
            self.logger.debug("Sent key '{}' value '{}' to zabbix".format(key, value))
        except:
            self.logger.error("Error sending key '{}' value '{}' to zabbix.".format(key,value))

    def Error (self, output, to_zabbix=1):
        if self.cfg['zabbix']:
            self.ZabbixSend( to_zabbix )
        self.logger.error(output)

    def Mount (self, mp):
        return RunCommand(['/usr/bin/mount', mp])

    def Umount(self, mp):
        result = RunCommand(['/usr/bin/umount', mp])
        if result:
            return result
        else:
            return RunCommand(['/usr/bin/umount', '-l', mp])

    def MountMon(self, mp):
        checkdir = "{}/{}".format(mp, self.cfg['mountpoints'][mp]['checkdir'])
        checkfile = "{}/{}".format(checkdir, self.cfg['mountpoints'][mp]['checkfile'])

        ## mountpoint check
        if not os.path.ismount(mp):
            if self.cfg['remount']:
                self.Error("{} found unmounted, attempting to mount".format(mp), 1)
                if self.Mount(mp):
                    ## insert delay before attempting to access
                    time.sleep(2)
                else:
                    self.Error("{} could not be mounted".format(mp), 1)
                    return 1
            else:
                self.Error("{} is not mounted".format(mp), 1)
                return 1

        ## list mountpoint directory
        ## if we can't, the mount is possibly stale, try to remount
        try:
            os.listdir(mp)
        except OSError:
            if self.cfg['remount']:
                self.Error("mountpoint {} appears stale, attmepting remount".format(mp), 2)
                if self.Umount(mp):
                    time.sleep(2)
                    if self.Mount(mp):
                        time.sleep(2)
                    else:
                        self.Error("Unmounted stale mountpoint {}, but cannot remount".format(mp), 2)
                        return 2
                else:
                    self.Error("{} could not be unmounted for remount".format(mp), 2)
                    return 2
            else:
                self.Error("{} not readable, appears stale".format(mp), 2)
                return 2

        ## file creation/writing check                 
        if self.cfg['mountpoints'][mp]['write_check']:

            ## checkdir
            try:
                os.listdir(checkdir)
            except OSError:
                try:
                    os.mkdir(checkdir, 0700)
                    self.logger.warning("Created monitor directory {}".format(checkdir))
                except:
                    self.Error("Dir {} does not exist and could not create it.".format(mp), 3)
                    return 3

            ## write file
            ## TODO: add timer
            try:
                with open(checkfile, 'w+') as f:
                    looptime = time.ctime()
                    f.write( "{}\n".format(looptime))
                f.close()
            except:
                self.Error("Could not write file: {}".format(checkfile), 4)
                return 4

        return 0

    def MainLoop(self):
        starttime = time.time()
        while True:
            try:
                for mountpoint in self.cfg['mountpoints']:
                    err = self.MountMon(mountpoint)
                    self.logger.debug ( "Looped at {}".format(time.time()))
                    self.logger.debug ( "return = {}".format(err) )
                    time.sleep (self.cfg['interval'] - ((time.time() - starttime) % self.cfg['interval']))
            except KeyboardInterrupt:
                return


if __name__ == '__main__':

    parser = argparse.ArgumentParser()
    parser.add_argument('-c', '--cfgfile', dest='cfgfile', help='Config file path',
            default='/etc/mountmon/mountmon.yaml')
    parser.add_argument('-z', '--zabbix_clear', help='Clear Zabbix alert', action='store_true')
    args = parser.parse_args()

    monitor = mountmon()
    monitor.GetConfig(args.cfgfile)

    ## For -z to clear zabbix: don't daemonize, send a 0, and exit
    if args.zabbix_clear:
        print("Clearing zabbix errors...")
        monitor.cfg['daemonize'] = False
        monitor.SetLogging()
        monitor.ZabbixSend(0)
        sys.exit()

    if monitor.cfg['daemonize']:
        context = daemon.DaemonContext (
            working_directory = monitor.cfg['working_dir'],
            pidfile = lockfile.FileLock(monitor.cfg['pidfile'])
        )
        with context:
            monitor.SetLogging()
            monitor.logger.info('Started mountmon')
            monitor.MainLoop()
    else:
        monitor.SetLogging()
        monitor.MainLoop()
