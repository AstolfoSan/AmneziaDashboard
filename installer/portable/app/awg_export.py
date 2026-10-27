"""Bounded, read-only conversion of an existing guest vpn:// export to AWG .conf."""
import base64
import ipaddress
import json
import re
import struct
import zlib

MAX_DOCUMENT = 262144
INTERFACE_KEYS = {
    k.lower(): k for k in (
        'PrivateKey', 'Address', 'DNS', 'MTU', 'Jc', 'Jmin', 'Jmax',
        'S1', 'S2', 'S3', 'S4', 'H1', 'H2', 'H3', 'H4',
        'I1', 'I2', 'I3', 'I4', 'I5', 'HeaderProtectionKey',
        'ContentPaddingAddition', 'RekeyAfterTime', 'RekeyTimeout',
        'RejectAfterTime', 'KeepaliveTimeout', 'MaxHandshakeAttempts',
        'RandomTrailers', 'DisableCookies',
    )
}
PEER_KEYS = {k.lower(): k for k in (
    'PublicKey', 'PresharedKey', 'AllowedIPs', 'Endpoint', 'PersistentKeepalive',
)}


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate profile field')
        result[key] = value
    return result


def _key(value):
    if not isinstance(value, str) or len(value) != 44:
        raise ValueError('Invalid profile key')
    if len(base64.b64decode(value, validate=True)) != 32:
        raise ValueError('Invalid profile key')


def _endpoint(value):
    match = re.fullmatch(r'(\[[0-9a-fA-F:]+\]|[A-Za-z0-9.-]+):(\d{1,5})', value)
    if not match or not 1 <= int(match[2]) <= 65535:
        raise ValueError('Invalid profile endpoint')
    host = match[1]
    if host.startswith('['):
        ipaddress.IPv6Address(host[1:-1])
    elif not re.fullmatch(r'(?=.{1,253}$)[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?', host):
        raise ValueError('Invalid profile host')


def _sections(text, dns):
    if not isinstance(text, str) or len(text) > 65536:
        raise ValueError('Invalid native profile')
    result = {'Interface': {}, 'Peer': {}}
    section = None
    seen = set()
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith(('#', ';')):
            continue
        if line.startswith('['):
            if line not in ('[Interface]', '[Peer]') or line in seen:
                raise ValueError('Unexpected profile section')
            if line == '[Peer]' and '[Interface]' not in seen:
                raise ValueError('Unexpected profile order')
            seen.add(line)
            section = line[1:-1]
            continue
        if section is None or '=' not in line:
            raise ValueError('Invalid profile line')
        key, value = (part.strip() for part in line.split('=', 1))
        canonical = (INTERFACE_KEYS if section == 'Interface' else PEER_KEYS).get(key.lower())
        if not canonical or canonical in result[section] or not value:
            raise ValueError('Unsupported or duplicate profile field')
        if len(value) > 4096 or any(ord(char) < 32 or ord(char) > 126 for char in value):
            raise ValueError('Invalid profile value')
        if canonical == 'DNS':
            value = value.replace('$PRIMARY_DNS', dns[0]).replace('$SECONDARY_DNS', dns[1])
            for address in value.split(','):
                ipaddress.ip_address(address.strip())
        result[section][canonical] = value
    interface, peer = result['Interface'], result['Peer']
    if not {'PrivateKey', 'Address'} <= interface.keys() or not {'PublicKey', 'PresharedKey', 'Endpoint', 'AllowedIPs'} <= peer.keys():
        raise ValueError('Incomplete profile')
    for value in (interface['PrivateKey'], peer['PublicKey'], peer['PresharedKey']):
        _key(value)
    if 'HeaderProtectionKey' in interface:
        _key(interface['HeaderProtectionKey'])
    for address in interface['Address'].split(','):
        ipaddress.ip_interface(address.strip())
    for address in peer['AllowedIPs'].split(','):
        ipaddress.ip_network(address.strip(), strict=False)
    for name in ('MTU', 'Jc', 'Jmin', 'Jmax', 'S1', 'S2', 'S3', 'S4'):
        if name in interface and (not interface[name].isdigit() or not 0 <= int(interface[name]) <= 65535):
            raise ValueError('Invalid numeric profile field')
    if 'PersistentKeepalive' in peer:
        value = peer['PersistentKeepalive']
        if not re.fullmatch(r'\d{1,5}(?:-\d{1,5})?', value):
            raise ValueError('Invalid keepalive')
        numbers = list(map(int, value.split('-')))
        if any(number > 65535 for number in numbers) or numbers != sorted(numbers):
            raise ValueError('Invalid keepalive range')
    _endpoint(peer['Endpoint'])
    return result


def conf_from_vpn(vpn):
    """Return the same guest identity, never create a peer or read live server keys."""
    if not isinstance(vpn, str) or len(vpn) > 65536 or not re.fullmatch(r'vpn://[A-Za-z0-9_-]+', vpn):
        raise ValueError('Invalid guest profile')
    encoded = vpn[6:]
    payload = base64.b64decode(encoded + '=' * (-len(encoded) % 4), altchars=b'-_', validate=True)
    if len(payload) < 6:
        raise ValueError('Incomplete guest profile')
    expected = struct.unpack('>I', payload[:4])[0]
    if not 2 <= expected <= MAX_DOCUMENT:
        raise ValueError('Oversized guest profile')
    decoder = zlib.decompressobj()
    raw = decoder.decompress(payload[4:], expected + 1)
    if len(raw) != expected or not decoder.eof or decoder.unused_data or decoder.unconsumed_tail:
        raise ValueError('Invalid compressed guest profile')
    document = json.loads(raw.decode('utf-8'), object_pairs_hook=_unique)
    allowed = {'containers', 'defaultContainer', 'description', 'dns1', 'dns2', 'hostName'}
    if not isinstance(document, dict) or document.keys() - allowed:
        raise ValueError('Guest profile required; management exports are not supported')
    containers = document.get('containers')
    if not isinstance(containers, list) or len(containers) != 1 or not isinstance(containers[0], dict):
        raise ValueError('One AWG guest profile required')
    container = containers[0]
    if container.get('container') != document.get('defaultContainer') or not isinstance(container.get('awg'), dict):
        raise ValueError('AWG profile required')
    last = json.loads(container['awg']['last_config'], object_pairs_hook=_unique)
    if not isinstance(last, dict):
        raise ValueError('Invalid AWG profile')
    dns = [document.get('dns1', ''), document.get('dns2', '')]
    for address in dns:
        ipaddress.ip_address(address)
    sections = _sections(last['config'], dns)
    interface, peer = sections['Interface'], sections['Peer']
    for name, expected_value in (
        ('client_priv_key', interface['PrivateKey']), ('server_pub_key', peer['PublicKey']),
        ('psk_key', peer['PresharedKey']),
    ):
        if name in last and last[name] != expected_value:
            raise ValueError('Inconsistent guest identity')
    if 'client_ip' in last and str(ipaddress.ip_interface(interface['Address']).ip) != last['client_ip']:
        raise ValueError('Inconsistent guest address')
    return '\n\n'.join('[' + section + ']\n' + '\n'.join(
        key + ' = ' + value for key, value in values.items()
    ) for section, values in sections.items()) + '\n'
