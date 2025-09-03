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
"""Tests for instances-update.py"""
import os
import subprocess
import json
import re
import pytest
# Debian requirements: apt install python3-pytest
# Run using: pytest

def get_paths():
    """Figure out all paths and return in a dict"""
    file_prefix = TEST_ENV.get('INSTANCES_BASE_PATH')
    file_suffix = ''
    file_id = TEST_ENV.get('INSTANCES_BASE_ID')
    if file_id:
        file_suffix = f'-{file_id}'
    return {
        'json': f'{file_prefix}{file_suffix}.json',
        'updated': f'{file_prefix}{file_suffix}.updated',
        'lock': f'{file_prefix}{file_suffix}.lock',
    }

UPDATE_COMMAND = './instances-update.py'
TEST_ENV = {
  'INSTANCES_BASE_PATH': './test-instances'
}
# Set this environment variable to use a different interface for --initialize:
TEST_INTERFACE = os.environ.get('INSTANCES_TEST_INTERFACE', default='br0')
TEST_PATHS = get_paths()
MAC_RE = r'([0-9a-f]{2}:){5}[0-9a-f]{2}'
IPV4_RE = r'([0-9]+\.){3}[0-9]+'
IPV6_RE = r'[0-9a-f:]+'
ENC = 'utf-8'

@pytest.fixture(autouse=True)
def run_around_tests():
    """Clean up after tests"""
    yield # Run test at this time
    for _, file_path in TEST_PATHS.items():
        if os.path.exists(file_path):
            os.remove(file_path)

def test_add_ipv4_and_ipv6():
    """Adding twice for the same instance (i.e, with the same MAC address)"""
    result = subprocess.run(f'"{UPDATE_COMMAND}" add "aa:bb:cc:dd:ee:ff" 111.112.113.114',
            env=TEST_ENV, shell=True, capture_output=True, text=True, check=False)
    assert result.returncode == 0
    assert os.path.exists(TEST_PATHS['json'])
    assert os.path.exists(TEST_PATHS['updated'])
    with open(TEST_PATHS['json'], 'r', encoding=ENC) as f:
        instances = json.load(f)
        assert isinstance(instances, dict)
        assert len(instances) == 1
        for mac, instance in instances.items():
            assert re.fullmatch(MAC_RE, mac)
            assert instance.get('name') == ''
            assert instance.get('ipv4') == '111.112.113.114'
            assert instance.get('ipv6_lla') == 'fe80::a8bb:ccff:fedd:eeff'
            for ip_address_field in ['ipv6_gua', 'ipv6_ula']:
                assert instance.get(ip_address_field) is None
    env = dict(TEST_ENV)
    env['DNSMASQ_MAC'] = 'aa:bb:cc:dd:ee:ff'
    os.remove(TEST_PATHS['updated']) # To make sure it's recreated
    result = subprocess.run(f'"{UPDATE_COMMAND}" add ignored "fdb8:7a32:ffb5::1234" client',
            env=env, shell=True, capture_output=True, text=True, check=False)
    assert result.returncode == 0
    assert os.path.exists(TEST_PATHS['json'])
    assert os.path.exists(TEST_PATHS['updated'])
    with open(TEST_PATHS['json'], 'r', encoding=ENC) as f:
        instances = json.load(f)
        assert len(instances) == 1
        for mac, instance in instances.items():
            assert re.fullmatch(MAC_RE, mac)
            assert instance.get('name') == '' # Only set automatically for new instance creation
            assert instance.get('ipv4') == '111.112.113.114'
            assert instance.get('ipv6_lla') == 'fe80::a8bb:ccff:fedd:eeff'
            assert instance.get('ipv6_ula') == 'fdb8:7a32:ffb5::1234'
            assert instance.get('ipv6_gua') is None

