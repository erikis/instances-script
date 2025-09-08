#!/usr/bin/env python3
# Source: https://github.com/erikis/instances-script
# MIT License
#
# Copyright (c) 2025 Erik Isaksson
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
"""Update, add, or remove an instance in instances JSON"""
import json
import sys
import os
import subprocess
import pathlib
import argparse
import re
import ipaddress
import filelock
# Debian requirements: apt install python3 python3-filelock jq

def main():
    """Update, add, or remove an instance in instances JSON"""
    parser = argparse.ArgumentParser(add_help=False, prefix_chars=[None],
            description="Update, add, or remove an instance in instances JSON \
            (default path /var/lib/misc/instances.json)")
    parser.add_argument('action', help="dnsmasq dhcp-script action, or special action: \
            --initialize, --rename, --remove, --help")
    parser.add_argument('mac_address', nargs='?', default=None, help="MAC address (if IPv6 then \
            ignored and DNSMASQ_MAC is used), or interface (e.g., br0) if action is --initialize")
    parser.add_argument('ip_address', nargs='?', default=None, help="IPv4 or IPv6 address, or \
            name if action is --initialize or --rename, or not used if action is --remove")
    parser.add_argument('hostname', nargs='?', default=None, help="name (only used by dnsmasq)")
    parser.add_argument('ignored', nargs='*', default=None, help="extra arguments for ignored \
            actions (only used by dnsmasq)")

    # When executed as dhcp-script there are only positional arguments, and in case they ever start
    # with --/-, parse without (valid) prefix_chars so that --/- options are effectively disabled.
    # Instead, use -- as prefix for special actions to avoid future conflicts with dnsmasq actions.
    args = parser.parse_args()
    action = args.action
    mac_address = args.mac_address
    ip_address = None
    hostname = None
    interface_name = None

    def check_arg_count(mini, maxi): # Action is always required but others depend on the action
        count = len(sys.argv) - 1 # Don't count the script name
        if (not mini is None and count < mini) or (not maxi is None and count > maxi):
            print(f"Wrong number of arguments for action {action}, see --help", file=sys.stderr)
            sys.exit(1)

    match action:
        case 'add' | 'old':
            # Executed by dnsmasq for lease creation (add) by using the dnsmasq option
            # --dhcp-script with the path to this script and on renewal (old) with the option
            # --script-on-renewal. Also invoked on dnsmasq startup and on HUP signal.
            check_arg_count(3, None) # No maximum number of arguments in case dnsmasq adds more
            try:
                ip_address = ipaddress.ip_address(args.ip_address)
            except ValueError:
                print(f"Invalid IP address: {args.ip_address}", file=sys.stderr)
                sys.exit(1)
            # For IPv6 the MAC address is instead provided in an environment variable
            if isinstance(ip_address, ipaddress.IPv6Address):
                mac_address = os.environ.get('DNSMASQ_MAC') # "MAC address of the client, if known"
                if not mac_address:
                    sys.exit(0) # No update is possible but not considered an error
            hostname = args.hostname # "the hostname, if known"
        case '--initialize':
            # Special action for creating the JSON file without being run as a dhcp-script.
            # Creates the instance for the interface, with the interface given as mac_address
            # (e.g., br0) and name (e.g., host) as ip_address (ip_address will remain None).
            check_arg_count(3, 3)
            interface_name = mac_address
            mac_address = None
            hostname = args.ip_address
        case '--rename':
            # Special action for changing the name of an instance identified by mac_address.
            # In this case the name is given as ip_address (ip_address will remain None).
            check_arg_count(3, 3)
            hostname = args.ip_address
        case '--remove':
            # Special action for removing an instance identified by mac_address.
            # Only mac_address is given (hostname and ip_address will remain None).
            check_arg_count(2, 2)
        case '--delete':
            print("Did you mean --remove? See --help", file=sys.stderr)
            sys.exit(0)
        case '--help' | '-h' | 'help': # Probably doesn't hurt to be more helpful
            parser.print_help()
            sys.exit(0)
        case _:
            # Other action when executed by dnsmasq as dhcp-script -- ignore.
            # Notably, the 'del' action when a lease has been destroyed is ignored, because in
            # normal operation the instances JSON file is regarded as append-only. If an instance
            # needs to be removed then use the special 'remove' action.
            sys.exit(0)

    # Roughly validate mac_address, hostname, interface_name
    mac_address_re = r'([0-9a-f]{2}:){5}[0-9a-f]{2}'
    if not mac_address is None and not re.fullmatch(mac_address_re, mac_address):
        print(f"Invalid MAC address: {mac_address}", file=sys.stderr)
        sys.exit(1)
    if not interface_name is None and not re.fullmatch(r'[^"]+', interface_name):
        print(f"Invalid interface name: {interface_name}", file=sys.stderr)
        sys.exit(1)
    if not hostname is None and not re.fullmatch(r'[a-zA-Z][a-zA-Z0-9-]*', hostname):
        print(f"Invalid hostname: {hostname}", file=sys.stderr)
        sys.exit(1)

    # Figure out all file paths
    file_prefix = os.environ.get('INSTANCES_BASE_PATH', default='/var/lib/misc/instances')
    file_suffix = ''
    file_id = os.environ.get('INSTANCES_BASE_ID')
    if file_id and not re.fullmatch(r'[a-zA-Z0-9_]+', file_id):
        print(f"Invalid instances base id: {file_id}", file=sys.stderr)
        sys.exit(1)
    if file_id:
        file_suffix = f'-{file_id}'
    file_path = f'{file_prefix}{file_suffix}.json'
    updated_path = f'{file_prefix}{file_suffix}.updated'
    lock_path = f'{file_prefix}{file_suffix}.lock'

    # While for dhcp-script "at most one instance of the script is ever running", the script can
    # also be executed manually, and the JSON file is read by instances-process.py, so there might
    # be concurrent access and a file lock is necessary.
    lock = filelock.FileLock(lock_path, timeout=10)
    lock.acquire()
    try:
        # Load existing instances
        instances, interface_mac_address = load_instances_json(interface_name, file_path)
        if mac_address is None:
            mac_address = interface_mac_address
            if mac_address is None:
                print(f"Couldn't get MAC address for interface {interface_name}", file=sys.stderr)
                sys.exit(1)
            elif not re.fullmatch(mac_address_re, mac_address):
                print(f"Invalid MAC address for interface {interface_name}: {mac_address}", \
                        file=sys.stderr)
                sys.exit(1) # In case of bad data (see load_instances_json)

        # Update or add the instance
        changes_made = update_instance(instances, mac_address, ip_address, hostname)

        # Save if changes were made
        if changes_made:
            save_instances_json(file_path, instances)
            pathlib.Path(updated_path).touch()
            print(f"Instance updated: {mac_address} [{ip_address}] ({hostname})", file=sys.stderr)
    finally:
        lock.release()

