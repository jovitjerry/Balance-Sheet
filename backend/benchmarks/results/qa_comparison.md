# Module 4-style Q&A comparison

Scored **separately** from normalization: picking a category from a closed list and explaining figures in prose are different jobs, and a model can be good at one and poor at the other.

**This is a screen, not a grade.** *Figures cited* is whether the amounts a correct answer must mention actually appear. *Refusals handled* is the two questions that ask for something a Balance Sheet does not contain - profit, and a year-on-year change - where the right answer is to say so. *Fabricated on refusal* is those same questions answered with a number instead, which is the failure that matters: a confident invented figure is the one a reader has no way to catch.

Neither column judges reasoning or prose. The full answers are in `qa_answers.md`; read them before choosing.

| Model | Figures cited | Questions fully cited | Refusals handled | Fabricated on refusal | Cold | Warm mean |
|---|---|---|---|---|---|---|
| llama3.1:8b | 80% | 75% | 100% | 0% | 16.9s | 4.54s |
| martain7r/finance-llama-8b:q4_k_m | 73% | 62% | 100% | 0% | 13.84s | 3.31s |
| qwen3:4b | 93% | 88% | 100% | 0% | 14.06s | 14.45s |
| qwen3:8b | 87% | 75% | 100% | 0% | 10.1s | 2.53s |
