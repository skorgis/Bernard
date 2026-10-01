"""Example module demonstrating how to structure code in this template."""


def greet(name: str) -> str:
    """Build a friendly greeting for the given name.

    Args:
        name: The name of the person to greet.

    Returns:
        A greeting message containing the name.

    Raises:
        ValueError: If name is empty or only whitespace.
    """
    if not name.strip():
        raise ValueError("name must not be empty")
    return f"Hello, {name}!"
