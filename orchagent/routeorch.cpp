#include "routeorch.h"

#include "logger.h"

#include "assert.h"

extern sai_object_id_t gVirtualRouterId;

extern sai_next_hop_group_api_t*    sai_next_hop_group_api;
extern sai_route_api_t*             sai_route_api;

extern PortsOrch *gPortsOrch;

bool RouteOrch::hasNextHopGroup(IpAddresses ipAddresses)
{
    return m_syncdNextHopGroups.find(ipAddresses) != m_syncdNextHopGroups.end();
}

void RouteOrch::doTask(Consumer& consumer)
{
    SWSS_LOG_ENTER();

    if (!gPortsOrch->isInitDone())
        return;

    auto it = consumer.m_toSync.begin();
    while (it != consumer.m_toSync.end())
    {
        KeyOpFieldsValuesTuple t = it->second;

        string key = kfvKey(t);
        string op = kfvOp(t);

        /* Get notification from application */
        /* resync application:
         * When routeorch receives 'resync' message, it marks all current
         * routes as dirty and waits for 'resync complete' message. For all
         * newly received routes, if they match current dirty routes, it unmarks
         * them dirty. After receiving 'resync complete' message, it creates all
         * newly added routes and removes all dirty routes.
         */
        if (key == "resync")
        {
            if (op == "SET")
            {
                /* Mark all current routes as dirty (DEL) in consumer.m_toSync map */
                SWSS_LOG_NOTICE("Start resync routes\n");
                for (auto i : m_syncdRoutes)
                {
                    vector<FieldValueTuple> v;
                    auto x = KeyOpFieldsValuesTuple(i.first.to_string(), DEL_COMMAND, v);
                    consumer.m_toSync[i.first.to_string()] = x;
                }
                m_resync = true;
            }
            else
            {
                SWSS_LOG_NOTICE("Complete resync routes\n");
                m_resync = false;
            }

            it = consumer.m_toSync.erase(it);
            continue;
        }

        if (m_resync)
        {
            it++;
            continue;
        }

        IpPrefix ip_prefix = IpPrefix(key);

        /* Currently we don't support IPv6 */
        if (!ip_prefix.isV4())
        {
            SWSS_LOG_WARN("Get unsupported IPv6 task ip:%s", ip_prefix.to_string().c_str());
            it = consumer.m_toSync.erase(it);
            continue;
        }

        if (op == SET_COMMAND)
        {
            IpAddresses ip_addresses;
            string alias;

            for (auto i : kfvFieldsValues(t))
            {
                if (fvField(i) == "nexthop")
                    ip_addresses = IpAddresses(fvValue(i));

                if (fvField(i) == "ifindex")
                    alias = fvValue(i);
            }

            // TODO: set to blackhold if nexthop is empty?
            if (ip_addresses.getSize() == 0)
            {
                it = consumer.m_toSync.erase(it);
                continue;
            }

            // TODO: cannot trust m_portsOrch->getPortIdByAlias because sometimes alias is empty
            // TODO: need to split aliases with ',' and verify the next hops?
            if (alias == "eth0" || alias == "lo" || alias == "docker0")
            {
                it = consumer.m_toSync.erase(it);
                continue;
            }

            if (m_syncdRoutes.find(ip_prefix) == m_syncdRoutes.end() || m_syncdRoutes[ip_prefix] != ip_addresses)
            {
                if (addRoute(ip_prefix, ip_addresses))
                    it = consumer.m_toSync.erase(it);
                else
                    it++;
            }
            else
                /* Duplicate entry */
                it = consumer.m_toSync.erase(it);
        }
        else if (op == DEL_COMMAND)
        {
            if (m_syncdRoutes.find(ip_prefix) != m_syncdRoutes.end())
            {
                if (removeRoute(ip_prefix))
                    it = consumer.m_toSync.erase(it);
                else
                    it++;
            }
            else
                /* Cannot locate the route */
                it = consumer.m_toSync.erase(it);
        }
        else
        {
            SWSS_LOG_ERROR("Unknown operation type %s\n", op.c_str());
            it = consumer.m_toSync.erase(it);
        }
    }
}

