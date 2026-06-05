"""OpenAPI 3.0 parser using prance."""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from models.schema import InterfaceDef

logger = logging.getLogger(__name__)


class OpenApiParser:
    """Parse OpenAPI 3.0 (JSON/YAML) specs into InterfaceDef list."""

    @staticmethod
    def parse(file_path: str) -> List[InterfaceDef]:
        """Parse an OpenAPI spec file and return a list of InterfaceDef."""
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"OpenAPI spec not found: {file_path}")

        try:
            import prance
        except ImportError:
            raise ImportError(
                "prance is required for OpenAPI parsing. "
                "Install with: pip install prance"
            )

        parser = prance.ResolvingParser(str(path), strict=False, recursion_limit=15)
        spec = parser.specification
        return OpenApiParser._extract_interfaces(spec)

    @staticmethod
    def _extract_interfaces(spec: Dict[str, Any]) -> List[InterfaceDef]:
        interfaces: List[InterfaceDef] = []
        paths = spec.get("paths", {})
        if not paths:
            return interfaces

        # Extract base info
        servers = spec.get("servers", [{}])
        base_url = servers[0].get("url", "") if servers else ""

        for path_url, path_item in paths.items():
            if not isinstance(path_item, dict):
                continue
            for method in ("get", "post", "put", "delete", "patch", "options",
                           "head"):
                operation = path_item.get(method)
                if not operation:
                    continue

                test_id = OpenApiParser._gen_test_id(method, path_url)
                api_name = (
                    operation.get("summary")
                    or operation.get("operationId")
                    or f"{method.upper()} {path_url}"
                )
                app_name = operation.get("tags", ["default"])[0] if operation.get(
                    "tags") else "default"

                # Extract request parameters
                request_head: Dict[str, Any] = {"Content-Type": "application/json"}
                request_body: Dict[str, Any] = {}
                status_code = 200

                # Parameters
                parameters = operation.get("parameters", [])
                for param in parameters:
                    if not isinstance(param, dict):
                        continue
                    param_in = param.get("in", "")
                    param_name = param.get("name", "")
                    if param_in == "header":
                        request_head[param_name] = OpenApiParser._schema_example(
                            param.get("schema", {}))
                    elif param_in == "query" and method.upper() == "GET":
                        request_body[param_name] = OpenApiParser._schema_example(
                            param.get("schema", {}))

                # Request body
                req_body = operation.get("requestBody", {})
                if req_body:
                    content = req_body.get("content", {})
                    json_content = content.get("application/json", {})
                    json_schema = json_content.get("schema", {})
                    request_body = OpenApiParser._schema_to_dict(json_schema)

                # Responses
                responses = operation.get("responses", {})
                # Find success status code
                for status_str in responses:
                    if status_str.startswith("2"):
                        status_code = int(status_str)
                        break

                # Assertions from expected response schema
                assert_dict = {"status_code": status_code}

                interfaces.append(InterfaceDef(
                    test_id=test_id,
                    api_name=api_name,
                    app_name=app_name,
                    method=method.upper(),
                    url=path_url,
                    request_head=request_head,
                    request_body=request_body,
                    status_code=status_code,
                    assert_dict=assert_dict,
                ))

        return interfaces

    @staticmethod
    def _gen_test_id(method: str, path: str) -> str:
        """Generate TestID like 'api_login_post'."""
        clean = path.strip("/").replace("/", "_").replace("-", "_").replace(
            "{", "").replace("}", "").lower()
        if clean:
            return f"api_{clean}_{method.lower()}"
        return f"api_root_{method.lower()}"

    @staticmethod
    def _schema_example(schema: Dict[str, Any]) -> Any:
        """Generate a placeholder/example value from a schema."""
        if not schema:
            return ""
        if "example" in schema:
            return schema["example"]
        if "default" in schema:
            return schema["default"]
        schema_type = schema.get("type", "string")
        if schema_type == "string":
            return "<string>"
        if schema_type == "integer":
            return 0
        if schema_type == "number":
            return 0.0
        if schema_type == "boolean":
            return False
        if schema_type == "array":
            return []
        if schema_type == "object":
            return {}
        return ""

    @staticmethod
    def _schema_to_dict(schema: Dict[str, Any]) -> Dict[str, Any]:
        """Convert an OpenAPI schema object to a dict with example values."""
        if not schema:
            return {}
        schema_type = schema.get("type", "object")
        if schema_type == "object":
            result = {}
            for prop_name, prop_schema in schema.get("properties", {}).items():
                result[prop_name] = OpenApiParser._schema_example(prop_schema)
            return result
        return {}