ENC = 'utf-8'
ULA = ipaddress.IPv6Network('fc00::/7') # RFC 4193 Unique Local IPv6 Unicast Addresses

def load_instances_json(interface_name, file_path):
    """Load the instances JSON file, return empty dict if file doesn't exist"""
    if os.path.exists(file_path):
        try:
            with open(file_path, 'r', encoding=ENC) as f:
                instances = json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            print(f"Error reading JSON file: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        instances = {}

    # For the special 'initialize' action an interface name is provided. Use it to create (or
    # update) an instance for the interface, with info equivalent to that of other instances.
    if interface_name:
        # Get the interface's MAC address, IPv4 address, and IPv6 addresses using the ip command.
        # Secondary IPv4 and temporary IPv6 addresses (see "man ip-address") are not supported.
        results = []
        commands = [
            f"ip -json address show dev \"{interface_name}\" | jq -r '.[] | .address'",
            f"ip -json address show dev \"{interface_name}\" -secondary | jq -r '.[] | .addr_info[] | select(.family==\"inet\") | .local'",  # pylint: disable=line-too-long
            f"ip -json address show dev \"{interface_name}\" -temporary | jq -r '.[] | .addr_info[] | select(.family==\"inet6\") | .local'"  # pylint: disable=line-too-long
        ]
        for command in commands:
            result = subprocess.run(command, shell=True, capture_output=True, text=True,
                    check=False)
            results.append(result.stdout.splitlines())
        if len(results[0]) != 1:
            # Unable to get the MAC address -- wrong interface name?
            return instances, None
        mac_address = results[0][0] # Validated in main
        instance = {
            'name': '' # The instance name will be set later by update_instance
        }
        if len(results[1]) == 1:
            try:
                instance['ipv4'] = str(ipaddress.IPv4Address(results[1][0]))
            except ipaddress.AddressValueError:
                pass # In case of bad data
        for ipv6_address in results[2]:
            try:
                ip_address = ipaddress.IPv6Address(ipv6_address)
                ip_network = ipaddress.ip_network(int(ip_address))
                if ip_address.is_global:
                    instance['ipv6_gua'] = str(ip_address) # Global unicast
                elif ULA.supernet_of(ip_network):
                    instance['ipv6_ula'] = str(ip_address) # Unique local
                elif ip_address.is_link_local:
                    instance['ipv6_lla'] = str(ip_address) # Link-local
            except ipaddress.AddressValueError:
                continue # In case of bad data
        instances[mac_address] = instance
        return instances, mac_address
    return instances, None

def save_instances_json(file_path, instances):
    """Save the instances JSON to file"""
    try:
        with open(file_path, 'w', encoding=ENC) as f:
            json.dump(instances, f, indent=2)
    except IOError as e:
        print(f"Error writing JSON file: {e}", file=sys.stderr)
        sys.exit(1)

def update_instance(instances, mac_address, ip_address, hostname):
    """Update or add instance in the instances dictionary"""

    # Find or create the instance
    updated = False
    if mac_address not in instances:
        if ip_address is None:
            # Trying to rename or remove non-existent instance -- ignore
            return updated
        # Check if there's a name that can be used
        name = ''
        if hostname:
            # If another instance has the same name then don't allow it for this instance
            # (instead, it would need to be named using the 'rename' command of this script)
            name = hostname
            for mac, ins in instances.items():
                if ins.get('name') == hostname:
                    name = ''
        # Calculate the EUI-64 IPv6 link-local address based on the MAC address
        # Following RFC 4291 Appendix A:
        # 1. Invert universal/local bit (bit 7) (^2 = XOR 2nd bit, [2:] = skip '0x')
        # 2. Insert two octets 0xFF and 0xFE in the middle of the 48-bit MAC address
        mac_hex = mac_address.replace(':', '') # Assume already lower-case
        eui64 = f'{mac_hex[0:1]}{hex(int(mac_hex[1:2],16)^2)[2:]}{mac_hex[2:6]}fffe{mac_hex[6:]}'
        ipv6_lla = f'fe80::{eui64[0:4]}:{eui64[4:8]}:{eui64[8:12]}:{eui64[12:16]}'
        instance = {
            'name': name,
            'ipv6_lla': ipv6_lla # Link-local
        }
        instances[mac_address] = instance
        updated = True
    else:
        instance = instances[mac_address]

    # Handle special actions (ip_address is None)
    if ip_address is None:
        if hostname is None:
            # Not actually updating IP address but removing the instance
            del instances[mac_address]
            updated = True
        else:
            # Not actually updating IP address but renaming the instance
            if instance.get('name') != hostname:
                instance['name'] = hostname
                updated = True
            # If another instance has the same name then clear its name
            for mac, ins in instances.items():
                if mac != mac_address:
                    if ins.get('name') == hostname:
                        ins['name'] = ''
                        updated = True

    # Update IP address field based on address type
    else:
        if isinstance(ip_address, ipaddress.IPv6Address):
            ip_network = ipaddress.ip_network(int(ip_address))
            if ip_address.is_global:
                if instance.get('ipv6_gua') != str(ip_address):
                    instance['ipv6_gua'] = str(ip_address) # Global unicast
                    updated = True
            elif ULA.supernet_of(ip_network):
                if instance.get('ipv6_ula') != str(ip_address):
                    instance['ipv6_ula'] = str(ip_address) # Unique local
                    updated = True
        elif isinstance(ip_address, ipaddress.IPv4Address):
            if instance.get('ipv4') != str(ip_address):
                instance['ipv4'] = str(ip_address)
                updated = True

        # If another instance has the same IP address then no longer use it for that instance
        ip_address_fields = ['ipv4', 'ipv6_gua', 'ipv6_ula']
        for mac, ins in instances.items():
            if mac != mac_address:
                for ip_address_field in ip_address_fields:
                    ins_ip_address = ins.get(ip_address_field)
                    if ins_ip_address and ins_ip_address == instance.get(ip_address_field):
                        del ins[ip_address_field]
                        updated = True

    return updated

if __name__ == '__main__':
    main()
