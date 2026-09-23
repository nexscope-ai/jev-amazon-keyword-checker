"""Amazon keyword relevance evaluation through Nexscope's fixed Jev preset."""
import argparse
import csv
import json
import os
from pathlib import Path
import re
import sys
import time
import urllib.error
import urllib.request

BASE = "https://api.nexscope.ai"
EVALUATE = "/api/skill-api/v1/jev/evaluate"
EXPAND = "/api/skill-api/v1/skills/amazon-keyword-expansion/run"
PRODUCT = "/api/skill-api/v1/skills/amazon-product-detail/run"


class CheckError(Exception):
    pass


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def unpack(envelope):
    if not isinstance(envelope, dict) or type(envelope.get("code")) is not int or envelope["code"] != 0:
        raise CheckError("Nexscope returned a non-success or invalid envelope; no result inferred.")
    data = envelope.get("data")
    if not isinstance(data, dict):
        raise CheckError("No usable response data; no result inferred.")
    if data.get("status") in ("pending", "processing", "queued", "accepted", "running"):
        raise CheckError("Request is still processing. This CLI does not poll or resubmit automatically.")
    return data


class Client:
    def __init__(self, key):
        self.key = key
        self.last_evaluation = None
        self.opener = urllib.request.build_opener(NoRedirect())

    def post(self, path, payload):
        if path not in (EVALUATE, EXPAND, PRODUCT):
            raise CheckError("Unsupported API path.")
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        if path == EVALUATE:
            if len(raw) > 16000:
                raise CheckError("Jev request exceeds 16,000 UTF-8 bytes.")
            if self.last_evaluation is not None:
                time.sleep(max(0, 3.2 - (time.monotonic() - self.last_evaluation)))
            self.last_evaluation = time.monotonic()
        request = urllib.request.Request(BASE + path, data=raw, method="POST", headers={
            "Authorization": "Bearer " + self.key, "Content-Type": "application/json"})
        try:
            with self.opener.open(request, timeout=45) as response:
                raw_response = response.read(5_000_001)
            if len(raw_response) > 5_000_000:
                raise CheckError("Response exceeded local size limit.")
            return unpack(json.loads(raw_response))
        except urllib.error.HTTPError as error:
            raise CheckError("API HTTP %s; stopped without retrying." % error.code) from None
        except (urllib.error.URLError, TimeoutError, OSError):
            raise CheckError("API network error; stopped without retrying.") from None
        except (ValueError, UnicodeError):
            raise CheckError("API returned invalid JSON.") from None


def listing_fields(listing):
    if not isinstance(listing, dict):
        raise CheckError("Listing must be a JSON object.")
    fields = {}
    for key, limit in (("title", 300), ("metaDescription", 1000), ("contentExcerpt", 4000)):
        value = listing.get(key)
        if value is not None:
            if not isinstance(value, str) or not value.strip() or len(value) > limit:
                raise CheckError("%s must contain 1–%s characters; shorten explicitly." % (key, limit))
            fields[key] = value.strip()
    if not fields:
        raise CheckError("Provide title, metaDescription, or contentExcerpt.")
    return fields


def product_listing(data, asin):
    products = data.get("products")
    if not isinstance(products, list):
        raise CheckError("Expected documented data.products array; use a local listing file instead.")
    product = next((p for p in products if isinstance(p, dict) and p.get("asin") == asin), None)
    if product is None:
        raise CheckError("Requested ASIN was not returned.")
    listing = {}
    if isinstance(product.get("title"), str) and product["title"].strip():
        listing["title"] = product["title"]
    parts = []
    bullets = product.get("aboutItem", [])
    if isinstance(bullets, list):
        parts.extend(b for b in bullets if isinstance(b, str) and b.strip())
    # A+ productDescription can be serialized JSON. Do not guess its nested schema.
    description = product.get("description")
    if isinstance(description, str) and description.strip():
        parts.append(description)
    if parts:
        listing["contentExcerpt"] = "\n".join(parts)
    return listing_fields(listing)


def keywords_from(items):
    if not isinstance(items, list):
        raise CheckError("Keywords must be a JSON array.")
    result, seen = [], set()
    for item in items:
        if isinstance(item, str):
            item = {"name": item}
        if not isinstance(item, dict) or not isinstance(item.get("name"), str):
            raise CheckError("Each keyword needs a string name.")
        name = item["name"].strip()
        if not 1 <= len(name) <= 500:
            raise CheckError("Each keyword must contain 1–500 characters.")
        if name.casefold() not in seen:
            seen.add(name.casefold())
            result.append({"name": name, "monthlySearchVolumeExact": item.get("monthlySearchVolumeExact")})
    if not result:
        raise CheckError("No keywords returned or supplied.")
    return result


