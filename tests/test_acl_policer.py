# This test suite covers the functionality of mirror feature in SwSS

import pytest
import time

from swsscommon import swsscommon


class TestAclPolicer(object):
    def setup_db(self, dvs):
        self.pdb = swsscommon.DBConnector(0, dvs.redis_sock, 0)
        self.adb = swsscommon.DBConnector(1, dvs.redis_sock, 0)
        self.cdb = swsscommon.DBConnector(4, dvs.redis_sock, 0)
        self.sdb = swsscommon.DBConnector(6, dvs.redis_sock, 0)

    def set_interface_status(self, interface, admin_status):
        tbl = swsscommon.Table(self.cdb, "PORT")
        fvs = swsscommon.FieldValuePairs([("admin_status", "up")])
        tbl.set(interface, fvs)
        time.sleep(1)

    def add_ip_address(self, interface, ip):
        tbl = swsscommon.Table(self.cdb, "INTERFACE")
        fvs = swsscommon.FieldValuePairs([("NULL", "NULL")])
        tbl.set(interface + "|" + ip, fvs)
        time.sleep(1)

    def remove_ip_address(self, interface, ip):
        tbl = swsscommon.Table(self.cdb, "INTERFACE")
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

    def create_policer(self, name):
        tbl = swsscommon.Table(self.cdb, "POLICER")
        fvs = swsscommon.FieldValuePairs([("meter_type", "packets"),
                                          ("mode", "sr_tcm"),
                                          ("cir", "600"),
                                          ("cbs", "600"),
                                          ("red_packet_action", "drop")])
        tbl.set(name, fvs)
        time.sleep(1)

    def remove_policer(self, name):
        tbl = swsscommon.Table(self.cdb, "POLICER")
        tbl._del(name)
        time.sleep(1)

    def create_acl_table(self, table, interfaces):
        tbl = swsscommon.Table(self.cdb, "ACL_TABLE")
        fvs = swsscommon.FieldValuePairs([("policy_desc", "mirror_test"),
                                          ("type", "mirror"),
                                          ("ports", ",".join(interfaces))])
        tbl.set(table, fvs)
        time.sleep(1)

    def remove_acl_table(self, table):
        tbl = swsscommon.Table(self.cdb, "ACL_TABLE")
        tbl._del(table)
        time.sleep(1)

    def create_mirror_acl_dscp_rule(self, table, rule, dscp, session, policer):
        tbl = swsscommon.Table(self.cdb, "ACL_RULE")
        fvs = swsscommon.FieldValuePairs([("priority", "1000"),
                                          ("mirror_action", session),
                                          ("policer_action", policer),
                                          ("DSCP", dscp)])
        tbl.set(table + "|" + rule, fvs)
        time.sleep(1)

    def remove_mirror_acl_dscp_rule(self, table, rule):
        tbl = swsscommon.Table(self.cdb, "ACL_RULE")
        tbl._del(table + "|" + rule)
        time.sleep(2)

    def test_AclPolicerAddRemove(self, dvs, testlog):
        self.setup_db(dvs)

        session = "TEST_MIRROR"
        policer = "TEST_POLICER"
        acl_table = "TEST_ACL_TABLE"
        acl_rule = "TEST_ACL_RULE"

        self.set_interface_status("Ethernet32", "up")
        self.add_ip_address("Ethernet32", "20.0.0.0/31")
        self.add_neighbor("Ethernet32", "20.0.0.1", "02:04:06:08:10:12")
        self.add_route(dvs, "4.4.4.4", "20.0.0.1")

        self.create_mirror_session(session, "3.3.3.3", "4.4.4.4", "0x6558", "8", "100", "0")
        self.create_policer(policer)
        self.create_acl_table(acl_table, ["Ethernet0", "Ethernet4"])
        self.create_mirror_acl_dscp_rule(acl_table, acl_rule, "48", session, policer)

        # Get policer OID
        tbl = swsscommon.Table(self.adb, "ASIC_STATE:SAI_OBJECT_TYPE_POLICER")
        policer_entries = tbl.getKeys()
        assert len(policer_entries) == 1

        # Get rule OID
        tbl = swsscommon.Table(self.adb, "ASIC_STATE:SAI_OBJECT_TYPE_ACL_ENTRY")
        rule_entries = [k for k in tbl.getKeys() if k not in dvs.asicdb.default_acl_entries]
        assert len(rule_entries) == 1

        # Assert rule is associated with policer
        (status, fvs) = tbl.get(rule_entries[0])
        assert status == True
        for fv in fvs:
            if fv[0] == "SAI_ACL_ENTRY_ATTR_ACTION_SET_POLICER":
                assert fv[1] == policer_entries[0]

        self.remove_mirror_acl_dscp_rule(acl_table, acl_rule)
        self.remove_acl_table(acl_table)
        self.remove_policer(policer)
        self.remove_mirror_session(session)

        self.remove_route(dvs, "4.4.4.4")
        self.remove_neighbor("Ethernet32", "20.0.0.1")
        self.remove_ip_address("Ethernet32", "20.0.0.0/31")
        self.set_interface_status("Ethernet32", "down")

    def test_AclPolicerAddRemoveOrder(self, dvs, testlog):
        self.setup_db(dvs)

        session = "TEST_MIRROR"
        policer = "TEST_POLICER"
        acl_table = "TEST_ACL_TABLE"
        acl_rule = "TEST_ACL_RULE"

        self.set_interface_status("Ethernet32", "up")
        self.add_ip_address("Ethernet32", "20.0.0.0/31")
        self.add_neighbor("Ethernet32", "20.0.0.1", "02:04:06:08:10:12")
        self.add_route(dvs, "4.4.4.4", "20.0.0.1")

        self.create_mirror_session(session, "3.3.3.3", "4.4.4.4", "0x6558", "8", "100", "0")
        self.create_acl_table(acl_table, ["Ethernet0", "Ethernet4"])
        self.create_mirror_acl_dscp_rule(acl_table, acl_rule, "48", session, policer)

        # Get policer OID
        tbl = swsscommon.Table(self.adb, "ASIC_STATE:SAI_OBJECT_TYPE_POLICER")
        policer_entries = tbl.getKeys()
        assert len(policer_entries) == 0

        # Get rule OID
        tbl = swsscommon.Table(self.adb, "ASIC_STATE:SAI_OBJECT_TYPE_ACL_ENTRY")
        rule_entries = [k for k in tbl.getKeys() if k not in dvs.asicdb.default_acl_entries]
        assert len(rule_entries) == 0

        self.create_policer(policer)

        # Get policer OID
        tbl = swsscommon.Table(self.adb, "ASIC_STATE:SAI_OBJECT_TYPE_POLICER")
        policer_entries = tbl.getKeys()
        assert len(policer_entries) == 1

        # Get rule OID
        tbl = swsscommon.Table(self.adb, "ASIC_STATE:SAI_OBJECT_TYPE_ACL_ENTRY")
        rule_entries = [k for k in tbl.getKeys() if k not in dvs.asicdb.default_acl_entries]
        assert len(rule_entries) == 1

        # Assert rule is associated with policer
        (status, fvs) = tbl.get(rule_entries[0])
        assert status == True
        for fv in fvs:
            if fv[0] == "SAI_ACL_ENTRY_ATTR_ACTION_SET_POLICER":
                assert fv[1] == policer_entries[0]

        self.remove_policer(policer)

        # Get policer OID
        tbl = swsscommon.Table(self.adb, "ASIC_STATE:SAI_OBJECT_TYPE_POLICER")
        policer_entries = tbl.getKeys()
        assert len(policer_entries) == 1

        # Get rule OID
        tbl = swsscommon.Table(self.adb, "ASIC_STATE:SAI_OBJECT_TYPE_ACL_ENTRY")
        rule_entries = [k for k in tbl.getKeys() if k not in dvs.asicdb.default_acl_entries]
        assert len(rule_entries) == 1

        self.remove_mirror_acl_dscp_rule(acl_table, acl_rule)

        # Get policer OID
        tbl = swsscommon.Table(self.adb, "ASIC_STATE:SAI_OBJECT_TYPE_POLICER")
        policer_entries = tbl.getKeys()
        assert len(policer_entries) == 0

        # Get rule OID
        tbl = swsscommon.Table(self.adb, "ASIC_STATE:SAI_OBJECT_TYPE_ACL_ENTRY")
        rule_entries = [k for k in tbl.getKeys() if k not in dvs.asicdb.default_acl_entries]
        assert len(rule_entries) == 0

        self.remove_acl_table(acl_table)
        self.remove_mirror_session(session)

        self.remove_route(dvs, "4.4.4.4")
        self.remove_neighbor("Ethernet32", "20.0.0.1")
        self.remove_ip_address("Ethernet32", "20.0.0.0/31")
        self.set_interface_status("Ethernet32", "down")

