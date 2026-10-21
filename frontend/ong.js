"use strict";
const $=s=>document.querySelector(s);
const esc=v=>String(v??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const number=v=>new Intl.NumberFormat("pt-BR",{maximumFractionDigits:2}).format(Number(v)||0);
const CATEGORIAS={hortifruti:"Hortifrúti",padaria:"Padaria",laticinios:"Laticínios",carnes:"Carnes",prontos:"Pratos prontos",nao_perecivel:"Não perecível"};
const PRIORIDADES={baixa:"Baixa",media:"Média",alta:"Alta"};
const date=v=>v?new Date(String(v).slice(0,10)+"T12:00:00").toLocaleDateString("pt-BR"):"—";
const isoLocal=d=>d.getFullYear()+"-"+String(d.getMonth()+1).padStart(2,"0")+"-"+String(d.getDate()).padStart(2,"0");
const dias=v=>Math.round((new Date(String(v).slice(0,10)+"T12:00:00")-new Date(isoLocal(new Date())+"T12:00:00"))/864e5);
let [ongId,codigo]=(location.hash.slice(1)||"").split(".");
let dados=null,ocupado=false;
const guarda={get(k){try{return sessionStorage.getItem(k)||"";}catch{return "";}},set(k,v){try{v?sessionStorage.setItem(k,v):sessionStorage.removeItem(k);}catch{}}};
let usuario=(()=>{try{return JSON.parse(guarda.get("ong_usuario")||"null");}catch{return null;}})();
function aviso(texto,tipo){const a=$("#aviso");a.textContent=texto;a.hidden=!texto;a.className=tipo||"";}
async function enviar(url,metodo="GET",corpo,comLink){
 let resposta,json={};
 const cab={"Content-Type":"application/json"},token=guarda.get("ong_token");
 if(token)cab.Authorization="Bearer "+token;else if(comLink!==false&&ongId&&codigo){cab["X-Ong-Id"]=ongId;cab["X-Ong-Codigo"]=codigo;}
 try{resposta=await fetch(url,{method:metodo,headers:cab,body:metodo==="POST"?JSON.stringify(corpo||{}):undefined});}
 catch{throw Error("Sem conexão com o servidor. Verifique sua internet.");}
 try{json=await resposta.json();}catch{}
 if(!resposta.ok){const e=Error(json.error||"Não foi possível concluir a operação.");e.status=resposta.status;e.codigo=json.codigo;throw e;}
 return json;
}
const chamar=(caminho,metodo="GET",corpo)=>enviar("/api/ong-portal/"+caminho,metodo,corpo);
function iniciarSessao(r){guarda.set("ong_token",r.token);guarda.set("ong_usuario",JSON.stringify(r.usuario));usuario=r.usuario;ongId=codigo=undefined;history.replaceState(null,"","/ong");}
function encerrarSessaoLocal(){guarda.set("ong_token","");guarda.set("ong_usuario","");usuario=null;}
function confirmar({titulo,mensagem,sim,perigo=true}){return new Promise(resolve=>{const d=$("#confirm");$("#confirm-yes").classList.toggle("danger",perigo);$("#confirm-title").textContent=titulo;$("#confirm-message").textContent=mensagem;$("#confirm-yes").textContent=sim;d.returnValue="";d.addEventListener("close",()=>resolve(d.returnValue==="yes"),{once:true});d.showModal();});}
function validadeTag(m){if(m.status!=="pendente"&&m.status!=="aceito")return"";const d=dias(m.validade);return d<0?' <span class="badge cancelada">Vencida</span>':d<=3?' <span class="badge reservada">'+(d===0?"Vence hoje":"Vence em "+d+" d")+"</span>":"";}
function card(m){
 const contato=m.doador?'<div class="contato"><strong>Contato do doador</strong><p>'+esc(m.doador.nome)+"<br>"+esc(m.doador.telefone||"Telefone não informado")+"<br>"+esc(m.doador.email)+"</p></div>":"";
 const recebido=m.status==="aceito"?'<div class="acoes-card"><button class="primary" data-receber="'+m.id+'">Confirmar recebimento</button></div>':"";
 const acoes=m.status==="pendente"?'<div class="acoes-card"><button class="primary" data-aceitar="'+m.id+'">Aceitar doação</button><button data-recusar="'+m.id+'">Recusar</button></div>':"";
 return '<article class="oferta"><div class="oferta-topo"><h3>'+esc(m.alimento)+'</h3><span class="badge '+esc(m.prioridade)+'">Prioridade '+esc(PRIORIDADES[m.prioridade]||m.prioridade)+'</span></div><dl><div><dt>Quantidade</dt><dd>'+number(m.quantidade_kg)+' kg</dd></div><div><dt>Categoria</dt><dd>'+esc(CATEGORIAS[m.categoria]||m.categoria||"—")+'</dd></div><div><dt>Validade</dt><dd>'+esc(date(m.validade))+validadeTag(m)+'</dd></div><div><dt>Região do doador</dt><dd>'+esc(m.regiao_doador||"—")+'</dd></div></dl>'+contato+acoes+recebido+"</article>";
}
function secao(titulo,descricao,itens){return itens.length?'<section class="grupo"><h2>'+titulo+"</h2><p>"+descricao+'</p><div class="ofertas">'+itens.map(card).join("")+"</div></section>":"";}
function render(){
 const m=dados.matches,por=s=>m.filter(x=>x.status===s);
 $("#titulo").textContent=dados.ong.nome;$("#subtitulo").textContent="Doações indicadas para a sua organização.";
 const html=secao("Aguardando sua resposta","Aceite para receber o contato do doador e combinar a retirada.",por("pendente"))+secao("Aceitas","Combine a retirada com o doador. Quando o alimento chegar, confirme o recebimento aqui: é assim que a entrega passa a contar.",por("aceito"))+secao("Concluídas","Doações já entregues.",por("concluido"))+secao("Recusadas","Doações que você recusou.",por("recusado"));
 $("#conteudo").innerHTML=html||'<section class="solo-card"><h2>Nenhuma doação por enquanto</h2><p>Quando uma doação for indicada para a sua organização, ela aparece aqui.</p></section>';
}
function mostrar(estado){
 // estado: "sessao" (logada por conta), "link" (so pelo link), "visitante"
 $("#barra").hidden=estado!=="sessao";$("#criar-conta").hidden=estado!=="link";
 $("#entrar").hidden=$("#acesso").hidden=$("#pedido").hidden=estado!=="visitante";
 if(estado==="sessao")$("#quem-ong").textContent=(usuario&&usuario.nome?usuario.nome:"")+(usuario&&usuario.ong_nome?" · "+usuario.ong_nome:"");
}
async function carregar(silencioso){
 const comSessao=!!guarda.get("ong_token"),comLink=!!(ongId&&codigo);
 if(!comSessao&&!comLink){dados=null;$("#conteudo").innerHTML="";$("#titulo").textContent="Portal da ONG";$("#subtitulo").textContent="Entre com o seu e-mail e senha ou com o link da sua organização.";mostrar("visitante");return;}
 mostrar(comSessao?"sessao":"link");
 try{dados=await chamar("matches");if(!silencioso)aviso("");render();}
 catch(error){
  if(error.status===403&&error.codigo==="trocar_senha"){abrirSenha(true);return;}
  if(error.status===401){encerrarSessaoLocal();if(!comSessao)ongId=codigo=undefined;dados=null;$("#conteudo").innerHTML="";$("#subtitulo").textContent="";mostrar("visitante");}
  if(!silencioso||error.status===401)aviso(error.message,"erro");
 }
}
function abrirSenha(forcada){
 const d=$("#senha-dialog");d.classList.toggle("forcada",!!forcada);
 $("#senha-eyebrow").textContent=forcada?"PRIMEIRO ACESSO":"MINHA CONTA";$("#senha-titulo").textContent=forcada?"Defina a sua senha":"Alterar senha";
 $("#senha-intro").textContent=forcada?"Você entrou com uma senha provisória. Escolha uma senha só sua para continuar.":"Ao trocar, as suas outras sessões são encerradas.";
 $("#cancelar-senha").hidden=$("#fechar-senha").hidden=!!forcada;$("#senha-erro").textContent="";$("#senha-form").reset();
 if(!d.open)d.showModal();
}
$("#senha-dialog").addEventListener("cancel",e=>{if(e.target.classList.contains("forcada"))e.preventDefault();});
$("#fechar-senha").addEventListener("click",()=>$("#senha-dialog").close());
$("#cancelar-senha").addEventListener("click",()=>$("#senha-dialog").close());
$("#alterar-senha").addEventListener("click",()=>abrirSenha(false));
$("#senha-form").addEventListener("submit",async e=>{
 e.preventDefault();
 const f=e.target,erro=$("#senha-erro"),botao=$("#salvar-senha");erro.textContent="";
 if(f.nova.value!==f.repita.value){erro.textContent="As duas senhas novas não são iguais.";return;}
 botao.disabled=true;
 try{await enviar("/api/eu/senha","POST",{senha_atual:f.atual.value,senha_nova:f.nova.value});f.reset();$("#senha-dialog").close();aviso("Senha trocada. As suas outras sessões foram encerradas.","ok");await carregar(true);}
 catch(error){erro.textContent=error.message;}
 finally{botao.disabled=false;}
});
$("#sair-ong").addEventListener("click",async()=>{
 try{await enviar("/api/logout","POST");}catch{}
 encerrarSessaoLocal();location.href="/ong";
});
$("#entrar-form").addEventListener("submit",async e=>{
 e.preventDefault();
 const erro=$("#entrar-erro"),botao=$("#entrar-botao"),f=e.target;erro.textContent="";botao.disabled=true;
 try{
  guarda.set("ong_token","");
  const r=await enviar("/api/login","POST",{email:f.email.value.trim(),senha:f.senha.value},false);
  if(r.usuario.perfil!=="ong"){await fetch("/api/logout",{method:"POST",headers:{"Content-Type":"application/json","Authorization":"Bearer "+r.token},body:"{}"}).catch(()=>{});throw Error("Esta conta é do painel do gestor. Entre pelo endereço /admin.");}
  f.reset();iniciarSessao(r);await carregar();
 }catch(error){erro.textContent=error.message;}
 finally{botao.disabled=false;}
});
$("#conta-form").addEventListener("submit",async e=>{
 e.preventDefault();
 const f=e.target,erro=$("#conta-erro"),botao=$("#conta-botao");erro.textContent="";
 if(f.senha.value!==f.repita.value){erro.textContent="As duas senhas não são iguais.";return;}
 botao.disabled=true;
 try{const r=await chamar("conta","POST",{nome:f.nome.value.trim(),email:f.email.value.trim(),senha:f.senha.value});f.reset();iniciarSessao(r);await carregar();aviso("Conta criada! Da próxima vez, entre em /ong com o seu e-mail e a sua senha.","ok");}
 catch(error){erro.textContent=error.message;}
 finally{botao.disabled=false;}
});
document.addEventListener("click",async e=>{
 const b=e.target.closest("button");if(!b||ocupado)return;
 const aceitar=b.dataset.aceitar,recusar=b.dataset.recusar,receber=b.dataset.receber;if(!aceitar&&!recusar&&!receber)return;
 if(receber&&!await confirmar({titulo:"Você recebeu este alimento?",mensagem:"A entrega passa a contar como concluída e vai para o histórico. Confirme só depois de receber.",sim:"Sim, recebi",perigo:false}))return;
 if(recusar&&!await confirmar({titulo:"Recusar esta doação?",mensagem:"Ela volta a ficar disponível para outras organizações. Esta ação não pode ser desfeita.",sim:"Recusar"}))return;
 ocupado=true;b.disabled=true;
 try{await chamar("matches/"+(aceitar||recusar||receber)+"/"+(aceitar?"aceitar":receber?"receber":"recusar"),"POST");aviso(aceitar?"Doação aceita. O contato do doador está no cartão.":receber?"Recebimento confirmado. Obrigado por registrar!":"Doação recusada.","ok");await carregar(true);}
 catch(error){if(error.status===403&&error.codigo==="trocar_senha")abrirSenha(true);else aviso(error.message,"erro");b.disabled=false;}
 finally{ocupado=false;}
});
$("#acesso-form").addEventListener("submit",e=>{
 e.preventDefault();
 const texto=$("#acesso-input").value.trim(),m=texto.match(/(\d+)\.([A-Za-z0-9_-]+)\s*$/);
 if(!m){aviso("Link ou código inválido. Copie-o novamente do que o administrador enviou.","erro");return;}
 [,ongId,codigo]=m;history.replaceState(null,"","/ong#"+ongId+"."+codigo);$("#acesso-input").value="";carregar();
});
let enviandoPedido=false;
$("#pedido-form").addEventListener("submit",async e=>{
 e.preventDefault();if(enviandoPedido)return;
 const f=e.target,erro=$("#pedido-erro"),botao=$("#pedido-enviar"),d=Object.fromEntries(new FormData(f));
 erro.textContent="";enviandoPedido=true;botao.disabled=true;
 const corpo={nome:d.nome.trim(),email:d.email.trim(),telefone:d.telefone.trim()||null,endereco:Object.fromEntries(["cidade","estado","bairro","rua","numero","complemento","cep"].map(c=>[c,d[c].trim()])),mensagem:d.mensagem.trim()||null,cnpj:d.cnpj.trim()||null,capacidade_kg:d.capacidade_kg?Number(d.capacidade_kg):null,aceite:f.elements.aceite.checked,site:d.site};
 try{
  const r=await fetch("/api/publico/ong-acesso",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(corpo)});
  let json={};try{json=await r.json();}catch{}
  if(!r.ok)throw Error(json.error||"Não foi possível enviar agora. Tente novamente em instantes.");
  $("#pedido-ok").textContent=json.mensagem||"Recebemos seu pedido.";$("#pedido-ok").hidden=false;$("#pedido-area").hidden=true;f.reset();
 }catch(error){erro.textContent=error instanceof TypeError?"Sem conexão com o servidor. Verifique sua internet.":error.message;}
 finally{enviandoPedido=false;botao.disabled=false;}
});
setInterval(()=>{if(!document.hidden&&dados&&!ocupado)carregar(true);},20000);
carregar();
