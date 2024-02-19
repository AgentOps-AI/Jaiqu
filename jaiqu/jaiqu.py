
import jq
import json
from jsonschema import validate
from .helpers import identify_key, create_jq_string, repair_query, dict_to_jq_filter


def validate_schema(input_json, output_schema, key_hints=None) -> tuple[dict, bool]:
    """Validates whether the required data in the output json schema is present in the input json."""
    results = {}
    valid = True
    for key, value in output_schema['properties'].items():
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

    return results, valid


def translate_schema(input_json, output_schema, key_hints=None,  max_retries=10) -> str:
    """Translates the output schema into a jq filter to extract the required data from the input json."""

    schema_properties, is_valid = validate_schema(input_json, output_schema, key_hints)
    if not is_valid:
        raise RuntimeError(
            f"The input JSON does not contain the required data to satisfy the output schema: \n\n{json.dumps(schema_properties, indent=2)}")

    filtered_schema = {k: v for k, v in schema_properties.items() if v['identified'] == True}

    tries = 0
    filter_query = {}

    for key, value in filtered_schema.items():
        jq_string = create_jq_string(input_json, key, value)

        if jq_string == "None":  # If the response is empty, skip the key
            continue

        while True:
            query = ""
            try:
                query = jq.compile(jq_string).input(input_json).all()
                break
            except Exception as e:
                tries += 1
                jq_string = repair_query(jq_string, str(e), input_json)
                if tries > max_retries:
                    raise RuntimeError(f"Failed to create a valid jq filter after {max_retries} retries.")

        filter_query[key] = jq_string

    complete_filter = dict_to_jq_filter(filter_query)
    # Validate JSON
    while True:
        try:
            result = jq.compile(complete_filter).input(input_json).all()[0]
            validate(instance=result, schema=output_schema)
            break
        except Exception as e:
            tries += 1
            if tries > max_retries:
                raise RuntimeError(f"Failed to create a valid jq filter after {max_retries} retries.")
            complete_filter = repair_query(complete_filter, str(e), input_json)

    return complete_filter
