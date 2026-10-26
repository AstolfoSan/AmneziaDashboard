"""Fresh VPN identities and private mutual-TLS credentials, generated in memory."""
import base64
import datetime as dt
import ipaddress
import secrets
from cryptography import x509
from cryptography.hazmat.primitives import hashes,serialization
from cryptography.hazmat.primitives.asymmetric import ec,ed25519,x25519
from cryptography.x509.oid import ExtendedKeyUsageOID,NameOID

def b64(data):return base64.b64encode(data).decode('ascii')
def wg_key():
    key=x25519.X25519PrivateKey.generate()
    return {'private':b64(key.private_bytes(serialization.Encoding.Raw,serialization.PrivateFormat.Raw,serialization.NoEncryption())),
            'public':b64(key.public_key().public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw))}

def awg_header(private,port,address,protection):
    return '\n'.join(['[Interface]','Address = '+address,'PrivateKey = '+private,'ListenPort = '+str(port),
        'Jc = 4','Jmin = 10','Jmax = 50','S1 = 45','S2 = 35','S3 = 42','S4 = 12',
        'H1 = 1','H2 = 2','H3 = 3','H4 = 4','HeaderProtectionKey = '+protection,
        'ContentPaddingAddition = 10-100','RekeyAfterTime = 100-120','RekeyTimeout = 3-7',
        'RejectAfterTime = 150-180','KeepaliveTimeout = 5-15','MaxHandshakeAttempts = 15-20',
        'RandomTrailers = on','DisableCookies = on'])+'\n'

def ssh_key():
    key=ed25519.Ed25519PrivateKey.generate()
    return {'private':key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.OpenSSH,serialization.NoEncryption()).decode(),
            'public':key.public_key().public_bytes(serialization.Encoding.OpenSSH,serialization.PublicFormat.OpenSSH).decode()}

def mutual_tls(foreign_ip):
    now=dt.datetime.now(dt.timezone.utc);ca_key=ec.generate_private_key(ec.SECP256R1())
    name=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,'AmneziaDashboard private cascade CA')])
    ca=(x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(ca_key.public_key())
        .serial_number(x509.random_serial_number()).not_valid_before(now-dt.timedelta(minutes=5)).not_valid_after(now+dt.timedelta(days=3650))
        .add_extension(x509.BasicConstraints(ca=True,path_length=0),True)
        .add_extension(x509.KeyUsage(False,False,False,False,False,True,True,False,False),True)
        .sign(ca_key,hashes.SHA256()))
    result={'ca.pem':ca.public_bytes(serialization.Encoding.PEM).decode()}
    for role,usage in [('server',ExtendedKeyUsageOID.SERVER_AUTH),('client',ExtendedKeyUsageOID.CLIENT_AUTH)]:
        key=ec.generate_private_key(ec.SECP256R1())
        cert=(x509.CertificateBuilder().subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,'cascade-'+role)]))
              .issuer_name(name).public_key(key.public_key()).serial_number(x509.random_serial_number())
              .not_valid_before(now-dt.timedelta(minutes=5)).not_valid_after(now+dt.timedelta(days=3650))
              .add_extension(x509.BasicConstraints(ca=False,path_length=None),True)
              .add_extension(x509.ExtendedKeyUsage([usage]),False))
        if role=='server':cert=cert.add_extension(x509.SubjectAlternativeName([x509.IPAddress(ipaddress.IPv4Address(foreign_ip))]),False)
        cert=cert.sign(ca_key,hashes.SHA256())
        result[role+'.pem']=cert.public_bytes(serialization.Encoding.PEM).decode()
        result[role+'.key']=key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()).decode()
    return result

def vpn_configs(settings,client_subnet,tunnel_subnet):
    clients=ipaddress.IPv4Network(client_subnet);outer=ipaddress.IPv4Network(tunnel_subnet)
    entry=awg_header(wg_key()['private'],settings.vpn_port,str(clients.network_address+1)+'/'+str(clients.prefixlen),b64(secrets.token_bytes(32)))
    files={'entry':{'awg/awg0.conf':entry,'awg/clientsTable':'[]\n'}}
    if settings.mode=='cascade':
        ru,foreign=wg_key(),wg_key();psk=b64(secrets.token_bytes(32));protection=b64(secrets.token_bytes(32))
        front=awg_header(ru['private'],51821,str(outer.network_address+2)+'/30',protection)
        front+='\n[Peer]\nPublicKey = '+foreign['public']+'\nPresharedKey = '+psk+'\nAllowedIPs = 0.0.0.0/0\nEndpoint = 127.0.0.1:15543\nPersistentKeepalive = 25\n'
        exit_cfg=awg_header(foreign['private'],51821,str(outer.network_address+1)+'/30',protection)
        exit_cfg+='\n[Peer]\nPublicKey = '+ru['public']+'\nPresharedKey = '+psk+'\nAllowedIPs = '+str(outer.network_address+2)+'/32, '+str(clients)+'\n'
        files['entry']['awg/awgout.conf']=front
        files['foreign']={'awg/awgout.conf':exit_cfg}
    return files
