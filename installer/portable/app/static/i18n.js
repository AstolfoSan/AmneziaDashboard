(function(root,factory){'use strict';const api=factory(root);if(typeof module==='object'&&module.exports)module.exports=api;else root.DashboardI18n=api;})(globalThis,function(root){
  'use strict';
  const catalog=root.DashboardEnglish||{},cache=new Map();
  const escape=value=>value.replace(/[.*+?^${}()|[\]\\]/g,'\\$&');
  const entries=Object.entries(catalog).sort((a,b)=>b[0].length-a[0].length).map(([ru,en])=>
    [new RegExp('(?<![А-Яа-яЁё])'+escape(ru)+'(?![А-Яа-яЁё])','g'),en]);
  let language='ru';
  try{const stored=root.localStorage?.getItem('dashboard-language');language=['ru','en'].includes(stored)?stored:/^en\b/i.test(root.navigator?.language||'')?'en':'ru';}catch{}
  function english(value){const source=String(value);if(cache.has(source))return cache.get(source);let result=source;
    // Called only on trusted source literals/static initial HTML, never user data.
    for(const [pattern,replacement]of entries)result=result.replace(pattern,()=>replacement);
    cache.set(source,result);return result;
  }
  function text(value){return language==='en'?english(value):value;}
  function locale(){return language==='en'?'en-GB':'ru-RU';}
  function setLanguage(value,reload=true){if(!['ru','en'].includes(value))throw Error('Unsupported language');language=value;
    try{root.localStorage?.setItem('dashboard-language',value);}catch{}
    if(root.document){root.document.documentElement.lang=value;root.document.cookie='dashboard_lang='+value+';Path=/;SameSite=Lax'+(root.location?.protocol==='https:'?';Secure':'');}
    if(reload&&root.location)root.location.reload();
  }
  function initial(){
    const doc=root.document;if(!doc)return;setLanguage(language,false);
    if(language==='en'){
      const walker=doc.createTreeWalker(doc.body,4),nodes=[];while(walker.nextNode())nodes.push(walker.currentNode);
      for(const node of nodes)if(!node.parentElement?.closest('script,style,textarea,[data-no-i18n]'))node.textContent=text(node.textContent);
      for(const el of doc.querySelectorAll('[placeholder],[title],[aria-label],[alt]'))for(const name of ['placeholder','title','aria-label','alt'])if(el.hasAttribute(name))el.setAttribute(name,text(el.getAttribute(name)));
      doc.title=text(doc.title);
    }
    const hosts=[doc.querySelector('#login .brand'),doc.querySelector('.topbar>.actions'),doc.querySelector('.join>header')].filter(Boolean);
    if(!hosts.length)hosts.push(doc.querySelector('main')||doc.body);
    for(const host of hosts){const label=doc.createElement('label');label.className='language-switch';label.append(doc.createTextNode(text('Язык')+' '));
      const select=doc.createElement('select');select.setAttribute('aria-label','Language / Язык');
      for(const [value,caption]of [['ru','Русский'],['en','English']]){const option=doc.createElement('option');option.value=value;option.textContent=caption;select.append(option);}
      select.value=language;select.addEventListener('change',()=>setLanguage(select.value));label.append(select);host.append(label);
    }
  }
  const api={text,english,locale,setLanguage,get language(){return language;},catalog};
  if(root.document){if(root.document.readyState==='loading')root.document.addEventListener('DOMContentLoaded',initial,{once:true});else initial();}
  return api;
});
