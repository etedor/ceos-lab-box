# cEOS Lab-in-a-Box
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

Quick and dirty cEOS lab environment using [docker-topo](https://github.com/networkop/docker-topo) and [Nornir](https://github.com/nornir-automation/nornir).

## Installation
A [CentOS 7](http://mirrors.ocf.berkeley.edu/centos/7.7.1908/isos/x86_64/CentOS-7-x86_64-Minimal-1908.iso) installation on a physical machine or hypervisor is a pre-requisite.

2 CPU / 4GB is suggested.

#### Install Docker
```
sudo yum install -y yum-utils \
  device-mapper-persistent-data \
  lvm2
```

```
sudo yum-config-manager \
    --add-repo \
    https://download.docker.com/linux/centos/docker-ce.repo
```

```
sudo yum install -y docker-ce docker-ce-cli containerd.io
```

```
sudo systemctl enable docker &&
    sudo systemctl start docker
```

Add your user to the `docker` group:
```
iam="$(whoami)"; sudo usermod -a -G docker "${iam}"
```

#### Import cEOS Image

Download a cEOS image (e.g., 4.22.3M) from [arista.com](https://www.arista.com/en/support/software-download).

Copy the image over to your CentOS machine:
```
scp cEOS-lab-4.22.3M.tar.xz $CENTOS:/tmp
```

Import into Docker:
```
docker import /tmp/cEOS-lab-4.22.3M.tar.xz ceos-lab:4.22.3M
```

#### Install Python and Packages
```
sudo yum install -y epel-release
sudo yum install -y git jq python3 python3-pip unzip &&
    pip3 install --user pipenv
```

#### Clone repo to your CentOS machine:
```
git clone https://github.com/etedor/ceos-lab-box.git
```

## Initialize
```
PIPENV_VENV_IN_PROJECT=true pipenv install
# use eth0 for management:
sed -i '409i \                               "MAPETH0": 1,' .venv/src/docker-topo/bin/docker-topo
sed -i '410i \                               "MGMT_INTF": "eth0",' .venv/src/docker-topo/bin/docker-topo
```

```
pipenv shell
```

```
docker-topo --create topo/lab.yaml &&
    sleep 300 &&
    bash ctl/ceosctl cfg_mgmt lab &&
    bash ctl/ceosctl free_space lab &&
    python3 norn/provision.py -t lab --run &&
    bash ctl/ceosctl free_space lab
```

## Lab!
List switches with:
```
bash ctl/ceosctl ls_
```

Attach to a switch with e.g.:
```
bash ctl/ceosctl attach $CONTAINER_ID
```

Run a command on a switch with e.g.:
```
bash ctl/ceosctl fast_cli $CONTAINER_ID "show version"
```

Run a command on multiple switches with e.g:
```
bash ctl/ceosctl multi_cli lab "show version"
```