void RouteOrch::increaseNextHopRefCount(IpAddresses ipAddresses)
{

    if (ipAddresses.getSize() == 1)
    {
        IpAddress ip_address(ipAddresses.to_string());
        m_neighOrch->increaseNextHopRefCount(ip_address);
    }
    else
    {
        m_syncdNextHopGroups[ipAddresses].ref_count ++;
    }
}
void RouteOrch::decreaseNextHopRefCount(IpAddresses ipAddresses)
{
    if (ipAddresses.getSize() == 1)
    {
        IpAddress ip_address(ipAddresses.to_string());
        m_neighOrch->decreaseNextHopRefCount(ip_address);
    }
    else
    {
        m_syncdNextHopGroups[ipAddresses].ref_count --;
    }
}

bool RouteOrch::addNextHopGroup(IpAddresses ipAddresses)
{
    SWSS_LOG_ENTER();

    assert(!hasNextHopGroup(ipAddresses));

    if (m_nextHopGroupCount > NHGRP_MAX_SIZE)
    {
        SWSS_LOG_DEBUG("Failed to create next hop group. Exceeding maximum number of next hop groups.\n");
        return false;
    }

    vector<sai_object_id_t> next_hop_ids;
    set<IpAddress> next_hop_set = ipAddresses.getIpAddresses();

    /* Assert each IP address exists in m_syncdNextHops table,
     * and add the corresponding next_hop_id to next_hop_ids. */
    for (auto it : next_hop_set)
    {
        if (!m_neighOrch->hasNextHop(it))
        {
            SWSS_LOG_NOTICE("Failed to get next hop entry ip:%s",
                    it.to_string().c_str());
            return false;
        }

        sai_object_id_t next_hop_id = m_neighOrch->getNextHopId(it);
        next_hop_ids.push_back(next_hop_id);
    }

    sai_attribute_t nhg_attr;
    vector<sai_attribute_t> nhg_attrs;

    nhg_attr.id = SAI_NEXT_HOP_GROUP_ATTR_TYPE;
    nhg_attr.value.s32 = SAI_NEXT_HOP_GROUP_ECMP;
    nhg_attrs.push_back(nhg_attr);

    nhg_attr.id = SAI_NEXT_HOP_GROUP_ATTR_NEXT_HOP_LIST;
    nhg_attr.value.objlist.count = next_hop_ids.size();
    nhg_attr.value.objlist.list = next_hop_ids.data();
    nhg_attrs.push_back(nhg_attr);

    sai_object_id_t next_hop_group_id;
    sai_status_t status = sai_next_hop_group_api->
            create_next_hop_group(&next_hop_group_id, nhg_attrs.size(), nhg_attrs.data());
    if (status != SAI_STATUS_SUCCESS)
    {
        SWSS_LOG_ERROR("Failed to create next hop group nh:%s\n",
                       ipAddresses.to_string().c_str());
        return false;
    }

    m_nextHopGroupCount ++;
    SWSS_LOG_NOTICE("Create next hop group nhgid:%llx nh:%s \n",
                    next_hop_group_id, ipAddresses.to_string().c_str());

    /* Increate the ref_count for the next hops used by the next hop group. */
    for (auto it : next_hop_set)
        m_neighOrch->increaseNextHopRefCount(it);

    /*
     * Initialize the next hop gruop structure with ref_count as 0. This
     * count will increase once the route is successfully syncd.
     */
    NextHopGroupEntry next_hop_group_entry;
    next_hop_group_entry.next_hop_group_id = next_hop_group_id;
    next_hop_group_entry.ref_count = 0;
    m_syncdNextHopGroups[ipAddresses] = next_hop_group_entry;

    return true;
}

