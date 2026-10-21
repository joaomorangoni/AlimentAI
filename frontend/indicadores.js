"use strict";
/* Dashboard de indicadores: KPIs, graficos em SVG (sem bibliotecas externas, compativel com a CSP). */
const ind={
 esc:v=>String(v??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c])),
 num:(v,d=2)=>new Intl.NumberFormat("pt-BR",{maximumFractionDigits:d}).format(Number(v)||0),
 pct:v=>new Intl.NumberFormat("pt-BR",{style:"percent",maximumFractionDigits:1}).format(Number(v)||0),
};
ind.tile=(titulo,valor,nota)=>'<article class="stat"><p>'+ind.esc(titulo)+'</p><strong>'+ind.esc(valor)+'</strong><small>'+ind.esc(nota)+'</small></article>';
ind.barras=(linhas,rotulo)=>{
 if(!linhas.length)return '<p class="chart-empty">Sem dados por região ainda.</p>';
 const max=Math.max(...linhas.map(l=>l.valor),1),h=34*linhas.length+10;
 return '<svg class="chart" role="img" aria-label="'+ind.esc(rotulo)+'" viewBox="0 0 520 '+h+'" preserveAspectRatio="xMinYMin meet">'+linhas.map((l,i)=>{
  const w=Math.round(300*l.valor/max),y=10+i*34;
  return '<text x="0" y="'+(y+15)+'" class="chart-label">'+ind.esc(l.nome)+'</text><rect x="130" y="'+y+'" width="'+w+'" height="20" rx="4" class="bar"/><text x="'+(136+w)+'" y="'+(y+15)+'" class="chart-value">'+ind.num(l.valor,0)+'</text>';
 }).join("")+'</svg>';
};
ind.mapaCalor=(regioes)=>{
 const cols=["disponivel","reservada","concluida","cancelada"],nomes={disponivel:"Disponível",reservada:"Reservada",concluida:"Concluída",cancelada:"Cancelada"};
 if(!regioes.length)return '<p class="chart-empty">Sem dados por região ainda.</p>';
 const max=Math.max(...regioes.flatMap(r=>cols.map(c=>r.kg_por_status[c]||0)),1),cw=88,x0=130,h=40+34*regioes.length;
 let out='<svg class="chart" role="img" aria-label="Mapa de calor: kg por região e status" viewBox="0 0 '+(x0+cw*cols.length)+' '+h+'">';
 cols.forEach((c,j)=>{out+='<text x="'+(x0+j*cw+cw/2)+'" y="16" text-anchor="middle" class="chart-label">'+nomes[c]+'</text>';});
 regioes.forEach((r,i)=>{const y=26+i*34;out+='<text x="0" y="'+(y+20)+'" class="chart-label">'+ind.esc(r.regiao)+'</text>';
  cols.forEach((c,j)=>{const v=r.kg_por_status[c]||0,op=(0.08+0.92*v/max).toFixed(2);
   out+='<g><rect x="'+(x0+j*cw+2)+'" y="'+y+'" width="'+(cw-4)+'" height="28" rx="5" class="heat" fill-opacity="'+op+'"><title>'+ind.esc(r.regiao)+' · '+nomes[c]+': '+ind.num(v)+' kg</title></rect><text x="'+(x0+j*cw+cw/2)+'" y="'+(y+19)+'" text-anchor="middle" class="'+(op>0.55?"heat-text-on":"heat-text")+'">'+ind.num(v,0)+'</text></g>';});});
 return out+'</svg>';
};
/* Contorno simplificado do Brasil, (longitude, latitude): so para dar contexto ao mapa; nao serve para medir area ou fronteira. */
ind.brasil=[
 [-60.2,5.27],[-59.9,4.4],[-59.7,3.9],[-59.8,3.0],[-58.9,1.9],[-58.0,1.6],[-56.5,2.0],[-55.5,2.0],[-54.6,2.3],
 [-53.8,2.3],[-52.9,3.2],[-52.0,4.0],[-51.6,4.4],
 [-50.7,2.1],[-50.0,0.9],[-50.2,-0.2],[-49.3,-0.5],[-48.5,-0.8],[-47.4,-0.6],[-46.0,-1.0],[-44.7,-1.8],[-44.3,-2.5],
 [-43.0,-2.5],[-41.8,-2.8],[-40.0,-2.9],[-38.5,-3.7],[-37.0,-4.4],[-35.2,-5.15],[-35.2,-5.8],[-34.8,-7.1],[-34.9,-8.1],
 [-35.7,-9.7],[-37.0,-11.0],[-38.5,-13.0],[-39.0,-14.8],[-39.0,-16.4],[-39.2,-17.9],[-40.3,-20.3],[-41.0,-22.0],[-42.0,-23.0],
 [-43.2,-22.95],[-44.3,-23.0],[-46.3,-24.0],[-47.9,-25.0],[-48.5,-25.5],[-48.5,-27.6],[-48.8,-28.5],[-49.7,-29.35],[-51.0,-31.0],
 [-52.1,-32.0],[-53.4,-33.75],
 [-53.4,-32.6],[-54.2,-31.9],[-55.5,-30.9],[-56.4,-30.4],[-57.6,-30.2],[-56.0,-28.7],[-54.2,-27.3],[-53.6,-26.25],[-53.8,-25.7],
 [-54.6,-25.6],[-54.4,-24.8],[-54.3,-24.05],[-55.0,-23.9],[-55.7,-22.5],[-57.9,-22.1],[-57.9,-21.7],[-57.8,-20.5],[-57.65,-19.0],
 [-58.1,-17.9],[-58.4,-16.3],[-60.2,-16.3],[-60.5,-15.0],[-60.1,-13.5],[-61.9,-13.5],[-63.9,-12.1],[-65.35,-10.4],[-67.5,-10.5],
 [-68.75,-11.0],[-70.5,-9.45],[-72.0,-9.5],[-73.8,-7.5],[-73.3,-6.5],[-72.5,-5.5],[-71.5,-4.6],[-69.95,-4.2],
 [-69.4,-1.2],[-70.05,-0.2],[-69.5,0.7],[-69.8,1.1],[-68.5,1.8],[-67.3,2.0],[-66.9,1.25],[-66.0,0.9],[-65.0,1.3],[-64.0,2.0],
 [-63.4,2.2],[-62.8,3.6],[-61.4,4.3],[-60.7,5.2]
 ];
