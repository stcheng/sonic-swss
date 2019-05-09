# This test suite covers the functionality of mirror feature in SwSS

import pytest
import time

from swsscommon import swsscommon


class TestPolicer(object):
    def setup_db(self, dvs):
        self.pdb = swsscommon.DBConnector(0, dvs.redis_sock, 0)
        self.adb = swsscommon.DBConnector(1, dvs.redis_sock, 0)
        self.cdb = swsscommon.DBConnector(4, dvs.redis_sock, 0)
        self.sdb = swsscommon.DBConnector(6, dvs.redis_sock, 0)

    def test_PolicerAddRemove(self, dvs, testlog):
        self.setup_db(dvs)

        session = "TEST_SESSION"

        # Add policer
        tbl = swsscommon.Table(self.cdb, "POLICER")
        fvs = swsscommon.FieldValuePairs([("meter_type", "packets"),
                                          ("mode", "sr_tcm"),
                                          ("cir", "600"),
                                          ("cbs", "600"),
                                          ("red_packet_action", "drop")])
        tbl.set("test", fvs)
        time.sleep(1)

        # Check ASIC database
        tbl = swsscommon.Table(self.adb, "ASIC_STATE:SAI_OBJECT_TYPE_POLICER")
        policer_entries = tbl.getKeys()
        assert len(policer_entries) == 1

        (status, fvs) = tbl.get(policer_entries[0])
        assert status == True
        assert len(fvs) == 5
        for fv in fvs:
            if fv[0] == "SAI_POLICER_ATTR_METER_TYPE":
                assert fv[1] == "SAI_METER_TYPE_PACKETS"
            if fv[0] == "SAI_POLICER_ATTR_MODE":
                assert fv[1] == "SAI_POLICER_MODE_SR_TCM"
            if fv[0] == "SAI_POLICER_ATTR_CIR":
                assert fv[1] == "600"
            if fv[0] == "SAI_POLICER_ATTR_CBS":
                assert fv[1] == "600"
            if fv[0] == "SAI_POLICER_ATTR_RED_PACKET_ACTION":
                assert fv[1] == "SAI_PACKET_ACTION_DROP"

        # Remove policer
        tbl = swsscommon.Table(self.cdb, "POLICER")
        tbl._del("test")
        time.sleep(1)

        # Check ASIC database
        tbl = swsscommon.Table(self.adb, "ASIC_STATE:SAI_OBJECT_TYPE_POLICER")
        policer_entries = tbl.getKeys()
        assert len(policer_entries) == 0

