import jq
from jaiqu import translate_schema


def test_translate_schema():
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

    new_schema = translate_schema(input_json, schema, key_hints=key_hints)
    # there are many permutations possible so we check the result rather than the schema...
    # some_possible_schemas = [
    #     '{ "id": (.["call.id"] // "None"), "date": (.datetime // "None") }',
    #     '{ "id": .["call.id"], "date": (.datetime // "None") }',
    #     '{ "id": .["call.id"] // "None", "date": .datetime // null }',
    #     '{ "id": (."call.id"? // "None"), "date": (.datetime? // "None") }',
    #     '{ "id": .["call.id"] // "None", "date": .datetime // "None" }',
    #     '{ "id": (.["call.id"] // "None"), "date": (.datetime // null) }'
    # ]
    actual = jq.compile(new_schema).input(input_json).all()
    assert actual == [{'id': '123', 'date': '2022-01-01'}]
