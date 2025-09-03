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
"""Read instances JSON and output hosts and nftables files"""
import json
import sys
import os
import argparse
import re
import ipaddress
import filelock
# Debian requirements: apt install python3 python3-filelock

def main():
    """Read instances JSON and output hosts and nftables files"""
    parser = argparse.ArgumentParser(description="Read instances JSON (default path \
            /var/lib/misc/instances.json) and output hosts and nftables files")
    parser.add_argument('-f', '--force', action='store_true',
            help="process even if an update is not detected")

    args = parser.parse_args()
    is_forced = args.force

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
    hosts_path = f'{file_prefix}{file_suffix}.hosts'
    nftables_path = f'{file_prefix}{file_suffix}.nftables'
    updated_path = f'{file_prefix}{file_suffix}.updated'
    lock_path = f'{file_prefix}{file_suffix}.lock'

    # Acquire a file lock and start processing
    lock = filelock.FileLock(lock_path, timeout=10)
    lock.acquire()
    try:
        if os.path.exists(updated_path):
            os.remove(updated_path)
        elif not is_forced:
            # Checked whether updated and wasn't -- no need to process
            sys.exit(10) # Special status 10 for not updated
        print("Loading:", end=' ', file=sys.stderr)
        instances = load_instances_json(file_path)
        print(f"{len(instances)} instances;", end=' ', file=sys.stderr)
        print("saving:", end=' ', file=sys.stderr)
        count = save_instances_hosts(hosts_path, instances)
        print(f"{count} host addresses,", end=' ', file=sys.stderr)
        count, count_sets = save_instances_nftables(nftables_path, instances)
        print(f"{count} nftables rules, {count_sets} nftables sets;", end=' ', file=sys.stderr)
        print("done", file=sys.stderr)
    finally:
        lock.release()

ENC = 'utf-8'

def load_instances_json(file_path):
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
    return instances

def save_instances_hosts(file_path, instances):
    """Save the host addresses to file"""
    count = 0
    domain = os.environ.get('INSTANCES_HOSTS_DOMAIN', default='.instance.internal')
    if not re.fullmatch(r'[a-zA-Z0-9\.-]*', domain):
        print(f"Invalid hosts domain: {domain}", file=sys.stderr)
        return count
    try:
        with open(file_path, 'w', encoding=ENC) as f:
            ip_address_fields = ['ipv4', 'ipv6_gua', 'ipv6_ula', 'ipv6_lla']
            for _, instance in instances.items():
                name = instance.get('name')
                if name:
                    for ip_address_field in ip_address_fields:
                        ip_address = instance.get(ip_address_field)
                        if ip_address:
                            # Write <ip-address> <full-name> <extra-names>
                            full_name = f'{name}{domain}'
                            extra_names = ''
                            match ip_address_field:
                                case 'ipv4':
                                    # Extra name for only resolving to IPv4 address
                                    extra_names = f' {name}.v4{domain}'
                                case 'ipv6_gua':
                                    # Extra names for resolving to IPv6 globally reachable address
                                    extra_names = f' {name}.v6{domain} {name}.g6{domain}'
                                case 'ipv6_ula':
                                    # Extra names for resolving to IPv6 unique local address
                                    extra_names = f' {name}.v6{domain} {name}.u6{domain}'
                                case 'ipv6_lla':
                                    # Ensure IPv6 link-local address is only used if asked for
                                    full_name = f'{name}.l6{domain}'
                            f.write(f'{ip_address} {full_name}{extra_names}\n')
                            count += 1
    except IOError as e:
        print(f"Error writing hosts file: {e}", file=sys.stderr)
        sys.exit(1)
    return count

