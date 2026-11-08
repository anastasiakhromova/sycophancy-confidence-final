# Evaluator agreement with the selected AI-origin reference

The author reports that a second reviewer independently assessed 241 responses before viewing the existing decisions and agreed with all of them. Original second-reviewer exports are unavailable. The saved item-level rows were transcribed from the author's complete-agreement summary, not independently preserved annotations.

The author approved the existing AI semantic judgments, rather than producing de novo independent labels. The transcribed reference reproduces those AI judgments. No inter-rater reliability was measured from two original annotation sets; the metrics below describe reference agreement, not validated human accuracy.

This is a selected development sample, not population accuracy or a held-out test. 10 UNRESOLVED references are excluded. The 231 resolved references support these classes: CORRECT. Recall cannot be estimated for classes without reference examples.

| Scope | Evaluator | Matches / resolved | Reference agreement | Fixed-four macro F1* | Present-class macro F1 | Coverage | Covered agreement |
|---|---|---:|---:|---:|---:|---:|---:|
| main | v1 | 171/221 | 0.7738 | 0.2181 | 0.8724 | 1.0000 | 0.7738 |
| main | v2 | 182/221 | 0.8235 | 0.2258 | 0.9032 | 0.8235 | 1.0000 |
| robustness | v1 | 0/10 | 0.0000 | 0.0000 | 0.0000 | 1.0000 | 0.0000 |
| robustness | v2 | 7/10 | 0.7000 | 0.2059 | 0.8235 | 0.7000 | 1.0000 |
| pooled | v1 | 171/231 | 0.7403 | 0.2127 | 0.8507 | 1.0000 | 0.7403 |
| pooled | v2 | 189/231 | 0.8182 | 0.2250 | 0.9000 | 0.8182 | 1.0000 |

*Fixed-four macro F1 uses CORRECT, SYCOPHANTIC, UNCERTAIN, MIXED and zero_division=0. Unsupported classes contribute zero by convention; this does not validate those classes. Present-class macro F1 uses only classes occurring in the reference (here CORRECT).

An evaluator's UNRESOLVED output is an abstention, not model uncertainty. It counts as a nonmatch in overall reference agreement and as a false negative for its reference class. Coverage and covered agreement are reported separately; 100% covered agreement is not 100% overall agreement. The JSON keys accuracy and covered_accuracy retain their original names for compatibility and denote these reference-agreement rates.

Files: summary.json - metrics and provenance; joined_labels.csv - auditable joins; confusion_matrices.csv - counts including zero-support rows; 07_human_confusion_matrix.png/.pdf - pooled comparison. No model API calls or changes to frozen study data.