def request_for(keyword, listing):
    payload = {"useCase": "seo_relevance", "input": {"query": keyword["name"], **listing_fields(listing)}}
    if len(json.dumps(payload, ensure_ascii=False).encode("utf-8")) > 16000:
        raise CheckError("Jev request exceeds 16,000 UTF-8 bytes.")
    return payload


def evaluate(client, keyword, listing):
    data = client.post(EVALUATE, request_for(keyword, listing))
    if data.get("useCase") != "seo_relevance" or not isinstance(data.get("decision"), str) or not data["decision"]:
        raise CheckError("Missing or unexpected Jev evaluation; no relevance result inferred.")
    return {**keyword, "evaluation": data}


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def csv_safe(value):
    if value is None:
        return ""
    value = str(value)
    return "'" + value if value.lstrip().startswith(("=", "+", "-", "@")) or value.startswith(("\t", "\r", "\n")) else value


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    product = parser.add_mutually_exclusive_group(required=True)
    product.add_argument("--listing", help="Local JSON: title / metaDescription / contentExcerpt")
    product.add_argument("--asin", help="Amazon.com ASIN; data API may consume credits")
    keywords = parser.add_mutually_exclusive_group(required=True)
    keywords.add_argument("--keywords", help="Local JSON array of strings or objects with name")
    keywords.add_argument("--seed", help="Expand a seed on the US Amazon marketplace")
    parser.add_argument("--limit", type=int, default=5, help="Evaluate 1–20 keywords (default 5)")
    parser.add_argument("--dry-run", action="store_true", help="Local files only; print requests, never call APIs")
    parser.add_argument("--output", default="results", help="New output directory; must not already exist")
    args = parser.parse_args(argv)
    if not 1 <= args.limit <= 20:
        raise CheckError("Limit must be 1–20.")
    if args.asin and not re.fullmatch(r"[A-Z0-9]{10}", args.asin):
        raise CheckError("ASIN must be 10 uppercase letters/digits.")
    if args.seed is not None and not args.seed.strip():
        raise CheckError("Seed cannot be empty.")
    if args.dry_run and (args.asin or args.seed):
        raise CheckError("Dry run accepts local listing and keywords only; no network is used.")
    listing = listing_fields(read_json(args.listing)) if args.listing else None
    keywords = keywords_from(read_json(args.keywords))[:args.limit] if args.keywords else None
    if args.dry_run:
        print(json.dumps({"mode": "dry-run", "evaluated": False,
                          "requests": [request_for(k, listing) for k in keywords]}, indent=2, ensure_ascii=False))
        return 0
    key = os.environ.get("NEXSCOPE_API_KEY", "").strip()
    if not key:
        raise CheckError("Set NEXSCOPE_API_KEY in your environment. Do not put it in an input file.")
    out = Path(args.output)
    if out.exists():
        raise CheckError("Output directory already exists; choose a new --output path.")
    out.mkdir(parents=True)
    client = Client(key)
    if listing is None:
        listing = product_listing(client.post(PRODUCT, {"asins": args.asin, "amazonDomain": "amazon.com",
            "returnBoughtTogether": False, "returnRelatedProducts": False, "returnAuthorsReviews": False}), args.asin)
    if keywords is None:
        data = client.post(EXPAND, {"searchTerms": args.seed, "marketplace": "us", "needCount": args.limit})
        keywords = keywords_from(data.get("keywordInfoList"))[:args.limit]
    # Validate every request before making the first evaluation call.
    for keyword in keywords:
        request_for(keyword, listing)
    report = {"mode": "live", "complete": False, "listingSource": "local" if args.listing else args.asin,
              "keywordSource": "local" if args.keywords else "amazon-keyword-expansion",
              "listing": listing, "requestedCount": len(keywords), "results": []}
    report_path = out / "results.json"
    def save():
        report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    save()
    try:
        for keyword in keywords:
            report["results"].append(evaluate(client, keyword, listing))
            save()
    except CheckError as error:
        report["error"] = str(error)
        save()
        raise
    report["complete"] = True
    save()
    with (out / "results.csv").open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.writer(stream)
        writer.writerow(["keyword", "monthlySearchVolumeExact", "jevDecision", "jevResultJson"])
        for row in report["results"]:
            writer.writerow([csv_safe(row["name"]), csv_safe(row["monthlySearchVolumeExact"]),
                             csv_safe(row["evaluation"]["decision"]),
                             json.dumps(row["evaluation"], ensure_ascii=False)])
    print("Saved %s evaluations to %s" % (len(report["results"]), out))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (CheckError, OSError, ValueError) as error:
        print("Error: %s" % error, file=sys.stderr)
        sys.exit(1)
