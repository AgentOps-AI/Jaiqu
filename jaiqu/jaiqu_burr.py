import pprint
from typing import List, Optional, Tuple

import burr.core
from burr.core import Action, Application, ApplicationBuilder, State, default, expr
from burr.core.action import action
from burr.lifecycle import LifecycleAdapter, PostRunStepHook, PreRunStepHook

import jq
import json
from jsonschema import validate
from tqdm.auto import tqdm  # Use the auto submodule for notebook-friendly output if necessary
from helpers import identify_key, create_jq_string, repair_query, dict_to_jq_filter

@action(
    reads=["input_json", "output_schema", "key_hints"],
    writes=["valid_schema", "schema_properties"]
)
def validate_schema(state: State) -> tuple[dict, State]:
    output_schema = state["output_schema"]
    input_json = state["input_json"]
    key_hints = state["key_hints"]
    results = {}
    valid = True
    with tqdm(total=len(output_schema['properties']), desc="Validating schema") as pbar:
        for key, value in output_schema['properties'].items():
            pbar.set_postfix_str(f"Key: {key}", refresh=True)
            response_key, response_reasoning = identify_key(key, value, input_json, None, key_hints)

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

    state = state.update(valid_schema=valid, schema_properties=results)
    return results, state

@action(
    reads=["input_json", "schema_properties", "max_retries"],
    writes=["max_retries_hit", "jq_filter"]
)
def create_jq_filter_query(state: State) -> tuple[dict, State]:
    schema_properties = state["schema_properties"]
    input_json = state["input_json"]
    max_retries = state["max_retries"]
    filtered_schema = {k: v for k, v in schema_properties.items() if v['identified'] == True}

    filter_query = {}

    with tqdm(total=len(filtered_schema),
              desc="Translating schema") as pbar, tqdm(total=max_retries,
                                                       desc="Retry attempts") as pbar_retries:
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
                        return {"error": f"Failed to create a valid jq filter for key '{key}' after {max_retries} retries."}, state
            pbar.update(1)
            filter_query[key] = jq_string
        pbar.close()
        pbar_retries.close()
    complete_filter = dict_to_jq_filter(filter_query)
    state = state.update(jq_filter=complete_filter, max_retries_hit=False)
    return {"filter": complete_filter}, state

@action(
    reads=["input_json", "jq_filter", "output_schema", "max_retries"],
    writes=["max_retries_hit", "valid_json", "complete_filter"]
)
def validate_json(state: State) -> tuple[dict, State]:
    output_schema = state["output_schema"]
    complete_filter = state["jq_filter"]
    input_json = state["input_json"]
    max_retries = state["max_retries"]
    # Validate JSON
    tries = 0
    with tqdm(total=max_retries, desc="Validation attempts") as pbar_validation:
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


if __name__ == '__main__':
    app = (
        ApplicationBuilder()
        .with_state(
            **{
                "input_json": "",
                "output_schema": "",
            }
        )
        .with_actions(
            # bind the vector store to the AI conversational step
            validate_schema=validate_schema,
            create_jq_filter_query=create_jq_filter_query,
            validate_json=validate_json,
            error_state=burr.core.Result("chat_history"),
            good_result=burr.core.Result("chat_history"),
        )
        .with_transitions(
            ("validate_schema", "create_jq_filter_query", default),
            ("create_jq_filter_query", "validate_json", expr("'exit' in question")),
            ("validate_json", "good_result", expr("valid_json")),
            ("validate_schema", "good_result", expr("valid_schema")),
            ("validate_schema", "error_state", expr("not valid_schema")),
            ("create_jq_filter_query", "error_state", expr("max_retries_hit")),
            ("validate_json", "error_state", expr("max_retries_hit")),
        )
        .with_entrypoint("validate_schema")
        .with_tracker(project="example:jaiqu")
        .with_identifiers(partition_key="dagworks")
        .build()
    )
    app.visualize(
        output_file_path="jaiqu", include_conditions=True, view=True, format="png"
    )