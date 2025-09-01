# Instances

_Instances_ is a [dnsmasq](https://thekelleys.org.uk/dnsmasq/doc.html) DHCP script for updating a JSON registry of addresses and names and a script for processing that registry to generate a hosts file, nftables bridge firewall rules, and nftables address sets.

## Features

_Instances_ can:

- **Register IPv4/IPv6 addresses assigned by dnsmasq's DHCPv4/DHCPv6 server** in a JSON file, with an object for every _instance_, uniquely identified by its MAC address and if known also by its hostname.
- **Register IPv4/IPv6 addresses and a name of the server** as its own instance.
- **Resolve names under the .instance.internal domain to registered addresses** using a host file for dnsmasq's DNS server, with additional subdomains for each specific address type: IPv4, IPv6, and IPv6 global unicast, unique local, and link-local (for which addresses are automatically calculated based on EUI-64).
- **Write bridge firewall rules** for [nftables](https://netfilter.org/projects/nftables/), intended to help prevent IPv4/IPv6 address spoofing (in combination with external MAC address filtering) and only allow registered addresses to be advertised on the bridge
- **Produce address sets** that can be used in nftables configuration, for all registered addresses and those of specific named instances, with empty sets generated for non-existent instances to avoid firewall startup errors.

The term _instance_ is from [Incus](https://linuxcontainers.org/incus/) where it applies to both containers and virtual machines. The main intended use case is with Incus and an externally configured bridge (not managed by Incus) and externally configured dnsmasq, with an IPv6 prefix longer than 64 bits which prevents stateless address auto-configuration (SLAAC) from being used. Other use cases may be possible where IPv6 managed address configuration (M) is enabled and SLAAC (A) is disabled, which is the default for dnsmasq's `enable-ra` option and for managed Incus bridge networks with `ipv6.dhcp.stateful: true`.

## Functionality

_Instances_ is implemented in Python (requiring version 3.11 or newer) as two scripts:

1. **instances-update.py** is a DHCP script for use with dnsmasq's `dhcp-script` option. With input being a MAC address, an IPv4/IPv6 address, and an optional hostname, the script reads a JSON file called **/var/lib/misc/instances.json** by default. An object for the MAC address is looked up. If it doesn’t exist it is created, while also storing the name, unless the name is already in use. The IP address in the object is updated, with separate fields for the IPv4 address and IPv6 global unicast, unique local, and link-local addresses. If any changes were made, the instances are written back to the file and an **instances.updated** file is created. Beyond handling DHCP script actions defined by dnsmasq, the script also supports several special actions when run manually, with the action specified as the first argument (using a `--` prefix to prevent possible future dnsmasq conflicts):
    1. **initialize** initializes the JSON file if it doesn't exist and creates an instance based on an interface name and hostname (as the second and third arguments).
    2. **rename** renames an instance identified by its MAC address (second argument) and removes the new name (third argument) from use by any other instance.
    3. **remove** removes an instance identified by its MAC address (second argument).
2. **instances-process.py** is separate script which, if the **instances.updated** file exists, deletes it, reads **instances.json**, and generates several files. If and only if processing wasn't done due to an update not being detected, the script exits with status 10. If processing was done, the generated files are:
    1. **instances.hosts** with names resolvable to registered addresses under the .instance.internal domain, with additional separate subdomains for specific address types. To use the file in dnsmasq, move the file to a directory used with its `hostsdir` option, from where the file will be read automatically.
    2. **instances.nftables_chains** with nftables chains containing firewall rules intended to prevent IPv4/IPv6 address spoofing. This assumes that MAC address spoofing is prevented elsewhere, e.g., in Incus with `security.mac_filtering: true` for eth0 in the default profile. To use the chains, `include` the file within a `table bridge` and for input and forward chains, add `jump` instructions as explained in the file (if necessary preceded by, e.g., `meta ibrname "br0"`).
    3. **instances.nftables_sets** with nftables sets of IPv4/IPv6 addresses, both for all registered addresses together and for any addresses of specific instances (specified by name), with additional separate sets for specific address types. To use an address set, `include` the file and write `@` and the set's name.

Both scripts acquire a file lock before accessing files, in order to prevent concurrent access if **instances-update.py** is run manually and when **instances-process.py** is run.

## Requirements

### Debian

```bash
 apt install python3 python3-filelock jq
```

## Usage

### instances-update.py

```
usage: instances-update.py action [mac_address] [ip_address] [hostname] [ignored ...]

Update, add, or remove an instance in instances JSON (default path /var/lib/misc/instances.json)

positional arguments:
  action       dnsmasq dhcp-script action, or special action: --initialize, --rename, --remove, --help
  mac_address  MAC address (if IPv6 then ignored and DNSMASQ_MAC is used), or interface (e.g., br0) if action is --initialize
  ip_address   IPv4 or IPv6 address, or name if action is --initialize or --rename, or not used if action is --remove
  hostname     name (only used by dnsmasq)
  ignored      extra arguments for ignored actions (only used by dnsmasq)
```

### instances-process.py

```
usage: instances-process.py [-h] [-f]

Read instances JSON (default path /var/lib/misc/instances.json) and output hosts and nftables files

options:
  -h, --help   show this help message and exit
  -f, --force  process even if an update is not detected
```

## Configuration

| Environment variable  | Description  | Default |
|-----------------------|--------------|---------|
| `INSTANCES_ADDRESS_SETS` | Address sets to include (comma-separated hostnames) | host |
| `INSTANCES_BASE_PATH` | Base path to derive all file paths from (file name without extension) | /var/lib/misc/instances |
| `INSTANCES_BASE_ID` | Id to append to base path after a hyphen (e.g., br0) | (none) |
| `INSTANCES_HOSTS_DOMAIN` | Domain for names in hosts file (with initial dot) | .instance.internal |

## License

Copyright © 2025 Erik Isaksson. Licensed under an [MIT license](LICENSE).
