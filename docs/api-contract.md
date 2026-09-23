# API contract and implementation boundaries

Public documentation checked on 2026-09-23. No authenticated smoke test has been performed for this repository.

| Step | POST path | Request | Parsed response |
| --- | --- | --- | --- |
| Keywords | `/api/skill-api/v1/skills/amazon-keyword-expansion/run` | `searchTerms`, `marketplace: us`, `needCount` | `data.keywordInfoList[].name`, optional `monthlySearchVolumeExact` |
| Product | `/api/skill-api/v1/skills/amazon-product-detail/run` | `asins`, `amazonDomain: amazon.com`, optional related-content flags set false | Matching `data.products[].asin`, `title`, string `aboutItem` entries, `description` |
| Evaluation | `/api/skill-api/v1/jev/evaluate` | `useCase: seo_relevance`, `input.query`, listing fields | `data.useCase`, `data.decision`; remaining evaluation data preserved |

All calls use the fixed `https://api.nexscope.ai` origin and Bearer authentication. Redirects are rejected to prevent forwarding the credential elsewhere. An HTTP 200 alone does not mean success: the JSON envelope must have integer `code: 0` and usable data. Pending states stop this CLI; no polling endpoint is invented. Request timeout is 45 seconds and response size is capped at 5 MB.

Jev input limits: query 500 characters, title 300, meta description 1,000, content excerpt 4,000; serialized body at most 16,000 UTF-8 bytes. The server owns decision thresholds. The client does not implement custom questions or relabel service confidence as accuracy.

## Live validation still required

1. Run a small authorized batch with local, de-identified listing text and keywords; inspect returned relevance dimensions.
2. Verify keyword expansion and product parsing with a representative Amazon.com ASIN.
3. Compare evaluations against human labels on relevant, irrelevant, ambiguous, and conflicting examples. Do not publish accuracy claims without a held-out evaluation.
4. Check invalid-key, quota and no-data behavior without putting private service responses into the repository.

If provider response contracts change, stop and update parsers with sanitized regression fixtures. Do not guess schemas or replace missing outputs with samples.

Sources: [JEV Evaluate](https://www.nexscope.ai/api-docs/jev-evaluate?co-from=githubjev), [Keyword Expansion](https://www.nexscope.ai/api-docs/amazon-keyword-expansion?co-from=githubjev), [Product Detail](https://www.nexscope.ai/api-docs/amazon-product-detail?co-from=githubjev).