def test_add_and_old():
    """Add and then old for the same instance (add and old should be handled in the same way)"""
    result = subprocess.run(f'"{UPDATE_COMMAND}" add "aa:bb:cc:dd:ee:ff" 111.112.113.114 carrot',
            env=TEST_ENV, shell=True, capture_output=True, text=True, check=False)
    assert result.returncode == 0
    with open(TEST_PATHS['json'], 'r', encoding=ENC) as f:
        instances = json.load(f)
        assert len(instances) == 1
        for mac, instance in instances.items():
            assert re.fullmatch(MAC_RE, mac)
            assert instance.get('name') == 'carrot'
            assert instance.get('ipv4') == '111.112.113.114'
            assert instance.get('ipv6_lla') == 'fe80::a8bb:ccff:fedd:eeff'
            for ip_address_field in ['ipv6_gua', 'ipv6_ula']:
                assert instance.get(ip_address_field) is None
    result = subprocess.run(f'"{UPDATE_COMMAND}" old "aa:bb:cc:dd:ee:ff" 111.112.113.115',
            env=TEST_ENV, shell=True, capture_output=True, text=True, check=False)
    assert result.returncode == 0
    with open(TEST_PATHS['json'], 'r', encoding=ENC) as f:
        instances = json.load(f)
        assert len(instances) == 1
        for mac, instance in instances.items():
            assert re.fullmatch(MAC_RE, mac)
            assert instance.get('name') == 'carrot'
            assert instance.get('ipv4') == '111.112.113.115'
            assert instance.get('ipv6_lla') == 'fe80::a8bb:ccff:fedd:eeff'
            for ip_address_field in ['ipv6_gua', 'ipv6_ula']:
                assert instance.get(ip_address_field) is None

def test_add_same_twice():
    """Adding twice with everything the same shouldn't recreate .updated file"""
    result = subprocess.run(f'"{UPDATE_COMMAND}" add "aa:bb:cc:dd:ee:ff" 111.112.113.114',
            env=TEST_ENV, shell=True, capture_output=True, text=True, check=False)
    assert result.returncode == 0
    assert os.path.exists(TEST_PATHS['json'])
    assert os.path.exists(TEST_PATHS['updated'])
    with open(TEST_PATHS['json'], 'r', encoding=ENC) as f:
        instances = json.load(f)
        assert isinstance(instances, dict)
        assert len(instances) == 1
        for mac, instance in instances.items():
            assert re.fullmatch(MAC_RE, mac)
            assert instance.get('name') == ''
            assert instance.get('ipv4') == '111.112.113.114'
            assert instance.get('ipv6_lla') == 'fe80::a8bb:ccff:fedd:eeff'
            for ip_address_field in ['ipv6_gua', 'ipv6_ula']:
                assert instance.get(ip_address_field) is None
    os.remove(TEST_PATHS['updated']) # To make sure it's NOT recreated
    result = subprocess.run(f'"{UPDATE_COMMAND}" add "aa:bb:cc:dd:ee:ff" 111.112.113.114',
            env=TEST_ENV, shell=True, capture_output=True, text=True, check=False)
    assert result.returncode == 0
    assert os.path.exists(TEST_PATHS['json'])
    assert not os.path.exists(TEST_PATHS['updated']) # Does NOT exist
    with open(TEST_PATHS['json'], 'r', encoding=ENC) as f:
        instances = json.load(f)
        assert len(instances) == 1
        for mac, instance in instances.items():
            assert re.fullmatch(MAC_RE, mac)
            assert instance.get('name') == ''
            assert instance.get('ipv4') == '111.112.113.114'
            assert instance.get('ipv6_lla') == 'fe80::a8bb:ccff:fedd:eeff'
            for ip_address_field in ['ipv6_gua', 'ipv6_ula']:
                assert instance.get(ip_address_field) is None

def test_add_two_instances():
    """Adding two instances (i.e, with different MAC addresses)"""
    result = subprocess.run(f'"{UPDATE_COMMAND}" add "aa:bb:cc:dd:ee:ff" 111.112.113.114 radish',
            env=TEST_ENV, shell=True, capture_output=True, text=True, check=False)
    assert result.returncode == 0
    env = dict(TEST_ENV)
    env['DNSMASQ_MAC'] = 'aa:bb:cc:11:22:33'
    result = subprocess.run(f'"{UPDATE_COMMAND}" add ignored "2001:1234:5678::9abc" potato',
            env=env, shell=True, capture_output=True, text=True, check=False)
    assert result.returncode == 0
    assert os.path.exists(TEST_PATHS['json'])
    assert os.path.exists(TEST_PATHS['updated'])
    with open(TEST_PATHS['json'], 'r', encoding=ENC) as f:
        instances = json.load(f)
        assert len(instances) == 2
        assert isinstance(instances.get('aa:bb:cc:dd:ee:ff'), dict)
        assert isinstance(instances.get('aa:bb:cc:11:22:33'), dict)
        for mac, instance in instances.items():
            assert isinstance(instance.get('name'), str)
            if mac == 'aa:bb:cc:dd:ee:ff':
                assert instance.get('name') == 'radish'
                assert instance.get('ipv4') == '111.112.113.114'
                assert instance.get('ipv6_lla') == 'fe80::a8bb:ccff:fedd:eeff'
                for ip_address_field in ['ipv6_gua', 'ipv6_ula']:
                    assert instance.get(ip_address_field) is None
            else:
                assert mac == 'aa:bb:cc:11:22:33'
                assert instance.get('name') == 'potato'
                assert instance.get('ipv4') is None
                assert instance.get('ipv6_lla') == 'fe80::a8bb:ccff:fe11:2233'
                assert instance.get('ipv6_gua') == '2001:1234:5678::9abc'
                assert instance.get('ipv6_ula') is None

