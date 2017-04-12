#ifndef SWSS_ROUTEORCH_H
#define SWSS_ROUTEORCH_H

#include "orch.h"
#include "observer.h"
#include "intfsorch.h"
#include "neighorch.h"

#include "ipaddress.h"
#include "ipaddresses.h"
#include "ipprefix.h"

#include <map>

using namespace std;
using namespace swss;

/* Maximum next hop group number */
#define NHGRP_MAX_SIZE 128

struct NextHopGroupEntry
{
    sai_object_id_t     next_hop_group_id;  // next hop group id
    int                 ref_count;          // reference count
};

struct RouteUpdate
{
    IpPrefix prefix;
    IpAddresses nexthopGroup;
};

struct RouteObserverEntry;

/* NextHopGroupTable: next hop group IP addersses, NextHopGroupEntry */
typedef map<IpAddresses, NextHopGroupEntry> NextHopGroupTable;
/* RouteTable: destination network, next hop IP address(es) */
typedef map<IpPrefix, IpAddresses> RouteTable;
/* RouteObserverTable: destination IP address, next hop observer entry */
typedef map<IpAddress, RouteObserverEntry> RouteObserverTable;
/* NextHopRouteTable: next hop IP, route table associated with this next hop */
typedef map<IpAddress, RouteTable> NextHopRouteTable;

struct RouteObserverEntry
{
    RouteTable routeTable;
    list<Observer *> observers;
};

class RouteOrch : public Orch, public Observer, public Subject
{
public:
    RouteOrch(DBConnector *db, string tableName, NeighOrch *neighOrch);

    bool hasNextHopGroup(IpAddresses);

    void attach(Observer *, const IpAddress&);
    void detach(Observer *, const IpAddress&);

    void update(SubjectType, void *);
private:
    NeighOrch *m_neighOrch;

    int m_nextHopGroupCount;
    bool m_resync;

    RouteTable m_syncdRoutes;
    NextHopGroupTable m_syncdNextHopGroups;

    set<IpAddress> m_unresolvedNextHops;
    NextHopRouteTable m_unresolvedNextHopRoutes;

    RouteObserverTable m_routeObservers;

    void increaseNextHopRefCount(IpAddresses);
    void decreaseNextHopRefCount(IpAddresses);

    bool addNextHopGroup(IpAddresses);
    bool removeNextHopGroup(IpAddresses);

    void addTempRoute(IpPrefix, IpAddresses);
    bool addRoute(IpPrefix, IpAddresses);
    bool removeRoute(IpPrefix);

    void doTask(Consumer& consumer);

    void notifyRouteChangeObservers(IpPrefix, IpAddresses, bool);

    void addUnresolvedNextHopRoute(IpAddress, IpPrefix, IpAddresses);
};

#endif /* SWSS_ROUTEORCH_H */
