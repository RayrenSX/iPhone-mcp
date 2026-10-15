"""Remove display-only JSON Schema titles without changing field names or validation."""
from mcp.server.fastmcp import FastMCP


def without_titles(value):
    if isinstance(value, list):
        return [without_titles(item) for item in value]
    if not isinstance(value, dict):
        return value
    result = {key: item for key, item in value.items() if key != "title"}
    # Only recurse into schema-bearing keywords. Other dictionaries can be literal
    # data or maps of field names (e.g. dependentRequired), including a name "title".
    for key in {"properties", "$defs", "definitions", "patternProperties", "dependentSchemas", "dependencies"}:
        if key in result:
            result[key] = {name: without_titles(schema) for name, schema in result[key].items()}
    for key in {"items", "prefixItems", "additionalItems", "contains", "unevaluatedItems",
                "additionalProperties", "unevaluatedProperties", "propertyNames", "contentSchema",
                "allOf", "anyOf", "oneOf", "not", "if", "then", "else"}:
        if key in result:
            result[key] = without_titles(result[key])
    return result


class LeanFastMCP(FastMCP):
    async def list_tools(self):
        tools = await super().list_tools()
        for tool in tools:
            tool.inputSchema = without_titles(tool.inputSchema)
        return tools
