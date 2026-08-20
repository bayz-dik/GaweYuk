const fmt = n => n ? new Intl.NumberFormat('id-ID').format(n) : 'Unknown';
const decisionOrder = {APPLY:0, REVIEW:1, SKIP:2, BLOCK:3};

function card(j){
  const evidence = [...j.positive_evidence.slice(0,3), ...j.negative_evidence.slice(0,2)];
  return `<article class="job ${j.decision.toLowerCase()}">
    <div class="job-head"><div><span class="decision">${j.decision}</span><h2>${j.title}</h2><p>${j.company} · ${j.location}</p></div><div class="one-score">${Math.round((j.match_score+j.trust_score)/2)}<small>ONE SCORE</small></div></div>
    <div class="meters"><div><span>Profile match</span><strong>${j.match_score}</strong></div><div><span>Trust</span><strong>${j.trust_score}</strong></div><div><span>Salary</span><strong>${fmt(j.salary_min)}–${fmt(j.salary_max)}</strong></div></div>
    <div class="sources">${j.sources.map(s=>`<span>${s.official?'✓ ':''}${s.name}</span>`).join('')}</div>
    <ul>${evidence.map(e=>`<li>${e}</li>`).join('')}</ul>
    <p class="reason">${j.decision_reasons[0]||''}</p>
  </article>`;
}

async function load(){
  const jobs = await fetch('/api/jobs').then(r=>r.json());
  jobs.sort((a,b)=>decisionOrder[a.decision]-decisionOrder[b.decision]);
  document.querySelector('#count').textContent = jobs.length;
  const groups = ['APPLY','REVIEW','SKIP','BLOCK'].map(k=>[k,jobs.filter(j=>j.decision===k).length]);
  document.querySelector('#stats').innerHTML = groups.map(([k,v])=>`<div><span>${k}</span><strong>${v}</strong></div>`).join('');
  document.querySelector('#jobs').innerHTML = jobs.map(card).join('');
}
document.querySelector('#refresh').addEventListener('click', load); load();
