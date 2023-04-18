import re
from typing import Any, Dict, Optional, ForwardRef, List


class TypeScriptGenerator:
    __all_types__: Dict[str, str] = {}
    __route_pattern__ = re.compile(r"<(\w+):(\w+)>")

    @staticmethod
    def get_all_types() -> str:
        result = ""
        for v in TypeScriptGenerator.__all_types__.values():
            result += f"{v}\n"
        return result + "\n"

    @staticmethod
    def get_all_routes(data, base_url) -> str:
        result = []
        for route_info in data:
            func_name = f"{TypeScriptGenerator.to_camel_case(route_info['func_name'])}"
            result.append(
                TypeScriptGenerator.__generate_function(route_info, func_name,
                                                        base_url))

        return '\n'.join(result)

    @classmethod
    def __generate_function(cls, route_info, func_name, base_url) -> str:
        headers = f'headers: new Headers({{"Content-Type": "application/json", "X-Request-Id": uuidv4(), "X-Fyrest-Session": session}})'
        method = route_info['method']

        if method == 'GET':
            return cls.__generate_get_function(route_info, func_name, headers,
                                               base_url)
        else:
            if route_info['accept_files']:
                headers = f'headers: new Headers({{"X-Request-Id": uuidv4(), "X-Fyrest-Session": session}})'
                return cls.__generate_post_function_with_files(
                    route_info, func_name, headers, base_url)
            else:
                return cls.__generate_post_function(route_info, func_name,
                                                    headers, base_url)

    @staticmethod
    def to_camel_case(s: str) -> str:
        s = s.strip('/').replace('-', '_')
        return ''.join(word.capitalize() if i > 0 else word
                       for i, word in enumerate(s.split('_')))

    @classmethod
    def get_typescript(cls, dataclass_obj: Any) -> str:
        if dataclass_obj.__name__ in cls.__all_types__:
            return cls.__all_types__[dataclass_obj.__name__]

        ts_type = cls.__generate_typescript(dataclass_obj)
        cls.__all_types__[dataclass_obj.__name__] = ts_type
        return ts_type

    @classmethod
    def __generate_typescript(cls, dataclass_obj: Any) -> str:
        field_lines = []
        print(dataclass_obj)
        for field_name, field in dataclass_obj.__dataclass_fields__.items():
            field_line = f"{field_name}: {cls.__convert_to_ts_type(field.type)};"
            field_lines.append(field_line)

        ts_type = "type %s = {\n  %s\n};" % (dataclass_obj.__name__,
                                             '\n  '.join(field_lines))
        return ts_type

    @classmethod
    def __convert_to_ts_type(cls, field_type: Any) -> str:
        print(field_type)

        if hasattr(field_type, "__dataclass_fields__"):
            cls.__generate_typescript(field_type)

        if isinstance(field_type, str):
            return field_type  # Return the string as is

        if field_type is int:
            return "number"
        if field_type is float:
            return "number"
        if field_type is str:
            return "string"
        if field_type is bool:
            return "boolean"

        if hasattr(field_type, "__dataclass_fields__"):
            cls.get_typescript(
                field_type)  # Add nested dataclasses to __all_types__
            return field_type.__name__

        if isinstance(field_type, ForwardRef):
            return f'{field_type.__forward_arg__}'

        if field_type.__name__ == "Optional":
            nested_type = cls.__convert_to_ts_type(field_type.__args__[0])
            return f"{nested_type} | null"

        if field_type.__name__ == "List":
            nested_type = cls.__convert_to_ts_type(field_type.__args__[0])
            return f"Array<{nested_type}>"

        return "any"

    @staticmethod
    def route_to_ts_params(route: str, files: bool = False) -> str:
        matches = TypeScriptGenerator.__route_pattern__.findall(route)
        args = []
        params = []
        _route = route
        for type_name, param_name in matches:
            ts_type = "any"
            if type_name == "int":
                ts_type = "number"
            elif type_name == "float":
                ts_type = "number"
            elif type_name == "string":
                ts_type = "string"
            params.append(f"{param_name}: {ts_type}")
            args.append([param_name, ts_type])
            _route = _route.replace('<', '').replace('>', '')
            _route = _route.replace(
                f"{type_name}:{param_name}",
                '${%s}' % TypeScriptGenerator.to_camel_case(param_name))

        params.append("params: { [key: string]: any }")
        if files:
            params.append("files: { [key: string]: File | Blob }")
        return f"{', '.join(params)}", _route, args

    @classmethod
    def __generate_get_function(cls, route_info, func_name, headers,
                                base_url) -> str:
        response_type = route_info['type']
        route_params, route_url, route_args = TypeScriptGenerator.route_to_ts_params(
            route_info['route'])
        route = route_info['route'].format(
            **{f"{arg[0]}": f"{{{arg[0]}}}" for arg in route_args})
        return f'''
export async function {func_name}({route_params}): Promise<{response_type}> {{
    const queryParams = Object.entries(params).map(([key, value]) => `${{encodeURIComponent(key)}}=${{encodeURIComponent(value)}}`).join('&');
    const url = `{base_url}{route_url}` + (queryParams ? `?${{queryParams}}` : '');
    const response = await fetch(url, {{
        method: '{route_info['method']}',
        {headers}
    }});
    return (await response.json()) as {response_type};
}}'''

    @classmethod
    def __generate_post_function_with_files(cls, route_info, func_name, headers,
                                            base_url) -> str:

        response_type = route_info['type']
        route_params, route_url, route_args = TypeScriptGenerator.route_to_ts_params(
            route_info['route'], True)
        route = route_info['route'].format(
            **{f"{arg[0]}": f"{{{arg[0]}}}" for arg in route_args})
        return f'''
export async function {func_name}({route_params}): Promise<{response_type}> {{
    const formData = new FormData();
    Object.entries(params).forEach(([key, value]) => formData.append(key, value));
    Object.entries(files).forEach(([key, file]) => formData.append(key, file));
    
    const url = `{base_url}{route_url}`;
    const response = await fetch(url, {{
        method: '{route_info['method']}',
        {headers},
        body: formData
    }});
    return (await response.json()) as {response_type};
}}'''

    @classmethod
    def __generate_post_function(cls, route_info, func_name, headers,
                                 base_url) -> str:
        response_type = route_info['type']
        route_params, route_url, route_args = TypeScriptGenerator.route_to_ts_params(
            route_info['route'])
        route = route_info['route'].format(
            **{f"{arg[0]}": f"{{{arg[0]}}}" for arg in route_args})
        return f'''
export async function {func_name}({route_params}): Promise<{response_type}> {{
    const url = `{base_url}{route_url}`;
    const response = await fetch(url, {{
        method: '{route_info['method']}',
        {headers},
        body: JSON.stringify(params)
    }});
    return (await response.json()) as {response_type};
}}'''