bool RouteOrch::removeNextHopGroup(IpAddresses ipAddresses)
{
    SWSS_LOG_ENTER();

    assert(hasNextHopGroup(ipAddresses));

    if (m_syncdNextHopGroups[ipAddresses].ref_count == 0)
    {
        sai_object_id_t next_hop_group_id = m_syncdNextHopGroups[ipAddresses].next_hop_group_id;
        sai_status_t status = sai_next_hop_group_api->remove_next_hop_group(next_hop_group_id);
        if (status != SAI_STATUS_SUCCESS)
        {
            SWSS_LOG_ERROR("Failed to remove next hop group nhgid:%llx\n", next_hop_group_id);
            return false;
        }

        m_nextHopGroupCount --;

        set<IpAddress> ip_address_set = ipAddresses.getIpAddresses();
        for (auto it : ip_address_set)
            m_neighOrch->decreaseNextHopRefCount(it);

        m_syncdNextHopGroups.erase(ipAddresses);
    }

    return true;
}

void RouteOrch::addTempRoute(IpPrefix ipPrefix, IpAddresses nextHops)
{
    bool to_add = false;
    auto it_route = m_syncdRoutes.find(ipPrefix);
    auto next_hop_set = nextHops.getIpAddresses();

    /*
     * A temporary entry is added when route is not in m_syncdRoutes,
     * or it is in m_syncdRoutes but the original next hop(s) is not a
     * subset of the next hop group to be added.
     */
    if (it_route != m_syncdRoutes.end())
    {
        auto tmp_set = m_syncdRoutes[ipPrefix].getIpAddresses();
        for (auto it : tmp_set)
        {
            if (next_hop_set.find(it) == next_hop_set.end())
                to_add = true;
        }
    }
    else
        to_add = true;

    if (to_add)
    {
        /* Remove next hops that are not in m_syncdNextHops */
        for (auto it = next_hop_set.begin(); it != next_hop_set.end();)
        {
            if (!m_neighOrch->hasNextHop(*it))
            {
                SWSS_LOG_NOTICE("Failed to get next hop entry ip:%s",
                       (*it).to_string().c_str());
                it = next_hop_set.erase(it);
            }
            else
                it++;
        }

        /* Return if next_hop_set is empty */
        if (next_hop_set.empty())
            return;

        /* Randomly pick an address from the set */
        auto it = next_hop_set.begin();
        advance(it, rand() % next_hop_set.size());

        /* Set the route's temporary next hop to be the randomly picked one */
        IpAddresses tmp_next_hop((*it).to_string());
        addRoute(ipPrefix, tmp_next_hop);
    }
}

