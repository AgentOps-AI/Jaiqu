
import jq
import json
from jsonschema import validate
from tqdm.auto import tqdm  # Use the auto submodule for notebook-friendly output if necessary
from .helpers import identify_key, create_jq_string, repair_query, dict_to_jq_filter


def validate_schema(input_json: dict, output_schema: dict, openai_api_key: str | None = None, key_hints=None) -> tuple[dict, bool]:
    """Validates the schema of the input JSON against the output schema.
    Args:
        input_json (dict): The input JSON parsed into a dictionary.
        output_schema (dict): The output schema against which the input JSON schema needs to be validated.
        openai_api_key (str | None, optional): The OpenAI API key. Defaults to None.
        key_hints (any, optional): Key hints to assist in identifying keys. Defaults to None.

    Returns:
        tuple[dict, bool]: A tuple containing the results of the validation and a boolean indicating if the validation was successful.
    """

    results = {}
    valid = True
    with tqdm(total=len(output_schema['properties']), desc="Validating schema") as pbar:
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


def translate_schema(input_json, output_schema, openai_api_key: str | None = None, key_hints=None, max_retries=10) -> str:
    """
    Translate the input JSON schema into a filtering query using jq.

    Args:
        input_json (dict): The input JSON to be reformatted.
        output_schema (dict): The desired output schema using standard schema formatting.
        openai_api_key (str, optional): OpenAI API key. Defaults to None.
        key_hints (None, optional): Hints for translating keys. Defaults to None.
        max_retries (int, optional): Maximum number of retries for creating a valid jq filter. Defaults to 10.

    Returns:
        str: The filtering query in jq syntax.

    Raises:
        RuntimeError: If the input JSON does not contain the required data to satisfy the output schema.
        RuntimeError: If failed to create a valid jq filter after maximum retries.
        RuntimeError: If failed to validate the jq filter after maximum retries.
    """

    schema_properties, is_valid = validate_schema(input_json, output_schema, key_hints)
    if not is_valid:
        raise RuntimeError(
            f"The input JSON does not contain the required data to satisfy the output schema: \n\n{json.dumps(schema_properties, indent=2)}")

    filtered_schema = {k: v for k, v in schema_properties.items() if v['identified'] == True}

    filter_query = {}

    with tqdm(total=len(filtered_schema), desc="Translating schema") as pbar, tqdm(total=max_retries, desc="Retry attempts") as pbar_retries:
        for key, value in filtered_schema.items():
            pbar.set_postfix_str(f"Key: {key}", refresh=True)
            jq_string = create_jq_string(input_json, key, value, openai_api_key)

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
                    jq_string = repair_query(jq_string, str(e), input_json, openai_api_key)
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
                complete_filter = repair_query(complete_filter, str(e), input_json, openai_api_key)
        pbar.close()
    return complete_filter
