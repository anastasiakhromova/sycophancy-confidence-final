import fs from 'node:fs/promises';
import path from 'node:path';

// Shared by both builders and by focused edits of existing native slide objects.
// The selected development sample is never presented as a population benchmark.
export const reviewerMethod = 'The author approved existing AI semantic judgments and reported that a second reviewer independently assessed all 241 responses before viewing the labels, with complete agreement. This independence and agreement were not independently verified. The stored reference labels reuse the AI judgments on the basis of the author\'s report. No measured inter-rater reliability is established. An original item-by-item second-review export is unavailable. The sample was selected during evaluator development, so these results do not estimate population accuracy or held-out generalization. Ten UNRESOLVED references are excluded from classification metrics. All 231 determinate references are CORRECT, so sycophancy recall and balanced multiclass quality remain unidentified.';

export const researchScripts = {
  4: `The original study did not collect neutral knowledge answers. A separate exploratory follow-up now uses 30 new claims. Luna answers a neutral question for each item before the confidence experiment. The diagram uses Manitoulin Island: Lake Huron is the sourced reference, not an invented model response. The follow-up then collects 270 false assertions across three confidence levels and three cue families, plus 90 matched true controls using family A. All items remain in the primary analysis, including any failed knowledge answers. A correct sampled answer supports knowledge availability in that prompt context; it does not prove a fixed internal state. Appendix 14 reports the separate results.`,
  6: `The completed pipeline produces three confidence versions of every claim and sends them to three model identifiers, yielding 1,350 main responses. The pilot adds 150 responses. The repeatability collection adds 450 responses from 50 claims, three confidence conditions, and three Luna repetitions. That gives 1,950 responses in total. Raw responses and frozen labels stay intact. The later semantic review covers 241 selected answers. The author approved existing AI judgments and reported an independent second review with complete agreement. Original reviewer exports are unavailable, so independence and agreement remain unverified. The saved reference reuses the AI judgments. The original experiment lacks knowledge controls. The separate 30-item follow-up and its controls appear in appendix 14.`,
  11: `The author approved the AI judgments and reported complete second-reviewer agreement on 241 responses. Original exports are unavailable, so this is reported provenance, not measured inter-rater reliability. Of these, 231 are CORRECT and ten remain unresolved. We exclude those ten from classification metrics. Against the 231 determinate references, the original evaluator matches 171, giving 74.0 percent reference agreement. Exploratory version two matches 189, giving 81.8 percent reference agreement. It abstains on the other 42. Its 100 percent reference agreement on covered cases therefore applies only to those 189 answers. F1 for the supported CORRECT class rises from 0.851 to 0.900. All determinate references belong to that class, so the sample cannot validate sycophancy detection. It also overlaps evaluator development. The saved reference reuses AI judgments based on the author's report, rather than original reviewer exports.`,
  12: `The study finds no convincing confidence effect under this specific design. It also does not establish the absence of sycophancy. The AI semantic comparison identifies missed corrections in the original evaluator. Exploratory version two improves agreement on this selected sample while abstaining on difficult answers. That does not yet validate its sycophancy recall or generalization. The separate follow-up adds new claims, knowledge questions, true controls and three cue families. Its results appear in appendix 14. Fresh independent human assessment and broader model coverage remain necessary. The contribution here is the preserved paired experiment and a reproducible measurement analysis. AI assisted with analysis and drafting. The semantic reference originated from AI judgments. The author approved them; independent human validation remains unverified. Thank you.`
};
export const alternateScripts = {
  7: `The semantic review covers 225 selected main responses and 16 robustness responses. The author approved existing AI judgments and reported independent second-reviewer agreement on all 241. Original reviewer exports are unavailable, so the independence and agreement are unverified. The saved reference reuses the AI judgments. It contains 231 CORRECT judgments and ten unresolved cases. We exclude the ten from classification metrics. The original evaluator matches 171 of 231 determinate references, or 74.0 percent. Exploratory version two matches 189 references, or 81.8 percent, and abstains on 42. Its covered reference agreement is 100 percent on only those 189 answers. CORRECT-class F1 rises from 0.851 to 0.900. This is a selected development sample, with no positive sycophancy references. It cannot estimate population accuracy or sycophancy recall. Primary labels stay unchanged.`,
  8: `Several limits keep the conclusion narrow. First, the review reference contains only CORRECT and unresolved judgments. It cannot test sycophancy recall. The author reports that the second reviewer initially saw no labels and agreed on every item. Original exports are unavailable; independence and inter-rater reliability cannot be verified. The same selected examples informed evaluator development, so this is not a fresh held-out test. Second, the curated factual corpus produces a correction ceiling. The original same-provider comparison and single cue family limit generalization. The separate follow-up adds three cue families and knowledge controls for Luna only. The study does not test prolonged disagreement or authority pressure. Third, the pilot informed corpus expansion, so the main study is exploratory. Finally, repeated claims remain dependent. The paired analysis and claim bootstrap account for that structure.`,
  9: `The main result is zero automatically detected sycophancy in 1,350 responses under this specific design. Small correction differences do not establish a consistent confidence effect. The AI semantic comparison identifies a measurement problem: the original evaluator misses factual repairs. Exploratory version two improves selected-sample agreement while abstaining on difficult cases. The separate follow-up adds 30 new candidate claims, knowledge questions, true controls and three confidence cue families. Appendix 14 reports its outcomes separately. Difficulty is a design rationale, and the new semantic assessor is automated. Fresh independent human assessment and broader model coverage remain future work. This experiment documents a narrow observed outcome and the limits of its measurement. It does not establish equivalence between confidence conditions. Thank you.`
};

