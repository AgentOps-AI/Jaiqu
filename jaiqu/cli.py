import json
import sys

from typer import Option, Typer

from .jaiqu import translate_schema

typer_app = Typer()


@typer_app.command()
def jaiqu(
    schema_file: str = Option(..., "-s", "--schema", help="Json schema file path"),
    data_file: str = Option(
        None,
        "-d",
        "--data",
        help="Json data file path. if not passed will try to read from stdin",
    ),
    quiet: bool = Option(False, "-q", "--quiet", help="Quiet mode, only print errors"),
    key_hints: str = Option(
        None,
        "-k",
        "--key-hints",
        help="Extra prompt for the ai to help it complete the task",
    ),
    max_retries: int = Option(
        10,
        "-r",
        "--max-retries",
        help="Max number of retries for the ai to complete the task",
    ),
    save_trace: bool = Option(
        False,
        "-s",
        "--save-trace",
        help="Saves a trace for introspection using the Burr UI.",
    ),
):
    """
    Validate and translate a json schema to jq filter
    """
    with open(schema_file) as f:
        output_schema = json.load(f)
    if data_file is None:
        if sys.stdin.isatty():
            sys.exit("Error: No data piped to stdin.")
        else:
            if not quiet:
                print("--data not provided, reading from stdin")
            data_file = sys.stdin.read()
            input_json = json.loads(data_file)
    else:
        with open(data_file) as f:
            input_json = json.load(f)

    query = translate_schema(
        output_schema=output_schema,
        input_json=input_json,
        key_hints=key_hints,
        max_retries=max_retries,
        quiet=quiet,
        save_trace=save_trace,
    )
    print(query)


def main():
    typer_app()


if __name__ == "__main__":
    main()
