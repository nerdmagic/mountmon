# mountmon

`mountmon` is a python service for monitoring the status of POSIX filesystem mountpoints.

Written originally to monitor cephfs_fuse mountpoints, but can be easily extended to use for NFS, direct attached storage or any other type of mountpoint.

`mountmon` uses a yaml configuraion file, located by default at `/etc/mountmon/mountmon.yaml`. See the example file in the project root.
