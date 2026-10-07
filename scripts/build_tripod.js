// Build the TRIPOD+AI checklist (Table S1) as a Word (.docx):
//  - single full-grid table (0.5 pt borders), five columns: Section/Topic,
//    Item, Development/Evaluation, Checklist item, Reported on page
//  - checklist-item text is the official TRIPOD+AI 2024 wording
// Usage: node scripts/build_tripod.js
const fs = require("fs");
const path = require("path");
const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
  AlignmentType, BorderStyle, WidthType, VerticalAlign, VerticalMergeType,
  Footer, PageNumber,
} = require("docx");

const FONT = "Times New Roman";
const SZ = 20;            // 10 pt
const B = { style: BorderStyle.SINGLE, size: 4, color: "000000" }; // 0.5 pt
const GRID = { top: B, bottom: B, left: B, right: B };
const CONTENT_W = 8640;   // US Letter, 1.25" left/right margins (DXA)
const COLW = [1180, 360, 470, 3340, 3290];
const SP = { before: 20, after: 20, line: 252 };

// checklist content: official TRIPOD+AI 2024 wording + manuscript locations
const SECTIONS = [
  { name: "TITLE", groups: [
    { topic: "Title", rows: [
      { item: "1", de: "D;E",
        text: "Identify the study as developing or evaluating the performance of a multivariable prediction model, the target population, and the outcome to be predicted",
        rep: "Title page (title identifies the work as the development and preliminary cross-database evaluation of a machine-learning model that predicts the Nutri-Score grade [outcome] of packaged foods [target population] from incomplete label data for front-of-pack nutrient profiling)" },
    ]},
  ]},
  { name: "ABSTRACT", groups: [
    { topic: "Abstract", rows: [
      { item: "2", de: "D;E", text: "See TRIPOD+AI for Abstracts checklist",
        rep: "Abstract (structured Background, Objectives, Methods, Results, Conclusions; reports data sources, the withheld-FVL target, the model, the comparator baselines, and grade-recovery metrics)" },
    ]},
  ]},
  { name: "INTRODUCTION", groups: [
    { topic: "Background", rows: [
      { item: "3a", de: "D;E",
        text: "Explain the healthcare context (including whether diagnostic or prognostic) and rationale for developing or evaluating the prediction model, including references to existing models",
        rep: "Introduction, paragraphs 1-5 (diet-related noncommunicable-disease burden, front-of-pack Nutri-Score profiling, the nutrient-profiling-at-scale use case, and why the closed-form 2023 algorithm cannot be evaluated when the FVL percentage is missing; existing Nutri-Score and label-based machine-learning models cited)" },
      { item: "3b", de: "D;E",
        text: "Describe the target population and the intended purpose of the prediction model in the context of the care pathway, including its intended users (eg, healthcare professionals, patients, public)",
        rep: "Introduction, paragraphs 2 and 4 and final paragraph (target population: packaged-food records in food-composition databases; intended purpose: estimate the Nutri-Score grade for records the exact formula cannot score, enabling front-of-pack nutrient profiling at database scale; intended users: researchers, food-policy bodies, and database curators)" },
      { item: "3c", de: "D;E",
        text: "Describe any known health inequalities between sociodemographic groups",
        rep: "Not applicable in the clinical sense; the study analyzes aggregated product-level data with no human participants and predicts a food-label grade, not an individual health outcome. Market and geographic skew of the data is characterized in Results (Composition and bias of the declared-FVL set) and Discussion (Strengths and limitations)" },
    ]},
    { topic: "Objectives", rows: [
      { item: "4", de: "D;E",
        text: "Specify the study objectives, including whether the study describes the development or validation of a prediction model (or both)",
        rep: "Introduction, final paragraph (three aims: develop a label-only model predicting the grade from incomplete inputs; separate manufacturer-declared from text-estimated FVL to prevent leakage; evaluate grade-recovery accuracy, geographic transportability, and external-dataset feasibility). Development plus preliminary evaluation" },
    ]},
  ]},
  { name: "METHODS", groups: [
    { topic: "Data", rows: [
      { item: "5a", de: "D;E",
        text: "Describe the sources of data separately for the development and evaluation datasets (eg, randomised trial, cohort, routine care or registry data), the rationale for using these data, and representativeness of the data",
        rep: "Methods, Study design and data sources (development: Open Food Facts, >4.5 million products, Open Database License bulk Parquet; external-dataset feasibility: USDA FoodData Central Branded Foods, public domain). Representativeness limits addressed in Results (Composition and bias of the declared-FVL set) and Discussion (Strengths and limitations)" },
      { item: "5b", de: "D;E",
        text: "Specify the dates of the collected participant data, including start and end of participant accrual; and, if applicable, end of follow-up",
        rep: "Methods, Study design and data sources (the Open Food Facts snapshot was pinned to a single dated revision; both sources cited with access date 2026-06-11, References 21-22). No participant accrual or follow-up: units are product records, not persons" },
    ]},
    { topic: "Participants", rows: [
      { item: "6a", de: "D;E",
        text: "Specify key elements of the study setting (eg, primary care, secondary care, general population) including the number and location of centres",
        rep: "Methods, Study design and data sources (units are packaged-food product records, not persons; Open Food Facts is a worldwide community-maintained database and FoodData Central compiles US manufacturer label data). No clinical centres" },
      { item: "6b", de: "D;E",
        text: "Describe the eligibility criteria for study participants",
        rep: "Methods, Reference grade and provenance of the target (eligibility required a complete set of Nutri-Score nutrients and a reported or validly zero FVL value; obsolete products, products without a computable grade, and out-of-range nutrient records were excluded; the primary development set was further restricted to manufacturer-declared FVL provenance)" },
      { item: "6c", de: "D;E",
        text: "Give details of any treatments received, and how they were handled during model development or evaluation, if relevant",
        rep: "Not applicable; the units are food products and no treatments were received" },
    ]},
    { topic: "Data preparation", rows: [
      { item: "7", de: "D;E",
        text: "Describe any data pre-processing and quality checking, including whether this was similar across relevant sociodemographic groups",
        rep: "Methods, Reference grade and provenance of the target, Predictors and outcome, and Model development and baselines (category assignment derived from Open Food Facts taxonomy closures; ingredient text represented as TF-IDF features; category-mean FVL computed on training data only; predicted FVL clipped to 0-100; all preprocessing fitted on the training partition only and applied unchanged to held-out and transportability data)" },
    ]},
    { topic: "Outcome", rows: [
      { item: "8a", de: "D;E",
        text: "Clearly define the outcome that is being predicted and the time horizon, including how and when assessed, the rationale for choosing this outcome, and whether the method of outcome assessment is consistent across sociodemographic groups",
        rep: "Methods, Reference grade and provenance of the target and Predictors and outcome (outcome = the Nutri-Score grade A-E computed by a version-pinned implementation of the official 2023 algorithm from complete inputs; this is the grade that database-scale nutrient profiling must assign). No time horizon: deterministic label, not a prognosis" },
      { item: "8b", de: "D;E",
        text: "If outcome assessment requires subjective interpretation, describe the qualifications and demographic characteristics of the outcome assessors",
        rep: "Not applicable; the outcome is computed deterministically by the official algorithm and requires no subjective assessor interpretation. Computation fidelity is validated in Results (Reference-grade validity and data availability)" },
      { item: "8c", de: "D;E",
        text: "Report any actions to blind assessment of the outcome to be predicted",
        rep: "Not applicable; the outcome is algorithm-computed, so no blinded outcome adjudication is involved. The FVL value that drives the grade was withheld from the model by design (Methods, Predictors and outcome)" },
    ]},
    { topic: "Predictors", rows: [
      { item: "9a", de: "D",
        text: "Describe the choice of initial predictors (eg, literature, previous models, all available predictors) and any pre-selection of predictors before model building",
        rep: "Methods, Predictors and outcome (Table 1): initial predictors are the per-100 g nutrients realistically present in a food-composition record, the ingredient statement (TF-IDF word unigrams and bigrams), and a category-mean FVL feature; the FVL value is deliberately excluded. Engineered ingredient-list-length and additive-mention indicators were available but not used in this feasibility model, which used the text representation, the nutrient vector, and the category feature alone; the text vocabulary was capped at 4000 features" },
      { item: "9b", de: "D;E",
        text: "Clearly define all predictors, including how and when they were measured (and any actions to blind assessment of predictors for the outcome and other predictors)",
        rep: "Methods, Predictors and outcome (Table 1): all predictors defined with measurement context (declared label nutrients, multilingual ingredient text, training-set category mean); the withheld FVL value is the recovery target and is excluded from predictors, preventing predictor-outcome overlap" },
      { item: "9c", de: "D;E",
        text: "If predictor measurement requires subjective interpretation, describe the qualifications and demographic characteristics of the predictor assessors",
        rep: "Not applicable; predictors are drawn from structured label fields and ingredient text and require no subjective adjudication" },
    ]},
    { topic: "Sample size", rows: [
      { item: "10", de: "D;E",
        text: "Explain how the study size was arrived at (separately for development and evaluation), and justify that the study size was sufficient to answer the research question. Include details of any sample size calculation",
        rep: "Methods, Model development and baselines and Missing data and statistical analysis; Results, Grade recovery under withheld FVL (Table 3): the declared-FVL set was partitioned 75:25 at the product level, stratified by grade (held-out test n=3112; FVL-sensitive subgroup n=534); transportability split 8411 train/4034 test. This feasibility study reports single-split estimates with bootstrap 95% confidence intervals for the headline comparisons; formal sample-size powering for external validation (Reference 24) is deferred to the full study" },
    ]},
    { topic: "Missing data", rows: [
      { item: "11", de: "D;E",
        text: "Describe how missing data were handled. Provide reasons for omitting any data",
        rep: "Methods, Missing data and statistical analysis (missingness is the substance of the task; eligibility required a complete nutrient panel, so the evaluated degradation is the withheld FVL value; handling of additionally missing nutrient fields in incomplete records is deferred to the full study, guided by missing-data best practice [Reference 23] rather than naive case deletion)" },
    ]},
    { topic: "Analytical methods", rows: [
      { item: "12a", de: "D",
        text: "Describe how the data were used (eg, for development and evaluation of model performance) in the analysis, including whether the data were partitioned, considering any sample size requirements",
        rep: "Methods, Model development and baselines (data partitioned at the product level into 75% training and 25% held-out test, stratified by grade, with no product in more than one partition; training partition used for fitting and feature construction, held-out test used only for evaluation)" },
      { item: "12b", de: "D",
        text: "Depending on the type of model, describe how predictors were handled in the analyses (functional form, rescaling, transformation, or any standardisation)",
        rep: "Methods, Predictors and outcome and Model development and baselines (nutrients used as declared per-100 g values; ingredient text vectorized as TF-IDF unigrams and bigrams capped at 4000 features; category-mean FVL on training data; predicted FVL clipped to 0-100 before grading; the gradient-boosted tree learner requires no standardization)" },
      { item: "12c", de: "D",
        text: "Specify the type of model, rationale, all model building steps, including any hyperparameter tuning, and method for internal validation",
        rep: "Methods, Model development and baselines (a LightGBM gradient-boosted decision-tree regressor [400 trees, learning rate 0.05, up to 63 leaves, row subsampling 0.8, feature subsampling 0.6, seed 42, 4000-feature TF-IDF vocabulary with minimum document frequency 5] predicts FVL, which the version-pinned scorer converts to the grade; no further hyperparameter tuning was performed, so reported performance reflects an untuned configuration; internal evaluation via a single grade-stratified held-out split)" },
      { item: "12d", de: "D;E",
        text: "Describe if and how any heterogeneity in estimates of model parameter values and model performance was handled and quantified across clusters (eg, hospitals, countries). See TRIPOD-Cluster for additional considerations",
        rep: "Methods, Missing data and statistical analysis and Model development and baselines; Results, Geographic transportability (heterogeneity across geography assessed by a France-to-non-French transportability split rather than cluster-level random effects; no formal multi-cluster modeling in this feasibility step)" },
      { item: "12e", de: "D;E",
        text: "Specify all measures and plots used (and their rationale) to evaluate model performance (eg, discrimination, calibration, clinical utility) and, if relevant, to compare multiple models",
        rep: "Methods, Missing data and statistical analysis (performance evaluated by exact-match accuracy and quadratic weighted kappa against the reference grade, overall and within the FVL-sensitive subgroup, and by mean absolute error of the predicted FVL value; Table 3 and Figure 2 compare the five methods, a confusion matrix (Figure 4) shows the grade-level error structure, and a SHAP feature-attribution summary is reported (Figure 3)); calibration and decision-curve net benefit (References 26-27) are deferred to the full study (Discussion, Strengths and limitations and Future work)" },
      { item: "12f", de: "E",
        text: "Describe any model updating (eg, recalibration) arising from the model evaluation, either overall or for particular sociodemographic groups or settings",
        rep: "Not applicable; no model updating or recalibration was performed in this preliminary evaluation; recalibration is identified as future work (Discussion, Future work)" },
      { item: "12g", de: "E",
        text: "For model evaluation, describe how the model predictions were calculated (eg, formula, code, object, application programming interface)",
        rep: "Methods, Predictors and outcome and Model development and baselines (for evaluation, each method's predicted FVL value was passed through the identical version-pinned 2023 scorer to produce the grade, so methods differ only in the FVL estimate; the scorer implementation, category-flag taxonomy, scripts, and dataset revision identifiers are available, Data availability)" },
    ]},
    { topic: "Class imbalance", rows: [
      { item: "13", de: "D;E",
        text: "If class imbalance methods were used, state why and how this was done, and any subsequent methods to recalibrate the model or the model predictions",
        rep: "No class-imbalance resampling was applied. The training and held-out partitions were stratified by grade (Methods, Model development and baselines), and the ordinal quadratic weighted kappa metric plus the FVL-sensitive subgroup analysis (Methods, Missing data and statistical analysis) account for the uneven grade distribution reported in Results (Composition and bias of the declared-FVL set)" },
    ]},
    { topic: "Fairness", rows: [
      { item: "14", de: "D;E",
        text: "Describe any approaches that were used to address model fairness and their rationale",
        rep: "No formal fairness or subgroup-equity audit was performed, as stated in Discussion (Strengths and limitations). The geographic and compositional selection bias of the declared-FVL set is quantified in Results (Composition and bias of the declared-FVL set; population stability index 0.146 for grade and 0.279 for FVL), and inverse-probability weighting with stratified, subgroup-resolved reporting is identified as required future work (Discussion, Strengths and limitations and Future work)" },
    ]},
    { topic: "Model output", rows: [
      { item: "15", de: "D",
        text: "Specify the output of the prediction model (eg, probabilities, classification). Provide details and rationale for any classification and how the thresholds were identified",
        rep: "Methods, Predictors and outcome and Model development and baselines (the model outputs a continuous FVL estimate clipped to 0-100, which the deterministic 2023 scorer maps to the categorical Nutri-Score grade A-E); assigning a calibrated grade with a per-grade confidence is described as a prospective use in Discussion (Implications), and calibration itself was not evaluated in this feasibility step (Discussion, Strengths and limitations)" },
    ]},
    { topic: "Training versus evaluation", rows: [
      { item: "16", de: "D;E",
        text: "Identify any differences between the development and evaluation data in healthcare setting, eligibility criteria, outcome, and predictors",
        rep: "Methods, Study design and data sources and Missing data and statistical analysis; Results, External dataset feasibility (differences between the Open Food Facts development data and the USDA FoodData Central external data in setting [community-maintained worldwide vs US mandatory labeling], nutrient completeness [33.3% vs 79.3%], and barcode overlap are described; the full model was not run on FoodData Central in this preliminary step, which is an external-dataset feasibility assessment only)" },
    ]},
    { topic: "Ethical approval", rows: [
      { item: "17", de: "D;E",
        text: "Name the institutional research board or ethics committee that approved the study and describe the participant informed consent or the ethics committee waiver of informed consent",
        rep: "Methods, Ethical considerations (the analysis used aggregated product-level data with no personal information and no human participants, so it did not constitute human-subjects research and required no institutional review board approval or informed consent; the Open Database License and public-domain status of the data are stated)" },
    ]},
  ]},
  { name: "OPEN SCIENCE", groups: [
    { topic: "Funding", rows: [
      { item: "18a", de: "D;E",
        text: "Give the source of funding and the role of the funders for the present study",
        rep: "Funding section (the research received no specific grant from any funding agency in the public, commercial, or not-for-profit sectors)" },
    ]},
    { topic: "Conflicts of interest", rows: [
      { item: "18b", de: "D;E",
        text: "Declare any conflicts of interest and financial disclosures for all authors",
        rep: "Conflict of interest section (the authors declared no potential conflicts of interest with respect to the research, authorship, or publication of this article)" },
    ]},
    { topic: "Protocol", rows: [
      { item: "18c", de: "D;E",
        text: "Indicate where the study protocol can be accessed or state that a protocol was not prepared",
        rep: "Methods, Ethical considerations (no separate study protocol was prepared beyond the analysis plan described in the Methods; the design of the planned full study is outlined in Discussion, Future work)" },
    ]},
    { topic: "Registration", rows: [
      { item: "18d", de: "D;E",
        text: "Provide registration information for the study, including register name and registration number, or state that the study was not registered",
        rep: "Methods, Ethical considerations (the study was not prospectively registered; it is a secondary analysis of openly licensed aggregated product databases with no human participants, for which prospective registration does not apply)" },
    ]},
    { topic: "Data sharing", rows: [
      { item: "18e", de: "D;E",
        text: "Provide details of the availability of the study data",
        rep: "Data availability section (Open Food Facts is available under the Open Database License and USDA FoodData Central is in the public domain; both are cited with access dates, References 21-22)" },
    ]},
    { topic: "Code sharing", rows: [
      { item: "18f", de: "D;E",
        text: "Provide details of the availability of the analytical code",
        rep: "Data availability section and Appendix A (Supplementary data) (the version-pinned 2023 Nutri-Score implementation, the category-flag taxonomy, the analysis scripts, and the dataset revision identifiers will be deposited in a public repository upon publication and are available from the corresponding author in the interim)" },
    ]},
  ]},
  { name: "PATIENT AND PUBLIC INVOLVEMENT", groups: [
    { topic: "Patient and public involvement", rows: [
      { item: "19", de: "D;E",
        text: "Provide details of any patient and public involvement during the design, conduct, reporting, interpretation, or dissemination of the study or state no involvement",
        rep: "Methods, Ethical considerations (no patient or public involvement in the design or conduct, consistent with a secondary analysis of aggregated product-label databases with no human participants)" },
    ]},
  ]},
  { name: "RESULTS", groups: [
    { topic: "Participants", rows: [
      { item: "20a", de: "D;E",
        text: "Describe the flow of participants through the study, including the number of participants with and without the outcome and, if applicable, a summary of the follow-up time. A diagram may be helpful",
        rep: "Results, Reference-grade validity and data availability (Table 2; Figure 1): flow from 4,529,349 development products to 1,506,178 with complete nutrients (33.3%) and 14,998 with a manufacturer-declared FVL value (0.3%, of which 13,627 also carry an ingredient statement); provenance breakdown in Table 2. No human follow-up" },
      { item: "20b", de: "D;E",
        text: "Report the characteristics overall and, where applicable, for each data source or setting, including the key dates, key predictors (including demographics), treatments received, sample size, number of outcome events, follow-up time, and amount of missing data. A table may be helpful. Report any differences across key demographic groups",
        rep: "Results, Composition and bias of the declared-FVL set (narrative): characteristics of the declared-FVL set reported, including market distribution (France 66%, Spain 20%, Belgium 5%), category coverage (3119 vs 40,870 leaf categories), grade distribution (grade A 22.2% vs 14.5%), and processing (comparable NOVA), with differences across provenance groups; provenance counts are in Table 2" },
      { item: "20c", de: "E",
        text: "For model evaluation, show a comparison with the development data of the distribution of important predictors (demographics, predictors, and outcome)",
        rep: "Results, Composition and bias of the declared-FVL set and External dataset feasibility (distribution comparison between the declared and text-estimated sets via population stability index [grade 0.146; FVL 0.279], and between Open Food Facts and FoodData Central for nutrient completeness and barcode overlap [85.1% overlap with the full database; 0.01% with the training set])" },
    ]},
    { topic: "Model development", rows: [
      { item: "21", de: "D;E",
        text: "Specify the number of participants and outcome events in each analysis (eg, for model development, hyperparameter tuning, model evaluation)",
        rep: "Results, Grade recovery under withheld FVL and Geographic transportability (Table 3): held-out declared-FVL test n=3112 (FVL-sensitive subgroup n=534); transportability split 8411 training/4034 test; the FVL value was grade-determining for 17.2% of products overall" },
    ]},
    { topic: "Model specification", rows: [
      { item: "22", de: "D",
        text: "Provide details of the full prediction model (eg, formula, code, object, application programming interface) to allow predictions in new individuals and to enable third party evaluation and implementation, including any restrictions to access or reuse (eg, freely available, proprietary)",
        rep: "Methods, Model development and baselines specifies the model class and fixed hyperparameters (LightGBM gradient-boosted decision-tree regressor; 400 trees, learning rate 0.05, up to 63 leaves, row subsampling 0.8, feature subsampling 0.6, seed 42, 4000-feature TF-IDF vocabulary with minimum document frequency 5) and the deterministic 2023 scorer that converts FVL to grade; the implementation and scripts are described in Appendix A (Supplementary data) and will be deposited in a public repository upon publication (Data availability)" },
    ]},
    { topic: "Model performance", rows: [
      { item: "23a", de: "D;E",
        text: "Report model performance estimates with confidence intervals, including for any key subgroups (eg, sociodemographic). Consider plots to aid presentation",
        rep: "Results, Grade recovery under withheld FVL (Table 3; Figures 2 and 4) and Geographic transportability (Figure 5): accuracy and quadratic weighted kappa overall and within the FVL-sensitive subgroup, and FVL mean absolute error, for the full model vs baselines (FVL-sensitive accuracy 0.76 vs 0.61; QWK 0.88 vs 0.78); transportability subgroup accuracy 0.59 vs 0.52. Bootstrap 95% confidence intervals are reported for the headline FVL-sensitive comparisons (full vs baseline accuracy delta +0.15, 95% CI 0.11-0.19; QWK delta +0.10, 95% CI 0.08-0.13); repeated-split estimates are deferred to the full study (Methods, Missing data and statistical analysis)" },
      { item: "23b", de: "D;E",
        text: "If examined, report results of any heterogeneity in model performance across clusters. See TRIPOD-Cluster for additional details",
        rep: "Results, Geographic transportability (heterogeneity across the France-to-non-French geographic shift reported as an attenuated but persistent advantage; no further multi-cluster modeling in this feasibility step)" },
    ]},
    { topic: "Model updating", rows: [
      { item: "24", de: "E",
        text: "Report the results from any model updating, including the updated model and subsequent performance",
        rep: "Not applicable; no model updating or recalibration was performed in this preliminary evaluation (Discussion, Future work)" },
    ]},
  ]},
  { name: "DISCUSSION", groups: [
    { topic: "Interpretation", rows: [
      { item: "25", de: "D;E",
        text: "Give an overall interpretation of the main results, including issues of fairness in the context of the objectives and previous studies",
        rep: "Discussion, Principal findings, Comparison with literature, and Implications (overall interpretation that a provenance-aware label-only model recovers the grade better than deterministic imputation where the FVL value is decisive, with the advantage persisting under geographic transport; situated against prior label-based machine-learning work, with selection-bias and transportability issues discussed)" },
    ]},
    { topic: "Limitations", rows: [
      { item: "26", de: "D;E",
        text: "Discuss any limitations of the study (such as a non-representative sample, sample size, overfitting, missing data) and their effects on any biases, statistical uncertainty, and generalisability",
        rep: "Discussion, Strengths and limitations (small, geographically skewed leakage-free training set; approximate deterministic baselines; feasibility-only external analysis with record-level overlap requiring GTIN deduplication; single-split estimates (with bootstrap confidence intervals) rather than repeated splits; the subgroup focus narrows the effective sample; calibration and decision-analytic utility not yet evaluated; residual reference-grade target error and sensitivity to nutrient rounding)" },
    ]},
    { topic: "Usability of the model in the context of current care", rows: [
      { item: "27a", de: "D",
        text: "Describe how poor quality or unavailable input data (eg, predictor values) should be assessed and handled when implementing the prediction model",
        rep: "Discussion, Implications and Future work; Methods, Missing data and statistical analysis (the method is designed precisely for the missing-FVL case; assigning an estimated grade with a per-grade confidence is described as a prospective use (Discussion, Implications); calibration and the handling of additionally missing nutrient fields are deferred to the full study)" },
      { item: "27b", de: "D",
        text: "Specify whether users will be required to interact in the handling of the input data or use of the model, and what level of expertise is required of users",
        rep: "Discussion, Implications (positioned as a label-only method for database curators and researchers, not a consumer-facing tool; inputs are read from food-composition records; assigning an estimated grade with a per-grade confidence and a short rationale is described as the intended use, calibration being deferred to the full study)" },
      { item: "27c", de: "D;E",
        text: "Discuss any next steps for future research, with a specific view to applicability and generalisability of the model",
        rep: "Discussion, Future work (multimodal model; inverse-probability weighting and stratified, subgroup-resolved transportability analysis; deduplicated external validation reporting discrimination, calibration, and decision-curve net benefit with bootstrap confidence intervals; direct comparison against the operator's ingredient-based FVL estimator; a manually adjudicated audit of failure-prone categories; and pre-registration of the full analysis plan before external data are accessed)" },
    ]},
  ]},
];

