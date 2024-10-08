import datetime
import traceback
from time import sleep

from ceph.ceph import CommandFailed
from tests.cephfs.cephfs_utilsV1 import FsUtils
from utility.log import Log

log = Log(__name__)


def wait_for_stable_fs(client, standby_replay, timeout=180, interval=5):
    end_time = datetime.datetime.now() + datetime.timedelta(seconds=timeout)
    log.info("Wait for the command to pass")
    while end_time > datetime.datetime.now():
        try:
            out1, rc = client.exec_command(sudo=True, cmd="ceph fs status")
            print(out1)
            out, rc = client.exec_command(
                sudo=True, cmd="ceph fs status | awk '{print $2}'"
            )
            output = out.splitlines()
            if (
                "active" in output[3]
                and "standby-replay" in output[4]
                and standby_replay == "true"
            ):
                return 0
            if "standby-replay" not in output[4] and standby_replay == "false":
                return 0
            sleep(interval)
        except Exception as e:
            log.info(e)
            log.info(traceback.format_exc())
            raise CommandFailed


def run(ceph_cluster, **kw):
    try:
        """
        CEPH-83573269 - [Cephfs] configure standby-replay daemon
        Pre-requisites :
        1. Create cephfs volume

        Test Case Flow:
        1. Set max_mds to 1
        2. Set allow_standby_replay to true & verify it
        3. Set allow_standby_replay to false & verify it
        """
        tc = "CEPH-83573269"
        log.info("Running cephfs %s test case" % (tc))
        client = ceph_cluster.get_ceph_objects("client")
        client1 = client[0]
        test_data = kw.get("test_data")
        fs_util = FsUtils(ceph_cluster, test_data=test_data)
        erasure = (
            FsUtils.get_custom_config_value(test_data, "erasure")
            if test_data
            else False
        )
        fs_name = "cephfs" if not erasure else "cephfs-ec"
        fs_details = fs_util.get_fs_info(client1, fs_name)

        if not fs_details:
            fs_util.create_fs(client1, fs_name)

        cmd = f"ceph fs set {fs_name} max_mds 1"
        client1.exec_command(sudo=True, cmd=cmd)
        cmd = f"ceph fs set {fs_name} allow_standby_replay true"
        client1.exec_command(sudo=True, cmd=cmd)
        wait_for_stable_fs(client1, standby_replay="true")
        cmd = f"ceph fs set {fs_name} allow_standby_replay false"
        client1.exec_command(sudo=True, cmd=cmd)
        wait_for_stable_fs(client1, standby_replay="false")
        return 0
    except Exception as e:
        log.error(e)
        log.error(traceback.format_exc())
        return 1
