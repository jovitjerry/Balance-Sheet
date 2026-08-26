# Model comparison

Measured on this machine against `normalization_cases.json`. **No winner is declared here** - this is the evidence, not the decision.

**Accuracy** is exact canonical-label match on the cases that have a right answer. **Abstained correctly** is the ambiguous and unknown cases the model declined, and **over-answered** is the same set it answered anyway - a high score in the first column with a high over-answered rate is a model that guesses well, which is not the same thing as a model that is right.

**Cold** is the first request, which pays to load the weights into VRAM; **warm mean** is every request after it. Averaging the two describes neither.

**Unmeasured** is the share of cases the model never actually answered. It must be blank. Anything else means the run did not measure what the other columns claim - a model that 404s on every request abstains from everything perfectly.

| Model | Accuracy | Abstained correctly | Over-answered | Cold | Warm mean | VRAM (MB) | Unmeasured |
|---|---|---|---|---|---|---|---|
| llama3.1:8b | 95% | 46% | 54% | 18.06s | 4.39s | 6156.0 | - |
| martain7r/finance-llama-8b:q4_k_m | 95% | 15% | 85% | 11.47s | 4.85s | 5141 | - |
| qwen3:4b | 95% | 62% | 38% | 15.69s | 4.68s | 4160.0 | - |
| qwen3:8b | 97% | 54% | 46% | 80.91s | 4.15s | 6460.0 | - |
