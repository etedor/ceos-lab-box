#!/usr/bin/env python3

import argparse
import re

from common import (LoadMethod, get_interface, get_peer_ip, load_template,
                    load_yaml, get_interface_ip)
from nornir import InitNornir
from nornir.core.deserializer.inventory import Inventory
from nornir.core.task import Result
from nornir.plugins.functions.text import print_result
from nornir.plugins.tasks.networking import napalm_configure
from netaddr import IPNetwork
from pathlib import Path

LOAD_METHOD = LoadMethod.FILE


def task(task):
    dry_run = task.is_dry_run()
    napalm = task.host.get_connection("napalm", task.nornir.config)

    intf_types = {
        "et": "Ethernet",
        "lo": "Loopback",
        "ma": "Management",
    }
    leaf_roles = {
        "compute",
        "service",
        "storage",
    }

    root = Path(__file__).parent
    templates = Path(f"{root}/templates")

    # fmt: off
    evpn_af_evpn_template = load_template(LOAD_METHOD, f"{templates}/jinja_evpn_af_evpn.j2")
    evpn_af_ipv4_template = load_template(LOAD_METHOD, f"{templates}/jinja_evpn_af_ipv4.j2")
    evpn_bgp_template = load_template(LOAD_METHOD, f"{templates}/jinja_evpn_bgp.j2")
    evpn_bgp_overlay_neighbor_template = load_template(LOAD_METHOD, f"{templates}/jinja_evpn_bgp_overlay_neighbor.j2")
    evpn_bgp_underlay_neighbor_template = load_template(LOAD_METHOD, f"{templates}/jinja_evpn_bgp_underlay_neighbor.j2")
    interface_template = load_template(LOAD_METHOD, f"{templates}/jinja_interface.j2")
    mlag_template = load_template(LOAD_METHOD, f"{templates}/jinja_mlag.j2")
    mlag_ibgp_template = load_template(LOAD_METHOD, f"{templates}/jinja_mlag_ibgp.j2")
    # fmt: on

    switches = load_yaml(LOAD_METHOD, f"{root}/switches.yaml")

    leaves = []
    spines = []
    for sw in switches:
        sw_name = sw.get("name")
        if sw["role"] in leaf_roles:
            leaves.append(sw_name)
        elif sw["role"] == "spine":
            spines.append(sw_name)
    leaves.sort()
    spines.sort()

    name = str(task.host)
    sw = next(sw for sw in switches if sw["name"] == name)

    intfs_routed = []
    for intf in sw["interfaces"]:
        intf_name = list(intf.keys())[0]
        intf_type, _ = get_interface(intf_name)
        intf_ip = intf.get(intf_name, {}).get("ip")
        if intf_type == "et" and intf_ip:
            intfs_routed.append(intf)

    peer_ips = []
    for intf in intfs_routed:
        intf_name = list(intf.keys())[0]
        intf_ip = intf.get(intf_name, {}).get("ip")
        peer_ip = get_peer_ip(intf_ip)
        peer_ips.append(peer_ip)

    config = []
    config.extend(["hostname {name}".format(name=sw["name"])])

    for intf in sw.get("interfaces"):
        intf_name = list(intf.keys())[0]
        intf_pattern = re.compile(r"([a-zA-Z]+)(\d+(?:\/\d+)?)")
        intf_type, intf_number = get_interface(intf_name)
        intf_ip = intf.get(intf_name, {}).get("ip")
        intf_description = intf.get(intf_name, {}).get("desc")

        configlet = interface_template.render(
            description=intf_description,
            ip=intf_ip,
            number=intf_number,
            type_=intf_types[intf_type],
        )
        config.extend(configlet.split("\n"))

    if "mlag" in sw:
        mlag = sw.get("mlag", {})
        ip = mlag.get("ip")

        interfaces = []
        for intf in mlag.get("interfaces", []):
            intf_type, intf_number = get_interface(intf)
            interfaces.append(
                "{type_}{number}".format(
                    number=intf_number, type_=intf_types[intf_type],
                )
            )

        configlet = mlag_template.render(
            domain=sw.get("bgp-as"),
            interfaces=interfaces,
            ip=ip,
            peer_ip=get_peer_ip(ip),
            port_channel=mlag.get("port-channel"),
            vlan=mlag.get("vlan"),
        )
        config.extend(configlet.split("\n"))

    if "bgp-as" in sw:
        router_id = next(
            intf.get("lo0", {}).get("ip")
            for intf in sw.get("interfaces", [])
            if "lo0" in intf
        ).replace("/32", "")

        configlet = evpn_bgp_template.render(
            bgp_as=sw.get("bgp-as"), router_id=router_id,
        )
        config.extend(configlet.split("\n"))

        if sw.get("role") in leaf_roles:
            peers = spines
        elif sw.get("role") == "spine":
            peers = leaves
        for peer in peers:
            pr = next(sw for sw in switches if sw.get("name") == peer)
            peer_ip = next(
                intf.get("lo0", {}).get("ip")
                for intf in pr.get("interfaces", [])
                if "lo0" in intf
            ).replace("/32", "")
            peer_as = pr.get("bgp-as")
            configlet = evpn_bgp_overlay_neighbor_template.render(
                neighbor_as=peer_as,
                neighbor_ip=peer_ip,
                neighbor_name="{peer} lo0".format(peer=peer),
            )
            config.extend(configlet.split("\n"))

            for intf in pr.get("interfaces", []):
                intf_name = list(intf.keys())[0]
                intf_ip = intf.get(intf_name, {}).get("ip").split("/")[0]
                if intf_ip in peer_ips:
                    configlet = evpn_bgp_underlay_neighbor_template.render(
                        neighbor_as=peer_as,
                        neighbor_ip=intf_ip,
                        neighbor_name="{peer} {intf}".format(
                            peer=peer, intf=intf_name,
                        ),
                    )
                    config.extend(configlet.split("\n"))

        if "mlag" in sw:
            configlet = mlag_ibgp_template.render(
                bgp_as=sw.get("bgp-as"),
                mlag_neighbor=get_peer_ip(sw.get("mlag", {}).get("ip")),
            )
            config.extend(configlet.split("\n"))

        configlet = evpn_af_evpn_template.render()
        config.extend(configlet.split("\n"))

        networks = []
        for intf in sw["interfaces"]:
            intf_name = list(intf.keys())[0]
            if intf_name.startswith("lo"):
                networks.append(intf.get(intf_name, {}).get("ip"))
        configlet = evpn_af_ipv4_template.render(networks=networks,)
        config.extend(configlet.split("\n"))

    vxlan_template = load_template(LOAD_METHOD, f"{templates}/jinja_vxlan.j2")
    vlans = load_yaml(LOAD_METHOD, f"{root}/vlans.yaml")
    vrfs = load_yaml(LOAD_METHOD, f"{root}/vrfs.yaml")

    for vlan in vlans:
        vlan["network"] = IPNetwork(vlan.get("gateway")).cidr

    bgp_as = sw.get("bgp-as")

    sw_intfs = sw.get("interfaces", [])
    lo0_ip = get_interface_ip("lo0", sw_intfs)
    lo100_ip = get_interface_ip("lo100", sw_intfs)

    router_id = lo0_ip
    vxlan_src = "100" if lo100_ip else "0"

    configlet = vxlan_template.render(
        bgp_as=bgp_as, router_id=router_id, vlans=vlans, vxlan_src=vxlan_src, vrfs=vrfs
    )
    config.extend(configlet.split("\n"))

    configuration = "\n".join(config)

    filename = None
    replace = False
    if replace:
        napalm.load_replace_candidate(filename=filename, config=configuration)
    else:
        napalm.load_merge_candidate(filename=filename, config=configuration)
    diff = napalm.compare_config()

    if not dry_run and diff:
        napalm.commit_config()
    else:
        napalm.discard_config()

    return Result(host=task.host, diff=diff, changed=len(diff) > 0)


def main(dry_run, topology, site=None, role=None):
    nr = InitNornir(
        core={"num_workers": 100},
        inventory={"plugin": "docker_inventory.DockerInventory", "options": {"topology": topology}},
        dry_run=dry_run
    )
    if site and role:
        hosts = nr.filter(site=site, role=role)
        result = hosts.run(task=task)
    elif site:
        hosts = nr.filter(site=site)
        result = hosts.run(task=task)
    elif role:
        hosts = nr.filter(role=role)
        result = hosts.run(task=task)
    else:
        result = nr.run(task=task)
    print_result(result)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-t", "--topology", dest="topology", required=True)

    dry_run_parser = parser.add_mutually_exclusive_group(required=False)
    dry_run_parser.add_argument("--dry-run", dest="dry_run", action="store_true")
    dry_run_parser.add_argument("--run", dest="dry_run", action="store_false")

    parser.set_defaults(dry_run=True)
    args = parser.parse_args()

    main(dry_run=args.dry_run, topology=args.topology)
