# Decision Record

The final scientific decision is **RETAIN_BASELINE**.

PRISM passed evidence integrity, data validity, privacy accounting, inference-health,
falsification, weighted-RMSE materiality, paired uncertainty, macro, long-tail, and decision
guardrails. It failed the frozen interval-coverage guardrail (70.6% observed; 80% required).
Promotion rules were conjunctive, so no post-lock exception or tuning was permitted.

B3 remains the strongest eligible aggregate-only baseline by the prespecified development metric.
Its uncertainty intervals are not endorsed; retention is a model-selection decision pending a new,
separately frozen uncertainty-calibration iteration.
