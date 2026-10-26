"""Bounded UDP framing over mutually authenticated TLS 1.3. No public UDP proxy."""
import argparse
import asyncio
import contextlib
import json
from pathlib import Path
import ssl
import struct

MAX_PACKET=65507

class Datagram(asyncio.DatagramProtocol):
    def __init__(self,expected=None):self.queue=asyncio.Queue(256);self.expected=expected;self.transport=None
    def connection_made(self,transport):self.transport=transport
    def datagram_received(self,data,address):
        if self.expected and address!=self.expected:return
        if len(data)>MAX_PACKET:return
        try:self.queue.put_nowait(data)
        except asyncio.QueueFull:pass
    def send(self,data):
        if self.expected:self.transport.sendto(data,self.expected)
        else:self.transport.sendto(data)

async def bridge(reader,writer,udp):
    async def send():
        while True:
            try:data=await asyncio.wait_for(udp.queue.get(),15)
            except asyncio.TimeoutError:data=b''
            writer.write(struct.pack('!H',len(data))+data);await asyncio.wait_for(writer.drain(),30)
    async def receive():
        while True:
            size=struct.unpack('!H',await asyncio.wait_for(reader.readexactly(2),50))[0]
            if size>MAX_PACKET:raise ValueError('Oversized frame')
            if size:udp.send(await asyncio.wait_for(reader.readexactly(size),30))
    tasks=[asyncio.create_task(send()),asyncio.create_task(receive())]
    try:
        done,_=await asyncio.wait(tasks,return_when=asyncio.FIRST_COMPLETED)
        for task in done:task.result()
    finally:
        for task in tasks:task.cancel()
        await asyncio.gather(*tasks,return_exceptions=True)
        writer.close()
        with contextlib.suppress(Exception):await asyncio.wait_for(writer.wait_closed(),3)

def context(config,server=False):
    root=Path(config['cert_dir']);purpose=ssl.Purpose.CLIENT_AUTH if server else ssl.Purpose.SERVER_AUTH
    ctx=ssl.create_default_context(purpose,cafile=str(root/'ca.pem'));ctx.minimum_version=ssl.TLSVersion.TLSv1_3
    ctx.verify_mode=ssl.CERT_REQUIRED
    role='server' if server else 'client';ctx.load_cert_chain(str(root/(role+'.pem')),str(root/(role+'.key')))
    return ctx

async def run(config):
    loop=asyncio.get_running_loop()
    if config['role']=='client':
        expected=('127.0.0.1',int(config['awg_port']))
        transport,udp=await loop.create_datagram_endpoint(lambda:Datagram(expected),local_addr=('127.0.0.1',int(config['local_port'])))
        try:
            delay=1
            while True:
                try:
                    reader,writer=await asyncio.wait_for(asyncio.open_connection(config['host'],int(config['port']),
                        ssl=context(config),server_hostname=config['host'],ssl_handshake_timeout=12,limit=131072),20)
                    delay=1;await bridge(reader,writer,udp)
                except asyncio.CancelledError:raise
                except Exception:await asyncio.sleep(delay);delay=min(15,delay*2)
        finally:transport.close()
    else:
        active=set()
        async def accept(reader,writer):
            if len(active)>=2:writer.close();return
            task=asyncio.current_task();active.add(task)
            transport=None
            try:
                transport,udp=await loop.create_datagram_endpoint(Datagram,remote_addr=('127.0.0.1',int(config['awg_port'])))
                await bridge(reader,writer,udp)
            except asyncio.CancelledError:raise
            except Exception:pass
            finally:
                if transport:transport.close()
                active.discard(task);writer.close()
        server=await asyncio.start_server(accept,'0.0.0.0',int(config['port']),ssl=context(config,True),
                                         ssl_handshake_timeout=10,backlog=8,limit=131072)
        try:
            async with server:await server.serve_forever()
        finally:
            for task in active:task.cancel()
            await asyncio.gather(*active,return_exceptions=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('config');args=parser.parse_args()
    asyncio.run(run(json.loads(Path(args.config).read_text())))
