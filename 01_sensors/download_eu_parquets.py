"""Helper for re-downloading the EEA parquet files. The v5 release was
downloaded directly from the EEA download portal; this script fetches the
same files from the URL list the portal exports (ParquetFilesUrls.csv),
one at a time, skipping files already present.
Run: python3 download_eu_parquets.py
"""

import csv
import os
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path


# --- Config ---------------------------------------------------------

URL_CSV = os.environ.get(
    "URL_CSV",
    str(Path.home() / "Downloads" / "ParquetFilesUrls.csv"),
)

DEST_ROOT = Path.home() / "Desktop/Research/Neural Operators/Data/EU_v2_raw"

# Polite delay between requests (seconds). EEA is a public server;
# hitting it as fast as possible is rude and could get us throttled.
DELAY_BETWEEN = 0.3

# Request timeout per file (seconds)
TIMEOUT = 120

# User-Agent so we're identifiable
USER_AGENT = "WNO-research-download/1.0 (academic; contact: nils.rose@ottawa.edu)"


# --- Helpers --------------------------------------------------------

def load_urls(csv_path: str) -> list[str]:
    urls = []
    with open(csv_path, encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        header = next(reader, None)
        for row in reader:
            if row and row[0].strip():
                urls.append(row[0].strip())
    return urls


def country_from_url(url: str) -> str:
    """Extract country code from URL path. Returns '??' if unclear."""
    parts = url.rstrip("/").split("/")
    # Format: .../airquality-p{,extended}/CC/filename.parquet
    if len(parts) >= 2:
        candidate = parts[-2]
        if len(candidate) == 2 and candidate.isupper():
            return candidate
    return "??"


def filename_from_url(url: str) -> str:
    return url.rstrip("/").split("/")[-1]


def human_bytes(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def download_one(url: str, dest: Path) -> tuple[bool, str]:
    """Download url to dest. Returns (success, message)."""
    if dest.exists() and dest.stat().st_size > 0:
        return True, f"[skip] already exists ({human_bytes(dest.stat().st_size)})"

    tmp = dest.with_suffix(dest.suffix + ".part")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=TIMEOUT) as response:
            with tmp.open("wb") as f:
                while True:
                    chunk = response.read(64 * 1024)
                    if not chunk:
                        break
                    f.write(chunk)
        # Atomic rename: only replace dest if download completed
        tmp.replace(dest)
        return True, f"OK ({human_bytes(dest.stat().st_size)})"
    except urllib.error.HTTPError as e:
        if tmp.exists():
            tmp.unlink()
        return False, f"HTTP {e.code} {e.reason}"
    except Exception as e:
        if tmp.exists():
            tmp.unlink()
        return False, f"{type(e).__name__}: {e}"


# --- Main -----------------------------------------------------------

def main():
    csv_path = URL_CSV
    if not Path(csv_path).exists():
        print(f"ERROR: URL list not found at {csv_path}")
        print(f"Set URL_CSV environment variable if it's elsewhere.")
        sys.exit(1)

    print(f"Reading URLs from: {csv_path}")
    urls = load_urls(csv_path)
    print(f"Found {len(urls)} URLs")

    DEST_ROOT.mkdir(parents=True, exist_ok=True)
    print(f"Destination: {DEST_ROOT}")
    print(f"Delay between requests: {DELAY_BETWEEN}s")
    print(f"Timeout per file: {TIMEOUT}s")
    print()

    start = time.time()
    n_ok = 0
    n_skip = 0
    n_fail = 0
    failures = []

    for i, url in enumerate(urls, 1):
        country = country_from_url(url)
        fname = filename_from_url(url)
        country_dir = DEST_ROOT / country
        country_dir.mkdir(exist_ok=True)
        dest = country_dir / fname

        prefix = f"[{i:>4}/{len(urls)}] {country}/{fname[:60]}"
        was_skip = dest.exists() and dest.stat().st_size > 0
        ok, msg = download_one(url, dest)

        # Print result
        status_char = "-" if was_skip else ("OK" if ok else "!!")
        print(f"{prefix}  {status_char}  {msg}")

        if was_skip:
            n_skip += 1
        elif ok:
            n_ok += 1
        else:
            n_fail += 1
            failures.append((url, msg))

        # Polite delay (only if we actually downloaded, not for skips)
        if not was_skip and ok:
            time.sleep(DELAY_BETWEEN)

    elapsed = time.time() - start
    print()
    print("=" * 60)
    print(f"Done in {elapsed:.1f}s ({elapsed/60:.1f} min)")
    print(f"  Downloaded: {n_ok}")
    print(f"  Skipped (already had): {n_skip}")
    print(f"  Failed: {n_fail}")

    if failures:
        print()
        print(f"Failures ({len(failures)}):")
        for url, msg in failures[:20]:
            print(f"  {msg}: {url}")
        if len(failures) > 20:
            print(f"  ... and {len(failures) - 20} more")
        print()
        print("Re-running this script will retry failed downloads.")

    # Summary by country
    print()
    print("Files on disk by country:")
    for country_dir in sorted(DEST_ROOT.iterdir()):
        if country_dir.is_dir():
            files = list(country_dir.glob("*.parquet"))
            total = sum(f.stat().st_size for f in files)
            print(f"  {country_dir.name}: {len(files)} files, {human_bytes(total)}")


if __name__ == "__main__":
    main()