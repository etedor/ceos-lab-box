# -*- coding: utf-8 -*-`_

import re
from enum import Enum
from pathlib import Path

import docker
from jinja2 import Template
from netaddr import IPNetwork
from ruamel.yaml import YAML


class LoadMethod(Enum):
    CVP = 1
    FILE = 2
    HTTP = 3


def _load_file(path):
    file = Path(path)
    raw = file.read_text()
    return raw


def _load_raw(method, path):
    if method == LoadMethod.CVP:
        raise NotImplementedError
        # raw = load_configlet(path)
    elif method == LoadMethod.FILE:
        raw = _load_file(path)
    elif method == LoadMethod.HTTP:
        raise NotImplementedError
    return raw


def load_template(method, path):
    raw = _load_raw(method, path)
    template = Template(raw, lstrip_blocks=True, trim_blocks=True)
    return template


def load_yaml(method, path):
    y = YAML(typ="safe")
    raw = _load_raw(method, path)
    data = y.load(raw)
    return data


def get_interface(if_name):
    if_pattern = re.compile(r"([a-zA-Z]+)(\d+(?:\/\d+)?)")
    if_type = if_pattern.search(if_name).group(1)
    if_number = if_pattern.search(if_name).group(2)
    return if_type, if_number


def get_interface_ip(name, intfs):
    for intf in intfs:
        if name in intf:
            network = IPNetwork(intf[name].get("ip"))
            return network.ip
    return None


def get_peer_ip(ip):
    """Determine the peer IP in a /30 or /31 network."""
    network = IPNetwork(ip)
    if network.version != 4 or network.prefixlen not in {
        30,
        31,
    }:
        raise ValueError("ip: '%s' is not an IPv4 /30 or /31" % ip)

    local, cidr = network.ip, network.cidr.ip

    if network.prefixlen == 30:
        hosts = [cidr + 1, cidr + 2]
    elif network.prefixlen == 31:
        hosts = [cidr, cidr + 1]

    for peer in hosts:
        if peer != local:
            return str(peer)
