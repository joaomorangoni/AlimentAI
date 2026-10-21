"use strict";
function enderecoTexto(r){
 const e=r.endereco;
 return e?[e.rua,e.numero,e.complemento,e.bairro,e.cidade+" / "+e.estado,"CEP "+e.cep].filter(Boolean).join(", "):r.regiao||"";
}
const names={doacoes:"Doações",doadores:"Doadores",ongs:"ONGs parceiras",matches:"Matches",acessos:"Acessos",auditoria:"Auditoria",indicadores:"Indicadores"};
const descriptions={doacoes:"Aprove ofertas, gerencie os alimentos e acompanhe cada doação.",doadores:"Quem faz a solidariedade chegar mais longe.",ongs:"Organizações que transformam doações em cuidado.",matches:"Conecte doações às organizações da sua rede.",acessos:"Quem entra no painel e no portal das ONGs, com senha individual.",auditoria:"Quem fez o quê: as ações que alteram dados, com o nome de quem as fez.",indicadores:"Impacto social, desempenho da IA e segurança da plataforma."};
const newLabels={painel:"+ Nova doação",doacoes:"+ Nova doação",doadores:"+ Novo doador",ongs:"+ Nova ONG",matches:"+ Novo match",acessos:"+ Novo acesso"};
const state={page:"painel",data:{doacoes:[],doadores:[],ongs:[],matches:[]},pedidos:[],ofertas:[],usuario:null,usuarios:[],auditoria:[],indicadores:null,updated:"",search:"",status:"",loaded:false,loading:true,error:""};
const $=s=>document.querySelector(s);
const esc=v=>String(v??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const number=v=>new Intl.NumberFormat("pt-BR",{maximumFractionDigits:2}).format(Number(v)||0);
const plain=s=>String(s??"").normalize("NFD").replace(/[̀-ͯ]/g,"").toLowerCase();
const labels={disponivel:"Disponível",reservada:"Reservada",concluida:"Concluída",cancelada:"Cancelada",pendente:"Pendente",aceito:"Aceito",recusado:"Recusado",concluido:"Concluído",baixa:"Baixa",media:"Média",alta:"Alta",baixo:"Baixo",medio:"Médio",alto:"Alto"};
const STATUS={doacoes:["pendente","disponivel","reservada","concluida","cancelada"],matches:["pendente","aceito","recusado","concluido"]};
const STATUS_EDICAO=["disponivel","reservada","concluida","cancelada"];
const MATCH_PROXIMOS={pendente:["aceito","recusado"],aceito:["concluido","recusado"],recusado:[],concluido:[]};
const CATEGORIAS=[["hortifruti","Hortifrúti"],["padaria","Padaria"],["laticinios","Laticínios"],["carnes","Carnes"],["prontos","Pratos prontos"],["nao_perecivel","Não perecível"]];
const CATEGORIA_CHAVES=[["hortifruti",["fruta","verdura","legume","hortali","vegetal"]],["padaria",["pao","padaria","bolo","biscoito","massa fresca"]],["laticinios",["laticin","leite","queijo","iogurte"]],["carnes",["carne","frango","peixe","aves","embutido","frios"]],["prontos",["pronto","marmita","refeicao","congelad"]],["nao_perecivel",["grao","cereal","enlatado","conserva","arroz","feijao","mercearia","massa","perecivel"]]];
const categoriaDe=v=>{const t=plain(v).replace(/_/g," ");const exata=CATEGORIAS.find(([k])=>k.replace(/_/g," ")===t);if(exata)return exata[0];const achada=CATEGORIA_CHAVES.find(([,chaves])=>chaves.some(c=>t.includes(c)));return achada?achada[0]:"";};
const categoriaLabel=v=>{const k=categoriaDe(v);return k?CATEGORIAS.find(([c])=>c===k)[1]:v||"—";};
const isoLocal=d=>d.getFullYear()+"-"+String(d.getMonth()+1).padStart(2,"0")+"-"+String(d.getDate()).padStart(2,"0");
const date=v=>v?new Date(String(v).slice(0,10)+"T12:00:00").toLocaleDateString("pt-BR"):"—";
const daysUntil=v=>v?Math.round((new Date(String(v).slice(0,10)+"T12:00:00")-new Date(isoLocal(new Date())+"T12:00:00"))/864e5):null;
const dash=v=>v||"—";
const newestFirst=rows=>[...rows].sort((a,b)=>b.id-a.id);
const byId=(resource,id)=>state.data[resource].find(r=>r.id===Number(id));
let noticeTimer=null;
function notify(message,kind="warn"){const n=$("#notice");clearTimeout(noticeTimer);n.textContent=message;n.hidden=!message;n.className=kind==="ok"?"ok":"";if(message&&kind==="ok")noticeTimer=setTimeout(()=>{n.hidden=true;},4500);}
const tokenStore={get(){try{return sessionStorage.getItem("api_token")||"";}catch{return "";}},set(v){try{v?sessionStorage.setItem("api_token",v):sessionStorage.removeItem("api_token");}catch{}}};
const userStore={get(){try{return JSON.parse(sessionStorage.getItem("usuario")||"null");}catch{return null;}},set(v){try{v?sessionStorage.setItem("usuario",JSON.stringify(v)):sessionStorage.removeItem("usuario");}catch{}}};
let tokenPrompt=null;
function unlock(){document.body.classList.remove("locked");$("#login").hidden=true;}
function askToken(message){return new Promise(resolve=>{
 document.body.classList.add("locked");const tela=$("#login"),campo=$("#token-input");
 $("#login-error").textContent=message||"";campo.value="";if(!$("#email-input").value)$("#email-input").value=(userStore.get()||{}).email||"";campo.type="password";$("#mostrar-token").textContent="Mostrar";$("#entrar").disabled=false;$("#entrar").textContent="Entrar";
 tela.hidden=false;campo.focus();
 $("#login-form").onsubmit=async e=>{e.preventDefault();const botao=$("#entrar"),erro=$("#login-error");botao.disabled=true;botao.textContent="Verificando…";erro.textContent="";
  try{
   const r=await fetch("/api/login",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({email:$("#email-input").value.trim(),senha:campo.value})});
   const j=await r.json().catch(()=>({}));
   if(r.ok&&j.token&&j.usuario&&j.usuario.perfil!=="gestor"){
    fetch("/api/logout",{method:"POST",headers:{"Content-Type":"application/json","Authorization":"Bearer "+j.token},body:"{}"}).catch(()=>{});
    erro.textContent="Esta conta é de uma ONG. Entre pela página da ONG (/ong).";
   }else if(r.ok&&j.token){tokenStore.set(j.token);userStore.set(j.usuario);state.usuario=j.usuario;campo.value="";resolve();return;}
   if(!erro.textContent)erro.textContent=r.status===429&&!j.error?"Muitas tentativas. Aguarde um minuto e tente de novo.":(j.error||"Não foi possível entrar.");
  }catch{erro.textContent="Sem conexão com o servidor. Verifique sua internet.";}
  botao.disabled=false;botao.textContent="Entrar";campo.focus();};
});}
function requestToken(message){tokenPrompt=tokenPrompt||askToken(message).finally(()=>{tokenPrompt=null;});return tokenPrompt;}
$("#mostrar-token").addEventListener("click",()=>{const c=$("#token-input"),ver=c.type==="password";c.type=ver?"text":"password";$("#mostrar-token").textContent=ver?"Ocultar":"Mostrar";$("#mostrar-token").setAttribute("aria-pressed",String(ver));});
$("#sair").addEventListener("click",async()=>{
 try{const t=tokenStore.get();if(t)await fetch("/api/logout",{method:"POST",headers:{"Content-Type":"application/json","Authorization":"Bearer "+t},body:"{}"});}catch{}
 tokenStore.set("");userStore.set(null);location.reload();
});
async function api(resource,method="GET",body){
 if(!tokenStore.get())await requestToken();
 const used=tokenStore.get();let response,data;
 try{response=await fetch("/api/"+resource,{method,headers:{"Content-Type":"application/json","Authorization":"Bearer "+used},body:body?JSON.stringify(body):undefined});}catch{
  if(document.body.classList.contains("locked")){tokenStore.set("");await requestToken("Sem conexão com o servidor. Verifique sua internet e entre de novo.");return api(resource,method,body);}
  throw Error("Sem conexão com o servidor. Verifique sua internet e tente de novo.");}
 if(response.status===429&&document.body.classList.contains("locked")){tokenStore.set("");await requestToken("Muitas tentativas. Aguarde um minuto e entre de novo.");return api(resource,method,body);}
 if(response.status!==401&&response.status!==429)unlock();
 try{data=await response.json();}catch{throw Error("Resposta inválida do servidor.");}
 if(response.status===401){if(tokenStore.get()===used){tokenStore.set("");await requestToken("Sessão expirada. Entre novamente.");}return api(resource,method,body);}
 if(response.status===403&&data.codigo==="trocar_senha"){abrirConta(true);throw Error(data.error);}
 if(!response.ok){throw Error(data.error||"Não foi possível concluir a operação.");}
 return data;
}
function askConfirm({title,message,yes="Confirmar",no="Cancelar",danger=false,eyebrow="CONFIRMAÇÃO"}){return new Promise(resolve=>{const d=$("#confirm");$("#confirm-eyebrow").textContent=eyebrow;$("#confirm-title").textContent=title;$("#confirm-message").textContent=message;$("#confirm-yes").textContent=yes;$("#confirm-no").textContent=no;$("#confirm-yes").classList.toggle("danger",danger);d.returnValue="";d.addEventListener("close",()=>resolve(d.returnValue==="yes"),{once:true});d.showModal();});}
async function loadIndicadores(){state.indicadores=await api("indicadores");state.updated=new Date().toLocaleTimeString("pt-BR");}
async function load(silent=false){
 if(!silent){state.loading=true;state.error="";render();}
 const results=await Promise.allSettled([...Object.keys(state.data).map(async key=>{state.data[key]=await api(key);}),loadIndicadores(),api("ong-solicitacoes").then(r=>{state.pedidos=r;}).catch(()=>{}),api("ofertas").then(r=>{state.ofertas=r;}).catch(()=>{}),api("eu").then(u=>{state.usuario=u;userStore.set(u);mostrarQuem();if(u.trocar_senha)abrirConta(true);}).catch(()=>{})]);
 const failed=results.filter(r=>r.status==="rejected");
 state.loading=false;state.loaded=failed.length===0||(silent&&state.loaded);state.error=failed.length?failed[0].reason.message:"";
 if(state.error)notify(state.error+" Use Atualizar para tentar de novo.");else if(!silent)notify("");render();
}
const badge=v=>'<span class="badge '+esc(v)+'">'+esc(labels[v]||v||"—")+"</span>";
function validadeHtml(r){
 const dias=daysUntil(r.validade),aberta=["disponivel","reservada"].includes(r.status);let tag="";
 if(aberta&&dias!==null){if(dias<0)tag=' <span class="badge cancelada">Vencida</span>';else if(dias<=3)tag=' <span class="badge reservada">'+(dias===0?"Vence hoje":"Vence em "+dias+" d")+"</span>";}
 return esc(date(r.validade))+tag;
}
const col=(h,text,html)=>({h,text,html:html||(r=>esc(text(r)))});
const columns={
 doacoes:[col("Alimento",r=>r.alimento),col("Categoria",r=>categoriaLabel(r.categoria)),col("Doador",r=>r.doador_nome),col("Quantidade",r=>number(r.quantidade_kg)+" kg"),col("Validade",r=>date(r.validade),validadeHtml),col("Status",r=>labels[r.status]||r.status,r=>badge(r.status))],
 doadores:[col("Nome",r=>r.nome),col("E-mail",r=>r.email),col("Telefone",r=>dash(r.telefone)),col("Região",r=>dash(r.regiao))],
 ongs:[col("Nome",r=>r.nome),col("E-mail",r=>r.email),col("Telefone",r=>dash(r.telefone)),col("Região",r=>dash(r.regiao)),col("Capacidade",r=>number(r.capacidade_kg)+" kg"),col("CNPJ",r=>r.cnpj?fmtCnpj(r.cnpj):"—")],
 matches:[col("Alimento",r=>r.alimento),col("ONG",r=>r.ong_nome),col("Score IA",r=>number(Number(r.score_ia)*100)+"%"),col("Prioridade",r=>labels[r.prioridade]||r.prioridade,r=>badge(r.prioridade)),col("Status",r=>labels[r.status]||r.status,r=>badge(r.status))],
};
const searchText=(resource,r)=>plain(columns[resource].map(c=>c.text(r)).join(" "));
function rowActions(resource,row){
 const aprovacao=resource==="doacoes"&&row.status==="pendente"?'<button class="primary" data-aprovar="'+row.id+'">Aprovar</button><button data-recusar-oferta="'+row.id+'">Recusar</button>':"";
 const reco=resource==="doacoes"&&row.status==="disponivel"?'<button data-reco="'+row.id+'">Recomendar ONG</button>':"";
 const concluir=resource==="matches"&&row.status==="aceito"?'<button class="primary" data-concluir="'+row.id+'">Concluir entrega</button>':"";
 const avisar=resource==="matches"&&row.status==="pendente"?'<button data-avisar="'+row.ong_id+'" data-match="'+row.id+'">Avisar ONG</button>':"";
 const link=resource==="ongs"?'<button data-link="'+row.id+'">Link da ONG</button>':"";
 return '<div class="actions">'+aprovacao+reco+avisar+concluir+link+'<button data-edit="'+resource+'" data-id="'+row.id+'">Editar</button><button data-delete="'+resource+'" data-id="'+row.id+'">Excluir</button></div>';
}
function emptyState(resource){
 if(state.loading&&!state.loaded)return '<div class="empty"><h2>Carregando…</h2><p>Buscando os dados da sua rede.</p></div>';
 if(!state.loaded)return '<div class="empty"><h2>Não foi possível carregar</h2><p>'+esc(state.error||"Tente novamente em instantes.")+'</p><button class="primary" data-refresh>Tentar novamente</button></div>';
 const filtrando=state.search||state.status;
 return '<div class="empty"><h2>'+(filtrando?"Nenhum resultado":"Nenhum registro por aqui")+'</h2><p>'+(filtrando?"Nenhum registro corresponde à busca ou ao filtro.":"Comece cadastrando o primeiro registro da sua rede.")+'</p>'+(filtrando?'<button data-clear>Limpar filtros</button>':'<button class="primary" data-create="'+resource+'">'+newLabels[resource]+"</button>")+"</div>";
}
function table(resource,rows,compact=false){
 if(!rows.length)return emptyState(resource);
 return '<div class="table-wrap"><table><thead><tr>'+columns[resource].map(c=>"<th>"+c.h+"</th>").join("")+(compact?"":"<th>Ações</th>")+"</tr></thead><tbody>"+rows.map(r=>"<tr>"+columns[resource].map(c=>"<td>"+c.html(r)+"</td>").join("")+(compact?"":"<td>"+rowActions(resource,r)+"</td>")+"</tr>").join("")+"</tbody></table></div>";
}
function filteredRows(resource){
 const termo=plain(state.search.trim());
 return newestFirst(state.data[resource]).filter(r=>(!termo||searchText(resource,r).includes(termo))&&(!state.status||r.status===state.status));
}
function updateRows(){
 const resource=state.page,rows=filteredRows(resource);
 $("#count").textContent=state.loaded?rows.length+(rows.length===1?" registro encontrado":" registros encontrados"):"";
 $("#rows").innerHTML=table(resource,rows);
}
function painelPedidos(){
 if(!state.pedidos.length)return"";
 const itens=state.pedidos.map(p=>'<article class="pedido"><div class="pedido-info"><h3>'+esc(p.nome)+' '+(p.ong_id?'<span class="badge aceito">ONG cadastrada</span>':'<span class="badge reservada">E-mail não cadastrado</span>')+'</h3><p>'+esc(p.email)+(p.telefone?" · "+esc(p.telefone):"")+" · "+esc(enderecoTexto(p))+'</p>'+('<p>'+[p.cnpj?"CNPJ "+fmtCnpj(p.cnpj):"Sem CNPJ informado",p.capacidade_kg?"Recebe até "+number(p.capacidade_kg)+" kg por vez":""].filter(Boolean).join(" · ")+'</p>')+(p.mensagem?'<p class="pedido-msg">“'+esc(p.mensagem)+'”</p>':"")+'</div><div class="actions">'+(p.ong_id?'<button class="primary" data-link="'+p.ong_id+'">Ver link</button>':'<button class="primary" data-create="ongs" data-pedido="'+p.id+'">Cadastrar ONG</button>')+'<button data-atender="'+p.id+'">Marcar como atendido</button><button data-descartar="'+p.id+'">Descartar</button></div></article>').join("");
 return '<section class="panel pending-panel"><div class="panel-heading"><div><h2>Pedidos de acesso de ONGs ('+state.pedidos.length+')</h2><p>Enviados pela página do portal. Confirme que a organização é real antes de enviar o link: ele dá acesso às doações indicadas para ela.</p></div></div><div class="pedidos">'+itens+'</div></section>';
}
async function encerrarPedido(button,acao){
 const id=button.dataset.atender||button.dataset.descartar,p=state.pedidos.find(x=>String(x.id)===id);if(!p)return;
 if(acao==="descartar"&&!await askConfirm({title:"Descartar este pedido?",message:'O pedido de "'+p.nome+'" será removido da lista e os dados dele serão apagados. Nenhum aviso é enviado à organização.',yes:"Descartar",danger:true}))return;
 button.disabled=true;
 try{await api("ong-solicitacoes/"+id+"/"+(acao==="atender"?"atender":"descartar"),"POST",{});notify(acao==="atender"?"Pedido marcado como atendido.":"Pedido descartado.","ok");await load(true);}
 catch(error){notify(error.message);button.disabled=false;}
}
const quando=v=>{const d=new Date(v);return isNaN(d)?"":d.toLocaleDateString("pt-BR")+" "+d.toLocaleTimeString("pt-BR",{hour:"2-digit",minute:"2-digit"});};
function painelOfertas(){
 // Ofertas novas (tabela ofertas_publicas) e, se existirem, doações pendentes criadas antes dessa fila.
 const novas=state.ofertas,antigas=newestFirst(state.data.doacoes.filter(r=>r.status==="pendente"));
 const total=novas.length+antigas.length;if(!total)return"";
 const cartaoNovo=o=>'<article class="pedido"><div class="pedido-info"><h3>'+esc(o.alimento)+" · "+number(o.quantidade_kg)+' kg <span class="badge">'+esc(categoriaLabel(o.categoria))+'</span></h3><p>'+esc(o.nome)+" · "+esc(o.email)+(o.telefone?" · "+esc(o.telefone):"")+(o.regiao?" · "+esc(enderecoTexto(o)):"")+"</p><p>Validade "+validadeHtml({validade:o.validade,status:"disponivel"})+" · enviada em "+esc(quando(o.criado_em))+'</p></div><div class="actions"><button class="primary" data-oferta-aprovar="'+o.id+'">Aprovar</button><button data-oferta-recusar="'+o.id+'">Recusar</button></div></article>';
 const cartaoAntigo=r=>'<article class="pedido"><div class="pedido-info"><h3>'+esc(r.alimento)+" · "+number(r.quantidade_kg)+' kg <span class="badge reservada">Fila antiga</span></h3><p>'+esc(r.doador_nome)+" · enviada antes da fila de ofertas (o doador já está cadastrado)</p><p>Validade "+validadeHtml(r)+'</p></div><div class="actions"><button class="primary" data-aprovar="'+r.id+'">Aprovar</button><button data-recusar-oferta="'+r.id+'">Recusar</button></div></article>';
 return '<section class="panel pending-panel"><div class="panel-heading"><div><h2>Ofertas aguardando aprovação ('+total+')</h2><p>Enviadas pela página pública. Confira os dados antes de aprovar: só quem for aprovado vira doador da rede, e só ofertas aprovadas entram nas recomendações e nos indicadores. Recusar apaga os dados pessoais do doador.</p></div></div><div class="pedidos">'+novas.map(cartaoNovo).join("")+antigas.map(cartaoAntigo).join("")+"</div></section>";
}
function renderPainel(){
 const d=state.data,disponiveis=d.doacoes.filter(r=>r.status==="disponivel");
 const stats=[["Alimentos disponíveis",number(disponiveis.reduce((sum,r)=>sum+Number(r.quantidade_kg),0))+" kg","Volume disponível para doação"],["Doações cadastradas",d.doacoes.length,"Cada alimento tem um destino"],["Doadores na rede",d.doadores.length,"Solidariedade que se multiplica"],["ONGs parceiras",d.ongs.length,"Conectadas por um propósito"]];
 $("#content").innerHTML=painelPedidos()+painelOfertas()+'<section class="hero"><div><p class="eyebrow">MENOS DESPERDÍCIO. MAIS IMPACTO.</p><h2>O que sobra em uma mesa<br>pode fazer falta em outra.</h2><p>Conecte alimentos, pessoas e organizações. Uma rede de cuidado começa com uma doação.</p><button data-create="doacoes">Cadastrar uma doação ↗</button></div><svg class="hero-art" viewBox="0 0 24 24" aria-hidden="true"><path d="M11 20A7 7 0 0 1 9.8 6.1C15.5 5 17 4.48 19 2c1 2 2 4.18 2 8 0 5.5-4.78 10-10 10Z"/><path d="M2 21c0-3 1.85-5.36 5.08-6C9.5 14.52 12 13 13 12"/></svg></section><section class="stats">'+stats.map(s=>'<article class="stat"><p>'+s[0]+"</p><strong>"+(state.loaded?s[1]:"—")+"</strong><small>"+s[2]+"</small></article>").join("")+'</section><section class="panel"><div class="panel-heading"><div><h2>Últimas doações</h2><p>Acompanhe os alimentos que circulam na rede.</p></div><div class="tools"><button data-refresh>Atualizar</button><button data-go="doacoes">Ver todas ↗</button></div></div>'+table("doacoes",newestFirst(d.doacoes).slice(0,5),true)+"</section>";
}
function renderResource(resource){
 if($("#content").dataset.page===resource&&$("#rows")){updateRows();return;}
 const status=STATUS[resource]||[];
 $("#content").dataset.page=resource;
 $("#content").innerHTML='<section class="panel"><div class="panel-heading"><div><h2>'+names[resource]+'</h2><p id="count"></p></div><div class="tools"><input id="search" type="search" aria-label="Buscar registros" placeholder="Buscar registros…" autocomplete="off" value="'+esc(state.search)+'">'+(status.length?'<select id="status-filter" aria-label="Filtrar por status"><option value="">Todos os status</option>'+status.map(s=>'<option value="'+s+'" '+(state.status===s?"selected":"")+'>'+labels[s]+"</option>").join("")+"</select>":"")+'<button data-refresh>Atualizar</button></div></div><div id="rows"></div></section>';
 updateRows();
}
function render(){
 const page=state.page;
 $("#page-title").textContent=names[page]||"Visão geral";$("#page-description").textContent=descriptions[page]||"Acompanhe sua rede e transforme excedentes em oportunidades.";
 $("#new-button").textContent=newLabels[page]||"";$("#new-button").hidden=page==="indicadores"||page==="auditoria";
 document.querySelectorAll("nav button").forEach(b=>{b.classList.toggle("active",b.dataset.page===page);b.setAttribute("aria-current",b.dataset.page===page?"page":"false");});
 if(page==="indicadores"||page==="painel"||page==="acessos"||page==="auditoria")delete $("#content").dataset.page;
 if(page==="indicadores")$("#content").innerHTML=ind.render(state.loaded?state.indicadores:null,state.updated);
 else if(page==="painel")renderPainel();
 else if(page==="acessos")renderAcessos();
 else if(page==="auditoria")renderAuditoria();
 else renderResource(page);
}
function setPage(page){
 if(!(page==="painel"||names[page]))page="painel";
 const changed=page!==state.page;state.page=page;state.search="";state.status="";
 if(location.hash!=="#"+page)history.replaceState(null,"","#"+page);
 if(changed&&$("#notice").className==="ok")notify("");
 delete $("#content").dataset.page;render();
 if(changed&&state.loaded)load(true);
 if(page==="acessos")carregarAcessos();
 if(page==="auditoria")carregarAuditoria();
}
const field=(name,label,type="text",extra="",wide=false)=>({name,label,type,extra,wide});
const readonly=(label,value,wide=true)=>({label,value,readonly:true,wide});
const FONE='pattern="[0-9+\\(\\) \\-]{8,20}" title="Use de 8 a 20 caracteres: números, +, parênteses, espaço ou hífen" maxlength="20"';
const COORD=(n,l,min,max)=>field(n,l+" (opcional, no Brasil)","number",'min="'+min+'" max="'+max+'" step="any"');
const nomeField=field("nome","Nome","text",'minlength="2" maxlength="120"',true);
const emailField=field("email","E-mail","email",'maxlength="160"',true);
const baseFields=[nomeField,emailField,field("telefone","Telefone","tel",FONE),field("regiao","Região","text",'maxlength="80"')];
const schemas={
 doadores:[...baseFields,COORD("latitude","Latitude",-34,6),COORD("longitude","Longitude",-74,-34)],
 ongs:[...baseFields,field("capacidade_kg","Capacidade (kg)","number",'min="0.01" max="1000000" step="0.01"',true),field("cnpj","CNPJ (opcional)","text",'maxlength="18" inputmode="numeric" placeholder="00.000.000/0000-00" title="14 dígitos, com ou sem pontuação"',true),COORD("latitude","Latitude",-34,6),COORD("longitude","Longitude",-74,-34)],
 doacoes:[field("doador_id","Doador","select","",true),field("alimento","Alimento","text",'minlength="2" maxlength="60" pattern="[A-Za-zÀ-ÿ][A-Za-zÀ-ÿ0-9 .,\'%\\(\\)\\/\\-]{1,59}" title="De 2 a 60 caracteres, começando por letra"'),field("categoria","Categoria","select"),field("quantidade_kg","Quantidade (kg)","number",'min="0.01" max="10000" step="0.01"'),field("validade","Validade","date",'min="'+isoLocal(new Date())+'"')],
 matches:[field("doacao_id","Doação","select","",true),field("ong_id","ONG","select","",true),field("score_ia","Score informado (0 a 1)","number",'min="0" max="1" step="0.01"'),field("prioridade","Prioridade","select")],
};
const VALIDADE_MAXIMA_DIAS={hortifruti:60,padaria:90,laticinios:365,carnes:365,prontos:180,nao_perecivel:1095};
const somaDias=n=>{const d=new Date();d.setDate(d.getDate()+n);return isoLocal(d);};
function limitarValidade(){const c=$('select[name=categoria]'),v=$('input[name=validade]');if(!c||!v)return;const dias=VALIDADE_MAXIMA_DIAS[c.value];if(dias)v.max=somaDias(dias);else v.removeAttribute('max');}
const OPCIONAIS=["telefone","latitude","longitude","cnpj"];
const NUMEROS=["doador_id","ong_id","doacao_id","quantidade_kg","capacidade_kg","score_ia","latitude","longitude"];
function editSchema(resource,row){
 if(resource==="doadores")return[nomeField,readonly("E-mail",row.email),baseFields[2],baseFields[3]];
 if(resource==="ongs")return[nomeField,readonly("E-mail",row.email),baseFields[2],baseFields[3],schemas.ongs[4],schemas.ongs[5]];
 if(resource==="doacoes"){const[,alimento,categoria,quantidade,validade]=schemas.doacoes;return[readonly("Doador",row.doador_nome),{...alimento,wide:true},categoria,quantidade,{...validade,extra:""},field("status","Status","select")];}
 return[readonly("Alimento",row.alimento),readonly("ONG",row.ong_nome),field("status","Status","select","",true)];
}
function selectOptions(f,resource,row){
 if(f.name==="categoria")return CATEGORIAS;
 if(f.name==="doador_id")return [...state.data.doadores].sort((x,y)=>x.nome.localeCompare(y.nome,"pt-BR")).map(r=>[r.id,r.nome+(r.regiao?" · "+r.regiao:"")]);
 if(f.name==="doacao_id")return state.data.doacoes.filter(r=>r.status==="disponivel").map(r=>[r.id,r.alimento+" · "+r.doador_nome+" · "+number(r.quantidade_kg)+" kg"]);
 if(f.name==="ong_id")return state.data.ongs.map(r=>[r.id,r.nome+(r.regiao?" · "+r.regiao:"")]);
 if(f.name==="prioridade")return["baixa","media","alta"].map(s=>[s,labels[s]]);
 if(resource==="matches")return[row.status,...MATCH_PROXIMOS[row.status]].map(s=>[s,labels[s]]);
 return(row?.status==="pendente"?["pendente",...STATUS_EDICAO]:STATUS_EDICAO).map(s=>[s,labels[s]]);
}
let prefill=null;
const fmtCnpj=v=>v?v.replace(/^(\d{2})(\d{3})(\d{3})(\d{4})(\d{2})$/,"$1.$2.$3/$4-$5"):"";
function fieldHtml(f,resource,row){
 const cls=f.wide?' class="wide"':"";
 if(f.readonly)return "<label"+cls+">"+f.label+'<input value="'+esc(f.value)+'" readonly tabindex="-1" aria-readonly="true"></label>';
 if(f.type==="select"){
  const opts=selectOptions(f,resource,row),atual=f.name==="categoria"?categoriaDe(row?.categoria):row?.[f.name];
  const vazio=!opts.length?'<small class="hint">'+({doador_id:"Nenhum doador cadastrado. Cadastre um doador antes.",doacao_id:"Nenhuma doação disponível para um match.",ong_id:"Nenhuma ONG cadastrada. Cadastre uma ONG antes."}[f.name]||"")+"</small>":"";
  return "<label"+cls+">"+f.label+'<select name="'+f.name+'" required autocomplete="off"><option value="">Selecione</option>'+opts.map(([v,l])=>'<option value="'+esc(v)+'"'+(String(atual)===String(v)?" selected":"")+">"+esc(l)+"</option>").join("")+"</select>"+vazio+"</label>";
 }
 const valor=f.type==="date"?String(row?.[f.name]??"").slice(0,10):(f.name==="cnpj"&&(row||prefill)?.cnpj?fmtCnpj((row||prefill).cnpj):(row||prefill)?.[f.name])??"";
 return "<label"+cls+">"+f.label+'<input name="'+f.name+'" type="'+f.type+'" '+f.extra+" "+(OPCIONAIS.includes(f.name)?"":"required")+' autocomplete="off" value="'+esc(valor)+'"></label>';
}
let editing=null,saving=false;
function openForm(resource,id,sugestao){
 const row=id?byId(resource,id):null;
 if(id&&!row){notify("Esse registro não existe mais. Atualize a página.");return;}
 editing={resource,row};prefill=row?null:sugestao||null;saving=false;$("#save").disabled=false;$("#form-error").textContent="";
 $("#form-title").textContent=(row?"Editar · ":"Cadastrar · ")+names[resource];
 $("#fields").innerHTML=(row?editSchema(resource,row):schemas[resource]).map(f=>fieldHtml(f,resource,row)).join("");
 limitarValidade();
 if(!$("#modal").open)$("#modal").showModal();
 const primeiro=$("#fields").querySelector("input:not([readonly]),select");if(primeiro)primeiro.focus();
}
function collectBody(form){
 const body={};
 for(const[key,raw]of new FormData(form)){
  const v=String(raw).trim();
  if(NUMEROS.includes(key)){if(v==="")body[key]=OPCIONAIS.includes(key)?null:undefined;else{const n=Number(v);if(Number.isNaN(n))throw Error("Valor numérico inválido em "+key+".");body[key]=n;}}
  else body[key]=v===""&&OPCIONAIS.includes(key)?null:v;
 }
 if(body.email)body.email=body.email.toLowerCase();
 return body;
}
async function submitForm(e){
 e.preventDefault();if(saving)return;
 const{resource,row}=editing,button=$("#save"),erro=$("#form-error");
 saving=true;button.disabled=true;erro.textContent="";
 try{
  const body=collectBody(e.target),path=resource+(row?"/"+row.id:""),method=row?"PUT":"POST";
  await api(path,method,body);
  $("#modal").close();
  notify((row?"Alterações salvas":"Cadastro realizado")+" com sucesso.","ok");
  await load(true);
 }catch(error){erro.textContent=error.message;}
 finally{saving=false;button.disabled=false;}
}
const riscos={baixo:"baixo",medio:"medio",alto:"alto"};
const kmTexto=km=>km<1?"menos de 1 km":number(km)+" km";
const distanciaHtml=c=>(c.distancia_origem==="estimativa"?"~"+kmTexto(c.distancia_km)+' <small class="muted">(estimada)</small>':kmTexto(c.distancia_km)+(c.distancia_origem==="cidade"?' <small class="muted">(entre cidades)</small>':""))+(c.distancia_acima_da_faixa_do_modelo?' <small class="muted" title="O modelo foi treinado com distâncias de até 25 km: acima disso, o risco é calculado como se fosse 25 km.">*</small>':"");
async function openReco(button){
 const body=$("#reco-body");body.textContent="Calculando recomendações…";if(!$("#reco").open)$("#reco").showModal();button.disabled=true;
 try{
  const r=await api("doacoes/"+button.dataset.reco+"/recomendacoes");
  const existe=ong=>state.data.matches.some(m=>m.doacao_id===r.doacao_id&&m.ong_id===ong&&m.status!=="recusado");
  body.innerHTML=(r.recomendacoes.length?'<p>Prioridade sugerida: <strong>'+esc(labels[r.prioridade_sugerida]||"—")+'</strong> · validade em '+esc(r.dias_ate_validade)+' dia(s)</p><div class="table-wrap"><table><thead><tr><th>ONG</th><th>Região</th><th>Distância</th><th>Score IA</th><th>Risco de descarte</th><th></th></tr></thead><tbody>'+r.recomendacoes.map(c=>"<tr><td>"+esc(c.ong_nome)+"</td><td>"+esc(dash(c.regiao))+"</td><td>"+distanciaHtml(c)+"</td><td>"+number(c.score_ia*100)+"%</td><td>"+badge(riscos[c.risco_descarte]||c.risco_descarte)+"</td><td>"+(existe(c.ong_id)?'<span class="muted">Match já criado</span>':'<button class="primary" data-doacao="'+esc(r.doacao_id)+'" data-ong="'+esc(c.ong_id)+'" data-score="'+esc(c.score_ia)+'" data-prio="'+esc(r.prioridade_sugerida)+'">Criar match</button>')+"</td></tr>").join("")+"</tbody></table></div>":'<p>Nenhuma ONG com capacidade suficiente para este lote.</p>')+'<p class="reco-note">'+esc(r.aviso)+"</p>";
 }catch(error){body.textContent=error.message;}finally{button.disabled=false;}
}
async function createMatch(button){
 button.disabled=true;
 try{
  await api("matches","POST",{doacao_id:Number(button.dataset.doacao),ong_id:Number(button.dataset.ong),score_ia:Number(button.dataset.score),prioridade:button.dataset.prio});
  $("#reco").close();notify("Match criado com sucesso.","ok");await load(true);
 }catch(error){$("#reco-body").insertAdjacentHTML("beforeend",'<p class="error">'+esc(error.message)+"</p>");button.disabled=false;}
}
const recordName=(resource,row)=>({doacoes:()=>row.alimento+" ("+row.doador_nome+")",doadores:()=>row.nome,ongs:()=>row.nome,matches:()=>row.alimento+" → "+row.ong_nome}[resource])();
async function deleteRecord(button){
 const resource=button.dataset.delete,row=byId(resource,button.dataset.id);if(!row)return;
 const ok=await askConfirm({title:"Excluir registro?",message:'"'+recordName(resource,row)+'" será removido. Esta ação não pode ser desfeita.',yes:"Excluir",danger:true});
 if(!ok)return;
 button.disabled=true;
 try{await api(resource+"/"+row.id,"DELETE");notify("Registro excluído.","ok");await load(true);}
 catch(error){notify(error.message);button.disabled=false;}
}
async function concluirEntrega(button){
 const row=byId("matches",button.dataset.concluir);if(!row)return;
 if(!await askConfirm({title:"Concluir esta entrega?",message:'Confirme que "'+row.alimento+'" já foi entregue à ONG "'+row.ong_nome+'". A doação passa a contar como concluída nos indicadores. (A própria ONG também pode confirmar o recebimento pelo portal.)',yes:"Concluir entrega"}))return;
 button.disabled=true;
 try{await api("matches/"+row.id,"PUT",{status:"concluido"});notify("Entrega concluída.","ok");await load(true);}
 catch(error){notify(error.message);button.disabled=false;}
}
async function decidirOfertaNova(button,acao){
 const id=button.dataset.ofertaAprovar||button.dataset.ofertaRecusar,o=state.ofertas.find(x=>String(x.id)===id);if(!o)return;
 if(acao==="recusar"&&!await askConfirm({title:"Recusar esta oferta?",message:'"'+o.alimento+'" de '+o.nome+" será recusada e os dados pessoais do doador serão apagados. Esta ação não pode ser desfeita.",yes:"Recusar",danger:true}))return;
 button.disabled=true;
 try{await api("ofertas/"+id+"/"+acao,"POST",{});notify(acao==="aprovar"?"Oferta aprovada: o doador foi cadastrado e a doação já está disponível.":"Oferta recusada e dados pessoais apagados.","ok");await load(true);}
 catch(error){notify(error.message);button.disabled=false;await load(true);}
}
async function decidirOferta(button,acao){
 const id=button.dataset.aprovar||button.dataset.recusarOferta,row=byId("doacoes",id);if(!row)return;
 if(acao==="recusar"&&!await askConfirm({title:"Recusar esta oferta?",message:'"'+row.alimento+'" de '+row.doador_nome+" será marcada como cancelada e não entrará na rede.",yes:"Recusar",danger:true}))return;
 button.disabled=true;
 try{await api("doacoes/"+id+"/"+acao,"POST",{});notify(acao==="aprovar"?"Oferta aprovada: já aparece como disponível.":"Oferta recusada.","ok");await load(true);}
 catch(error){notify(error.message);button.disabled=false;}
}
let ongDoLink=null;
const LINK_VELHO_DIAS=90;
function mostrarIdadeDoLink(r){
 const info=$("#link-info"),dias=r.gerado_em?Math.floor((Date.now()-new Date(r.gerado_em))/864e5):null;
 $("#desativar-link").hidden=r.ativo===false;
 if(r.ativo===false){info.className="link-info velho";info.textContent="Link desativado: ninguém entra por ele (só por e-mail e senha). Gerar um novo link reativa o acesso por link.";$("#enviar-link").hidden=true;return;}
 info.className="link-info"+(dias!==null&&dias>=LINK_VELHO_DIAS?" velho":"");
 if(!r.gerado_em)info.textContent="Link original, válido desde o cadastro da ONG. Se ele vazou ou mudou de mãos, gere um novo.";
 else info.textContent="Gerado em "+date(r.gerado_em)+(dias<=0?" (hoje)":" (há "+dias+(dias===1?" dia)":" dias)"))+(dias>=LINK_VELHO_DIAS?". Já faz tempo: considere gerar um novo.":".");
}
const telefoneWhats=t=>{const d=String(t||"").replace(/\D/g,"");return d.length===10||d.length===11?"55"+d:(d.length===12||d.length===13)&&d.startsWith("55")?d:"";};
function montarEnvio(ong,url,match){
 const intro=match?"Olá, "+ong.nome+"! Há uma nova doação para a sua organização ("+match.alimento+"). Veja os detalhes e responda pelo portal da Rede Alimenta:":"Olá, "+ong.nome+"! Este é o link de acesso da sua organização ao portal da Rede Alimenta. Nele você vê as doações indicadas para vocês e responde:";
 const texto=intro+"\n"+url+"\n\nO link é pessoal da organização: não o compartilhe.";
 const assunto=match?"Nova doação para a sua organização":"Acesso ao portal da Rede Alimenta";
 $("#enviar-email").href="mailto:"+(/^[^\s@,;?&]+@[^\s@,;?&]+$/.test(ong.email||"")?ong.email:"")+"?subject="+encodeURIComponent(assunto)+"&body="+encodeURIComponent(texto);
 $("#enviar-whats").href="https://wa.me/"+telefoneWhats(ong.telefone)+"?text="+encodeURIComponent(texto);
 $("#enviar-link").hidden=false;
}
async function abrirLink(id,match){
 const ong=byId("ongs",id);if(!ong)return;
 ongDoLink=ong;$("#link-titulo").textContent=match?"Avisar a ONG":"Link de acesso";$("#link-ong").textContent=ong.nome;$("#link-url").value="";$("#link-erro").textContent="";$("#link-info").textContent="";$("#enviar-link").hidden=true;if(!$("#link").open)$("#link").showModal();
 try{const r=await api("ongs/"+id+"/link");$("#link-url").value=location.origin+r.caminho;mostrarIdadeDoLink(r);if(r.ativo!==false)montarEnvio(ong,$("#link-url").value,match);}catch(error){$("#link-erro").textContent=error.message;}
}
async function copiarLink(){
 const campo=$("#link-url");campo.select();
 try{await navigator.clipboard.writeText(campo.value);$("#link-erro").textContent="";$("#copiar-link").textContent="Copiado!";setTimeout(()=>{$("#copiar-link").textContent="Copiar";},1800);}
 catch{$("#link-erro").textContent="Copie manualmente: selecione o endereço e use Ctrl+C.";}
}
async function renovarLink(){
 if(!ongDoLink)return;
 if(!await askConfirm({title:"Gerar novo link?",message:"O link atual de "+ongDoLink.nome+" deixa de funcionar imediatamente. Envie o novo link para a organização.",yes:"Gerar novo link",danger:true}))return;
 try{const r=await api("ongs/"+ongDoLink.id+"/link/renovar","POST",{});$("#link-url").value=location.origin+r.caminho;$("#link-erro").textContent="";mostrarIdadeDoLink(r);montarEnvio(ongDoLink,$("#link-url").value,null);}
 catch(error){$("#link-erro").textContent=error.message;}
}

