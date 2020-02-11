import docker
from nornir.core.deserializer.inventory import Inventory


class DockerInventory(Inventory):
    def __init__(self, **kwargs):
        topology = kwargs.get("topology", None)
        if not topology:
            raise ValueError("you must specify a docker-topo topology")

        client = docker.from_env()
        containers = client.containers.list()

        hosts = {}
        for container in containers:
            a = container.attrs
            if "ceos" not in a["Config"]["Image"]:
                continue
            ma = f"{topology}_net-0"

            name = a["Name"].split("/")[1]
            id_ = a["Id"]
            ip = a["NetworkSettings"]["Networks"][ma]["IPAddress"]

            roles = []
            if "lf" in name:
                roles.append("leaf")
            if "sp" in name:
                roles.append("spine")

            hosts.update(
                {
                    name.replace(f"{topology}_", ""): {
                        "data": {"id": id_, "roles": roles},
                        "hostname": ip,
                        "password": "admin",
                        "platform": "eos",
                        "port": None,
                        "username": "admin",
                    }
                }
            )

        defaults = {}
        groups = {}

        super().__init__(
            hosts=hosts, groups=groups, defaults=defaults, **kwargs
        )
