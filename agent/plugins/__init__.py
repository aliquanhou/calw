"""Claw plugins — drop .py files here to add tools without modifying tools.py.

Each plugin must export a `register()` function that returns a PluginSpec dict:

    def register() -> dict:
        return {
            "name": "tool_name",                  # unique tool identifier
            "description": "What this tool does",  # description for LLM
            "input_schema": {...},                 # JSON schema for parameters
            "handler": my_handler,                 # handler(params_dict) -> str
        }

The handler receives a single dict argument with the tool parameters.
Return a string result.
"""
