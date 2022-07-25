#!/usr/bin/env python3

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

DOCUMENTATION = '''
    name: custom
    short_description: TODO
    description:
      - TODO
    options:
      plugin:
        description: setting that ensures this is a source file for this plugin
        required: false
        type: str
        choices: ['aise.dsu.docker']
      machines:
        description: list of addresses of machines to use as container hosts
        type: list
        default: []
      containers_per_machine:
        description: how many containers to spin on each machine
        required: false
        type: int
        default: 1
      credentials:
        description: user and pass to use for ssh-ing into each machine type
        required: true
        type: dict
      vars:
        description: variables that all hosts should hold
        required: false
        type: dict
        default: {}
'''

import os

from ansible.plugins.inventory import BaseFileInventoryPlugin

NoneType = type(None)

class InventoryModule(BaseFileInventoryPlugin):

    NAME = 'custom'


    def __init__(self):
        super(InventoryModule, self).__init__()

    def verify_file(self, path: str) -> bool:
        """Check scenario file for integrity."""
        # return super(InventoryModule, self).verify_file(path)
        return True

    def parse(self, inventory, loader, path, cache=True):
        ''' parses the inventory file '''

        self.inventory = inventory

        super(InventoryModule, self).parse(inventory, loader, path, cache=cache)
        self._read_config_data(path)

        self.login_credentials = self.get_option('credentials')
        self.common_vars = self.get_option('vars')

        machines = self.canonicalize_machine_dicts(self.get_option('machines'))

        groups = self.create_groups(machines)

        hosts = self.create_machine_hosts(machines)

        self.add_hosts_to_groups(hosts, groups)

        self.create_docker_hosts(hosts, groups)

    def create_docker_hosts(self, hosts, groups):
        count = 0
        for host in hosts:
            if host.vars['role'] == 'server':
                continue

            docker_daemon = 'root@' + host.vars['ansible_host']

            for index in range(0, host.vars['num_containers']):
                self.inventory.add_host(f"docker_host_{count}")

                docker_host = self.inventory.hosts[f"docker_host_{count}"]
                docker_host.set_variable("ansible_docker_host", docker_daemon)
                docker_host.set_variable("docker_server", host.name)

                groups['docker_clients'].add_host(docker_host)

                if index in host.vars['poisoned_containers']:
                    groups['poisoned_clients'].add_host(docker_host)

                count = count + 1

    def add_hosts_to_groups(self, hosts, groups):
        for host in hosts:
            groups[host.vars['role']].add_host(host)
            groups[host.vars['type']].add_host(host)
            groups['machines'].add_host(host)

    def create_machine_hosts(self, machines):
        hosts = []

        keys = set(machines[0].keys()).difference(['name', 'address'])

        for index, machine in enumerate(machines):
            self.inventory.add_host(machine['name'])

            host = self.inventory.hosts[machine['name']]
            host.set_variable('ansible_host', machine['address'])
            host.set_variable('ansible_user', 'root')
            host.set_variable('ansible_ssh_private_key_file', '~/.ssh/aise-dsu')

            for key in keys:
                host.set_variable(key, machine[key])

            hosts.append(host)

        return hosts

    def create_groups(self, machines):
        group_names = {
            'machines': 'machines',

            # machine role
            'server': 'servers',
            'client': 'client_machines',

            # machine type
            'vm': 'vms',
            'agx': 'agxs',
            'pi': 'pis',
            'coral': 'corals',

            # other
            'docker_clients': 'docker_clients',
            'poisoned_clients': 'poisoned_clients',
        }

        groups = {}

        for key, value in group_names.items():
            self.inventory.add_group(value)
            groups[key] = self.inventory.groups[value]


        self.inventory.groups['all'].vars = self.common_vars

        return groups

    def canonicalize_machine_dicts(self, machines):
        """Canonicalize the dict that describes each machine.

        Each element in the machines list will, after this method has run, have
        the following keys:
            name: a name for the machine
            address: the IP address/domain name of the machine
            type: the type of the machine (amd64 vm, agx, ...)
            role: whether this machine will be a server or a client in FL
            num_containers: number of docker containers to spin on the machines
            poisoned_containers: list of the docker containers will be poisoned (requires role=client)
            original_credentials: the user/pass edgelab gave us to ssh into the machine
        """
        canonicalized_machines = []
        for machine in machines:
            # address key
            if isinstance(machine, str):
                machine = {'address': machine}

            # type key
            match(machine['address'][:3]):
                case s if s.isdigit():
                    machine['type'] = 'vm'
                case s if s == 'agx':
                    machine['type'] = 'agx'

            # role key
            machine['role'] = machine.get('role', 'client')

            # num_containers key
            machine['num_containers'] = machine.get('num_containers',
                    self.get_option('containers_per_machine'))

            # poisoned_containers key
            machine['poisoned_containers'] = machine.get('poisoned_containers', [])

            machine['original_credentials'] = self.login_credentials[machine['type']]

            canonicalized_machines.append(machine)

        for machine_type in {machine['type'] for machine in canonicalized_machines}:
            count = 0
            for index, machine in enumerate(canonicalized_machines):
                if machine['type'] != machine_type:
                    continue

                canonicalized_machines[index]['name'] = f"{machine_type}_{count}"

                count = count + 1

        return canonicalized_machines
