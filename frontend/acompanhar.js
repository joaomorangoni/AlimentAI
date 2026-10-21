"use strict";
const $=s=>document.querySelector(s);
const esc=v=>String(v??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const number=v=>new Intl.NumberFormat("pt-BR",{maximumFractionDigits:2}).format(Number(v)||0);
const PASSOS=["Oferta recebida","Aprovada pela equipe","ONG indicada","Entregue"];
const CODIGO=/([A-Za-z0-9_-]{16,64})\s*$/;
let codigo=((location.hash.slice(1).match(CODIGO)||[])[1])||"",timer=null,ocupado=false;
function aviso(texto,tipo){const a=$("#aviso");a.textContent=texto;a.hidden=!texto;a.className=tipo||"";}
function quando(v){const d=new Date(v);return isNaN(d)?"":d.toLocaleDateString("pt-BR")+" às "+d.toLocaleTimeString("pt-BR",{hour:"2-digit",minute:"2-digit"});}
function mostrarBusca(texto){clearInterval(timer);$("#resultado").hidden=true;$("#busca").hidden=false;aviso(texto||"","erro");}
function render(d){
 $("#busca").hidden=true;$("#resultado").hidden=false;aviso("");
 const falha=d.etapa==="recusada"||d.etapa==="encerrada";
 $("#res-titulo").textContent=d.titulo;$("#res-desc").textContent=d.descricao;
 $("#res-item").textContent=d.alimento+" · "+number(d.quantidade_kg)+" kg · enviada em "+quando(d.enviada_em);
 $("#passos").innerHTML=PASSOS.map((rotulo,i)=>{
  const n=i+1,feito=falha?n<=d.passo:(n<d.passo||(n===d.passo&&d.final)),cls=feito?"feito":(!falha&&n===d.passo?"atual":"");
  return '<li class="'+cls+'"><span>'+(feito?"✓":n)+"</span>"+esc(rotulo)+"</li>";
 }).join("");
 $("#resultado").classList.toggle("falha",falha);
 $("#res-auto").hidden=d.final;
 clearInterval(timer);
 if(!d.final)timer=setInterval(()=>{if(!document.hidden)consultar(true);},30000);
}
async function consultar(silencioso){
 if(ocupado||!codigo)return;
 ocupado=true;
 try{
  const r=await fetch("/api/publico/acompanhar",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({codigo})});
  let j={};try{j=await r.json();}catch{}
  if(r.status===404){history.replaceState(null,"","/acompanhar");codigo="";mostrarBusca(j.error);return;}
  if(!r.ok)throw Error(j.error||"Não foi possível consultar agora.");
  render(j);
 }catch(e){if(!silencioso)mostrarBusca(e instanceof TypeError?"Sem conexão com o servidor. Verifique sua internet.":e.message);}
 finally{ocupado=false;}
}
$("#busca-form").addEventListener("submit",e=>{
 e.preventDefault();
 const m=$("#codigo-input").value.trim().match(CODIGO);
 if(!m){aviso("Código inválido. Copie-o novamente, inteiro.","erro");return;}
 codigo=m[1];history.replaceState(null,"","/acompanhar#"+codigo);$("#codigo-input").value="";consultar(false);
});
window.addEventListener("hashchange",()=>{
 const novo=((location.hash.slice(1).match(CODIGO)||[])[1])||"";
 if(novo&&novo!==codigo){codigo=novo;consultar(false);}
});
if(codigo)consultar(false);else mostrarBusca("");
