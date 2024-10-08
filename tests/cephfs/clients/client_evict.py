import time
import timeit
import traceback

from ceph.ceph import CommandFailed
from ceph.parallel import parallel
from tests.cephfs.cephfs_utils import FsUtils
from tests.cephfs.cephfs_utilsV1 import FsUtils as FsUtilsV1
from utility.log import Log

log = Log(__name__)


def run(ceph_cluster, **kw):
    """
    CEPH-11335 - Client eviction:
    Test case Steps:
    1. Mount the volumes on ceph-fuse and kernel mounts and Add fstab entries
    2. Kill the client process in client node and check if the clients have been removed
    3. Manually evict client using ceph tell mds.<rank> client evict id=<client id>
    4. Check client has been removed

    Args:
        ceph_cluster:
        **kw:

    Returns:

    """
    try:
        start = timeit.default_timer()
        tc = "11335"
        log.info("Running cephfs %s test case" % (tc))
        test_data = kw.get("test_data")
        fs_util_v1 = FsUtilsV1(ceph_cluster, test_data=test_data)
        erasure = (
            FsUtilsV1.get_custom_config_value(test_data, "erasure")
            if test_data
            else False
        )
        default_fs = "cephfs" if not erasure else "cephfs-ec"
        fs_util = FsUtils(ceph_cluster)
        config = kw.get("config")
        build = config.get("build", config.get("rhbuild"))
        client_info, rc = fs_util.get_clients(build)
        if rc == 0:
            log.info("Got client info")
        else:
            raise CommandFailed("fetching client info failed")
        client1, client2, client3, client4 = ([] for _ in range(4))
        client1.append(client_info["fuse_clients"][0])
        client2.append(client_info["fuse_clients"][1])
        client3.append(client_info["kernel_clients"][0])
        client4.append(client_info["kernel_clients"][1])
        fs_details = fs_util_v1.get_fs_info(client1[0], default_fs)
        if not fs_details:
            fs_util_v1.create_fs(client1[0], default_fs)
        rc1 = fs_util_v1.auth_list(client1)
        rc2 = fs_util_v1.auth_list(client2)
        rc3 = fs_util_v1.auth_list(client3)
        rc4 = fs_util_v1.auth_list(client4)
        print(rc1, rc2, rc3, rc4)
        if rc1 == 0 and rc2 == 0 and rc3 == 0 and rc4 == 0:
            log.info("got auth keys")
        else:
            log.error("auth list failed")
            return 1

        fs_util_v1.fuse_mount(
            client1,
            client_info["mounting_dir"],
            extra_params=f" --client_fs {default_fs}",
        )
        fs_util_v1.fuse_mount(
            client2,
            client_info["mounting_dir"],
            extra_params=f" --client_fs {default_fs}",
        )
        fs_util_v1.kernel_mount(
            client3,
            client_info["mounting_dir"],
            ",".join(client_info["mon_node_ip"]),
            extra_params=f",fs={default_fs}",
        )
        fs_util_v1.kernel_mount(
            client4,
            client_info["mounting_dir"],
            ",".join(
                client_info["mon_node_ip"],
            ),
            extra_params=f",fs={default_fs}",
        )
        rc = fs_util_v1.activate_multiple_mdss(
            client_info["clients"][0:], fs_name=default_fs
        )
        time.sleep(60)
        if rc == 0:
            log.info("Activate multiple mdss successfully")
        else:
            raise CommandFailed("Activate multiple mdss failed")
        active_mds_list = fs_util_v1.get_active_mdss(client1[0], default_fs)

        with parallel() as p:
            p.spawn(
                fs_util.read_write_IO,
                client1,
                client_info["mounting_dir"],
                "m",
                "write",
            )
            p.spawn(
                fs_util.read_write_IO, client2, client_info["mounting_dir"], "m", "read"
            )
            p.spawn(
                fs_util.read_write_IO,
                client4,
                client_info["mounting_dir"],
                "m",
                "readwrite",
            )
            p.spawn(
                fs_util.read_write_IO,
                client3,
                client_info["mounting_dir"],
                "m",
                "readwrite",
            )
            for op in p:
                return_counts, rc = op

        result = fs_util.rc_verify("", return_counts)
        print(result)

        log.info("Performing Auto Eviction:")
        mds1_before_evict, _, rc = fs_util_v1.get_mds_info(
            *active_mds_list, info="session ls"
        )
        rc = fs_util_v1.auto_evict(
            client1[0], client_info["clients"], active_mds_list[0]
        )
        if rc == 0:
            log.info("client process killed successfully for auto eviction")
        else:
            raise CommandFailed("client process killing failed for auto eviction")
        log.info("Waiting 300 seconds for auto eviction---")
        time.sleep(300)
        mds1_after_evict, _, rc = fs_util_v1.get_mds_info(
            *active_mds_list, info="session ls"
        )
        if mds1_before_evict != mds1_after_evict:
            log.info("Auto eviction Passed")
        else:
            raise CommandFailed("Auto eviction Failed")
        print("-------------------------------------------------------")
        if client3[0].pkg_type == "deb" and client4[0].pkg_type == "deb":
            for client in client_info["fuse_clients"]:
                client.exec_command(
                    cmd="sudo fusermount -u %s -z" % (client_info["mounting_dir"])
                )
                client.exec_command(
                    cmd="sudo rm -rf %s" % (client_info["mounting_dir"])
                )
        else:
            for client in client_info["fuse_clients"]:
                client.exec_command(
                    cmd="sudo fusermount -u %s -z" % (client_info["mounting_dir"])
                )
                client.exec_command(
                    cmd="sudo rm -rf %s" % (client_info["mounting_dir"])
                )

            for client in client_info["kernel_clients"]:
                client.exec_command(
                    cmd="sudo umount %s -l" % (client_info["mounting_dir"])
                )
                client.exec_command(
                    cmd="sudo rm -rf %s" % (client_info["mounting_dir"])
                )

        fs_util_v1.fuse_mount(
            client1,
            client_info["mounting_dir"],
            extra_params=f" --client_fs {default_fs}",
        )
        fs_util_v1.fuse_mount(
            client2,
            client_info["mounting_dir"],
            extra_params=f" --client_fs {default_fs}",
        )
        fs_util_v1.kernel_mount(
            client3,
            client_info["mounting_dir"],
            ",".join(client_info["mon_node_ip"]),
            extra_params=f",fs={default_fs}",
        )
        fs_util_v1.kernel_mount(
            client4,
            client_info["mounting_dir"],
            ",".join(client_info["mon_node_ip"]),
            extra_params=f",fs={default_fs}",
        )
        with parallel() as p:
            p.spawn(
                fs_util.read_write_IO,
                client1,
                client_info["mounting_dir"],
                "m",
                "write",
            )
            p.spawn(
                fs_util.read_write_IO, client2, client_info["mounting_dir"], "m", "read"
            )
            p.spawn(
                fs_util.stress_io,
                client3,
                client_info["mounting_dir"],
                "",
                0,
                1,
                iotype="smallfile",
            )
            p.spawn(
                fs_util.read_write_IO,
                client4,
                client_info["mounting_dir"],
                "m",
                "readwrite",
            )
            for op in p:
                return_counts, rc = op

        result = fs_util.rc_verify("", return_counts)
        print(result)
        log.info("Performing Manual eviction:")
        active_mds_list = fs_util_v1.get_active_mdss(client1[0], default_fs)
        active_mds_node_obj_1 = fs_util_v1.ceph_cluster.get_node_by_hostname(
            active_mds_list[0].split(".")[1]
        )
        ip_addr = fs_util.manual_evict(client1[0], active_mds_list[0])
        mds1_after_evict, _, rc = fs_util_v1.get_mds_info(
            *active_mds_list, info="session ls"
        )
        print(mds1_before_evict)
        print("------------------------")
        print(mds1_after_evict)
        print("-----------------------")
        if mds1_before_evict != mds1_after_evict:
            log.info("Manual eviction success")
        else:
            raise CommandFailed("Manual Eviction Failed")
        log.info("Removing client from OSD blacklisting:")
        rc = fs_util_v1.osd_blacklist_rm_client(client1[0], ip_addr)
        if rc == 0:
            log.info("Removing client from OSD blacklisting successfull")
        else:
            raise CommandFailed("Removing client from OSD blacklisting Failed")
        print("-" * 10)

        if client3[0].pkg_type == "deb" and client4[0].pkg_type == "deb":
            for client in client_info["fuse_clients"]:
                client.exec_command(
                    cmd="sudo fusermount -u %s -z" % (client_info["mounting_dir"])
                )
                client.exec_command(
                    cmd="sudo rm -rf %s" % (client_info["mounting_dir"])
                )
        else:
            for client in client_info["fuse_clients"]:
                client.exec_command(
                    cmd="sudo fusermount -u %s -z" % (client_info["mounting_dir"])
                )
                client.exec_command(
                    cmd="sudo rm -rf %s" % (client_info["mounting_dir"])
                )

            for client in client_info["kernel_clients"]:
                client.exec_command(
                    cmd="sudo umount %s -l" % (client_info["mounting_dir"])
                )
                client.exec_command(
                    cmd="sudo rm -rf %s" % (client_info["mounting_dir"])
                )

        fs_util_v1.fuse_mount(
            client1,
            client_info["mounting_dir"],
            extra_params=f" --client_fs {default_fs}",
        )
        fs_util_v1.fuse_mount(
            client2,
            client_info["mounting_dir"],
            extra_params=f" --client_fs {default_fs}",
        )
        fs_util_v1.kernel_mount(
            client3,
            client_info["mounting_dir"],
            ",".join(client_info["mon_node_ip"]),
            extra_params=f",fs={default_fs}",
        )
        fs_util_v1.kernel_mount(
            client4,
            client_info["mounting_dir"],
            ",".join(client_info["mon_node_ip"]),
            extra_params=f",fs={default_fs}",
        )
        with parallel() as p:
            p.spawn(
                fs_util.read_write_IO,
                client1,
                client_info["mounting_dir"],
                "m",
                "write",
            )
            p.spawn(
                fs_util.read_write_IO, client2, client_info["mounting_dir"], "m", "read"
            )
            p.spawn(
                fs_util.stress_io,
                client3,
                client_info["mounting_dir"],
                "",
                0,
                1,
                iotype="smallfile",
            )
            p.spawn(
                fs_util.read_write_IO,
                client4,
                client_info["mounting_dir"],
                "m",
                "readwrite",
            )
            for op in p:
                return_counts, rc = op

        result = fs_util.rc_verify("", return_counts)
        print(result)
        log.info("Performing configuring blacklisting:")

        rc = fs_util_v1.config_blacklist_manual_evict(
            active_mds_node_obj_1, active_mds_list[0], service_name=active_mds_list[0]
        )
        if rc == 0:
            log.info("Configure blacklisting for manual evict success")
            rc = fs_util_v1.config_blacklist_manual_evict(
                active_mds_node_obj_1,
                active_mds_list[0],
                revert=True,
                service_name=active_mds_list[0],
            )
        else:
            raise CommandFailed("Configure blacklisting for manual evict failed")
        print("-" * 10)
        rc = fs_util_v1.config_blacklist_auto_evict(
            active_mds_node_obj_1, active_mds_list[0], service_name=active_mds_list[0]
        )
        if rc == 0:
            log.info("Configure blacklisting for auto evict success")
            rc = fs_util_v1.config_blacklist_auto_evict(
                active_mds_node_obj_1,
                active_mds_list[0],
                revert=True,
                service_name=active_mds_list[0],
            )
            if rc == 0:
                log.info("Reverted successfully")
            else:
                raise CommandFailed("Configure blacklisting for auto evict failed")
        else:
            raise CommandFailed("Configure blacklisting for auto evict failed")

        if client3[0].pkg_type == "deb" and client4[0].pkg_type == "deb":
            for client in client_info["fuse_clients"]:
                client.exec_command(
                    cmd="sudo fusermount -u %s -z" % (client_info["mounting_dir"])
                )
                client.exec_command(
                    cmd="sudo rm -rf %s" % (client_info["mounting_dir"])
                )
        else:
            for client in client_info["fuse_clients"]:
                client.exec_command(
                    cmd="sudo fusermount -u %s -z" % (client_info["mounting_dir"])
                )
                client.exec_command(
                    cmd="sudo rm -rf %s" % (client_info["mounting_dir"])
                )

            for client in client_info["kernel_clients"]:
                client.exec_command(
                    cmd="sudo umount %s -l" % (client_info["mounting_dir"])
                )
                client.exec_command(
                    cmd="sudo rm -rf %s" % (client_info["mounting_dir"])
                )
        fs_util_v1.fuse_mount(
            client1,
            client_info["mounting_dir"],
            extra_params=f" --client_fs {default_fs}",
        )
        fs_util_v1.fuse_mount(
            client2,
            client_info["mounting_dir"],
            extra_params=f" --client_fs {default_fs}",
        )
        fs_util_v1.kernel_mount(
            client3,
            client_info["mounting_dir"],
            ",".join(client_info["mon_node_ip"]),
            extra_params=f",fs={default_fs}",
        )
        fs_util_v1.kernel_mount(
            client4,
            client_info["mounting_dir"],
            ",".join(client_info["mon_node_ip"]),
            extra_params=f",fs={default_fs}",
        )
        if client3[0].pkg_type == "deb" and client4[0].pkg_type == "deb":
            for client in client_info["fuse_clients"]:
                client.exec_command(
                    cmd="sudo rm -rf %s*" % (client_info["mounting_dir"])
                )
                client.exec_command(
                    cmd="sudo fusermount -u %s -z" % (client_info["mounting_dir"])
                )
                client.exec_command(
                    cmd="sudo rm -rf %s" % (client_info["mounting_dir"])
                )
        else:
            for client in client_info["fuse_clients"]:
                client.exec_command(
                    cmd="sudo rm -rf %s*" % (client_info["mounting_dir"])
                )
                client.exec_command(
                    cmd="sudo fusermount -u %s -z" % (client_info["mounting_dir"])
                )
                client.exec_command(
                    cmd="sudo rm -rf %s" % (client_info["mounting_dir"])
                )

            for client in client_info["kernel_clients"]:
                client.exec_command(
                    cmd="sudo umount %s -l" % (client_info["mounting_dir"])
                )
                client.exec_command(
                    cmd="sudo rm -rf %s" % (client_info["mounting_dir"])
                )

        print("Script execution time:------")
        stop = timeit.default_timer()
        total_time = stop - start
        mins, secs = divmod(total_time, 60)
        hours, mins = divmod(mins, 60)

        print("Hours:%d Minutes:%d Seconds:%f" % (hours, mins, secs))

        return 0

    except CommandFailed as e:
        log.info(e)
        log.info(traceback.format_exc())
        return 1
    except Exception as e:
        log.info(e)
        log.info(traceback.format_exc())
        return 1
