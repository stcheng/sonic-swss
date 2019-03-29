# This test suite covers the functionality of mirror feature in SwSS

import platform
import pytest
import time
from distutils.version import StrictVersion

from swsscommon import swsscommon


class TestMirror(object):
    def setup_db(self, dvs):
        self.pdb = swsscommon.DBConnector(0, dvs.redis_sock, 0)
        self.adb = swsscommon.DBConnector(1, dvs.redis_sock, 0)
        self.cdb = swsscommon.DBConnector(4, dvs.redis_sock, 0)
        self.sdb = swsscommon.DBConnector(6, dvs.redis_sock, 0)

    def set_interface_status(self, interface, admin_status):
        if interface.startswith("PortChannel"):
            tbl_name = "PORTCHANNEL"
        elif interface.startswith("Vlan"):
            tbl_name = "VLAN"
        else:
            tbl_name = "PORT"
        tbl = swsscommon.Table(self.cdb, tbl_name)
        fvs = swsscommon.FieldValuePairs([("admin_status", "up")])
        tbl.set(interface, fvs)
        time.sleep(1)

    def add_ip_address(self, interface, ip):
        if interface.startswith("PortChannel"):
            tbl_name = "PORTCHANNEL_INTERFACE"
        elif interface.startswith("Vlan"):
            tbl_name = "VLAN_INTERFACE"
        else:
            tbl_name = "INTERFACE"
        tbl = swsscommon.Table(self.cdb, tbl_name)
        fvs = swsscommon.FieldValuePairs([("NULL", "NULL")])
        tbl.set(interface + "|" + ip, fvs)
        time.sleep(1)

    def remove_ip_address(self, interface, ip):
        if interface.startswith("PortChannel"):
            tbl_name = "PORTCHANNEL_INTERFACE"
        elif interface.startswith("Vlan"):
            tbl_name = "VLAN_INTERFACE"
        else:
            tbl_name = "INTERFACE"
        tbl = swsscommon.Table(self.cdb, tbl_name)
        tbl._del(interface + "|" + ip)
        time.sleep(1)

    def add_neighbor(self, interface, ip, mac):
        tbl = swsscommon.ProducerStateTable(self.pdb, "NEIGH_TABLE")
        fvs = swsscommon.FieldValuePairs([("neigh", mac),
                                          ("family", "IPv4")])
        tbl.set(interface + ":" + ip, fvs)
        time.sleep(1)

    def remove_neighbor(self, interface, ip):
        tbl = swsscommon.ProducerStateTable(self.pdb, "NEIGH_TABLE")
        tbl._del(interface + ":" + ip)
        time.sleep(1)

    def add_route(self, dvs, prefix, nexthop):
        dvs.runcmd("ip route add " + prefix + " via " + nexthop)
        time.sleep(1)

    def remove_route(self, dvs, prefix):
        dvs.runcmd("ip route del " + prefix)
        time.sleep(1)

    def create_mirror_session(self, name, src, dst, gre, dscp, ttl, queue):
        tbl = swsscommon.Table(self.cdb, "MIRROR_SESSION")
        fvs = swsscommon.FieldValuePairs([("src_ip", src),
                                          ("dst_ip", dst),
                                          ("gre_type", gre),
                                          ("dscp", dscp),
                                          ("ttl", ttl),
                                          ("queue", queue)])
        tbl.set(name, fvs)
        time.sleep(1)

    def remove_mirror_session(self, name):
        tbl = swsscommon.Table(self.cdb, "MIRROR_SESSION")
        tbl._del(name)
        time.sleep(1)

    def get_mirror_session_status(self, name):
        return self.get_mirror_session_state(name)["status"]

    def get_mirror_session_state(self, name):
        tbl = swsscommon.Table(self.sdb, "MIRROR_SESSION")
        (status, fvs) = tbl.get(name)
        assert status == True
        assert len(fvs) > 0
        return { fv[0]: fv[1] for fv in fvs }

    def create_acl_table(self, table, interfaces, type):
        tbl = swsscommon.Table(self.cdb, "ACL_TABLE")
        fvs = swsscommon.FieldValuePairs([("policy_desc", "mirror_test"),
                                          ("type", type),
                                          ("ports", ",".join(interfaces))])
        tbl.set(table, fvs)
        time.sleep(1)

    def remove_acl_table(self, table):
        tbl = swsscommon.Table(self.cdb, "ACL_TABLE")
        tbl._del(table)
        time.sleep(1)

    def create_mirror_acl_ipv4_rule(self, table, rule, session):
        tbl = swsscommon.Table(self.cdb, "ACL_RULE")
        fvs = swsscommon.FieldValuePairs([("priority", "1000"),
                                          ("mirror_action", session),
                                          ("SRC_IP", "10.0.0.0/32"),
                                          ("DST_IP", "20.0.0.0/23")])
        tbl.set(table + "|" + rule, fvs)
        time.sleep(1)

    def create_mirror_acl_ipv6_rule(self, table, rule, session):
        tbl = swsscommon.Table(self.cdb, "ACL_RULE")
        fvs = swsscommon.FieldValuePairs([("priority", "1000"),
                                          ("mirror_action", session),
                                          ("SRC_IPV6", "2777::0/64"),
                                          ("DST_IPV6", "3666::0/128")])
        tbl.set(table + "|" + rule, fvs)
        time.sleep(1)

    def remove_mirror_acl_rule(self, table, rule):
        tbl = swsscommon.Table(self.cdb, "ACL_RULE")
        tbl._del(table + "|" + rule)
        time.sleep(1)


    def test_AclBindMirror(self, dvs, testlog):
        """
        This test verifies IPv6 rules cannot be inserted into MIRROR table
        """
        self.setup_db(dvs)

        session = "MIRROR_SESSION"
        acl_table = "MIRROR_TABLE"
        acl_rule = "MIRROR_RULE"

        # bring up port; assign ip; create neighbor; create route
        self.set_interface_status("Ethernet32", "up")
        self.add_ip_address("Ethernet32", "20.0.0.0/31")
        self.add_neighbor("Ethernet32", "20.0.0.1", "02:04:06:08:10:12")
        self.add_route(dvs, "4.4.4.4", "20.0.0.1")

        # create mirror session
        self.create_mirror_session(session, "3.3.3.3", "4.4.4.4", "0x6558", "8", "100", "0")
        assert self.get_mirror_session_state(session)["status"] == "active"

        # assert mirror session in asic database
        tbl = swsscommon.Table(self.adb, "ASIC_STATE:SAI_OBJECT_TYPE_MIRROR_SESSION")
        assert len(tbl.getKeys()) == 1
        mirror_session_oid = tbl.getKeys()[0]

        # create acl table
        self.create_acl_table(acl_table, ["Ethernet0", "Ethernet4"], "MIRROR")

        # create acl rule with IPv6 addresses
        self.create_mirror_acl_ipv6_rule(acl_table, acl_rule, session)

        # assert acl rule is NOT created
        tbl = swsscommon.Table(self.adb, "ASIC_STATE:SAI_OBJECT_TYPE_ACL_ENTRY")
        rule_entries = [k for k in tbl.getKeys() if k not in dvs.asicdb.default_acl_entries]
        assert len(rule_entries) == 0

        # remove acl rule
        self.remove_mirror_acl_rule(acl_table, acl_rule)

        # remove acl table
        self.remove_acl_table(acl_table)

        # remove mirror session
        self.remove_mirror_session(session)

        # assert no mirror session in asic database
        tbl = swsscommon.Table(self.adb, "ASIC_STATE:SAI_OBJECT_TYPE_MIRROR_SESSION")
        assert len(tbl.getKeys()) == 0

        # remove route; remove neighbor; remove ip; bring down port
        self.remove_route(dvs, "4.4.4.4")
        self.remove_neighbor("Ethernet32", "20.0.0.1")
        self.remove_ip_address("Ethernet32", "20.0.0.0/31")
        self.set_interface_status("Ethernet32", "down")

    def test_AclBindMirrorV6(self, dvs, testlog):
        """
        This test verifies IPv6 rules cannot be inserted into MIRROR table
        """
        self.setup_db(dvs)

        session = "MIRROR_SESSION"
        acl_table = "MIRROR_TABLE_V6"
        acl_rule = "MIRROR_RULE"

        # bring up port; assign ip; create neighbor; create route
        self.set_interface_status("Ethernet32", "up")
        self.add_ip_address("Ethernet32", "20.0.0.0/31")
        self.add_neighbor("Ethernet32", "20.0.0.1", "02:04:06:08:10:12")
        self.add_route(dvs, "4.4.4.4", "20.0.0.1")

        # create mirror session
        self.create_mirror_session(session, "3.3.3.3", "4.4.4.4", "0x6558", "8", "100", "0")
        assert self.get_mirror_session_state(session)["status"] == "active"

        # assert mirror session in asic database
        tbl = swsscommon.Table(self.adb, "ASIC_STATE:SAI_OBJECT_TYPE_MIRROR_SESSION")
        assert len(tbl.getKeys()) == 1
        mirror_session_oid = tbl.getKeys()[0]

        # create acl table
        self.create_acl_table(acl_table, ["Ethernet0", "Ethernet4"], "MIRRORV6")


        # create acl rule with IPv4 addresses
        self.create_mirror_acl_ipv4_rule(acl_table, acl_rule, session)

        # assert IPv4 acl rule is NOT created
        tbl = swsscommon.Table(self.adb, "ASIC_STATE:SAI_OBJECT_TYPE_ACL_ENTRY")
        rule_entries = [k for k in tbl.getKeys() if k not in dvs.asicdb.default_acl_entries]
        assert len(rule_entries) == 0

        # remove acl rule
        self.remove_mirror_acl_rule(acl_table, acl_rule)


        # create acl rule with IPv6 addresses
        self.create_mirror_acl_ipv6_rule(acl_table, acl_rule, session)

        # assert acl rule is created
        tbl = swsscommon.Table(self.adb, "ASIC_STATE:SAI_OBJECT_TYPE_ACL_ENTRY")
        rule_entries = [k for k in tbl.getKeys() if k not in dvs.asicdb.default_acl_entries]
        assert len(rule_entries) == 1

        (status, fvs) = tbl.get(rule_entries[0])
        assert status == True
        for fv in fvs:
            if fv[0] == "SAI_ACL_ENTRY_ATTR_FIELD_SRC_IPV6":
                assert fv[1] == "2777::&mask:ffff:ffff:ffff:ffff::"
            if fv[0] == "SAI_ACL_ENTRY_ATTR_ACTION_MIRROR_INGRESS":
                assert fv[1] == "1:" + mirror_session_oid

        # remove acl rule
        self.remove_mirror_acl_rule(acl_table, acl_rule)


        # remove acl table
        self.remove_acl_table(acl_table)

        # remove mirror session
        self.remove_mirror_session(session)

        # assert no mirror session in asic database
        tbl = swsscommon.Table(self.adb, "ASIC_STATE:SAI_OBJECT_TYPE_MIRROR_SESSION")
        assert len(tbl.getKeys()) == 0

        # remove route; remove neighbor; remove ip; bring down port
        self.remove_route(dvs, "4.4.4.4")
        self.remove_neighbor("Ethernet32", "20.0.0.1")
        self.remove_ip_address("Ethernet32", "20.0.0.0/31")
        self.set_interface_status("Ethernet32", "down")

    def test_AclBindMirrorV4V6(self, dvs, testlog):
        """
        This test verifies IPv6 rules cannot be inserted into MIRROR table
        """
        self.setup_db(dvs)

        session = "MIRROR_SESSION"
        acl_table = "MIRROR_TABLE_V6"
        acl_rule = "MIRROR_RULE"

        # bring up port; assign ip; create neighbor; create route
        self.set_interface_status("Ethernet32", "up")
        self.add_ip_address("Ethernet32", "20.0.0.0/31")
        self.add_neighbor("Ethernet32", "20.0.0.1", "02:04:06:08:10:12")
        self.add_route(dvs, "4.4.4.4", "20.0.0.1")

        # create mirror session
        self.create_mirror_session(session, "3.3.3.3", "4.4.4.4", "0x6558", "8", "100", "0")
        assert self.get_mirror_session_state(session)["status"] == "active"

        # assert mirror session in asic database
        tbl = swsscommon.Table(self.adb, "ASIC_STATE:SAI_OBJECT_TYPE_MIRROR_SESSION")
        assert len(tbl.getKeys()) == 1
        mirror_session_oid = tbl.getKeys()[0]

        # create acl table
        self.create_acl_table(acl_table, ["Ethernet0", "Ethernet4"], "MIRRORV4V6")


        # create acl rule with IPv4 addresses
        self.create_mirror_acl_ipv4_rule(acl_table, acl_rule, session)

        # assert IPv4 acl rule is created
        tbl = swsscommon.Table(self.adb, "ASIC_STATE:SAI_OBJECT_TYPE_ACL_ENTRY")
        rule_entries = [k for k in tbl.getKeys() if k not in dvs.asicdb.default_acl_entries]
        assert len(rule_entries) == 1

        (status, fvs) = tbl.get(rule_entries[0])
        assert status == True
        for fv in fvs:
            if fv[0] == "SAI_ACL_ENTRY_ATTR_FIELD_SRC_IP":
                assert fv[1] == "10.0.0.0&mask:255.255.255.255"
            if fv[0] == "SAI_ACL_ENTRY_ATTR_ACTION_MIRROR_INGRESS":
                assert fv[1] == "1:" + mirror_session_oid

        # remove acl rule
        self.remove_mirror_acl_rule(acl_table, acl_rule)


        # create acl rule with IPv6 addresses
        self.create_mirror_acl_ipv6_rule(acl_table, acl_rule, session)

        # assert acl rule is created
        tbl = swsscommon.Table(self.adb, "ASIC_STATE:SAI_OBJECT_TYPE_ACL_ENTRY")
        rule_entries = [k for k in tbl.getKeys() if k not in dvs.asicdb.default_acl_entries]
        assert len(rule_entries) == 1

        (status, fvs) = tbl.get(rule_entries[0])
        assert status == True
        for fv in fvs:
            if fv[0] == "SAI_ACL_ENTRY_ATTR_FIELD_SRC_IPV6":
                assert fv[1] == "2777::&mask:ffff:ffff:ffff:ffff::"
            if fv[0] == "SAI_ACL_ENTRY_ATTR_ACTION_MIRROR_INGRESS":
                assert fv[1] == "1:" + mirror_session_oid

        # remove acl rule
        self.remove_mirror_acl_rule(acl_table, acl_rule)


        # remove acl table
        self.remove_acl_table(acl_table)

        # remove mirror session
        self.remove_mirror_session(session)

        # assert no mirror session in asic database
        tbl = swsscommon.Table(self.adb, "ASIC_STATE:SAI_OBJECT_TYPE_MIRROR_SESSION")
        assert len(tbl.getKeys()) == 0

        # remove route; remove neighbor; remove ip; bring down port
        self.remove_route(dvs, "4.4.4.4")
        self.remove_neighbor("Ethernet32", "20.0.0.1")
        self.remove_ip_address("Ethernet32", "20.0.0.0/31")
        self.set_interface_status("Ethernet32", "down")
