"""console script entrypoint for the CPM CLI."""


def run() -> int:
    from .main import main as cli_main

    return cli_main()


def main() -> int:
    """Console entrypoint used by setuptools script hooks."""
    return run()


if __name__ == "__main__":
    raise SystemExit(run())
