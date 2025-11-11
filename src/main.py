"""Main entry point for blog article generation."""

import argparse
import json
import sys
from pathlib import Path

from .config import Config
from .generators.content_generator import ContentGenerator
from .schemas.input import InputSchema


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(description="Generate blog articles using AI")
    parser.add_argument(
        "--input",
        type=str,
        help="Input JSON file or JSON string",
        required=True,
    )
    parser.add_argument(
        "--output",
        type=str,
        help="Output file path (default: stdout)",
        default=None,
    )
    parser.add_argument(
        "--format",
        choices=["json", "html"],
        default="json",
        help="Output format (default: json)",
    )
    parser.add_argument(
        "--api-key",
        type=str,
        help="Google AI API key (optional, uses env var if not provided)",
        default=None,
    )

    args = parser.parse_args()

    # Load input
    try:
        if Path(args.input).exists():
            with open(args.input, "r", encoding="utf-8") as f:
                input_data = json.load(f)
        else:
            input_data = json.loads(args.input)
    except Exception as e:
        print(f"Error loading input: {e}", file=sys.stderr)
        sys.exit(1)

    # Validate input schema
    try:
        input_schema = InputSchema(**input_data)
    except Exception as e:
        print(f"Error validating input: {e}", file=sys.stderr)
        sys.exit(1)

    # Initialize generator
    config = Config()
    generator = ContentGenerator(config=config, api_key=args.api_key)

    # Generate content
    try:
        output = generator.generate(input_schema)
    except Exception as e:
        print(f"Error generating content: {e}", file=sys.stderr)
        import traceback

        traceback.print_exc()
        sys.exit(1)

    # Format output
    if args.format == "html" and output.html:
        output_text = output.html
    else:
        output_text = json.dumps(output.model_dump(), indent=2, ensure_ascii=False)

    # Write output
    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(output_text)
        print(f"Output written to {args.output}", file=sys.stderr)
    else:
        print(output_text)


if __name__ == "__main__":
    main()

