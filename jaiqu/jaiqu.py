import jq
from jsonschema import validate
from jsonschema.exceptions import ValidationError
from .helpers import identify_key, to_bool, create_jq_string, repair_query, dict_to_jq_filter


def validate_schema(input_json, output_schema):
    """Validates whether the required data in the output json schema is present in the input json."""
    results = {}
    valid = True
    for key, value in output_schema['properties'].items():
        response = identify_key(key, value, input_json)
        if to_bool(response):
            results[key] = {"identified": True, "message": response}
        else:
            results[key] = {"identified": False, "message": response}
        if key in output_schema['required']:
            results[key]['required'] = True
            if results[key]['identified'] == False:
                valid = False
        else:
            results[key]['required'] = False

    return results, valid


def translate_schema(input_json, output_schema) -> str:
    """Translates the output schema into a jq filter to extract the required data from the input json."""

    filter_query = {}

    for key, value in list(output_schema['properties'].items()):
        jq_string = create_jq_string(input_json, key, value)
        while True:
            print(jq_string)
            query = ""
            try:
                query = jq.compile(jq_string).input(input_json).all()
                break
            except Exception as e:
                continue
        print(query)
        filter_query[key] = jq_string

    complete_filter = dict_to_jq_filter(filter_query)
    # Validate JSON
    while True:
        try:
            result = jq.compile(complete_filter).input(input_json).all()[0]
            print(result)
            print(complete_filter)
            validate(instance=result, schema=output_schema)
            break
        except Exception as e:
            print(e)
            print('---')
            complete_filter = repair_query(complete_filter, str(e), input_json)

    return complete_filter
