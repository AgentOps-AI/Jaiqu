import streamlit as st
import json
import jq
from jaiqu import validate_schema, translate_schema

# Set page layout to wide
st.set_page_config(layout="wide")

# Title of the app
st.title('Jaiqu: JSON Schema to JQ Query')

st.header('Desired data format')
col1, col2 = st.columns(2)

with col1:
    schema_json = st.text_area('Enter the desired JSON schema', value=json.dumps({
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
    }, indent=2), height=200)

with col2:
    input_json_str = st.text_area('Enter the input JSON', value=json.dumps({
        "call.id": "123",
        "datetime": "2022-01-01",
        "timestamp": 1640995200,
        "Address": "123 Main St",
        "user": {
            "name": "John Doe",
            "age": 30,
            "contact": "john@email.com"
        }
    }, indent=2), height=200)

with col1:
    schema = json.loads(schema_json)
    st.json(schema, expanded=False)

with col2:
    input_json = json.loads(input_json_str)
    st.json(input_json, expanded=False)

st.write("---")  # This adds a horizontal line (break) in the Streamlit app

st.header('Optional Inputs')
opt_col1, opt_col2 = st.columns(2)

with opt_col1:
    key_hints = st.text_input('Enter any hints for key mapping',
                              value="We are processing outputs of an containing an id and a date of a user.")

with opt_col2:
    max_retries = st.number_input('Set maximum retries for translation', min_value=1, value=20, format="%d")

# Validate schema
if st.button('Validate Schema'):
    with st.spinner('Validating schema...'):
        schema_properties, valid = validate_schema(input_json, schema, key_hints)
        st.write('Schema is valid:', valid)
        st.json(schema_properties, expanded=False)

# Translate schema
if st.button('Translate Schema'):
    with st.spinner('Translating schema...'):
        jq_query = translate_schema(input_json, schema, key_hints=key_hints, max_retries=int(max_retries))
        st.text('Finalized jq query')
        st.code(jq_query)

        with st.spinner('Checking the jq query results...'):
            # Check the jq query results
            result = jq.compile(jq_query).input(input_json).all()
            st.write(result)
