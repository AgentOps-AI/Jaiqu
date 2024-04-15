import logging
import os

import burr.core
from burr.core import ApplicationBuilder, State, default, expr, when
from burr.core.action import action

import jq
from jsonschema import validate
from tqdm.auto import tqdm  # Use the auto submodule for notebook-friendly output if necessary
from .helpers import identify_key, create_jq_string, repair_query, dict_to_jq_filter

logger = logging.getLogger(__name__)


def validate_schema(input_json, output_schema, openai_api_key: str | None = None, key_hints=None, quiet=False):
    """Validates the schema of the input JSON against the output schema.
    Args:
        input_json (dict): The input JSON parsed into a dictionary.
        output_schema (dict): The output schema against which the input JSON schema needs to be validated.
        openai_api_key (str | None, optional): The OpenAI API key. Defaults to None.
        key_hints (any, optional): Key hints to assist in identifying keys. Defaults to None.

    Returns:
        tuple[dict, bool]: A tuple containing the results of the validation and a boolean indicating if the
        validation was successful.
    """
    results = {}
    valid = True
    with tqdm(total=len(output_schema['properties']), desc="Validating schema", disable=quiet) as pbar:
        for key, value in output_schema['properties'].items():
            pbar.set_postfix_str(f"Key: {key}", refresh=True)
            response_key, response_reasoning = identify_key(key, value, input_json, openai_api_key, key_hints)

            if response_key is not None:
                results[key] = {"identified": True, "key": response_key,
                                "message": response_reasoning,
                                **value}
            else:
                results[key] = {"identified": False, "key": response_key,
                                "message": response_reasoning,
                                **value}
            if key in output_schema['required']:
                results[key]['required'] = True
                if results[key]['identified'] == False:
                    valid = False
            else:
                results[key]['required'] = False
            pbar.update(1)
    return results, valid


@action(
    reads=["input_json", "output_schema", "key_hints", "quiet"],
    writes=["valid_schema", "schema_properties"]
)
def validate_schema_action(state: State) -> tuple[dict, State]:
    """Action to validate the provided input schema."""
    output_schema = state["output_schema"]
    input_json = state["input_json"]
    key_hints = state["key_hints"]
    quiet = state.get("quiet", False)
    results, valid = validate_schema(input_json, output_schema, key_hints=key_hints, openai_api_key=None, quiet=quiet)
    state = state.update(valid_schema=valid, schema_properties=results)
    return results, state


@action(
    reads=["input_json", "schema_properties", "max_retries", "quiet"],
    writes=["max_retries_hit", "jq_filter"]
)
def create_jq_filter_query(state: State) -> tuple[dict, State]:
    """Creates the JQ filter query."""
    schema_properties = state["schema_properties"]
    input_json = state["input_json"]
    max_retries = state["max_retries"]
    filtered_schema = {k: v for k, v in schema_properties.items() if v['identified'] == True}
    quiet = state.get("quiet", False)
    filter_query = {}

    with tqdm(total=len(filtered_schema),
              desc="Translating schema",
              disable=quiet) as pbar, tqdm(total=max_retries,
                                           desc="Retry attempts",
                                           disable=quiet) as pbar_retries:
        for key, value in filtered_schema.items():
            pbar.set_postfix_str(f"Key: {key}", refresh=True)
            jq_string = create_jq_string(input_json, key, value)

            if jq_string == "None":  # If the response is empty, skip the key
                pbar.update(1)
                continue

            tries = 0
            while True:
                try:
                    jq.compile(jq_string).input(input_json).all()
                    break
                except Exception as e:
                    tries += 1
                    pbar_retries.update(1)
                    jq_string = repair_query(jq_string, str(e), input_json, None)
                    if tries >= max_retries:
                        state = state.update(max_retries_hit=True, jq_filter=None)
                        return {
                            "error": f"Failed to create a valid jq filter for key '{key}' after {max_retries} retries."}, state
            pbar.update(1)
            filter_query[key] = jq_string
        pbar.close()
        pbar_retries.close()
    complete_filter = dict_to_jq_filter(filter_query)
    state = state.update(jq_filter=complete_filter, max_retries_hit=False)
    return {"filter": complete_filter}, state


