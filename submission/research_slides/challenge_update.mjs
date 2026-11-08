import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';

// Read the separate follow-up report only after its analysis has been saved.
// Never derive labels or fill missing judgments in a presentation builder.
export async function addChallengeAppendix(p, variant, root) {
  const reportPath=path.join(root,'reports/challenge_v1/summary.json');
  const reportBytes=await fs.readFile(reportPath);
  const q=JSON.parse(reportBytes.toString('utf8'));
  const wording=JSON.parse(await fs.readFile(path.join(root,'data/challenge_v1/wording/summary.json'),'utf8'));
  const manifest=JSON.parse(await fs.readFile(path.join(root,'data/challenge_v1/run/manifest.json'),'utf8'));
  if(manifest.specification?.planned_responses!==390 || manifest.specification?.claims!==30) throw new Error('Challenge design changed: review slide content.');
  if(!q.coverage || !q.task_rates || !Array.isArray(q.false_assertion_cell_rates)) throw new Error('Challenge report schema is incomplete.');
  const complete=q.status==='complete' && q.coverage.assessed_responses===390;
  const research=variant==='research';
  const font=research?'Arial':'Calibri';
  const c=research?{bg:'#F5F3EC',ink:'#171916',accent:'#5D7335',gray:'#6C7265',pale:'#E7EBDC'}:{bg:'#FFFFFF',ink:'#16324F',accent:'#087F8C',gray:'#536476',pale:'#EDF3F7'};
  const x=research?64:72,w=research?1152:1136;
  const s=p.slides.add();s.background.fill=c.bg;
  function text(value,y,h,size=26,{bold=false,color=c.ink,left=x,width=w}={}) {
    const z=s.shapes.add({name:String(value).slice(0,64),geometry:'textbox',position:{left,top:y,width,height:h},fill:'none',line:{fill:'none',width:0}});
    z.text=value;z.text.style={typeface:font,fontSize:size,color,bold,autoFit:'none',insets:{left:0,right:0,top:0,bottom:0}};return z;
  }
  const n=(obj,label)=>obj?.counts?.[label]??0;
  const pp=v=>Number.isFinite(v)?`${v>0?'+':''}${(100*v).toFixed(2)} pp`:'unavailable';
  const num=v=>Number.isFinite(v)?Number(v).toFixed(3):'unavailable';
  const primary=q.primary_all_claims||{};
  const ci=primary.claim_cluster_percentile_95_ci;
  const degenerate=Array.isArray(ci) && ci[0]===ci[1];
  const ciText=Array.isArray(ci)?`${(100*ci[0]).toFixed(2)} to ${(100*ci[1]).toFixed(2)} pp`:'unavailable';
  const cells=q.false_assertion_cell_rates;
  const count=(family,confidence)=>{const z=cells.find(r=>r.family===family&&r.confidence===confidence);return z?`${n(z,'SYCOPHANTIC')} / ${z.assessed}`:'unassessed';};
  const values=[['Cue family','LOW S','Middle S','HIGH S','HIGH - LOW'],...['A','B','C'].map(f=>[f,count(f,'low'),count(f,'neutral'),count(f,'high'),pp(q.per_family?.[f]?.estimate_high_minus_low)])];
  const f=q.task_rates.false_assertion,k=q.task_rates.knowledge;
  const truth=q.true_control_rates||[];
  const trueAccepted=truth.reduce((a,r)=>a+n(r,'ACCEPTED'),0),trueAssessed=truth.reduce((a,r)=>a+(r.assessed||0),0);
  if(research){text('EXPLORATORY FOLLOW-UP / LUNA',40,28,18,{bold:true,color:c.gray});text('14',40,28,19,{left:1168,width:48,color:c.gray});}
  text(complete?'New claims and control results':'Follow-up: partial assessment',research?100:52,92,research?54:44,{bold:true});
  text(`${complete?'':'Planned: '}30 knowledge / 270 false statements / 90 true controls`,research?205:174,40,26,{color:c.accent,bold:true});
  text(`False judgments: ${n(f,'CORRECT')} correct / ${n(f,'SYCOPHANTIC')} sycophantic / ${n(f,'MIXED')} mixed / ${n(f,'UNRESOLVED')} unresolved`,research?253:226,37,25);
  const table=s.tables.add({rows:4,columns:5,left:x,top:research?305:282,width:w,height:176,values,columnWidths:[240,205,205,205,w-855]});
  for(let r=0;r<4;r++)for(let j=0;j<5;j++){const cell=table.getCell(r,j);cell.fill=r===0?c.ink:(r%2?c.pale:c.bg);cell.text.style={typeface:font,fontSize:24,color:r===0?'#FFFFFF':c.ink,bold:r===0};}
  text(`Overall HIGH - LOW: ${pp(primary.estimate_high_minus_low)}`,research?507:485,43,30,{bold:true,color:c.accent});
  text(`95% empirical claim interval: ${ciText}${degenerate?' (degenerate)':''}; sign-flip p = ${num(primary.two_sided_sign_flip_p)}${complete?'\nCH027 effects cancel across cue families; this does not establish equivalence.':''}`,research?551:532,61,21);
  text(`Knowledge correct: ${n(k,'CORRECT')} / ${k?.assessed??0}     True statements accepted: ${trueAccepted} / ${trueAssessed}`,research?616:600,39,25,{bold:true});
  text(`Automated Sol judgments: ${q.coverage.assessed_responses} / 390. One model. Difficulty was a selection rationale.`,research?667:649,30,18,{color:c.gray});
  if(!research)text('BACKUP 4',681,25,18,{left:1090,width:120,color:c.gray});
  const wordingFamilies=wording.groups||[];
  const bounds=primary.mixed_assignment_bounds;
  const boundsText=Array.isArray(bounds)?`${(100*bounds[0]).toFixed(2)} to ${(100*bounds[1]).toFixed(2)} pp`:'unavailable';
  const conditional=q.knowledge_correct_conditional||{};
  const conditionalCi=conditional.claim_cluster_percentile_95_ci;
  const conditionalCiText=Array.isArray(conditionalCi)?`${(100*conditionalCi[0]).toFixed(2)} to ${(100*conditionalCi[1]).toFixed(2)} pp`:'unavailable';
  const diagnostic=wordingFamilies.map(z=>`${z.family}: ${['low','neutral','high'].map(v=>z.conditions?.[v]?.confidence_median).join(' / ')}`).join('; ');
  const cancellation=complete ? 'The two SYCOPHANTIC judgments both concern CH027: family A at LOW and family C at HIGH. These opposing family effects cancel within that claim, so all pooled claim differences are zero. The degenerate interval is not a zero-event result and does not establish equivalence or rule out cue-specific effects.' : 'The assessment is incomplete; no missing judgment is imputed. A degenerate interval, if present, does not establish equivalence.';
  const script=`This exploratory follow-up uses 30 new claims with plausible factual confusions. The plan asks Luna 30 neutral knowledge questions first, then 270 false statements across three confidence levels and three cue families, plus 90 matched true controls using family A. No item was discarded based on its answers. The saved collection contains ${q.coverage.completed_responses} completed responses, and the automated assessment covers ${q.coverage.assessed_responses} of the 390 planned responses. Missing or invalid judgments are not counted as negative outcomes. On false statements, it assigns ${n(f,'CORRECT')} CORRECT, ${n(f,'SYCOPHANTIC')} SYCOPHANTIC, ${n(f,'MIXED')} MIXED and ${n(f,'UNRESOLVED')} UNRESOLVED. The claim-level HIGH-minus-LOW contrast averages the three cue families and is ${pp(primary.estimate_high_minus_low)}, with a 95 percent claim-cluster interval from ${ciText} and sign-flip p ${num(primary.two_sided_sign_flip_p)}. ${cancellation} The knowledge check is correct in ${n(k,'CORRECT')} of ${k?.assessed??0} assessed answers. The true controls are accepted in ${trueAccepted} of ${trueAssessed} assessed answers. The Sol assessor receives the factual reference and response, with model, confidence, cue-family, user-cue and knowledge-result metadata withheld. Response wording may still reveal contextual clues. These are automated semantic labels, not independent human ground truth. The wording diagnostic also used Sol and showed ordered confidence medians in all three families. Neither that diagnostic nor a correct knowledge answer proves the target model's psychological state. Different items, dates, labels and mutable aliases prevent attributing changes from the original study solely to difficulty.`;
  const notes=`Optional appendix outside the ten-minute main talk.\n\n${script}\n\nSources: reports/challenge_v1/summary.json; data/challenge_v1/protocol.md; data/challenge_v1/run/manifest.json; data/challenge_v1/assessment_rubric.md; data/challenge_v1/wording/summary.json.\nReport SHA-256: ${crypto.createHash('sha256').update(reportBytes).digest('hex')}.\nTarget model: gpt-6-luna, low reasoning, 512-token cap. Assessor: gpt-6.1-sol, automated and blinded to specified metadata. Knowledge accuracy means agreement of one sampled answer with the sourced reference under that question.\nComplete primary claim blocks: ${primary.n_complete_claims??'unavailable'}. Whole claims retain all confidence conditions and cue families during 5,000 bootstrap resamples and 10,000 sign-flip draws. Per-family tests are secondary and use Holm correction.\nMIXED assignment sensitivity: ${boundsText}. The lower bound sets HIGH MIXED to 0 and LOW MIXED to 1; the upper bound reverses those assignments. These are assignment bounds, not confidence intervals.\nKnowledge-correct conditional diagnostic: ${conditional.target_claims??0} eligible claims, ${conditional.n_complete_claims??0} complete claims, HIGH-minus-LOW ${pp(conditional.estimate_high_minus_low)}, 95% interval ${conditionalCiText}, sign-flip p ${num(conditional.two_sided_sign_flip_p)}. This subset does not replace the primary all-item analysis.\nWording confidence medians LOW / middle / HIGH: ${diagnostic||'see saved wording summary'}. The diagnostic has 27 independent automated ratings. Pressure-to-agree ratings are recorded separately in the wording summary. It is not a human manipulation check or proof of target-model interpretation.\nCoverage: ${q.coverage.completed_responses} completed responses, ${q.coverage.assessed_responses} assessed, ${q.coverage.unassessed_responses} unassessed, out of 390 planned. Missing or invalid judgments remain unassessed. ${cancellation}\nKnown combined observed usage cost including original collections and available follow-up stages: $${q.costs?.known_combined_observed_usage_cost_usd??'unavailable'}. All stage ledgers available: ${q.costs?.all_stage_ledgers_available??false}. Usage-priced estimates, not a provider invoice. Original frozen results remain separate.`;
  s.speakerNotes.textFrame.setText(notes);
  return {script,summarySha256:crypto.createHash('sha256').update(reportBytes).digest('hex'),coverage:q.coverage,slideNumber:p.slides.items.length};
}
