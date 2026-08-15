"""
Trigger the Scrape workflow and print what comes back.

    uv run python -m scrape_run
"""

from scraper import FileOutput, MetadataOutput, ReleaseOutput, ScrapeInput, scrape_workflow


def main() -> None:
    result = scrape_workflow.run(ScrapeInput())

    release = ReleaseOutput.model_validate(result["release"])
    print(f"release={release.title}")

    for task in ("chapter_99", "chapters_1_97", "notes_pdf"):
        file = FileOutput.model_validate(result[task])
        print(f"  {file.path} ({file.bytes} bytes)")

    meta = MetadataOutput.model_validate(result["metadata"])
    print(f"provenance={meta.path}")


if __name__ == "__main__":
    main()