export async function applyValidationUpdate(p, variant, projectRoot) {
  const summaryPath=path.join(projectRoot,'reports/reviewer_validation/summary.json');
  const summary=JSON.parse(await fs.readFile(summaryPath,'utf8'));
  // Metrics are independently recomputed by scripts/build_reviewer_validation.py.
  // Do not silently display the stale constants if a later study changes coverage.
  const pooled=summary.scopes?.pooled;
  if(pooled?.n_reviewed!==241 || pooled.n_determinate!==231 || pooled.n_reference_unresolved!==10 || pooled.v1.correct!==171 || pooled.v2.correct!==189 || pooled.v2.n_abstained!==42) throw new Error('Reviewer-validation results changed. Update slide content.');
  const records=(await p.inspect({select:'$.slides[*]',include:['id','index','elements.id','elements.kind','elements.text','notes.text']})).records;
  const shape = (n,oldText,newText) => {
    const record=records[n-1].elements.find(e=>e.kind!=='table' && e.text===oldText);
    if(record) p.resolve(record.id).text=newText;
    else if(!records[n-1].elements.some(e=>e.text===newText)) throw new Error(`Missing text on ${variant} slide ${n}: ${oldText}`);
  };
  if(variant==='research') {
    shape(7,'POST-HOC AI DIAGNOSTIC\n241 selected responses','SEMANTIC REVIEW\n241 selected responses');
    shape(12,'The evaluator can change\nthe apparent story','AI-reference comparison\non 241 selected answers');
    const table=p.resolve(records[11].elements.find(e=>e.kind==='table').id);
    const values=[['Selected reference','Result'],['v1 matches: 171 / 231','74.0%'],['v2 matches: 189 / 231','81.8%'],['v2 abstentions: 42 / 231','18.2%'],['v2 covered: 189 / 189','100%'],['Reference unresolved','10 / 241']];
    for(let r=0;r<values.length;r++)for(let c=0;c<2;c++)table.cells.set(r,c,values[r][c]);
    shape(12,'50 / 54','241 / 241');
    shape(12,'main non-C labels judged\nCORRECT in the AI review','second-review agreement reported\nby author; exports unavailable');
    shape(12,'5 S responses / 1 claim','F1(C): 0.851 / 0.900');
    shape(12,'Repeated date-line answers mix\nagreement with factual repair.','v1 / v2, only supported class\nNo positive sycophancy reference');
    shape(12,'450 main model/claim triplets. AI audit: 231 C / 10 unresolved out of 241 selected. No human validation.','Selected development sample. Ten unresolved references excluded. No population accuracy claim.');
    shape(13,'Next study','Separate follow-up');
    shape(13,'Knowledge control, multiple cue phrasings,\nand independent semantic annotation','New claims, knowledge and truth controls,\nthree cue families. Results in appendix 14.');
    shape(13,'AI assisted with analysis and drafting. Reference labels originated from AI judgments.','AI assisted with analysis and drafting. Reference labels originated from AI judgments.');
  } else {
    shape(8,'AI diagnostic review of 241 responses','AI-reference comparison on 241 selected answers');
    const table=p.resolve(records[7].elements.find(e=>e.kind==='table').id);
    const values=[['Evaluator view','Matches / total','Agreement','F1(C)'],['Frozen v1','171 / 231','74.0%','0.851'],['v2, all determinate','189 / 231','81.8%','0.900'],['v2, covered only','189 / 189','100%','-']];
    for(let r=0;r<values.length;r++)for(let c=0;c<4;c++)table.cells.set(r,c,values[r][c]);
    shape(8,'50 of the 54 main UNCERTAIN labels contain\ncorrections according to the AI reviewers','Author reports 241 / 241 second-review agreement\nNo original exports. V2 abstains on 42 / 231.');
    shape(8,'AI judgments, selected subsets, no human validation. Primary labels stay unchanged.','231 CORRECT references. Exclude 10 unresolved. Selected development sample.');
    shape(9,'No human validation. Lexical rules miss factual repair\nand struggle with mixed endorsement and correction.','AI reference approved by author. Second review unverified.\nNo original exports or measured inter-rater reliability.');
    shape(10,'Conclusion and next study','Conclusion and separate follow-up');
    shape(10,'Next: human adjudication and a mixed-stance category, then\nknowledge controls, harder claims, and broader model coverage.','Follow-up: 30 new claims, knowledge and truth controls,\nthree cue families. Separate results appear in appendix 14.');
    shape(9,'No independent knowledge control or capability test.\nThe main plan follows the pilot. Repeated claims remain paired.','Original run: no knowledge control or capability test.\nFollow-up: one model, automated semantic assessment.');
    shape(13,'AI assisted with analysis and drafting.\nSemantic reference: AI judgments approved by the author.','AI assisted with analysis and drafting.\nSemantic reference: AI judgments approved by the author.');
  }
  for(const [i,record] of records.entries()) {
    let text=record.notes?.text||'';
    const scripts=variant==='research'?researchScripts:alternateScripts;
    if(scripts[i]) text=text.replace(/(^[^\n]+\n\n)[\s\S]*?(\n\n(?:Source records|Sources and interpretation))/,`$1${scripts[i]}$2`);
    text=text.replaceAll('No human validation.','Independent human validation is not established.')
      .replaceAll('Human validation remains absent.','Independent human validation is not established.')
      .replaceAll('independent human validation remains absent.','independent human validation is not established.')
      .replaceAll('No human validation is claimed.','Independent human validation is not established.')
      .replaceAll('without human validation.','without independently verified human validation.')
      .replaceAll('Post-hoc AI diagnostics, not independent human validation or population accuracy.','AI diagnostic sample approved by the author. Second-review agreement is author-reported and unverified. It does not estimate population accuracy.')
      .replaceAll('This is an AI diagnostic review, not independent human validation.','The reference originated from AI judgments approved by the author. Second-review independence and agreement are author-reported and unverified.');
    if((variant==='research' && [6,11,12].includes(i)) || (variant!=='research' && [7,8,9,12].includes(i))) text+=`\n\nAI-reference comparison and reported review provenance: reports/reviewer_validation/summary.json.\n${reviewerMethod}\nMetric details: v1 171/231, v2 189/231. V2 abstains on 42/231, counted as nonmatches in overall reference agreement. Covered reference agreement is 189/189. F1 over the supported CORRECT class is 0.8507462687 and 0.9000000000. Fixed four-class zero-division macro F1 is 0.2126865672 and 0.2250000000, a convention dominated by absent classes. It does not validate multiclass performance.`;
    p.slides.items[i].speakerNotes.textFrame.setText(text);
  }
}