def test_add_two_instances_same_ipv4():
    """Adding instances with the same IP address (IPv4) should let the new instance take it"""
    result = subprocess.run(f'"{UPDATE_COMMAND}" add "aa:bb:cc:dd:ee:ff" 111.112.113.114 radish',
            env=TEST_ENV, shell=True, capture_output=True, text=True, check=False)
    assert result.returncode == 0
    result = subprocess.run(f'"{UPDATE_COMMAND}" add "aa:bb:cc:11:22:33" 111.112.113.114 potato',
            env=TEST_ENV, shell=True, capture_output=True, text=True, check=False)
    assert result.returncode == 0
    assert os.path.exists(TEST_PATHS['json'])
    assert os.path.exists(TEST_PATHS['updated'])
    with open(TEST_PATHS['json'], 'r', encoding=ENC) as f:
        instances = json.load(f)
        assert len(instances) == 2
        assert isinstance(instances.get('aa:bb:cc:dd:ee:ff'), dict)
        assert isinstance(instances.get('aa:bb:cc:11:22:33'), dict)
        for mac, instance in instances.items():
            assert isinstance(instance.get('name'), str)
            if mac == 'aa:bb:cc:dd:ee:ff':
                assert instance.get('name') == 'radish'
                assert instance.get('ipv4') is None
                assert instance.get('ipv6_lla') == 'fe80::a8bb:ccff:fedd:eeff'
                for ip_address_field in ['ipv6_gua', 'ipv6_ula']:
                    assert instance.get(ip_address_field) is None
            else:
                assert mac == 'aa:bb:cc:11:22:33'
                assert instance.get('name') == 'potato'
                assert instance.get('ipv4') == '111.112.113.114'
                assert instance.get('ipv6_lla') == 'fe80::a8bb:ccff:fe11:2233'
                for ip_address_field in ['ipv6_gua', 'ipv6_ula']:
                    assert instance.get(ip_address_field) is None

def test_add_two_instances_same_ipv6_ula():
    """Adding instances with the same IP address (IPv6 ULA) should let the new instance take it"""
    env = dict(TEST_ENV)
    env['DNSMASQ_MAC'] = 'aa:bb:cc:dd:ee:ff'
    result = subprocess.run(f'"{UPDATE_COMMAND}" add ignored "fdb8:7a32:ffb5::1234" radish',
            env=env, shell=True, capture_output=True, text=True, check=False)
    assert result.returncode == 0
    env = dict(TEST_ENV)
    env['DNSMASQ_MAC'] = 'aa:bb:cc:11:22:33'
    result = subprocess.run(f'"{UPDATE_COMMAND}" add ignored "fdb8:7a32:ffb5::1234" potato',
            env=env, shell=True, capture_output=True, text=True, check=False)
    assert result.returncode == 0
    assert os.path.exists(TEST_PATHS['json'])
    assert os.path.exists(TEST_PATHS['updated'])
    with open(TEST_PATHS['json'], 'r', encoding=ENC) as f:
        instances = json.load(f)
        assert len(instances) == 2
        for mac, instance in instances.items():
            assert isinstance(instance.get('name'), str)
            if mac == 'aa:bb:cc:dd:ee:ff':
                assert instance.get('name') == 'radish'
                assert instance.get('ipv4') is None
                assert instance.get('ipv6_lla') == 'fe80::a8bb:ccff:fedd:eeff'
                assert instance.get('ipv6_ula') is None
                assert instance.get('ipv6_gua') is None
            else:
                assert mac == 'aa:bb:cc:11:22:33'
                assert instance.get('name') == 'potato'
                assert instance.get('ipv4') is None
                assert instance.get('ipv6_lla') == 'fe80::a8bb:ccff:fe11:2233'
                assert instance.get('ipv6_ula') == 'fdb8:7a32:ffb5::1234'
                assert instance.get('ipv6_gua') is None

