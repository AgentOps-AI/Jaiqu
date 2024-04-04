import burr.core
from burr.core import ApplicationBuilder, State, default, expr, when
from burr.core.action import action

import jq
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


def translate_schema(input_json, output_schema, openai_api_key: str | None = None, key_hints=None,
                     max_retries=10) -> str:
    app = build_application(input_json, output_schema, openai_api_key, key_hints, max_retries)
    last_action, result, state = app.run(halt_after=["error_state", "good_result"])
    if last_action == "error_state":
        raise RuntimeError(result)
    return result["complete_filter"]


def build_application(input_json="", output_schema="", openai_api_key: str | None = None, key_hints=None,
                      max_retries=10):
    return (
        ApplicationBuilder()
        .with_state(
            **{
                "input_json": input_json,
                "output_schema": output_schema,
                "key_hints": key_hints,
                "max_retries": max_retries,
            }
        )
        .with_actions(
            # bind the vector store to the AI conversational step
            validate_schema=validate_schema,
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
        .with_tracker(project="example:jaiqu")
        .with_identifiers(partition_key="dagworks")
        .build()
    )


if __name__ == '__main__':
    app = build_application()
    app.visualize(
        output_file_path="jaiqu_port", include_conditions=True, view=True, format="png"
    )
    schema = {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "type": "object",
        "properties": {
            "id": {
                "type": ["string", "null"],
                "description": "A unique identifier for the record."
            },
            "date": {
                "type": "string",
                "description": "A string describing the date."
            },
            "model": {
                "type": "string",
                "description": "A text field representing the model used."
            }
        },
        "required": [
            "id",
            "date"
        ]
    }

    # Provided data
    input_json = {
        "call.id": "123",
        "datetime": "2022-01-01",
        "timestamp": 1640995200,
        "Address": "123 Main St",
        "user": {
            "name": "John Doe",
            "age": 30,
            "contact": "john@email.com"
        }
    }

    # (Optional) Create hints so the agent knows what to look for in the input
    key_hints = "We are processing outputs of an containing an id, a date, and a model. All the required fields should be present in this input, but the names might be different."

    print(translate_schema(input_json, schema, key_hints=key_hints))
