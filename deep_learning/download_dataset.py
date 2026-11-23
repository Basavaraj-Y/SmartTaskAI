"""Download the public Apache-licensed Jira issue dataset used for priority training."""

from pathlib import Path
from urllib.request import urlretrieve

URL = (
    "https://raw.githubusercontent.com/javichur/jira-issue-dataset/main/"
    "100k-jira-issues-apache.csv"
)
DESTINATION = (
    Path(__file__).resolve().parent
    / "datasets"
    / "raw"
    / "100k-jira-issues-apache.csv"
)


def main():
    DESTINATION.parent.mkdir(parents=True, exist_ok=True)
    if DESTINATION.exists():
        print(f"Dataset already exists: {DESTINATION}")
        return
    urlretrieve(URL, DESTINATION)
    print(f"Downloaded {DESTINATION.stat().st_size:,} bytes to {DESTINATION}")
    print("Source repository license: Apache-2.0. See the repository LICENSE file.")


if __name__ == "__main__":
    main()