def test_add_two_instances_same_ipv6_gua():
    """Adding instances with the same IP addresses (IPv6 GUA) should let the new instance take it"""
    env = dict(TEST_ENV)
    env['DNSMASQ_MAC'] = 'aa:bb:cc:dd:ee:ff'
    result = subprocess.run(f'"{UPDATE_COMMAND}" add ignored "2001:1234:5678::9abc" radish',
            env=env, shell=True, capture_output=True, text=True, check=False)
    assert result.returncode == 0
    env = dict(TEST_ENV)
    env['DNSMASQ_MAC'] = 'aa:bb:cc:11:22:33'
    result = subprocess.run(f'"{UPDATE_COMMAND}" add ignored "2001:1234:5678::9abc" potato',
            env=env, shell=True, capture_output=True, text=True, check=False)
    assert result.returncode == 0
    assert os.path.exists(TEST_PATHS['json'])
    assert os.path.exists(TEST_PATHS['updated'])
    with open(TEST_PATHS['json'], 'r', encoding=ENC) as f:
        instances = json.load(f)
        assert len(instances) == 2
        for mac, instance in instances.items():
            assert isinstance(instance.get('name'), str)
            if mac == 'aa:bb:cc:dd:ee:ff':
                assert instance.get('name') == 'radish'
                assert instance.get('ipv4') is None
                assert instance.get('ipv6_lla') == 'fe80::a8bb:ccff:fedd:eeff'
                assert instance.get('ipv6_ula') is None
                assert instance.get('ipv6_gua') is None
            else:
                assert mac == 'aa:bb:cc:11:22:33'
                assert instance.get('name') == 'potato'
                assert instance.get('ipv4') is None
                assert instance.get('ipv6_lla') == 'fe80::a8bb:ccff:fe11:2233'
                assert instance.get('ipv6_ula') is None
                assert instance.get('ipv6_gua') == '2001:1234:5678::9abc'

def test_add_two_instances_same_name():
    """Adding two instances with the same name should let the previous instance keep it"""
    result = subprocess.run(f'"{UPDATE_COMMAND}" add "aa:bb:cc:dd:ee:ff" 111.112.113.114 radish',
            env=TEST_ENV, shell=True, capture_output=True, text=True, check=False)
    assert result.returncode == 0
    result = subprocess.run(f'"{UPDATE_COMMAND}" add "aa:bb:cc:11:22:33" 111.112.113.115 radish',
            env=TEST_ENV, shell=True, capture_output=True, text=True, check=False)
    assert result.returncode == 0
    assert os.path.exists(TEST_PATHS['json'])
    assert os.path.exists(TEST_PATHS['updated'])
    with open(TEST_PATHS['json'], 'r', encoding=ENC) as f:
        instances = json.load(f)
        assert len(instances) == 2
        for mac, instance in instances.items():
            assert isinstance(instance.get('name'), str)
            if mac == 'aa:bb:cc:dd:ee:ff':
                assert instance.get('name') == 'radish'
            else:
                assert mac == 'aa:bb:cc:11:22:33'
                assert instance.get('name') == ''

def test_unknown():
    """An unknown, ignored action shouldn't do anything, not even output"""
    result = subprocess.run(
            f'"{UPDATE_COMMAND}" 5a00f931-7832-4656-82b3-72119dc91265 abc def 123 456 789',
            env=TEST_ENV, shell=True, capture_output=True, text=True, check=False)
    assert result.returncode == 0
    assert len(result.stdout) == 0
    assert len(result.stderr) == 0
    assert not os.path.exists(TEST_PATHS['json'])
    assert not os.path.exists(TEST_PATHS['updated'])

def test_help():
    """--help shouldn't do anything except output some text to stdout"""
    result = subprocess.run(f'"{UPDATE_COMMAND}" --help', env=TEST_ENV, shell=True,
            capture_output=True, text=True, check=False)
    assert result.returncode == 0
    assert len(result.stdout) > 100
    assert len(result.stderr) == 0
    assert not os.path.exists(TEST_PATHS['json'])
    assert not os.path.exists(TEST_PATHS['updated'])

