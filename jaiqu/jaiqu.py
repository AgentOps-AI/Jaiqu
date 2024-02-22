
import jq
import json
from jsonschema import validate
from tqdm.auto import tqdm  # Use the auto submodule for notebook-friendly output if necessary
from .helpers import identify_key, create_jq_string, repair_query, dict_to_jq_filter


def validate_schema(input_json: dict, output_schema: dict, key_hints=None) -> tuple[dict, bool]:
    """Validates whether the required data in the output json schema is present in the input json."""
    """The input and output json should already be parsed into a dictionary"""
    results = {}
    valid = True
    with tqdm(total=len(output_schema['properties']), desc="Validating schema") as pbar:
        for key, value in output_schema['properties'].items():
            pbar.set_postfix_str(f"Key: {key}", refresh=True)
            response_key, response_reasoning = identify_key(key, value, input_json, key_hints)

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


def translate_schema(input_json, output_schema, key_hints=None, max_retries=10) -> str:
    """Translates the output schema into a jq filter to extract the required data from the input json."""

    schema_properties, is_valid = validate_schema(input_json, output_schema, key_hints)
    if not is_valid:
        raise RuntimeError(
            f"The input JSON does not contain the required data to satisfy the output schema: \n\n{json.dumps(schema_properties, indent=2)}")

    filtered_schema = {k: v for k, v in schema_properties.items() if v['identified'] == True}

    filter_query = {}

    with tqdm(total=len(filtered_schema), desc="Translating schema") as pbar, tqdm(total=max_retries, desc="Retry attempts") as pbar_retries:
        for key, value in filtered_schema.items():
            pbar.set_postfix_str(f"Key: {key}", refresh=True)
            jq_string = create_jq_string(input_json, key, value)

            if jq_string == "None":  # If the response is empty, skip the key
                pbar.update(1)
                continue

            tries = 0
            while True:
                try:
                    key_query = jq.compile(jq_string).input(input_json).all()
                    break
                except Exception as e:
                    tries += 1
                    pbar_retries.update(1)
                    jq_string = repair_query(jq_string, str(e), input_json)
                    if tries >= max_retries:
                        raise RuntimeError(
                            f"Failed to create a valid jq filter for key '{key}' after {max_retries} retries.")
            pbar.update(1)
            filter_query[key] = jq_string
        pbar.close()
        pbar_retries.close()
    complete_filter = dict_to_jq_filter(filter_query)
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
                    raise RuntimeError(f"Failed to validate the jq filter after {max_retries} retries.")
                complete_filter = repair_query(complete_filter, str(e), input_json)
        pbar.close()
    return complete_filter
