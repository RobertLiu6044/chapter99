"""
Trigger the Parse workflow and print what comes back.

    uv run python -m parse_run
"""

from parse_hts import ParseInput, ParseSummary, parse_workflow


def main() -> None:
    result = parse_workflow.run(ParseInput())
    summary = ParseSummary.model_validate(result["load_rules"])
    print(
        f"hts_base={summary.hts_base} "
        f"rules={summary.rules} "
        f"edges={summary.edges} "
        f"special_base={summary.special_base} "
        f"special_rule={summary.special_rule}"
    )


if __name__ == "__main__":
    main()
