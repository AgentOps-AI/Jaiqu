from openai.types.chat.chat_completion_message_param import ChatCompletionMessageParam
from typing import Optional, Union
from openai import OpenAI


def to_key(response: str) -> Union[str, None]:
    """Extract the key from the response."""
    key = response.split('`')[-2]
    if key == "None":
        return None
    return key


def identify_key(key, value, input_schema, openai_api_key=None, key_hints=None) -> tuple[Optional[str], str]:
    """Identify if a key is present in a schema. This function uses the OpenAI API to generate a response."""

    system_message = """You are a perfect system designed to validate and extract data from JSON files. 
For each field, you provide a short check about your reasoning. Go line by line and do a side by side comparison. For example:

Schema:
{
    "id": "123",
    "date": "2022-01-01",
    "timestamp": 1640995200,
    "Address": "123 Main St",
    "input": "hello"
    "user": {
        "name": "John Doe",
        "age": 30,
        "contact": "john@email.com"
    }
}

"id" | "id" : The field name is identical. Extracted key: `id`
"Date" | "date" : The field name is the same except for capitalization. Extracted key: `date`
"time" | "timestamp": This is the same concept, therefore it counts. Extracted key: `timestamp`
"addr" | "Address": This is the same concept and is a , therefore it counts. Extracted key: `Address`
"cats" | None: There no matching or remotely similar fields. Extracted key: `None`
"input" | "input": The names match, but the types are different. Extracted key: `None`

If we are given hints, we can use them to help us determine if a key is present. For example, if the hint states we are searching for emails in a schema where "email" is not present, we can infer:
"email" | "contact": The names are different, but contact implies email. Extracted key: `contact`

Some fields may not have the exact same names. Use your best judgement about the meaning of the field to determine if they should count.
Think of the key you are searching for in relation to other keys in the schema; this may help you determine if the key is present.
The content of the field may also help you determine if the key is present. For example, if you are searching for a date, and the field contains a date, it is likely the key you are searching for.
You come to a definitive conclusion, the name of the key you found, at the end of your response."""

    if key_hints is not None:
        system_message += "\n\nAdditionally, consider the following: " + key_hints
    messages: list[ChatCompletionMessageParam] = [{
        "role": "system",
        "content": system_message
    },
        {
        "role": "user",
        "content": f"Is `{key}` of type `{value}` present in the desired schema?:\n\n  {input_schema}"
    }]

    reasoning_response = OpenAI(openai_api_key).chat.completions.create(messages=messages,
                                                          model="gpt-4",
                                                          #                                                         logit_bias={2575: 100, 4139: 100},
                                                          #                                                         max_tokens=1
                                                          )
    completion = str(reasoning_response.choices[0].message.content)

    return to_key(completion), completion


def create_jq_string(input_schema, key, value, openai_api_key) -> str:
    messages: list[ChatCompletionMessageParam] = [{
        "role": "system",
        "content": f"""You are a perfect jq engineer designed to validate and extract data from JSON files using jq. Only reply with code. Do NOT use any natural language. Do NOT use markdown i.e. ```.
                 
Your task is to create a jq filter to extract the data from the following JSON:

{input_schema}

You will be given the type of the key you need to extract. Only extract the key that corresponds to the type.

* Do NOT extract values based on exact indices.
* Do NOT create default values.
* If the key is not present and it is not required, DO NOT extract it. Return the literal value `None`. This is NOT a string, but the actual value `None`.

"""
    },
        {
        "role": "user",
        "content": f"Write jq to extract the key `{key}`of type `{value['type']}`"
    }]

    response = OpenAI(openai_api_key).chat.completions.create(messages=messages, model="gpt-4-0125-preview")
    return str(response.choices[0].message.content)


def repair_query(query, error, input_schema, openai_api_key):
    messages: list[ChatCompletionMessageParam] = [{
        "role": "system",
                "content": "You are a perfect jq engineer designed to validate and extract data from JSON files using jq. Only reply with code. Do NOT use any natural language. Do NOT use markdown i.e. ```."
    },
        {
        "role": "user",
                "content": f"""The following query returned an error while extracting from the following schema:
                
Query: {query}

Error: {error}

Schema: {input_schema}"""}]
    response = OpenAI(openai_api_key).chat.completions.create(messages=messages,
                                                model="gpt-4-0125-preview")
    return str(response.choices[0].message.content)


def dict_to_jq_filter(transformation_dict) -> str:
    jq_filter_parts = []
    for new_key, json_path in transformation_dict.items():
        # For each item in the dictionary, create a string '"new_key": json_path'
        # Note: json_path is assumed to be a valid jq path expression as a string
        jq_filter_parts.append(f'"{new_key}": {json_path}')

    # Join all parts with commas and wrap in braces to form a valid jq object filter
    jq_filter = "{ " + ",\n ".join(jq_filter_parts) + " }"
    return jq_filter