def save_instances_nftables(file_path, instances):
    """Save the nftables rules and sets to files"""

    # Check which sets to include: comma-separated hostnames in INSTANCES_NFTABLES_ADDRESS_SETS
    all_addresses = { 'v4': [], 'v6': [], 'g6': [], 'u6': [], 'l6': [] }
    address_maps = { None: all_addresses } # Use None because instance names might be empty string
    for address_set in os.environ.get('INSTANCES_ADDRESS_SETS', default='host').split(','):
        name = address_set.strip()
        if name:
            if re.fullmatch(r'[a-zA-Z][a-zA-Z0-9-]*', name): # Name regex from instances-update.py
                name = name.replace('-', '_') # Hyphen not allowed in nftables identfier
                address_maps[name] = { key: [] for key, value in all_addresses.items() }
            else:
                # Print the error but continue, ignoring the invalid hostname
                print(f"Invalid hostname for address set: {name}", file=sys.stderr)

    # Write the rules file and also collect addresses for the sets
    count = 0
    try:
        with open(f'{file_path}_chains', 'w', encoding=ENC) as f:
            f.write('# Use: ether type arp jump instances_drop_arp\n')
            f.write('chain instances_drop_arp {\n')
            for mac_address, instance in instances.items():
                name = instance.get('name')
                if name:
                    comment = f' comment "{name}"'
                else:
                    comment = ''
                ip_address = instance.get('ipv4')
                if ip_address:
                    f.write(f'    arp saddr ip {ip_address} counter ether saddr {mac_address} counter return{comment}\n') # pylint: disable=line-too-long
                    count += 1
                    for address_map in [all_addresses, address_maps.get(name)]:
                        if address_map:
                            address_map['v4'].append(ip_address)
            f.write('    counter drop comment "lockdown" # prepend to log to dmesg: log prefix "[nftables] dropped ARP: "\n') # pylint: disable=line-too-long
            count += 1
            f.write('}\n')
            f.write('# Use: ether type ip6 icmpv6 type nd-neighbor-advert jump instances_drop_ndp\n') # pylint: disable=line-too-long
            f.write('chain instances_drop_ndp {\n')
            ip_address_fields = ['ipv6_gua', 'ipv6_ula', 'ipv6_lla']
            for mac_address, instance in instances.items():
                name = instance.get('name')
                if name:
                    comment = f' comment "{name}"'
                else:
                    comment = ''
                for ip_address_field in ip_address_fields:
                    ip_address = instance.get(ip_address_field)
                    if ip_address:
                        ip_hex = ipaddress.ip_address(ip_address).exploded.replace(':', '')
                        # See RFC 4861 "Neighbor Advertisement Message Format":
                        # Bit 384 of IPv6 packet = bit 64 of NA message = start of Target Address
                        f.write(f'    @nh,384,128 0x{ip_hex} counter ether saddr {mac_address} counter return{comment}\n') # pylint: disable=line-too-long
                        count += 1
                        for address_map in [all_addresses, address_maps.get(name)]:
                            if address_map:
                                if ip_address_field != 'ipv6_lla':
                                    address_map['v6'].append(ip_address)
                                    match ip_address_field:
                                        case 'ipv6_gua':
                                            address_map['g6'].append(ip_address)
                                        case 'ipv6_ula':
                                            address_map['u6'].append(ip_address)
                                else:
                                    address_map['l6'].append(ip_address)
            f.write('    counter drop comment "lockdown" # prepend to log to dmesg: log prefix "[nftables] dropped NDP: "\n') # pylint: disable=line-too-long
            count += 1
            f.write('}\n')
    except IOError as e:
        print(f"Error writing nftables file: {e}", file=sys.stderr)
        sys.exit(1)

    # Write the sets file with naming similar to that of the hosts file
    count_sets = 0
    try:
        with open(f'{file_path}_sets', 'w', encoding=ENC) as f:
            for address_name, address_map in address_maps.items():
                for address_type, ip_addresses in address_map.items():
                    if address_name:
                        f.write(f'# Use: @{address_name}.{address_type}.instance\n')
                        f.write(f'set {address_name}.{address_type}.instance {{\n')
                    else:
                        f.write(f'# Use: @all_{address_type}.instance\n')
                        f.write(f'set all_{address_type}.instance {{\n')
                    match address_type:
                        case 'v4':
                            f.write('    type ipv4_addr\n')
                        case 'v6' | 'g6' | 'u6' | 'l6':
                            f.write('    type ipv6_addr\n')
                    if len(ip_addresses) > 0: # Empty "elements = { }" is not allowed
                        f.write('    elements = { ')
                        for ip_address in ip_addresses:
                            f.write(f'{ip_address}, ')
                        f.write('}\n')
                    f.write('}\n')
                    count_sets += 1
    except IOError as e:
        print(f"Error writing nftables_sets file: {e}", file=sys.stderr)
        sys.exit(1)

    return count, count_sets

if __name__ == '__main__':
    main()