@action(
    reads=["input_json", "jq_filter", "output_schema", "max_retries", "quiet"],
    writes=["max_retries_hit", "valid_json", "complete_filter"]
)
def validate_json(state: State) -> tuple[dict, State]:
    """Validates the filter JSON."""
    output_schema = state["output_schema"]
    complete_filter = state["jq_filter"]
    input_json = state["input_json"]
    max_retries = state["max_retries"]
    quiet = state.get("quiet", False)
    # Validate JSON
    tries = 0
    with tqdm(total=max_retries, desc="Validation attempts", disable=quiet) as pbar_validation:
        while True:
            try:
                result = jq.compile(complete_filter).input(input_json).all()[0]
                validate(instance=result, schema=output_schema)
                pbar_validation.close()
                break
            except Exception as e:
                tries += 1
                pbar_validation.update(1)
                if tries >= max_retries:
                    state = state.update(max_retries_hit=True, valid_json=False, complete_filter=complete_filter)
                    return {
                        "error": f"Failed to validate the jq filter after {max_retries} retries."}, state

                complete_filter = repair_query(complete_filter, str(e), input_json, None)
    state = state.update(complete_filter=complete_filter, max_retries_hit=False, valid_json=True)
    return {"complete_filter": complete_filter}, state


def translate_schema(input_json, output_schema, openai_api_key: str | None = None, key_hints=None,
                     max_retries=10, quiet=False, save_trace: bool = False) -> str:
    """
        Translate the input JSON schema into a filtering query using jq.

        Args:
            input_json (dict): The input JSON to be reformatted.
            output_schema (dict): The desired output schema using standard schema formatting.
            openai_api_key (str, optional): OpenAI API key. Defaults to None.
            key_hints (None, optional): Hints for translating keys. Defaults to None.
            max_retries (int, optional): Maximum number of retries for creating a valid jq filter. Defaults to 10.
            quiet (bool, optional): Quiet mode to turn off TQDM progress bars. Defaults to False.
            save_trace (bool, optional): turn on Burr tracking to debug jaiqu runs. Defaults to False.

        Returns:
            str: The filtering query in jq syntax.

        Raises:
            RuntimeError: If the input JSON does not contain the required data to satisfy the output schema.
            RuntimeError: If failed to create a valid jq filter after maximum retries.
            RuntimeError: If failed to validate the jq filter after maximum retries.
        """
    if openai_api_key is not None:
        os.environ["OPENAI_API_KEY"] = openai_api_key
    app = build_application(input_json, output_schema,
                            key_hints=key_hints, max_retries=max_retries, quiet=quiet, save_trace=save_trace)
    last_action, result, state = app.run(halt_after=["error_state", "good_result"])
    if last_action == "error_state":
        raise RuntimeError(result)
    return result["complete_filter"]


def build_application(input_json,
                      output_schema,
                      key_hints: str = None,
                      max_retries: int = 10,
                      quiet: bool = False,
                      save_trace: bool = False,
                      visualize: bool = False):
    """
    Builds the application for translating the input JSON schema into a filtering query using jq.

    Args:
        input_json (dict): The input JSON to be reformatted.
        output_schema (dict): The desired output schema using standard schema formatting.
        key_hints (str, optional): Hints for translating keys. Defaults to None.
        max_retries (int, optional): Maximum number of retries for creating a valid jq filter. Defaults to 10.
        quiet (bool, optional): Quiet mode to turn off TQDM progress bars. Defaults to False.
        save_trace (bool, optional): Turn on Burr tracking to debug jaiqu runs. Defaults to False.
        visualize (bool, optional): If set to True, visualizes the application flow. Defaults to False.

    Returns:
        Application: The built application with the specified state, actions, and transitions.
    """
    _app = (
        ApplicationBuilder()
        .with_state(
            **{
                "input_json": input_json,
                "output_schema": output_schema,
                "key_hints": key_hints,
                "max_retries": max_retries,
                "quiet": quiet,
            }
        )
        .with_actions(
            # bind the vector store to the AI conversational step
            validate_schema=validate_schema_action,
            create_jq_filter_query=create_jq_filter_query,
            validate_json=validate_json,
            error_state=burr.core.Result("complete_filter"),
            good_result=burr.core.Result("complete_filter"),
        )
        .with_transitions(
            ("validate_schema", "create_jq_filter_query", default),
            ("create_jq_filter_query", "validate_json", when(max_retries_hit=False)),
            ("create_jq_filter_query", "error_state", when(max_retries_hit=True)),
            ("validate_json", "good_result", when(valid_json=True)),
            ("validate_json", "error_state", when(valid_json=False)),
            ("validate_schema", "good_result", when(valid_schema=True)),
            ("validate_schema", "error_state", when(valid_schema=False)),
        )
        .with_entrypoint("validate_schema")
    )
    if save_trace:
        logger.warning("To see trace information, start `burr` (pip install \"burr[start]\") in a separate terminal"
                       " and go to http://localhost:7241")
        _app = _app.with_tracker(project="jaiqu")
    _app = _app.build()
    if visualize:
        _app.visualize(
            output_file_path="jaiqu_app", include_conditions=True, view=False, format="png"
        )
    return _app


if __name__ == '__main__':
    """Recreate the image easily"""
    app = build_application("", "")
    app.visualize(
        output_file_path="jaiqu_app", include_conditions=True, view=False, format="png"
    )
