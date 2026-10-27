(function(root,factory){'use strict';const api=factory();if(typeof module==='object'&&module.exports)module.exports=api;else root.ClientChoice=api;})(globalThis,function(){
  'use strict';
  function mount(doc,nav={},change=()=>{}){
    const choices=doc.querySelector('#client-choice'),primary=doc.querySelector('#client-choice-primary'),
      more=doc.querySelector('#other-client'),slot=doc.querySelector('#other-client-options');
    if(!choices||!primary||!more||!slot)return null;
    const ios=globalThis.DeviceDownloads?.detect(nav)==='ios';
    (ios?primary:slot).append(choices);more.hidden=ios;more.open=false;choices.hidden=false;
    function select(value){
      if(!['vpn','awg'].includes(value))return;
      for(const node of doc.querySelectorAll('[data-client]'))node.hidden=node.dataset.client!==value;
      for(const node of choices.querySelectorAll('input[name="client"]'))node.checked=node.value===value;
      change(value);
    }
    choices.addEventListener('change',event=>{if(event.target.name==='client')select(event.target.value);});
    select('vpn');return {select,ios};
  }
  return {mount};
});