function p(text, bold) {
  return new Paragraph({ spacing: SP, alignment: AlignmentType.LEFT,
    children: [new TextRun({ text, bold: !!bold, font: FONT, size: SZ })] });
}

function cell(text, w, opts = {}) {
  const { bold = false, span, vMerge } = opts;
  const tc = {
    width: { size: w, type: WidthType.DXA }, borders: GRID,
    margins: { top: 30, bottom: 30, left: 80, right: 80 },
    verticalAlign: VerticalAlign.TOP,
    children: [p(text, bold)],
  };
  if (span) tc.columnSpan = span;
  if (vMerge) tc.verticalMerge = vMerge;
  return new TableCell(tc);
}

function build() {
  const rows = [];
  // header row
  rows.push(new TableRow({ tableHeader: true, children: [
    cell("Section/Topic", COLW[0], { bold: true }),
    cell("Item", COLW[1], { bold: true }),
    cell("Development/Evaluation", COLW[2], { bold: true }),
    cell("Checklist item", COLW[3], { bold: true }),
    cell("Reported on page", COLW[4], { bold: true }),
  ] }));
  for (const sec of SECTIONS) {
    // section header spanning all columns
    rows.push(new TableRow({ children: [cell(sec.name, CONTENT_W, { bold: true, span: 5 })] }));
    for (const g of sec.groups) {
      g.rows.forEach((r, idx) => {
        const naf = r.rep.startsWith("Not applicable") || r.rep.startsWith("No ") || r.rep.startsWith("The study was not");
        const topicCell = idx === 0
          ? cell(g.topic, COLW[0], { vMerge: g.rows.length > 1 ? VerticalMergeType.RESTART : undefined })
          : cell("", COLW[0], { vMerge: VerticalMergeType.CONTINUE });
        rows.push(new TableRow({ children: [
          topicCell,
          cell(r.item, COLW[1]),
          cell(r.de, COLW[2]),
          cell(r.text, COLW[3]),
          cell(r.rep, COLW[4], { bold: !naf }),
        ] }));
      });
    }
  }

  const table = new Table({
    width: { size: CONTENT_W, type: WidthType.DXA },
    columnWidths: COLW,
    borders: { top: B, bottom: B, left: B, right: B, insideHorizontal: B, insideVertical: B },
    rows,
  });

  const caption = new Paragraph({ spacing: { before: 0, after: 120 }, children: [
    new TextRun({ text: "TABLE S1. ", bold: true, font: FONT, size: SZ }),
    new TextRun({ text: "TRIPOD+AI checklist.", bold: true, font: FONT, size: SZ }),
  ] });
  const foot = new Paragraph({ spacing: { before: 120, after: 0 }, children: [
    new TextRun({ text: "TRIPOD+AI: Transparent Reporting of a multivariable prediction model for Individual Prognosis or Diagnosis, plus Artificial Intelligence; D: items relevant only to model development; E: items relevant only to model evaluation; D;E: items applicable to both; FVL: fruit, vegetable, and legume; TF-IDF: term frequency-inverse document frequency; QWK: quadratic weighted kappa; GTIN: Global Trade Item Number; NOVA: food-processing classification system. Checklist-item wording follows Collins GS, et al. BMJ 2024;385:e078378.",
      font: FONT, size: 18 }),
  ] });

  return new Document({
    styles: { default: { document: { run: { font: FONT, size: SZ } } } },
    sections: [{
      properties: { page: {
        size: { width: 12240, height: 15840 },
        margin: { top: 1440, right: 1800, bottom: 1440, left: 1800 } } },
      footers: { default: new Footer({ children: [new Paragraph({ alignment: AlignmentType.CENTER,
        children: [new TextRun({ children: [PageNumber.CURRENT], font: FONT, size: 18 })] })] }) },
      children: [caption, table, foot],
    }],
  });
}

(async () => {
  const out = path.join(__dirname, "..", "manuscript", "TRIPOD_AI_NutriScore.docx");
  fs.writeFileSync(out, await Packer.toBuffer(build()));
  const n = SECTIONS.reduce((a, s) => a + s.groups.reduce((b, g) => b + g.rows.length, 0), 0);
  console.log(`[written] ${out}  (${n} checklist rows)`);
})();