bool RouteOrch::addRoute(IpPrefix ipPrefix, IpAddresses nextHops)
{
    SWSS_LOG_ENTER();

    /* next_hop_id indicates the next hop id or next hop group id of this route */
    sai_object_id_t next_hop_id;
    auto it_route = m_syncdRoutes.find(ipPrefix);

    /* The route is pointing to a next hop */
    if (nextHops.getSize() == 1)
    {
        IpAddress ip_address(nextHops.to_string());
        if (m_neighOrch->hasNextHop(ip_address))
        {
            next_hop_id = m_neighOrch->getNextHopId(ip_address);
        }
        else
        {
            SWSS_LOG_NOTICE("Failed to get next hop entry ip:%s",
                    nextHops.to_string().c_str());
            return false;
        }
    }
    /* The route is pointing to a next hop group */
    else
    {
        if (!hasNextHopGroup(nextHops)) /* Create a new next hop group */
        {
            if (!addNextHopGroup(nextHops))
            {
                /* Add a temporary route when a next hop group cannot be added */
                addTempRoute(ipPrefix, nextHops);
                /* Return false since the original route is not successfully added */
                return false;
            }
        }

        next_hop_id = m_syncdNextHopGroups[nextHops].next_hop_group_id;
    }

    /* Sync the route entry */
    sai_unicast_route_entry_t route_entry;
    route_entry.vr_id = gVirtualRouterId;
    route_entry.destination.addr_family = SAI_IP_ADDR_FAMILY_IPV4;
    route_entry.destination.addr.ip4 = ipPrefix.getIp().getV4Addr();
    route_entry.destination.mask.ip4 = ipPrefix.getMask().getV4Addr();

    sai_attribute_t route_attr;
    route_attr.id = SAI_ROUTE_ATTR_NEXT_HOP_ID;
    route_attr.value.oid = next_hop_id;

    /* If the prefix is not in m_syncdRoutes, then we need to create the route
     * for this prefix with the new next hop (group) id. If the prefix is already
     * in m_syncdRoutes, then we need to update the route with a new next hop
     * (group) id. The old next hop (group) is then not used and the reference
     * count will decrease by 1.
     */
    if (it_route == m_syncdRoutes.end())
    {
        sai_status_t status = sai_route_api->create_route(&route_entry, 1, &route_attr);
        if (status != SAI_STATUS_SUCCESS)
        {
            SWSS_LOG_ERROR("Failed to create route %s with next hop(s) %s",
                    ipPrefix.to_string().c_str(), nextHops.to_string().c_str());
            /* Clean up the newly created next hop group entry */
            if (nextHops.getSize() > 1)
            {
                removeNextHopGroup(nextHops);
            }
            return false;
        }

        /* Increase the ref_count for the next hop (group) entry */
        increaseNextHopRefCount(nextHops);
        SWSS_LOG_INFO("Create route %s with next hop(s) %s",
                ipPrefix.to_string().c_str(), nextHops.to_string().c_str());
    }
    else
    {
        sai_status_t status = sai_route_api->set_route_attribute(&route_entry, &route_attr);
        if (status != SAI_STATUS_SUCCESS)
        {
            SWSS_LOG_ERROR("Failed to set route %s with next hop(s) %s",
                    ipPrefix.to_string().c_str(), nextHops.to_string().c_str());
            return false;
        }

        /* Increase the ref_count for the next hop (group) entry */
        increaseNextHopRefCount(nextHops);

        decreaseNextHopRefCount(it_route->second);
        if (it_route->second.getSize() > 1
            && m_syncdNextHopGroups[it_route->second].ref_count == 0)
        {
            removeNextHopGroup(it_route->second);
        }
        SWSS_LOG_INFO("Set route %s with next hop(s) %s",
                ipPrefix.to_string().c_str(), nextHops.to_string().c_str());
    }

    m_syncdRoutes[ipPrefix] = nextHops;
    return true;
}

bool RouteOrch::removeRoute(IpPrefix ipPrefix)
{
    SWSS_LOG_ENTER();

    sai_unicast_route_entry_t route_entry;
    route_entry.vr_id = gVirtualRouterId;
    route_entry.destination.addr_family = SAI_IP_ADDR_FAMILY_IPV4;
    route_entry.destination.addr.ip4 = ipPrefix.getIp().getV4Addr();
    route_entry.destination.mask.ip4 = ipPrefix.getMask().getV4Addr();

    sai_status_t status = sai_route_api->remove_route(&route_entry);
    if (status != SAI_STATUS_SUCCESS)
    {
        SWSS_LOG_ERROR("Failed to remove route prefix:%s\n", ipPrefix.to_string().c_str());
        return false;
    }

    /* Remove next hop group entry if ref_count is zero */
    auto it_route = m_syncdRoutes.find(ipPrefix);
    if (it_route != m_syncdRoutes.end())
    {
        /*
         * Decrease the reference count only when the route is pointing to a next hop.
         * Decrease the reference count when the route is pointing to a next hop group,
         * and check wheather the reference count decreases to zero. If yes, then we need
         * to remove the next hop group.
         */
        decreaseNextHopRefCount(it_route->second);
        if (it_route->second.getSize() > 1
            && m_syncdNextHopGroups[it_route->second].ref_count == 0)
        {
            removeNextHopGroup(it_route->second);
        }
    }
    SWSS_LOG_INFO("Remove route %s with next hop(s) %s",
            ipPrefix.to_string().c_str(), it_route->second.to_string().c_str());

    m_syncdRoutes.erase(ipPrefix);
    return true;
}
