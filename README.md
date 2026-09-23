# Amazon Keyword Relevance Checker — powered by Jev and Nexscope

Find Amazon keyword ideas with Nexscope and evaluate their relevance to listing text with Jev.

A small Python CLI for Amazon sellers and developers. Nexscope supplies keyword data and listing text; Jev evaluates how relevant that text is to each keyword. The tool exports the returned decisions alongside available exact search volume. It does not generate keywords with Jev or predict ad performance.

**Status:** initial implementation based on public API contracts. Offline tests and request previews are available. Authenticated end-to-end behavior and the quality of the SEO relevance preset on Amazon listings have not yet been verified. No hosted app is included.

[Get a Nexscope API key](https://www.nexscope.ai/api-docs/jev-evaluate?co-from=githubjev) · [Amazon keyword API](https://www.nexscope.ai/api-docs/amazon-keyword-expansion?co-from=githubjev) · [How it works](docs/api-contract.md)

## Try it without a key

Download the repository, open its folder, and run with Python 3.9 or newer. There are no third-party dependencies.

```sh
python3 checker.py --listing examples/listing.json --keywords examples/keywords.json --dry-run
python3 -m unittest discover -s tests -v
```

Dry run only prints the requests that would be sent. It makes **no network calls** and produces **no simulated Jev judgments**. The sample listing is fictional and the keywords have no invented search volumes.

## Run a real evaluation

Set `NEXSCOPE_API_KEY` in your shell environment or secret manager. `.env.example` documents the name; the program does not automatically load `.env` files. Never commit a real key or paste it into a command-line argument.

```sh
python3 checker.py --listing examples/listing.json --keywords examples/keywords.json --output results-local
```

This sends one Jev evaluation request per unique keyword, at most five by default. The maximum local batch is 20. It uses your Nexscope account; no separate TypeSafe key is needed.

To fetch Amazon.com listing data and expand a seed keyword:

```sh
python3 checker.py --asin YOUR_ASIN --seed "kids water bottle" --limit 5 --output results-amazon
```

Replace `YOUR_ASIN` with a real 10-character ASIN. This command is an integration example, not a verified live run. It makes one product request, one keyword expansion request, then up to five evaluation requests. Data calls may consume credits even if a later step fails.

You can combine `--listing` with `--seed`, or `--asin` with `--keywords`. The initial automatic import supports Amazon.com / US only; this restriction is local to this tool.

## Where Jev makes the decision

```text
Nexscope keyword expansion ── candidate keywords + search metrics
Nexscope product detail   ── listing title + available bullets/description
                                  ↓
                      Jev seo_relevance preset
                  query = one candidate keyword
                  title / contentExcerpt = listing text
                                  ↓
              Returned evaluation + original search metric
                                  ↓
                         JSON and CSV export
```

The application calls `POST /api/skill-api/v1/jev/evaluate` with the fixed `seo_relevance` preset. For example, the offline sample produces this request shape:

```json
{
  "useCase": "seo_relevance",
  "input": {
    "query": "kids water bottle",
    "title": "Fictional Kids Water Bottle",
    "contentExcerpt": "A reusable water bottle described for school lunches."
  }
}
```

The service evaluates relevance of the supplied text. It does not verify material claims, detect keyword intent, cluster keywords, or decide bids. This is an application of a general SEO relevance preset to Amazon listing text, pending domain-specific validation.

Nexscope's keyword `relevancyScore` describes relevance to the **seed**. Jev evaluates the supplied **listing text against a keyword**. These are different signals. This CLI does not combine them into an invented score.

## Inputs and outputs

- Listing JSON: `title` (up to 300 characters), `metaDescription` (1,000), and/or `contentExcerpt` (4,000). At least one nonempty field is required.
- Keywords JSON: an array of strings, or objects with `name` and optional `monthlySearchVolumeExact`. Duplicate names are removed case-insensitively.
- Long listing text is rejected, not silently truncated. For long imported products, use a local file with an explicit excerpt. A+ JSON descriptions are not automatically interpreted.
- `results.json`: submitted listing context, source labels, each returned evaluation, and a completion flag. If evaluation fails partway through, completed rows are saved with `complete: false` and an error. Earlier data-fetch failures may leave an empty output directory.
- `results.csv`: keyword, optional exact search volume, returned Jev decision, and full evaluation JSON. Created only when the batch completes. Spreadsheet-sensitive strings are escaped.
- Missing search volume remains missing; it is never converted to zero. Provider metrics are not Ahrefs KD.

Choose a new output directory for each run; existing directories are never overwritten. JSON retains service fields rather than guessing undocumented score structures. No fabricated output screenshot or benchmark is included.

## Access, limits, and privacy

The published contract requires an active Nexscope subscription. Jev nodes do not deduct Nexscope business credits; data APIs keep their own billing. Route and Evaluate share per-user and global quotas. This CLI spaces evaluation requests at least 3.2 seconds apart; other clients and global usage may still cause rate limiting. It does not retry or automatically resubmit pending tasks.

Only send authorized, de-identified text. Live listing excerpts and keywords go to Nexscope; evaluation excerpts are forwarded to TypeSafe according to the API contract. Output files contain submitted text and results: keep them private if your inputs are private.

A returned decision is advisory. Text relevance is not Amazon indexing eligibility, truth verification, legal approval, a ranking forecast, or a conversion estimate. Empty and invalid responses fail visibly. No generated recommendation replaces a missing evaluation.

## Build on the APIs

Use the same Nexscope interfaces in your own application:

- [JEV Evaluate — fixed evaluation presets](https://www.nexscope.ai/api-docs/jev-evaluate?co-from=githubjev)
- [Amazon Keyword Expansion — keyword ideas and metrics](https://www.nexscope.ai/api-docs/amazon-keyword-expansion?co-from=githubjev)
- [Amazon Product Detail — listing data](https://www.nexscope.ai/api-docs/amazon-product-detail?co-from=githubjev)
- [Browse Nexscope APIs](https://www.nexscope.ai/api-docs?co-from=githubjev)

## Contributing

Run the offline tests before proposing changes. Add regression cases for parsing, limits, partial failures, and missing data. Never attach API keys or private response logs. Improvements to Amazon-specific evaluation quality should use consented, human-labeled examples and report the dataset and failure cases.

Maintained by Nexscope. Independent community integration; not an official TypeSafe project. MIT license applies to this repository's code, not external API services or third-party product data.
