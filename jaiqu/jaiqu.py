import json
from openai import OpenAI
import jq

from helpers import create_jq_string, repair_query, identify_key, to_bool, dict_to_jq_filter


def validate_schema(input_json, output_schema):
    """Validates whether the required data in the output json schema is present in the input json."""
    results = {}
    valid = True
    for key in output_schema['properties'].keys():
        response = identify_key(key, input_json)
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


def translate_schema(input_json, output_schema):
    """Translates the output schema into a jq filter to extract the required data from the input json."""

    filter_query = {}

    for key in list(output_schema['properties'].keys()):
        while True:
            jq_string = create_jq_string(input_json, key)
            print(jq_string)
            query = ""
            try:
                query = jq.compile(jq_string).input(input_json).all()
                break
            except Exception as e:
                repair_query(query, str(e), input_json)
        print(query)
        filter_query[key] = jq_string
    return dict_to_jq_filter(filter_query)
