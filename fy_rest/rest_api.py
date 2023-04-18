import time
import re
from dataclasses import dataclass
from typing import Dict, Callable, Any, List
from flask import request, Flask, jsonify, current_app, Response
from flask.cli import with_appcontext
from functools import wraps
import click
import __main__

routeArgs = re.compile(r'\<(.*?)\>')


class TypeScriptGenerator:
    __TSTypes__ = {
        'Optional[float]': 'number',
        'bool': 'boolean',
        'str': 'string',
        'float': 'number',
        'int': 'number',
        'NoneType': 'null',
        'Any': 'unknown'
    }

    def __init__(self, rest_api: "RestAPI"):
        self.rest_api = rest_api

    def process_type(self, t: type) -> str:
        if t.__name__ in TypeScriptGenerator.__TSTypes__:
            return TypeScriptGenerator.__TSTypes__[t.__name__]
        elif t.__name__ == 'List':
            subtype = t.__args__[0]
            return f'Array<{self.process_type(subtype)}>'
        else:
            return t.__name__

    def to_camel_case(self, s: str) -> str:
        s = s.strip('/').replace('-', '_')
        return ''.join(word.capitalize() if i > 0 else word
                       for i, word in enumerate(s.split('_')))

    def generate_typescript_types(self) -> str:
        visited_types = set()
        result_types = []

        def visit_type(cls):
            if cls in visited_types or cls in TypeScriptGenerator.__TSTypes__:
                return
            visited_types.add(cls)
            if hasattr(cls, '__dataclass_fields__'):
                for field in cls.__dataclass_fields__.values():
                    visit_type(field.type)
                result_types.append(self.generate_types(cls))

        for cls in RestAPI.__APIDoc__.values():
            response_type_name = cls['name']
            response_type = RestAPI.__RegisteredTypes__[response_type_name]
            visit_type(response_type)

        return ''.join(result_types)

    def generate_types(self, cls: type) -> str:
        result = f'export interface {cls.__name__} {{\n'
        for field in cls.__dataclass_fields__.values():
            result += f"  {field.name}: {self.process_type(field.type)};\n"
        result += '}\n\n'
        return result

    def generate_typescript_fetch_functions(self) -> str:
        result = []

        for route_info in RestAPI.__APIRoute2Type__:
            func_name = f"{self.to_camel_case(route_info['func_name'])}"
            result.append(self.generate_function(route_info, func_name))

        return '\n'.join(result)

    def generate_function(self, route_info, func_name) -> str:
        headers = f'headers: new Headers({{"Content-Type": "application/json", "X-Request-Id": uuidv4(), "X-Fyrest-Session": session}})'
        route = route_info['route'].format(
            **{f"{arg[0]}": f"{{{arg[0]}}}" for arg in route_info['args']})
        method = route_info['method']
        response_type = route_info['type']

        if method == 'GET':
            return self.generate_get_function(route_info, func_name, headers)
        else:
            if route_info['accept_files']:
                headers = f'headers: new Headers({{"X-Request-Id": uuidv4(), "X-Fyrest-Session": session}})'
                return self.generate_post_function_with_files(
                    route_info, func_name, headers)
            else:
                return self.generate_post_function(route_info, func_name,
                                                   headers)

    def generate_get_function(self, route_info, func_name, headers) -> str:
        route = route_info['route'].format(
            **{f"{arg[0]}": f"{{{arg[0]}}}" for arg in route_info['args']})
        response_type = route_info['type']

        return f'''
export async function {func_name}({', '.join([f"{arg[0]}: {arg[1]}" for arg in route_info['args']] + ['params: { [key: string]: any }'])}): Promise<{response_type}> {{
    const queryParams = Object.entries(params).map(([key, value]) => `${{encodeURIComponent(key)}}=${{encodeURIComponent(value)}}`).join('&');
    const url = `{self.rest_api.base_url}{route}` + (queryParams ? `?${{queryParams}}` : '');
    const response = await fetch(url, {{
        method: '{route_info['method']}',
        {headers}
    }});
    return (await response.json()) as {response_type};
}}'''

    def generate_post_function_with_files(self, route_info, func_name,
                                          headers) -> str:
        route = route_info['route'].format(
            **{f"{arg[0]}": f"{{{arg[0]}}}" for arg in route_info['args']})
        response_type = route_info['type']

        return f'''
export async function {func_name}({', '.join([f"{arg[0]}: {arg[1]}" for arg in route_info['args']] + ['params: { [key: string]: any }', 'files: { [key: string]: File | Blob }'])}): Promise<{response_type}> {{
    const formData = new FormData();
    Object.entries(params).forEach(([key, value]) => formData.append(key, value));
    Object.entries(files).forEach(([key, file]) => formData.append(key, file));
    
    const url = `{self.rest_api.base_url}{route}`;
    const response = await fetch(url, {{
        method: '{route_info['method']}',
        {headers},
        body: formData
    }});
    return (await response.json()) as {response_type};
}}'''

    def generate_post_function(self, route_info, func_name, headers) -> str:
        route = route_info['route'].format(
            **{f"{arg[0]}": f"{{{arg[0]}}}" for arg in route_info['args']})
        response_type = route_info['type']

        return f'''
export async function {func_name}({', '.join([f"{arg[0]}: {arg[1]}" for arg in route_info['args']] + ['params: { [key: string]: any }'])}): Promise<{response_type}> {{
    const url = `{self.rest_api.base_url}{route}`;
    const response = await fetch(url, {{
        method: '{route_info['method']}',
        {headers},
        body: JSON.stringify(params)
    }});
    return (await response.json()) as {response_type};
}}'''


