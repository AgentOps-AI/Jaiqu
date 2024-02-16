from openai.types.chat.chat_completion_message_param import ChatCompletionMessageParam
from jaiqu import client


def identify_key(key, value, input_schema) -> str:
    """Identify if a key is present in a schema. This function uses the OpenAI API to generate a response."""

    messages = [{
        "role": "system",
        "content": """You are a perfect system designed to validate and extract data from JSON files. 
For each field, you provide a short check about your reasoning. Go line by line and do a side by side comparison. For example:

"id" | "id" : The field name is identical. True.
"time" | "timestamp": This is the same concept, therefore it counts. True.
"addr" | "Address": This is the same concept and is a , therefore it counts. True.
"cats" | None: There no matching or remotely similar fields. False.
"input" | "input": The names match, but the types are different. False.

Some fields may not have the exact same names. Use your best judgement about the meaning of the field to determine if they should count.

You come to a definitive conclusion- True or False at the end of your response."""
    },
        {
        "role": "user",
        "content": f"Is `{key}` of type `{value}` present in the desired schema:\n\n  {input_schema}"
    }]

    reasoning_response = client.chat.completions.create(messages=messages,
                                                        model="gpt-4",
                                                        #                                                         logit_bias={2575: 100, 4139: 100},
                                                        #                                                         max_tokens=1
                                                        )
    return str(reasoning_response.choices[0].message.content)


def to_bool(response: str) -> bool:
    if 'true' in response.lower():
        return True
    return False


def create_jq_string(input_schema, key, value) -> str:
    messages = [{
        "role": "system",
        "content": f"""You are a perfect jq engineer designed to validate and extract data from JSON files using jq. Only reply with code. Do NOT use any natural language. Do NOT use markdown i.e. ```.
                 
Your task is to create a jq filter to extract the data from the following JSON:

{input_schema}

You will be given the type of the key you need to extract. Only extract the key that corresponds to the type.

Do NOT extract values based on exact indices.
"""
    },
        {
        "role": "user",
        "content": f"Write jq to extract the key `{key}`of type `{value['type']}`"
    }]

    response = client.chat.completions.create(messages=messages, model="gpt-4-0125-preview")
    return str(response.choices[0].message.content)


def repair_query(query, error, input_schema):
    messages = [{
                "role": "system",
                "content": "You are a perfect jq engineer designed to validate and extract data from JSON files using jq. Only reply with code. Do NOT use any natural language. Do NOT use markdown i.e. ```."
                },
                {
                "role": "user",
                "content": f"""The following query returned an error while extracting from the following schema:
                
Query: {query}

Error: {error}

Schema: {input_schema}"""}]
    response = client.chat.completions.create(messages=messages,
                                              model="gpt-4-0125-preview")
    return response.choices[0].message.content


def dict_to_jq_filter(transformation_dict) -> str:
    jq_filter_parts = []
    for new_key, json_path in transformation_dict.items():
        # For each item in the dictionary, create a string '"new_key": json_path'
        # Note: json_path is assumed to be a valid jq path expression as a string
        jq_filter_parts.append(f'"{new_key}": {json_path}')

    # Join all parts with commas and wrap in braces to form a valid jq object filter
    jq_filter = "{ " + ",\n ".join(jq_filter_parts) + " }"
    return jq_filter
