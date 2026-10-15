import copy
import unittest

from iphonemirror_mcp.schema import without_titles


class SchemaTests(unittest.TestCase):
    def test_dependency_names_and_extension_data_are_not_schema_titles(self):
        schema = {"title": "Root", "type": "object",
                  "dependentRequired": {"title": ["subtitle"]},
                  "dependencies": {"title": ["subtitle"], "other": {"title": "Dependency", "required": ["title"]}},
                  "x-metadata": {"title": "literal extension title"},
                  "if": {"title": "Condition", "required": ["title"]},
                  "then": {"title": "Then", "required": ["subtitle"]}}
        result = without_titles(schema)
        self.assertEqual(result["dependentRequired"], {"title": ["subtitle"]})
        self.assertEqual(result["dependencies"], {"title": ["subtitle"], "other": {"required": ["title"]}})
        self.assertEqual(result["x-metadata"], {"title": "literal extension title"})
        self.assertEqual(result["if"], {"required": ["title"]})
        self.assertEqual(result["then"], {"required": ["subtitle"]})

    def test_only_schema_titles_are_removed_field_names_and_defaults_are_preserved(self):
        schema = {"title": "Arguments", "type": "object", "properties": {
            "title": {"title": "Title", "type": "string", "minLength": 1},
            "position": {"anyOf": [{"$ref": "#/$defs/Point"}, {"type": "null"}], "default": None},
            "options": {"type": "object", "default": {"title": "literal data"},
                        "examples": [{"title": "example data"}]}},
            "required": ["title"], "$defs": {"Point": {"title": "Point", "type": "object",
                "properties": {"x": {"title": "X", "type": "number", "minimum": 0}},
                "required": ["x"], "additionalProperties": False}}}
        original = copy.deepcopy(schema)
        result = without_titles(schema)
        self.assertNotIn("title", result)
        self.assertEqual(result["properties"]["title"], {"type": "string", "minLength": 1})
        self.assertEqual(result["properties"]["options"]["default"], {"title": "literal data"})
        self.assertEqual(result["properties"]["options"]["examples"], [{"title": "example data"}])
        self.assertEqual(result["properties"]["position"], schema["properties"]["position"])
        self.assertEqual(result["required"], ["title"])
        self.assertNotIn("title", result["$defs"]["Point"])
        self.assertEqual(result["$defs"]["Point"]["properties"]["x"], {"type": "number", "minimum": 0})
        self.assertFalse(result["$defs"]["Point"]["additionalProperties"])
        self.assertEqual(schema, original)