@dataclass
class APIResponse:
    success: bool
    data: Any = None
    message: str = None
    time: float = None


class RestContext:

    def __init__(self, headers, req, load_user: Callable[[], Any],
                 refresh_user: Callable[[], Any]):
        self.uuid = False
        self.start = time.time_ns()
        self.headers = headers
        self.userUuid = None
        self.user = None
        self.hasUser = False
        self.isAdmin = False
        self.session = None
        self.req = req
        self.header_session = self.headers.get('x-fy-session') or None
        self.load_user_fct = load_user
        self.refresh_user_fct = refresh_user
        self.request_id = self.headers.get('x-request-id')

        if self.req in ['user', 'admin']:
            self.loadUser()

        if self.header_session:
            self.session = self.header_session

    def get_time(self):
        return (time.time_ns() - self.start) / 1000000000

    def refresh_user(self):
        if self.refresh_user_fct:
            self.refresh_user_fct()

    def load_user(self):
        if self.load_user_fct:
            self.user = self.load_user_fct()
            self.hasUser = self.user is not None
            self.isAdmin = self.user and self.user.is_admin


class RestAPI:
    __APIDoc__ = {}
    __APIRoute2Type__ = []
    __RegisteredTypes__ = {}

    def __init__(self,
                 app: Flask = None,
                 base_url="http://localhost:5000",
                 load_user: Callable = None,
                 refresh_user: Callable = None):
        self.app = app
        self.load_user = load_user
        self.refresh_user = refresh_user
        self.base_url = 'http://localhost:5000'
        if app is not None:
            self.init_app(app)

    def register_blueprint(self, blueprint):
        blueprint.route = self.route_decorator(blueprint.route)

    def init_app(self, app: Flask):
        if not hasattr(app, 'extensions'):
            app.extensions = {}
        app.extensions['restapi'] = self
        app.route = self.route_decorator(app.route)

        @app.route('/ts')
        def ts(ctx):
            response = Response(self.get_all(), content_type='text/plain')
            return response

        app.cli.add_command(RestAPI.get_all_command)

    @click.command("rest-all",
                   help="Print API TypeScript types and fetch functions")
    @with_appcontext
    @staticmethod
    def get_all_command():
        print('import { v4 as uuidv4 } from "uuid";')
        rest_api = current_app.extensions['restapi']
        ts_gen = TypeScriptGenerator(self)
        types = ts_gen.generate_typescript_types()
        fetchs = ts_gen.generate_typescript_fetch_functions()
        print(types)
        print(fetchs)

    def get_all(self):
        ts_gen = TypeScriptGenerator(self)
        types = ts_gen.generate_typescript_types()
        fetchs = ts_gen.generate_typescript_fetch_functions()
        base = ''  #:import { v4 as uuidv4 } from "uuid";
        return f'''{base}\n{types}\n{fetchs}'''

    def route_decorator(self, original_route):

        def new_route_decorator(*args, **kwargs):
            req = kwargs.pop('req',
                             None)  # Add this line to get the 'req' parameter

            accept_files = None
            if 'accept_files' in kwargs:
                accept_files = kwargs.pop('accept_files')

            def decorator(f):
                if 'response_type' in kwargs:
                    response_type = kwargs.pop('response_type')
                    methods = kwargs.get('methods', ['GET'])
                    self.add_type_information(args[0], methods, response_type,
                                              req, f.__name__, accept_files)
                    self.register_type_recursively(response_type)

                if req:

                    @wraps(f)
                    def wrapped(*f_args, **f_kwargs):
                        rest_context = RestContext(request.headers, request,
                                                   self.load_user,
                                                   self.refresh_user)

                        if req == 'user' and not rest_context.hasUser:
                            return jsonify(
                                APIResponse(
                                    False,
                                    message="Unauthorized").__dict__), 401
                        elif req == 'admin' and not rest_context.isAdmin:
                            return jsonify(
                                APIResponse(False,
                                            message="Forbidden").__dict__), 403

                        return f(rest_context, *f_args, **f_kwargs)
                else:

                    @wraps(f)
                    def wrapped(*f_args, **f_kwargs):
                        rest_context = RestContext(request.headers, request,
                                                   self.load_user,
                                                   self.refresh_user)
                        return f(rest_context, *f_args, **f_kwargs)

                return original_route(*args, **kwargs)(wrapped)

            return decorator

        return new_route_decorator

    def add_type_information(self,
                             endpoint,
                             methods,
                             response_type,
                             req=None,
                             func_name=None,
                             accept_files=None):
        types = {
            f.name: TypeScriptGenerator.__TSTypes__.get(f.type.__name__,
                                                        f.type.__name__)
            for f in response_type.__dataclass_fields__.values()
        }
        name = response_type.__name__
        _endpoint = endpoint
        _args = []
        for m in routeArgs.findall(endpoint):
            _endpoint = _endpoint.replace('<', '').replace('>', '')
            _argsType, _argName = m.split(':')
            _endpoint = _endpoint.replace(m, '${%s}' % _argName)
            _args.append([_argName, TypeScriptGenerator.__TSTypes__[_argsType]])

        RestAPI.__APIDoc__[name] = dict(route=endpoint,
                                        methods=methods,
                                        response=types,
                                        name=name)
        RestAPI.__APIRoute2Type__.append({
            'route': _endpoint,
            'type': name,
            'method': methods[0],
            'name': name,
            'args': _args,
            'req': req,
            'func_name': func_name,
            'accept_files': accept_files
        })

    def get_api_types(self) -> Dict[str, Dict[str, str]]:
        return RestAPI.__APIDoc__

    def register_types(self, t: List[type]):
        for _t in t:
            self.register_type(_t)

    def register_type(self, t: type) -> None:
        RestAPI.__RegisteredTypes__[t.__name__] = t

    def register_type_recursively(self, t: type):
        if t.__name__ in RestAPI.__RegisteredTypes__ or t.__name__ in TypeScriptGenerator.__TSTypes__:
            return
        self.register_type(t)
        if hasattr(t, '__dataclass_fields__'):
            for field in t.__dataclass_fields__.values():
                if field.type.__name__ not in TypeScriptGenerator.__TSTypes__:
                    self.register_type_recursively(field.type)
