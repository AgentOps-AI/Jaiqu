<p align="center">
  <img src="https://github.com/AgentOps-AI/Jaiqu/blob/8d4c66b2603bf14fedd2bf4c615c8919f79ece9f/jaiqu.png" height="300" alt="Jaiqu" />
</p>
<p align="center">
  <em>Natural language to DSL agent for JSON querying</em>
</p>
<p align="center">
    <a href="https://pypi.org/project/jaiqu/" target="_blank">
        <img alt="Python" src="https://img.shields.io/badge/python-3670A0?style=for-the-badge&logo=python&logoColor=ffdd54" />
        <img alt="Version" src="https://img.shields.io/pypi/v/jaiqu?style=for-the-badge&color=3670A0">
    </a>
</p>
<p align="center">
<a href="https://jaiqu-agent.streamlit.app/">🔗 Main site</a>
<span>&nbsp;&nbsp;•&nbsp;&nbsp;</span>
<a href="https://twitter.com/agentopsai/">🐦 Twitter</a>
<span>&nbsp;&nbsp;•&nbsp;&nbsp;</span>
<a href="https://discord.gg/JHPt4C7r">📢 Discord</a>
<span>&nbsp;&nbsp;•&nbsp;&nbsp;</span>
<a href="https://agentops.ai/?jaiqu">🖇️ AgentOps</a>
</p>

# Jaiqu

[![Streamlit App](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)]([https://<your-custom-subdomain>.streamlit.app](https://jaiqu-agent.streamlit.app)) [![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT) ![PyPI - Version](https://img.shields.io/pypi/v/jaiqu)
[![X (formerly Twitter) Follow](https://img.shields.io/twitter/follow/AgentOpsAI)](https://x.com/agentopsai)


Replicable, AI-generated JSON transformation queries. Transform any JSON into any schema automatically.

Jaiqu is an AI agent for creating repeatable JSON transforms using [jq query language](https://jqlang.github.io/jq/) syntax. Jaiqu translates any arbitrary JSON inputs into any desired schema.

Building AI agents? Check out [AgentOps](https://agentops.ai/?jaiqu)

[Live Demo](https://jaiqu-agent.streamlit.app)

[Video Overview](https://youtu.be/exbV35-XWA0)

![Alt text](architecture.png)


### Features
* **Translate any schema to any schema** AI agent automatically maps data from a source schema to a desired format by iteratively prompting GPT-4 to create valid jq query syntax.
* **Schema validation** Given a requirement schema, automatically validate whether the required data is present in the input json.
* **Fuzzy term matching** Infers keys based on symantic similarity (i.e. datetime vs date_time). GPT-4 automaticlaly maps and translates input keys to desired output keys.

### Example usage:

```python
from jaiqu import validate_schema, translate_schema

# Desired data format 
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
key_hints="We are processing outputs of an containing an id, a date, and a model. All the required fields should be present in this input, but the names might be different."
```

Validating an input json contains all the information required in a schema
```python
schema_properties, valid = validate_schema(input_json, schema, key_hints)

print(schema_properties)

>>> {
      "id": {
          "identified": true,
          "key": "call.id",
          "message": "123",
          "type": [
          "string",
          "null"
          ],
          "description": "A unique identifier for the record.",
          "required": true
      },
      "date": {
          "identified": true,
          "key": "datetime",
          "message": "2022-01-01",
          "type": "string",
          "description": "A string describing the date."
          "required": true
      }
    }
print(valid)
>>> True
```

Creating a repeatable jq query for extracitng data from identically formatted input JSONs
```python
jq_query = jaiqu.translate_schema(input_json, schema, key_hints, max_retries=30)
>>>'{"id": .attributes["call.id"], "date": .datetime}'
```

## Installation

#### Recommended: [PyPI](https://pypi.org/project/jaiqu/):

```bash
pip install jaiqu
```


## Architecture
Unraveling the Jaiqu agentic workflow pattern 
```mermaid
flowchart TD
    A[Start translate_schema] --> B{Validate input schema}
    B -- Valid --> C[For each key, create a jq filter query]
    B -- Invalid --> D[Throw RuntimeError]
    C --> E[Compile and Test jq Filter]
    E -- Success --> F[Validate JSON]
    E -- Fail --> G[Retry Create jq Filter]
    G -- Success --> E
    G -- Fail n times--> H[Throw RuntimeError]
    F -- Success --> I[Return jq query string]
    F -- Fail --> J[Retry Validate JSON]
    J -- Success --> I
    J -- Fail n times --> K[Throw RuntimeError]
```


## Running tests

0. Install `pytest` if you don't have it already

```shell
pip install pytest
```

1. Run the `tests/` folder while in the parent directory

```shell
pytest tests
```

This repo also supports `tox`, simply run `python -m tox`.

## Contributing

Contributions to Jaiqu are welcome! Feel free to create an [issue](https://github.com/AgentOps-AI/jaiqu/issues) for any bug reports, complaints, or feature suggestions.

## License

Jaiqu is released under the MIT License.