def test_initialize():
    """--initialize should get info about an actual network interface"""
    result = subprocess.run(f'"{UPDATE_COMMAND}" --initialize "{TEST_INTERFACE}" host',
            env=TEST_ENV, shell=True, capture_output=True, text=True, check=False)
    assert result.returncode == 0
    assert os.path.exists(TEST_PATHS['json'])
    assert os.path.exists(TEST_PATHS['updated'])
    with open(TEST_PATHS['json'], 'r', encoding=ENC) as f:
        instances = json.load(f)
        assert len(instances) == 1
        for mac, instance in instances.items():
            assert re.fullmatch(MAC_RE, mac)
            assert instance.get('name') == 'host'
            assert re.fullmatch(IPV4_RE, instance.get('ipv4'))
            assert re.fullmatch(IPV6_RE, instance.get('ipv6_lla'))
            for ip_address_field in ['ipv6_gua', 'ipv6_ula', 'ipv6_lla']:
                ip_address = instance.get(ip_address_field)
                if not ip_address is None:
                    assert re.fullmatch(IPV6_RE, ip_address)

def test_rename():
    """--rename should (only) change the name of an instance"""
    result = subprocess.run(f'"{UPDATE_COMMAND}" add "aa:bb:cc:dd:ee:ff" 111.112.113.114 client',
            env=TEST_ENV, shell=True, capture_output=True, text=True, check=False)
    assert result.returncode == 0
    with open(TEST_PATHS['json'], 'r', encoding=ENC) as f:
        instances = json.load(f)
        assert len(instances) == 1
        for mac, instance in instances.items():
            assert re.fullmatch(MAC_RE, mac)
            assert instance.get('name') == 'client'
            assert instance.get('ipv4') == '111.112.113.114'
            assert instance.get('ipv6_lla') == 'fe80::a8bb:ccff:fedd:eeff'
            for ip_address_field in ['ipv6_gua', 'ipv6_ula']:
                assert instance.get(ip_address_field) is None
    env = dict(TEST_ENV)
    env['DNSMASQ_MAC'] = 'aa:bb:cc:dd:ee:ff'
    result = subprocess.run(f'"{UPDATE_COMMAND}" --rename "aa:bb:cc:dd:ee:ff" example',
            env=env, shell=True, capture_output=True, text=True, check=False)
    assert result.returncode == 0
    assert os.path.exists(TEST_PATHS['json'])
    assert os.path.exists(TEST_PATHS['updated'])
    with open(TEST_PATHS['json'], 'r', encoding=ENC) as f:
        instances = json.load(f)
        assert len(instances) == 1
        for mac, instance in instances.items():
            assert re.fullmatch(MAC_RE, mac)
            assert instance.get('name') == 'example'
            assert instance.get('ipv4') == '111.112.113.114'
            assert instance.get('ipv6_lla') == 'fe80::a8bb:ccff:fedd:eeff'
            for ip_address_field in ['ipv6_gua', 'ipv6_ula']:
                assert instance.get(ip_address_field) is None

def test_rename_conflict():
    """--rename if changing the name to another instance's name should clear the other's name"""
    result = subprocess.run(f'"{UPDATE_COMMAND}" add "aa:bb:cc:dd:ee:ff" 111.112.113.114 radish',
            env=TEST_ENV, shell=True, capture_output=True, text=True, check=False)
    assert result.returncode == 0
    env = dict(TEST_ENV)
    env['DNSMASQ_MAC'] = 'aa:bb:cc:11:22:33'
    result = subprocess.run(f'"{UPDATE_COMMAND}" add ignored "2001:1234:5678::9abc" potato',
            env=env, shell=True, capture_output=True, text=True, check=False)
    assert result.returncode == 0
    result = subprocess.run(f'"{UPDATE_COMMAND}" --rename "aa:bb:cc:11:22:33" radish',
            env=env, shell=True, capture_output=True, text=True, check=False)
    assert result.returncode == 0
    assert os.path.exists(TEST_PATHS['json'])
    assert os.path.exists(TEST_PATHS['updated'])
    with open(TEST_PATHS['json'], 'r', encoding=ENC) as f:
        instances = json.load(f)
        assert len(instances) == 2
        for mac, instance in instances.items():
            if mac == 'aa:bb:cc:dd:ee:ff':
                assert instance.get('name') == ''
            else:
                assert mac == 'aa:bb:cc:11:22:33'
                assert instance.get('name') == 'radish'

