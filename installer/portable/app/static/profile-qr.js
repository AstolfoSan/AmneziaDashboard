/* Local-only QR rendering. No URLs, telemetry, storage or profile creation. */
(function(root,factory){
  const api=factory();
  if(typeof module==='object'&&module.exports)module.exports=api;
  else root.ProfileQR=api;
})(typeof globalThis!=='undefined'?globalThis:this,function(){
  'use strict';
  // Amnezia's scanner consumes QDataStream frames, not a vpn:// paste link.
  // qint16(1984), quint8(total=1), quint8(index=0), QByteArray(qCompress).
  function payload(text,format){
    if(!['vpn','conf'].includes(format)||typeof text!=='string')throw Error('Invalid QR profile');
    if(format==='conf'){
      if(!text.startsWith('[Interface]\n')||!text.includes('\n[Peer]\n')||/[\x00-\x08\x0B-\x1F\x7F]/.test(text))throw Error('Invalid QR profile');
      return text;
    }
    if(!/^vpn:\/\/[A-Za-z0-9_-]+$/.test(text))throw Error('Invalid QR profile');
    const value=text.slice(6),alphabet='ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_';
    if(value.length>2320)throw Error('QR_TOO_LARGE');
    if(value.length%4===1)throw Error('Invalid QR profile');
    const bytes=[];let bits=0,buffer=0;
    for(const c of value){buffer=(buffer<<6)|alphabet.indexOf(c);bits+=6;if(bits>=8){bits-=8;bytes.push((buffer>>bits)&255);}}
    if(bits&&(buffer&((1<<bits)-1)))throw Error('Invalid QR profile');
    const size=bytes.length,rawSize=((bytes[0]*0x1000000)+(bytes[1]<<16)+(bytes[2]<<8)+bytes[3]);
    if(size<10||!Number.isInteger(rawSize)||rawSize<1||rawSize>262144||bytes[4]!==0x78||((bytes[4]<<8)+bytes[5])%31!==0)throw Error('Invalid QR profile');
    const frame=[7,192,1,0,(size>>>24)&255,(size>>>16)&255,(size>>>8)&255,size&255,...bytes];
    let encoded='';buffer=0;bits=0;
    for(const byte of frame){buffer=(buffer<<8)|byte;bits+=8;while(bits>=6){bits-=6;encoded+=alphabet[(buffer>>bits)&63];}}
    if(bits)encoded+=alphabet[(buffer<<(6-bits))&63];
    return encoded;
  }
  function encode(text,format,encoder=globalThis.qrcodegen){
    const value=payload(text,format);
    // Version 40, medium correction: 2331 byte-mode bytes. Never truncate or split.
    if(new TextEncoder().encode(value).length>2331)throw Error('QR_TOO_LARGE');
    if(!encoder?.QrCode)throw Error('QR_UNAVAILABLE');
    const qr=encoder.QrCode.encodeText(value,encoder.QrCode.Ecc.MEDIUM);
    return {size:qr.size,modules:Array.from({length:qr.size},(_,y)=>Array.from({length:qr.size},(_,x)=>qr.getModule(x,y)))};
  }
  function render(target,text,format,label,encoder=globalThis.qrcodegen){
    target.replaceChildren();
    const qr=encode(text,format,encoder),doc=target.ownerDocument,ns='http://www.w3.org/2000/svg',extent=qr.size+8;
    const svg=doc.createElementNS(ns,'svg'),paper=doc.createElementNS(ns,'rect'),ink=doc.createElementNS(ns,'path');
    svg.setAttribute('viewBox','0 0 '+extent+' '+extent);svg.setAttribute('role','img');
    svg.setAttribute('aria-label',label);svg.setAttribute('shape-rendering','crispEdges');
    paper.setAttribute('width',extent);paper.setAttribute('height',extent);paper.setAttribute('fill','#ffffff');
    let paths=[];
    for(let y=0;y<qr.size;y++)for(let x=0;x<qr.size;x++)if(qr.modules[y][x])paths.push('M'+(x+4)+','+(y+4)+'h1v1h-1z');
    ink.setAttribute('d',paths.join(''));ink.setAttribute('fill','#000000');
    svg.append(paper,ink);target.replaceChildren(svg);return qr.size;
  }
  return {payload,encode,render};
});
