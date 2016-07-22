#include "dbconnector.h"
#include "select.h"
#include "netdispatcher.h"
#include "netlink.h"
#include "portmap.h"
#include "producertable.h"
#include "portsyncd/linksync.h"

#include <getopt.h>

#include <iostream>
#include <fstream>
#include <sstream>
#include <vector>
#include <set>
#include <map>

#define DEFAULT_PORT_CONFIG_FILE     "port_config.ini"
#define DEFAULT_VLAN_INTERFACES_FILE "/etc/network/interfaces.d/vlan_interfaces"

using namespace std;
using namespace swss;

/*
 * This m_portSet contains all the front panel ports that the corresponding
 * host interfaces needed to be created. When this LinkSync class is
 * initialized, we check the database to see if some of the ports' host
 * interfaces are already created and remove them from this set. We will
 * remove the rest of the ports in the set when receiving the first netlink
 * message indicating that the host interfaces are created. After the set
 * is empty, we send out the signal ConfigDone and bring up VLAN interfaces
 * when the vlan_interfaces file exists. g_init is used to limit the command
 * to be run only once.
 */
set<string> g_portSet;
bool g_init = false;

void usage()
{
    cout << "Usage: portsyncd [-p port_config.ini] [-v vlan_interfaces]" << endl;
    cout << "       -p port_config.ini: MANDATORY import port lane mapping" << endl;
    cout << "                           default: port_config.ini" << endl;
    cout << "       -v vlan_interfaces: import VLAN interfaces configuration file" << endl;
    cout << "                           default: /etc/network/interfaces.d/vlan_interfaces" << endl;
}

void handlePortConfigFile(ProducerTable &p, string file);
void handleVlanIntfFile(string file);

int main(int argc, char **argv)
{
    int opt;
    string port_config_file = DEFAULT_PORT_CONFIG_FILE;
    string vlan_interfaces_file = DEFAULT_VLAN_INTERFACES_FILE;

    while ((opt = getopt(argc, argv, "p:v:h")) != -1 )
    {
        switch (opt)
        {
        case 'p':
            port_config_file.assign(optarg);
            break;
        case 'v':
            vlan_interfaces_file.assign(optarg);
            break;
        case 'h':
            usage();
            return 1;
        default: /* '?' */
            usage();
            return EXIT_FAILURE;
        }
    }

    DBConnector db(0, "localhost", 6379, 0);
    ProducerTable p(&db, APP_PORT_TABLE_NAME);

    LinkSync sync(&db);
    NetDispatcher::getInstance().registerMessageHandler(RTM_NEWLINK, &sync);
    NetDispatcher::getInstance().registerMessageHandler(RTM_DELLINK, &sync);

    try
    {
        NetLink netlink;
        Select s;

        netlink.registerGroup(RTNLGRP_LINK);
        cout << "Listen to link messages..." << endl;
        netlink.dumpRequest(RTM_GETLINK);

        handlePortConfigFile(p, port_config_file);

        s.addSelectable(&netlink);
        while (true)
        {
            Selectable *temps;
            int tempfd, ret;
            ret = s.select(&temps, &tempfd, 1);

            if (ret == Select::ERROR)
            {
                cerr << "Error had been returned in select" << endl;
                continue;
            }

            if (ret == Select::TIMEOUT)
            {
                if (!g_init && g_portSet.empty())
                {
                    /*
                     * After finishing reading port configuration file and
                     * creating all host interfaces, this daemon shall send
                     * out a signal to orchagent indicating port initialization
                     * procedure is done and other application could start
                     * syncing.
                     */
                    FieldValueTuple finish_notice("lanes", "0");
                    vector<FieldValueTuple> attrs = { finish_notice };
                    p.set("ConfigDone", attrs);

                    handleVlanIntfFile(vlan_interfaces_file);

                    g_init = true;
                }
            }
        }
    }
    catch (...)
    {
        cerr << "Exception had been thrown in deamon" << endl;
        return EXIT_FAILURE;
    }

    return 1;
}

void handlePortConfigFile(ProducerTable &p, string file)
{
    cout << "Read port configuration file..." << endl;

    map<set<int>, string> port_map = handlePortMap(file);

    for (auto it : port_map)
    {
        string alias = it.second;
        string lanes = "";
        for (auto l : it.first)
            lanes += to_string(l) + ",";
        lanes.pop_back();

        FieldValueTuple lanes_attr("lanes", lanes);
        vector<FieldValueTuple> attrs = { lanes_attr };
        p.set(alias, attrs);

        g_portSet.insert(alias);
    }
}

void handleVlanIntfFile(string file)
{
    ifstream infile(file);
    if (infile.good())
    {
        /* Bring up VLAN interfaces when vlan_interfaces_file exists */
        string cmd = "/sbin/ifup --all --force --interfaces " + file;
        int ret = system(cmd.c_str());
        if (!ret)
            cerr << "Execute command returns non-zero value! " << cmd << endl;
    }
}
