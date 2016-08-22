#ifndef SWSS_INTFSORCH_H
#define SWSS_INTFSORCH_H

#include "orch.h"
#include "portsorch.h"

#include "ipaddresses.h"
#include "macaddress.h"

#include <map>

extern sai_object_id_t gVirtualRouterId;
extern MacAddress gMacAddress;

struct IntfsEntry
{
    IpAddresses         ip_addresses;
    int                 ref_count;
};

typedef map<string, IntfsEntry> IntfsTable;

class IntfsOrch : public Orch
{
public:
    IntfsOrch(DBConnector *db, string tableName);

    sai_object_id_t getRouterIntfsId(string);

    void increaseRouterIntfsRefCount(string);
    void decreaseRouterIntfsRefCount(string);
private:
    IntfsTable m_syncdIntfses;
    void doTask(Consumer &consumer);

    int getRouterIntfsRefCount(string);
    void cleanUpRouterInterfaces();

    bool addRouterIntfs(Port &port,
            sai_object_id_t virtual_router_id = gVirtualRouterId,
            MacAddress mac_address = gMacAddress);
    bool removeRouterIntfs(Port &port);
};

#endif /* SWSS_INTFSORCH_H */