def test_rename_same():
    """--rename if changing the name to the same name should do nothing"""
    result = subprocess.run(f'"{UPDATE_COMMAND}" add "aa:bb:cc:dd:ee:ff" 111.112.113.114 radish',
            env=TEST_ENV, shell=True, capture_output=True, text=True, check=False)
    assert result.returncode == 0
    env = dict(TEST_ENV)
    env['DNSMASQ_MAC'] = 'aa:bb:cc:11:22:33'
    result = subprocess.run(f'"{UPDATE_COMMAND}" add ignored "2001:1234:5678::9abc" potato',
            env=env, shell=True, capture_output=True, text=True, check=False)
    assert result.returncode == 0
    result = subprocess.run(f'"{UPDATE_COMMAND}" --rename "aa:bb:cc:11:22:33" potato',
            env=env, shell=True, capture_output=True, text=True, check=False)
    assert result.returncode == 0
    assert os.path.exists(TEST_PATHS['json'])
    assert os.path.exists(TEST_PATHS['updated'])
    with open(TEST_PATHS['json'], 'r', encoding=ENC) as f:
        instances = json.load(f)
        assert len(instances) == 2
        for mac, instance in instances.items():
            if mac == 'aa:bb:cc:dd:ee:ff':
                assert instance.get('name') == 'radish'
            else:
                assert mac == 'aa:bb:cc:11:22:33'
                assert instance.get('name') == 'potato'

def test_remove():
    """--remove should remove an instance"""
    env = dict(TEST_ENV)
    env['INSTANCES_BASE_ID'] = 'REMOVE123' # Vary some other things which shouldn't affect results
    result = subprocess.run(f'"{UPDATE_COMMAND}" add aa:bb:cc:dd:ee:ff 111.112.113.114 radish',
            env=TEST_ENV, shell=True, capture_output=True, text=True, check=False)
    assert result.returncode == 0
    result = subprocess.run(f'"{UPDATE_COMMAND}" add aa:bb:cc:11:22:33 2001:1234:5678::9abc potato',
            env=TEST_ENV, shell=True, capture_output=True, text=True, check=False)
    assert result.returncode == 0
    result = subprocess.run(f'"{UPDATE_COMMAND}" --remove aa:bb:cc:11:22:33', env=TEST_ENV,
            shell=True, capture_output=True, text=True, check=False)
    assert result.returncode == 0
    assert os.path.exists(TEST_PATHS['json'])
    assert os.path.exists(TEST_PATHS['updated'])
    with open(TEST_PATHS['json'], 'r', encoding=ENC) as f:
        instances = json.load(f)
        assert len(instances) == 1
        for _, instance in instances.items():
            assert instance.get('name') == 'radish'
    # Do it again to verify no change
    result = subprocess.run(f'"{UPDATE_COMMAND}" --remove aa:bb:cc:11:22:33', env=TEST_ENV,
            shell=True, capture_output=True, text=True, check=False)
    assert result.returncode == 0
    with open(TEST_PATHS['json'], 'r', encoding=ENC) as f:
        instances = json.load(f)
        assert len(instances) == 1
        for _, instance in instances.items():
            assert instance.get('name') == 'radish'
    # Also remove the remaining instance
    result = subprocess.run(f'"{UPDATE_COMMAND}" --remove "aa:bb:cc:dd:ee:ff"', env=TEST_ENV,
            shell=True, capture_output=True, text=True, check=False)
    assert result.returncode == 0
    with open(TEST_PATHS['json'], 'r', encoding=ENC) as f:
        instances = json.load(f)
        assert len(instances) == 0
    # Do it again to verify no change
    result = subprocess.run(f'"{UPDATE_COMMAND}" --remove "aa:bb:cc:dd:ee:ff"', env=TEST_ENV,
            shell=True, capture_output=True, text=True, check=False)
    assert result.returncode == 0
    with open(TEST_PATHS['json'], 'r', encoding=ENC) as f:
        instances = json.load(f)
        assert len(instances) == 0
