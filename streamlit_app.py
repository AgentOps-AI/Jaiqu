import streamlit as st
import json
import jq
import os
from jaiqu import validate_schema, translate_schema
from agentops import Client

# Set page layout to wide
st.set_page_config(layout="wide", page_title="Jaiqu: AI JSON Schema to JQ Query Generator")

# Custom styles for Streamlit elements
st.markdown(
    """
    <style>
    .stTextArea {
        border: 2px solid #4CAF50;
        border-radius: 5px;
        padding: 10px; /* Increased padding */
        box-shadow: 0 4px 8px 0 rgba(0,0,0,0.2);
    }
    </style>
    """,
    unsafe_allow_html=True
)

# Title of the app with custom color
st.markdown("<h1 style='text-align: center; color: #4CAF50; padding: 0 1rem;'>Jaiqu: AI Schema to JQ Query Generator</h1>",
            unsafe_allow_html=True)  # Added horizontal padding to the title

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

st.markdown("<hr style='border-top: 3px solid #bbb; border-radius: 5px; margin: 0 1rem;'/>",  # Added horizontal margin to the horizontal line
            unsafe_allow_html=True)

st.header('Optional Inputs')
opt_col1, opt_col2 = st.columns(2)

with opt_col1:
    key_hints = st.text_area('Enter any hints for key mapping',
                             value="We are processing outputs of an containing an id and a date of a user.", height=100)

with opt_col2:
    max_retries = st.number_input('Set maximum retries for translation', min_value=1,
                                  value=20, format="%d")
    openai_api_key = st.text_input('Enter your OpenAI API key', type="password")
    if openai_api_key:
        os.environ['OPENAI_API_KEY'] = openai_api_key

# Validate schema
if st.button('Validate Schema', key="validate_schema"):
    with st.spinner('Validating schema...'):
        validation_session = Client(tags=["jaiqu", "schema-validation"])
        schema_properties, valid = validate_schema(input_json, schema, key_hints)
        st.write('Schema is valid:', valid)
        st.json(schema_properties, expanded=False)
        validation_session.end_session('Success' if valid else 'Fail', end_state_reason='Schema validation complete')

# Translate schema
if st.button('Translate Schema', key="translate_schema"):
    with st.spinner('Translating schema...'):
        translation_session = Client(tags=["jaiqu", "schema-translation"])
        jq_query = translate_schema(input_json, schema, key_hints=key_hints, max_retries=int(max_retries))
        st.text('Finalized jq query')
        st.code(jq_query, language="jq")

        with st.spinner('Checking the jq query results...'):
            # Check the jq query results
            st.text('JQ query results')
            try:
                result = jq.compile(jq_query).input(input_json).all()[0]
                st.write(result)
                translation_session.end_session('Success', end_state_reason='Schema translation complete')

            except Exception as e:
                st.error(f"Error: {e}")
                translation_session.end_session('Fail', end_state_reason='Schema translation failed')
