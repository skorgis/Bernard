"""Command-line entry point for the Python project template."""

import argparse

from python_template.greeting import greet


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments.

    Args:
        argv: Argument list to parse. Defaults to `sys.argv[1:]`.

    Returns:
        The parsed arguments.
    """
    parser = argparse.ArgumentParser(description="Greet someone by name.")
    parser.add_argument(
        "name", nargs="?", default="World", help="Name to greet."
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    """Run the command-line interface.

    Args:
        argv: Argument list to parse. Defaults to `sys.argv[1:]`.
    """
    args = parse_args(argv)
    print(greet(args.name))


if __name__ == "__main__":
    main()
