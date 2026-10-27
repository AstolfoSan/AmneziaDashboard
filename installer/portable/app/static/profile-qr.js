/* Local-only QR rendering. No URLs, telemetry, storage or profile creation. */
(function(root,factory){
  const api=factory();
  if(typeof module==='object'&&module.exports)module.exports=api;
  else root.ProfileQR=api;
})(typeof globalThis!=='undefined'?globalThis:this,function(){
  'use strict';
  function encode(text,format,encoder=globalThis.qrcodegen){
    if(!['vpn','conf'].includes(format)||typeof text!=='string')throw Error('Invalid QR profile');
    if(format==='vpn'? !/^vpn:\/\/[A-Za-z0-9_-]+$/.test(text):
      !text.startsWith('[Interface]\n')||!text.includes('\n[Peer]\n')||/[\x00-\x08\x0B-\x1F\x7F]/.test(text))throw Error('Invalid QR profile');
    // Version 40, medium correction: 2331 byte-mode bytes. Never truncate or split.
    if(new TextEncoder().encode(text).length>2331)throw Error('QR_TOO_LARGE');
    if(!encoder?.QrCode)throw Error('QR_UNAVAILABLE');
    const qr=encoder.QrCode.encodeText(text,encoder.QrCode.Ecc.MEDIUM);
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
  return {encode,render};
});
