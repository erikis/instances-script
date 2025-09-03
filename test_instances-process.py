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
"""Tests for instances-process.py"""
import os
import subprocess
import pytest
# Debian requirements: apt install python3-pytest
# Run using: pytest ("pytest -s" for extra output)

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
        'hosts': f'{file_prefix}{file_suffix}.hosts',
        'nftables_chains': f'{file_prefix}{file_suffix}.nftables_chains',
        'nftables_sets': f'{file_prefix}{file_suffix}.nftables_sets',
    }

UPDATE_COMMAND = './instances-update.py'
PROCESS_COMMAND = './instances-process.py'
TEST_ENV = {
  'INSTANCES_BASE_PATH': './test-instances',
  'INSTANCES_BASE_ID': 'process',
  'INSTANCES_ADDRESS_SETS': 'radish,potato,test'
}
TEST_PATHS = get_paths()
ENC = 'utf-8'

@pytest.fixture(autouse=True)
def run_around_tests():
    """Add data before tests and clean up after"""
    # Add some data by running instances-update.py
    result = subprocess.run(f'"{UPDATE_COMMAND}" add "aa:bb:cc:dd:ee:ff" 111.112.113.114 radish',
            env=TEST_ENV, shell=True, capture_output=True, text=True, check=False)
    assert result.returncode == 0
    result = subprocess.run(f'"{UPDATE_COMMAND}" add "aa:bb:cc:11:22:33" 111.112.113.115 potato',
            env=TEST_ENV, shell=True, capture_output=True, text=True, check=False)
    assert result.returncode == 0
    env = dict(TEST_ENV)
    env['DNSMASQ_MAC'] = 'aa:bb:cc:11:22:33'
    result = subprocess.run(f'"{UPDATE_COMMAND}" add ignored "2001:1234:5678::9abc" potato',
            env=env, shell=True, capture_output=True, text=True, check=False)
    assert result.returncode == 0
    result = subprocess.run(f'"{UPDATE_COMMAND}" add ignored "fdb8:7a32:ffb5::1234" potato',
            env=env, shell=True, capture_output=True, text=True, check=False)
    assert result.returncode == 0
    assert os.path.exists(TEST_PATHS['json'])
    assert os.path.exists(TEST_PATHS['updated'])
    yield # Run test at this time
    for _, file_path in TEST_PATHS.items():
        if os.path.exists(file_path):
            os.remove(file_path)

def test_process_updated_and_not_updated():
    """Process when updated and again when not updated"""
    result = subprocess.run(f'"{PROCESS_COMMAND}"', env=TEST_ENV, shell=True, capture_output=True,
            text=True, check=False)
    assert result.returncode == 0
    assert os.path.exists(TEST_PATHS['json'])
    assert not os.path.exists(TEST_PATHS['updated']) # No longer updated
    result = subprocess.run(f'"{PROCESS_COMMAND}"', env=TEST_ENV, shell=True, capture_output=True,
            text=True, check=False)
    assert result.returncode == 10 # Special status for not updated
    assert not os.path.exists(TEST_PATHS['updated']) # Still not updated
    for path_key in ['hosts', 'nftables_chains', 'nftables_sets']:
        assert os.path.exists(TEST_PATHS[path_key])
        with open(TEST_PATHS[path_key], 'r', encoding=ENC) as f:
            lines = f.readlines()
            line_count = len(lines)
            char_count = 0
            print(f'\n{line_count} lines in {path_key}:')
            for line in lines:
                char_count += len(line)
                print(f'{path_key}: {line}', end='') # Mk1 Eyeball Test (output using "pytest -s")
            print(f'Total: {char_count} characters')
            match path_key:
                case 'hosts':
                    assert line_count == 6 # Simple test verifying expected amount of output
                    assert char_count == 450
                case 'nftables_chains':
                    assert line_count == 14
                    assert char_count == 1073
                case 'nftables_sets':
                    assert line_count == 92
                    assert char_count == 1990

def test_help():
    """--help shouldn't do anything except output some text to stdout"""
    result = subprocess.run(f'"{PROCESS_COMMAND}" --help', env=TEST_ENV, shell=True,
            capture_output=True, text=True, check=False)
    assert result.returncode == 0
    assert len(result.stdout) > 100
    assert len(result.stderr) == 0
    assert os.path.exists(TEST_PATHS['updated']) # Still exists

def test_force():
    """--force should process even if not updated"""
    result = subprocess.run(f'"{PROCESS_COMMAND}" --help', env=TEST_ENV, shell=True,
            capture_output=True, text=True, check=False)
    result = subprocess.run(f'"{PROCESS_COMMAND}"', env=TEST_ENV, shell=True, capture_output=True,
            text=True, check=False)
    assert result.returncode == 0
    assert os.path.exists(TEST_PATHS['json'])
    assert not os.path.exists(TEST_PATHS['updated']) # No longer updated
    path_keys = ['hosts', 'nftables_chains', 'nftables_sets']
    for path_key in path_keys:
        os.remove(TEST_PATHS[path_key])
    result = subprocess.run(f'"{PROCESS_COMMAND}" --force', env=TEST_ENV, shell=True,
            capture_output=True, text=True, check=False)
    assert result.returncode == 0 # Not the "not updated" code
    for path_key in path_keys:
        assert os.path.exists(TEST_PATHS[path_key])