/* ---- Conta, acessos e auditoria ---------------------------------------------------------------------------------- */
const iniciais=nome=>(String(nome||"").split(/\s+/).filter(Boolean).slice(0,2).map(p=>p[0]).join("").toUpperCase())||"ADM";
function mostrarQuem(){
 const u=state.usuario;
 $("#quem").textContent=u?u.nome:"";
 $("#minha-conta").textContent=iniciais(u&&u.nome);$("#minha-conta").title=u?"Minha conta · "+u.nome:"Minha conta";
}
function abrirConta(forcada){
 const u=state.usuario||userStore.get()||{},d=$("#conta-dialog"),temConta=u.id!=null;
 d.classList.toggle("forcada",!!forcada);
 $("#conta-eyebrow").textContent=forcada?"PRIMEIRO ACESSO":"MINHA CONTA";
 $("#conta-titulo").textContent=forcada?"Defina a sua senha":"Minha conta";
 $("#conta-dados").textContent=forcada?"Você entrou com uma senha provisória. Escolha uma senha só sua para continuar.":temConta?u.nome+" · "+u.email+" · "+(u.perfil==="ong"?"ONG "+(u.ong_nome||""):"gestor"):"Você usa o token da API, que é definido no servidor.";
 $("#conta-campos").hidden=!temConta;$("#salvar-conta").hidden=!temConta;$("#conta-erro").textContent="";$("#conta-form").reset();
 $("#cancelar-conta").textContent=temConta?"Cancelar":"Fechar";
 if(!d.open)d.showModal();
}
$("#conta-dialog").addEventListener("cancel",e=>{if(e.target.classList.contains("forcada"))e.preventDefault();});
$("#conta-form").addEventListener("submit",async e=>{
 e.preventDefault();
 const f=e.target,erro=$("#conta-erro"),botao=$("#salvar-conta");erro.textContent="";
 if(f.nova.value!==f.repita.value){erro.textContent="As duas senhas novas não são iguais.";return;}
 botao.disabled=true;
 try{
  await api("eu/senha","POST",{senha_atual:f.atual.value,senha_nova:f.nova.value});
  f.reset();$("#conta-dialog").close();notify("Senha trocada. As suas outras sessões foram encerradas.","ok");
  state.usuario={...state.usuario,trocar_senha:false};userStore.set(state.usuario);await load(true);
 }catch(error){erro.textContent=error.message;}
 finally{botao.disabled=false;}
});
function mostrarSenhaProvisoria(titulo,texto,senha){
 $("#senha-titulo").textContent=titulo;$("#senha-texto").textContent=texto;$("#senha-valor").value=senha;$("#copiar-senha").textContent="Copiar";
 if(!$("#senha-dialog").open)$("#senha-dialog").showModal();
}
$("#senha-dialog").addEventListener("cancel",e=>e.preventDefault());
async function carregarAcessos(){
 try{state.usuarios=await api("usuarios");}catch(error){state.usuarios=null;state.erroAcessos=error.message;}
 if(state.page==="acessos")render();
}
async function carregarAuditoria(){
 try{state.auditoria=await api("auditoria?limite=200");}catch(error){state.auditoria=null;state.erroAuditoria=error.message;}
 if(state.page==="auditoria")render();
}
const situacaoUsuario=u=>!u.ativo?'<span class="badge desativado">Desativado</span>':u.trocar_senha?'<span class="badge pendente-senha">Aguardando o 1º acesso</span>':'<span class="badge aceito">Ativo</span>';
function renderAcessos(){
 const aviso="";
 let corpo;
 if(state.usuarios===null)corpo='<div class="empty"><h2>Não foi possível carregar</h2><p>'+esc(state.erroAcessos||"Tente novamente.")+'</p><button class="primary" data-refresh>Tentar novamente</button></div>';
 else if(!state.usuarios.length)corpo='<div class="empty"><h2>Nenhuma conta ainda</h2><p>Ainda não há contas. Crie a primeira conta de gestor aqui.</p><button class="primary" data-novo-acesso>+ Novo acesso</button></div>';
 else corpo='<div class="table-wrap"><table><thead><tr><th>Pessoa</th><th>Acesso</th><th>Situação</th><th>Último acesso</th><th>Ações</th></tr></thead><tbody>'+state.usuarios.map(u=>'<tr><td><strong>'+esc(u.nome)+'</strong><br><small class="muted">'+esc(u.email)+'</small></td><td>'+(u.perfil==="ong"?"ONG · "+esc(u.ong_nome||""):"Gestor da rede")+'</td><td>'+situacaoUsuario(u)+'</td><td>'+(u.ultimo_acesso?esc(quando(u.ultimo_acesso)):"—")+'</td><td><div class="actions">'+(u.ativo?'<button data-acesso-desativar="'+u.id+'">Desativar</button>':'<button data-acesso-reativar="'+u.id+'">Reativar</button>')+'<button data-acesso-redefinir="'+u.id+'">Nova senha</button></div></td></tr>').join("")+"</tbody></table></div>";
 $("#content").innerHTML=aviso+'<section class="panel"><div class="panel-heading"><div><h2>Acessos</h2><p>Gestores entram no painel; pessoas de uma ONG entram no portal da ONG. O link pessoal da ONG segue valendo até você desativá-lo (botão no diálogo do link, em ONGs parceiras).</p></div><div class="tools"><button data-refresh>Atualizar</button></div></div>'+corpo+"</section>";
}
function abrirNovoAcesso(){
 const f=$("#acesso-form");f.reset();$("#acesso-erro").textContent="";
 f.ong_id.innerHTML=state.data.ongs.length?state.data.ongs.map(o=>'<option value="'+o.id+'">'+esc(o.nome)+"</option>").join(""):'<option value="">Nenhuma ONG cadastrada</option>';
 $("#acesso-ong-rotulo").hidden=true;$("#acesso-dialog").showModal();f.nome.focus();
}
$("#acesso-form").addEventListener("change",e=>{if(e.target.name==="perfil")$("#acesso-ong-rotulo").hidden=e.target.value!=="ong";});
$("#acesso-form").addEventListener("submit",async e=>{
 e.preventDefault();
 const f=e.target,erro=$("#acesso-erro"),botao=$("#salvar-acesso");erro.textContent="";botao.disabled=true;
 try{
  const corpo={perfil:f.perfil.value,nome:f.nome.value.trim(),email:f.email.value.trim()};
  if(corpo.perfil==="ong")corpo.ong_id=Number(f.ong_id.value)||null;
  const r=await api("usuarios","POST",corpo);
  $("#acesso-dialog").close();
  mostrarSenhaProvisoria("Acesso criado para "+corpo.nome,"Entregue esta senha provisória a "+corpo.nome+" ("+corpo.email+"). No primeiro acesso, a pessoa define a própria senha.",r.senha_provisoria);
  await carregarAcessos();
 }catch(error){erro.textContent=error.message;}
 finally{botao.disabled=false;}
});
async function decidirAcesso(button){
 const id=button.dataset.acessoDesativar||button.dataset.acessoReativar||button.dataset.acessoRedefinir,u=(state.usuarios||[]).find(x=>String(x.id)===id);if(!u)return;
 const acao=button.dataset.acessoDesativar?"desativar":button.dataset.acessoReativar?"reativar":"redefinir-senha";
 const textos={desativar:{title:"Desativar este acesso?",message:u.nome+" não consegue mais entrar e as sessões abertas caem na hora. Dá para reativar depois.",yes:"Desativar",danger:true},
  reativar:{title:"Reativar este acesso?",message:u.nome+" volta a poder entrar com a senha de antes.",yes:"Reativar",danger:false},
  "redefinir-senha":{title:"Redefinir a senha?",message:"A senha atual de "+u.nome+" deixa de valer, as sessões abertas caem e uma senha provisória é gerada (ela aparece uma vez).",yes:"Redefinir",danger:true}}[acao];
 if(!await askConfirm(textos))return;
 button.disabled=true;
 try{
  const r=await api("usuarios/"+id+"/"+acao,"POST",{});
  if(acao==="redefinir-senha")mostrarSenhaProvisoria("Nova senha provisória de "+u.nome,"Entregue esta senha a "+u.nome+". No próximo acesso, a pessoa define a própria senha.",r.senha_provisoria);
  else notify(acao==="desativar"?"Acesso desativado.":"Acesso reativado.","ok");
  await carregarAcessos();
 }catch(error){notify(error.message);button.disabled=false;}
}
const SUJEITOS={doadores:"um doador",ongs:"uma ONG",doacoes:"uma doação",matches:"um match"};
function rotuloAcao(a){
 const n=a.registro_id!=null?" #"+a.registro_id:"";
 const exatos={"login":"Entrou no sistema","login falhou":"Tentativa de login recusada",
  "POST /api/logout":"Saiu do sistema","POST /api/eu/senha":"Trocou a própria senha","POST /api/usuarios":"Criou um acesso","POST /api/ong-portal/conta":"Criou a própria conta pelo link da ONG"};
 if(exatos[a.acao])return exatos[a.acao];
 const m=a.acao.match(/^(POST|PUT|DELETE) \/api\/(.+)$/);if(!m)return a.acao;
 const rota=m[2];
 const regras=[[/^ofertas\/\{id\}\/aprovar$/,"Aprovou a oferta"+n],[/^ofertas\/\{id\}\/recusar$/,"Recusou a oferta"+n+" (dados pessoais apagados)"],
  [/^doacoes\/\{id\}\/aprovar$/,"Aprovou a doação"+n],[/^doacoes\/\{id\}\/recusar$/,"Recusou a doação"+n],
  [/^ongs\/\{id\}\/link\/renovar$/,"Gerou um novo link da ONG"+n],[/^ongs\/\{id\}\/link\/desativar$/,"Desativou o link da ONG"+n],
  [/^ong-solicitacoes\/\{id\}\/atender$/,"Marcou o pedido de acesso"+n+" como atendido"],[/^ong-solicitacoes\/\{id\}\/descartar$/,"Descartou o pedido de acesso"+n],
  [/^usuarios\/\{id\}\/desativar$/,"Desativou o acesso"+n],[/^usuarios\/\{id\}\/reativar$/,"Reativou o acesso"+n],[/^usuarios\/\{id\}\/redefinir-senha$/,"Redefiniu a senha do acesso"+n],
  [/^ong-portal\/matches\/\{id\}\/aceitar$/,"Aceitou a doação do match"+n],[/^ong-portal\/matches\/\{id\}\/recusar$/,"Recusou a doação do match"+n],[/^ong-portal\/matches\/\{id\}\/receber$/,"Confirmou o recebimento do match"+n],
  [/^ia\/risco$/,"Consultou o risco de um lote"]];
 for(const[r,t]of regras)if(r.test(rota))return t;
 const g=rota.match(/^(doadores|ongs|doacoes|matches)(\/\{id\})?$/);
 if(g){const verbo={POST:"Cadastrou",PUT:"Editou",DELETE:"Excluiu"}[m[1]];return verbo+" "+SUJEITOS[g[1]]+n;}
 return a.acao;
}
function renderAuditoria(){
 let corpo;
 if(state.auditoria===null)corpo='<div class="empty"><h2>Não foi possível carregar</h2><p>'+esc(state.erroAuditoria||"Tente novamente.")+'</p><button class="primary" data-refresh>Tentar novamente</button></div>';
 else if(!state.auditoria.length)corpo='<div class="empty"><h2>Nada registrado ainda</h2><p>As ações que alteram dados aparecem aqui assim que alguém as fizer.</p></div>';
 else corpo='<div class="table-wrap auditoria"><table><thead><tr><th>Quando</th><th>Quem</th><th>O que fez</th></tr></thead><tbody>'+state.auditoria.map(a=>'<tr><td>'+esc(quando(a.quando))+'</td><td class="quem-linha">'+esc(a.ator_nome)+(a.ator_tipo==="usuario"?"":' <small class="muted">('+esc({token:"token da API",link:"link da ONG",sistema:"sistema"}[a.ator_tipo]||a.ator_tipo)+")</small>")+'</td><td class="acao">'+esc(rotuloAcao(a))+"</td></tr>").join("")+"</tbody></table></div>";
 $("#content").innerHTML='<section class="panel"><div class="panel-heading"><div><h2>Auditoria</h2><p>As 200 ações mais recentes que alteraram dados, e os logins. Não guardamos o conteúdo das requisições nem senhas.</p></div><div class="tools"><button data-refresh>Atualizar</button></div></div>'+corpo+"</section>";
}
$("#minha-conta").addEventListener("click",()=>abrirConta(false));
$("#fechar-conta").addEventListener("click",()=>$("#conta-dialog").close());
$("#cancelar-conta").addEventListener("click",()=>$("#conta-dialog").close());
$("#fechar-acesso").addEventListener("click",()=>$("#acesso-dialog").close());
$("#cancelar-acesso").addEventListener("click",()=>$("#acesso-dialog").close());
$("#fechar-senha").addEventListener("click",()=>$("#senha-dialog").close());
$("#copiar-senha").addEventListener("click",async()=>{const c=$("#senha-valor");c.select();try{await navigator.clipboard.writeText(c.value);$("#copiar-senha").textContent="Copiado!";}catch{$("#copiar-senha").textContent="Use Ctrl+C";}});
async function desativarLink(){
 if(!ongDoLink)return;
 if(!await askConfirm({title:"Desativar o link?",message:"Ninguém mais entra no portal de "+ongDoLink.nome+" pelo link: só por e-mail e senha. Faça isso depois que a ONG criar as contas. Gerar um novo link reativa.",yes:"Desativar link",danger:true}))return;
 try{const r=await api("ongs/"+ongDoLink.id+"/link/desativar","POST",{});mostrarIdadeDoLink(r);$("#link-erro").textContent="";}
 catch(error){$("#link-erro").textContent=error.message;}
}
setInterval(async()=>{if(document.hidden||!state.loaded||state.page==="indicadores"||document.querySelector("dialog[open]"))return;try{await load(true);if(state.page==="acessos")await carregarAcessos();if(state.page==="auditoria")await carregarAuditoria();}catch{}},30000);
setInterval(async()=>{if(state.page!=="indicadores"||document.hidden||!state.loaded)return;try{await loadIndicadores();render();}catch{}},15000);
document.addEventListener("click",async e=>{
 const b=e.target.closest("button");if(!b)return;
 if(b.dataset.page||b.dataset.go)setPage(b.dataset.page||b.dataset.go);
 else if(b.dataset.create)openForm(b.dataset.create,undefined,b.dataset.pedido?state.pedidos.find(x=>String(x.id)===b.dataset.pedido):undefined);
 else if(b.id==="new-button"){if(state.page==="acessos")abrirNovoAcesso();else openForm(state.page==="painel"?"doacoes":state.page);}
 else if(b.dataset.edit)openForm(b.dataset.edit,b.dataset.id);
 else if(b.hasAttribute("data-refresh")){await load();if(state.page==="acessos")await carregarAcessos();if(state.page==="auditoria")await carregarAuditoria();}
 else if(b.hasAttribute("data-clear")){state.search="";state.status="";delete $("#content").dataset.page;render();}
 else if(["close-modal","cancel"].includes(b.id))$("#modal").close();
 else if(b.dataset.reco)await openReco(b);
 else if(b.id==="close-reco")$("#reco").close();
 else if(b.dataset.ong)await createMatch(b);
 else if(b.dataset.delete)await deleteRecord(b);
 else if(b.dataset.ofertaAprovar)await decidirOfertaNova(b,"aprovar");
 else if(b.dataset.ofertaRecusar)await decidirOfertaNova(b,"recusar");
 else if(b.dataset.aprovar)await decidirOferta(b,"aprovar");
 else if(b.dataset.recusarOferta)await decidirOferta(b,"recusar");
 else if(b.dataset.concluir)await concluirEntrega(b);
 else if(b.dataset.atender)await encerrarPedido(b,"atender");
 else if(b.dataset.descartar)await encerrarPedido(b,"descartar");
 else if(b.dataset.avisar)await abrirLink(b.dataset.avisar,byId("matches",b.dataset.match));
 else if(b.dataset.link)await abrirLink(b.dataset.link);
 else if(b.id==="copiar-link")await copiarLink();
 else if(b.id==="renovar-link")await renovarLink();
 else if(b.id==="desativar-link")await desativarLink();
 else if(b.hasAttribute("data-novo-acesso"))abrirNovoAcesso();
 else if(b.dataset.acessoDesativar||b.dataset.acessoReativar||b.dataset.acessoRedefinir)await decidirAcesso(b);
 else if(b.id==="fechar-link")$("#link").close();
});
document.addEventListener("input",e=>{if(e.target.id==="search"){state.search=e.target.value;updateRows();}});
document.addEventListener("change",e=>{if(e.target.name==="categoria")limitarValidade();if(e.target.id==="status-filter"){state.status=e.target.value;updateRows();}});
window.addEventListener("hashchange",()=>{const page=location.hash.slice(1);if(page!==state.page)setPage(page);});
$("#record-form").addEventListener("submit",submitForm);
state.page=(()=>{const p=location.hash.slice(1);return p==="painel"||names[p]?p:"painel";})();
state.usuario=userStore.get();mostrarQuem();
load().then(()=>{if(state.page==="acessos")carregarAcessos();if(state.page==="auditoria")carregarAuditoria();});
