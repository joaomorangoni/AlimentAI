"use strict";
const $=s=>document.querySelector(s);
const VALIDADE_MAXIMA_DIAS={hortifruti:60,padaria:90,laticinios:365,carnes:365,prontos:180,nao_perecivel:1095};
const isoLocal=d=>d.getFullYear()+"-"+String(d.getMonth()+1).padStart(2,"0")+"-"+String(d.getDate()).padStart(2,"0");
const somaDias=n=>{const d=new Date();d.setDate(d.getDate()+n);return isoLocal(d);};
const form=$("#oferta");
function limitarValidade(){
 const v=form.elements.validade,dias=VALIDADE_MAXIMA_DIAS[form.elements.categoria.value];
 v.min=isoLocal(new Date());
 if(dias){v.max=somaDias(dias);$("#dica-validade").textContent="Para esta categoria, a validade pode ser de até "+dias+" dias.";}
 else{v.removeAttribute("max");$("#dica-validade").textContent="";}
}
form.elements.categoria.addEventListener("change",limitarValidade);
limitarValidade();
let enviando=false;
form.addEventListener("submit",async e=>{
 e.preventDefault();if(enviando)return;
 const botao=$("#enviar"),erro=$("#form-error");erro.textContent="";enviando=true;botao.disabled=true;
 const dados=Object.fromEntries(new FormData(form));
 const corpo={nome:dados.nome.trim(),email:dados.email.trim(),telefone:dados.telefone.trim()||null,endereco:Object.fromEntries(["cidade","estado","bairro","rua","numero","complemento","cep"].map(c=>[c,dados[c].trim()])),alimento:dados.alimento.trim(),categoria:dados.categoria,quantidade_kg:Number(dados.quantidade_kg),validade:dados.validade,aceite:form.elements.aceite.checked,site:dados.site||""};
 try{
  const resposta=await fetch("/api/publico/doacoes",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(corpo)});
  let json={};try{json=await resposta.json();}catch{}
  if(!resposta.ok)throw Error(json.error||"Não foi possível enviar agora. Tente novamente em instantes.");
  $("#mensagem-sucesso").textContent=json.mensagem||"Recebemos sua oferta.";
  $("#acompanhar-box").hidden=!json.codigo;
  if(json.codigo){$("#codigo-oferta").value=json.codigo;$("#link-acompanhar").href="/acompanhar#"+json.codigo;}
  $("#form-area").hidden=true;$("#sucesso").hidden=false;form.reset();limitarValidade();window.scrollTo(0,0);
 }catch(error){erro.textContent=error instanceof TypeError?"Sem conexão com o servidor. Verifique sua internet.":error.message;}
 finally{enviando=false;botao.disabled=false;}
});
$("#copiar-codigo").addEventListener("click",async()=>{
 const c=$("#codigo-oferta");c.select();
 try{await navigator.clipboard.writeText(c.value);$("#copiar-codigo").textContent="Copiado!";setTimeout(()=>{$("#copiar-codigo").textContent="Copiar";},1800);}
 catch{$("#copiar-codigo").textContent="Use Ctrl+C";}
});
$("#nova-oferta").addEventListener("click",()=>{$("#sucesso").hidden=true;$("#form-area").hidden=false;});