ind.rotulos=(pontos,k)=>{
 // Nomes ao lado dos círculos, sem se sobrepor: de cima para baixo, desce o nome que bateria no anterior.
 const colocados=[];let out="";
 [...pontos].sort((a,b)=>a.y-b.y).forEach(({r,x,y,raio})=>{
  const lx=x+raio+3*k;let ly=y+3.5*k;
  while(colocados.some(c=>Math.abs(c.ly-ly)<11*k&&Math.abs(c.lx-lx)<80*k))ly+=11*k;
  colocados.push({lx,ly});
  out+='<text x="'+lx.toFixed(1)+'" y="'+ly.toFixed(1)+'" class="mapa-rotulo" font-size="'+(10*k).toFixed(2)+'">'+ind.esc(r.regiao.length>20?r.regiao.slice(0,19)+"…":r.regiao)+'</text>';
 });
 return out;
};
ind.detalhe=(comPosicao,max)=>{
 // Quando todas as regiões estão juntas, o círculo no mapa do Brasil vira uma mancha: este quadro mostra só a área delas.
 const lats=comPosicao.map(r=>r.latitude),lons=comPosicao.map(r=>r.longitude),W=400,H=250,mx=46,my=18;
 const latMin=Math.min(...lats),latMax=Math.max(...lats),lonMin=Math.min(...lons),lonMax=Math.max(...lons);
 const vaoLat=Math.max(latMax-latMin,0.4)+0.5,vaoLon=Math.max(lonMax-lonMin,0.4)+0.5;
 const esc=Math.min((W-2*mx)/(vaoLon*0.966),(H-2*my)/vaoLat);
 const cx=(lonMin+lonMax)/2,cy=(latMin+latMax)/2;
 const X=lon=>W/2+(lon-cx)*0.966*esc,Y=lat=>H/2-(lat-cy)*esc;
 const passo=vaoLat>3?1:0.5;
 let out='<svg class="chart detalhe" role="img" aria-label="Detalhe ampliado das regiões atendidas, por latitude e longitude" viewBox="0 0 '+W+' '+H+'"><rect x="0.5" y="0.5" width="'+(W-1)+'" height="'+(H-1)+'" class="detalhe-fundo"/>';
 for(let lat=Math.ceil((cy-vaoLat/2)/passo)*passo;lat<=cy+vaoLat/2;lat+=passo)out+='<line x1="'+mx+'" x2="'+(W-8)+'" y1="'+Y(lat).toFixed(1)+'" y2="'+Y(lat).toFixed(1)+'" class="grade"/><text x="'+(mx-5)+'" y="'+(Y(lat)+3).toFixed(1)+'" text-anchor="end" class="chart-label">'+ind.num(lat,1)+'°</text>';
 for(let lon=Math.ceil((cx-vaoLon/2)/passo)*passo;lon<=cx+vaoLon/2;lon+=passo)out+='<line y1="'+my+'" y2="'+(H-16)+'" x1="'+X(lon).toFixed(1)+'" x2="'+X(lon).toFixed(1)+'" class="grade"/><text x="'+X(lon).toFixed(1)+'" y="'+(H-4)+'" text-anchor="middle" class="chart-label">'+ind.num(lon,1)+'°</text>';
 const pontos=[...comPosicao].sort((a,b)=>b.kg_entregues-a.kg_entregues).map(r=>({r,x:X(r.longitude),y:Y(r.latitude),raio:5+11*Math.sqrt(r.kg_entregues/max)}));
 pontos.forEach(({r,x,y,raio})=>{out+='<circle cx="'+x.toFixed(1)+'" cy="'+y.toFixed(1)+'" r="'+raio.toFixed(1)+'" class="ponto" fill-opacity="'+(0.3+0.55*r.kg_entregues/max).toFixed(2)+'"><title>'+ind.esc(r.regiao)+' · '+ind.num(r.kg_entregues)+' kg</title></circle>';});
 return out+ind.rotulos(pontos,1)+'</svg>';
};
ind.mapa=(regioes)=>{
 const comPosicao=regioes.filter(r=>r.latitude!=null&&r.longitude!=null&&r.kg_entregues>0),sem=regioes.filter(r=>(r.latitude==null||r.longitude==null)&&r.kg_entregues>0);
 if(!comPosicao.length)return '<p class="chart-empty">Ainda não há entregas concluídas com posição conhecida no mapa.</p>'+(sem.length?'<p class="chart-note">Sem posição: '+sem.map(r=>ind.esc(r.regiao)).join(", ")+'.</p>':"");
 const X=lon=>(lon+74.5)*9.66,Y=lat=>(6-lat)*10,max=Math.max(...comPosicao.map(r=>r.kg_entregues),1);
 const lats=comPosicao.map(r=>r.latitude),lons=comPosicao.map(r=>r.longitude);
 const agrupadas=Math.max(Math.max(...lats)-Math.min(...lats),(Math.max(...lons)-Math.min(...lons))*0.966)<8;
 const contorno="M"+ind.brasil.map(p=>X(p[0]).toFixed(1)+","+Y(p[1]).toFixed(1)).join("L")+"Z";
 let out='<svg class="chart mapa" role="img" aria-label="Mapa do Brasil com o volume entregue por região atendida" viewBox="0 0 400 410"><path d="'+contorno+'" class="brasil"/>';
 const pontos=[...comPosicao].sort((a,b)=>b.kg_entregues-a.kg_entregues).map(r=>({r,x:X(r.longitude),y:Y(r.latitude),raio:4+12*Math.sqrt(r.kg_entregues/max)}));
 pontos.forEach(({r,x,y,raio})=>{
  out+='<circle cx="'+x.toFixed(1)+'" cy="'+y.toFixed(1)+'" r="'+raio.toFixed(1)+'" class="ponto" fill-opacity="'+(0.3+0.55*r.kg_entregues/max).toFixed(2)+'"><title>'+ind.esc(r.regiao)+' · '+ind.num(r.kg_entregues)+' kg · '+ind.num(r.refeicoes,0)+' refeições'+(r.posicao_origem==="cidade"?" (posição: centro da cidade)":"")+'</title></circle>';
 });
 if(!agrupadas)out+=ind.rotulos(pontos,1.6);
 out+='</svg>';
 return out+(agrupadas?'<h3 class="detalhe-titulo">Detalhe ampliado das regiões</h3>'+ind.detalhe(comPosicao,max):"")+'<p class="chart-note">Posição aproximada: coordenadas da ONG ou, na falta, o centro da cidade.'+(sem.length?" Sem posição no mapa: "+sem.map(r=>ind.esc(r.regiao)).join(", ")+".":"")+'</p>';
};
ind.tabelaRegioes=(atendidas)=>atendidas.length?'<div class="table-wrap mini"><table><thead><tr><th>Região</th><th>ONGs</th><th>Kg entregues</th><th>Refeições</th></tr></thead><tbody>'+atendidas.map(r=>'<tr><td>'+ind.esc(r.regiao)+'</td><td>'+r.ongs+'</td><td>'+ind.num(r.kg_entregues)+'</td><td>'+ind.num(r.refeicoes,0)+'</td></tr>').join("")+'</tbody></table></div>':"";
ind.rosca=(mitigadas,analise,criticas)=>{
 const total=mitigadas+analise+criticas,C=2*Math.PI*40;
 const seg=(v,off,cls)=>v?'<circle cx="60" cy="60" r="40" class="donut '+cls+'" stroke-dasharray="'+(C*v/total).toFixed(2)+' '+C.toFixed(2)+'" stroke-dashoffset="'+(-C*off/total).toFixed(2)+'"/>':"";
 return '<svg class="donut-chart" role="img" aria-label="Vulnerabilidades: '+mitigadas+' mitigadas, '+analise+' em análise, '+criticas+' críticas abertas" viewBox="0 0 120 120">'+(total?seg(mitigadas,0,"ok")+seg(analise,mitigadas,"warn")+seg(criticas,mitigadas+analise,"bad"):'<circle cx="60" cy="60" r="40" class="donut empty"/>')+'<text x="60" y="66" text-anchor="middle" class="donut-total">'+total+'</text></svg>';
};
ind.render=(d,atualizadoEm)=>{
 if(!d)return '<div class="empty"><h2>Indicadores indisponíveis</h2><p>Não foi possível carregar os dados. Use Atualizar para tentar novamente.</p></div>';
 const i=d.impacto,m=d.matches,a=d.ia,s=d.seguranca,v=s.vulnerabilidades,e=m.entregas||{concluidas:0,confirmadas_pela_ong:0,confirmadas_pelo_gestor:0};
 const tempo=m.tempo_medio_horas==null?"—":(m.tempo_medio_horas<48?ind.num(m.tempo_medio_horas,1)+" h":ind.num(m.tempo_medio_horas/24,1)+" dias");
 const regioes=i.por_regiao,atendidas=i.por_regiao_atendida||[];
 const confirmadas=e.concluidas?ind.pct(e.confirmadas_pela_ong/e.concluidas)+" confirmadas pela ONG":"Doações concluídas";
 return '<p class="live"><span class="pulse" aria-hidden="true"></span>Ao vivo · atualizado às '+ind.esc(atualizadoEm)+' · atualiza a cada 15 s</p>'+
 '<section class="stats stats-6">'+
  ind.tile("Alimentos salvos",ind.num(i.kg_salvos)+" kg",confirmadas)+
  ind.tile("Refeições geradas",ind.num(i.refeicoes_estimadas,0),"Estimativa: "+ind.num(i.kg_por_refeicao)+" kg por refeição")+
  ind.tile("Acurácia da IA",ind.pct(a.acuracia),"Baseline "+ind.pct(a.acuracia_baseline)+" · dados "+a.origem_dados+"s")+
  ind.tile("Tempo médio de match",tempo,m.amostra_tempo+" matches medidos")+
  ind.tile("Vulnerabilidades mitigadas",v.mitigadas,v.criticas_altas_abertas+" HIGH/CRITICAL abertas")+
  ind.tile("Lotes com validade crítica",i.lotes_validade_critica.lotes,ind.num(i.lotes_validade_critica.kg)+" kg em até "+i.lotes_validade_critica.dias+" dias")+
 '</section>'+
 '<section class="grid-2"><div class="panel pad"><h2>Refeições entregues por região atendida</h2><p>Região da ONG que recebeu o alimento. '+ind.esc(i.nota)+'</p>'+ind.barras(atendidas.map(r=>({nome:r.regiao,valor:r.refeicoes})),"Refeições entregues por região atendida")+ind.tabelaRegioes(atendidas)+'</div>'+
 '<div class="panel pad"><h2>Mapa das regiões atendidas</h2><p>Cada círculo é uma região onde ONGs receberam alimento; quanto maior e mais escuro, maior o volume entregue.</p>'+ind.mapa(atendidas)+'</div></section>'+
 '<section class="grid-2"><div class="panel pad"><h2>Mapa de calor: oferta por região do doador</h2><p>Kg por região de origem e status da doação; quanto mais escuro, maior o volume.</p>'+ind.mapaCalor(regioes)+'</div>'+
 '<div class="panel pad"><h2>IA: predição de descarte</h2><p>Métricas no conjunto de teste ('+a.amostras_teste+' lotes). '+ind.esc(a.limitacoes)+'</p>'+
  ind.barras([{nome:"Acurácia",valor:a.acuracia*100},{nome:"Baseline",valor:a.acuracia_baseline*100},{nome:"F1 macro",valor:a.f1_macro*100},{nome:"Recall alto risco",valor:a.recall_alto_risco*100}],"Métricas da IA em porcentagem")+
  '<p>Latência: '+ind.num(a.latencia_ms,3)+' ms por lote · modelo '+ind.esc(a.modelo)+'</p></div></section>'+
 '<section class="grid-2"><div class="panel pad"><h2>Entregas e tempo de resposta</h2><p>'+ind.esc(m.nota)+'</p>'+
  ind.barras([{nome:"Concluídas",valor:e.concluidas},{nome:"Pela ONG",valor:e.confirmadas_pela_ong},{nome:"Pelo gestor",valor:e.confirmadas_pelo_gestor}],"Entregas concluídas e quem as confirmou")+
  '<p>Tempo médio até o match: <strong>'+tempo+'</strong> ('+m.amostra_tempo+' matches medidos). Matches por situação: '+Object.entries(m.por_status).map(([k,n])=>ind.esc(k)+" "+n).join(" · ")+'.</p></div>'+
 '<div class="panel pad"><h2>Status de segurança (SAST)</h2><div class="sec-row">'+ind.rosca(v.mitigadas,v.em_analise,v.criticas_altas_abertas)+
  '<ul class="legend"><li><i class="dot ok"></i>Mitigadas: '+v.mitigadas+'</li><li><i class="dot warn"></i>Em análise: '+v.em_analise+'</li><li><i class="dot bad"></i>Críticas/altas abertas: '+v.criticas_altas_abertas+'</li></ul></div>'+
  '<ul class="detail">'+v.detalhe.map(t=>'<li>'+ind.esc(t)+'</li>').join("")+'</ul></div></section>'+
 '<section class="panel"><div class="panel-heading"><div><h2>Security Gates do pipeline</h2><p>'+ind.esc(s.observacao)+'</p></div></div><div class="table-wrap"><table><thead><tr><th>Gate</th><th>Tipo</th><th>Bloqueia</th><th>Última execução local</th></tr></thead><tbody>'+
  s.gates.map(g=>'<tr><td>'+ind.esc(g.nome)+'</td><td>'+ind.esc(g.tipo)+'</td><td>'+ind.esc(g.bloqueia)+'</td><td><span class="badge concluido">'+ind.esc(g.ultima_execucao_local)+'</span></td></tr>').join("")+'</tbody></table></div></section>';
};
