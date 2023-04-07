import time
import re
from dataclasses import dataclass
from typing import Dict, List, Union, Callable, Any
from flask import request, Flask, jsonify
from flask.cli import with_appcontext
from functools import wraps
import click


routeArgs = re.compile(r'\<(.*?)\>')


@dataclass
class APIResponse:
    success: bool
    data: Any = None
    message: str = None
    time: float = None
        
class RestContext:
    def __init__(self, headers, req, load_user: Callable[[], Any], refresh_user: Callable[[], Any]):
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
        self.load_user = load_user
        self.refresh_user = refresh_user
        self.request_id = self.headers.get('x-request-id')

        if self.req in ['user', 'admin']:
            self.loadUser()

        if self.header_session:
            self.session = self.header_session
            
    def get_time(self):
        return time.time_ns() - self.start
    
    def refresh_user(self):
        if self.refresh_user:
            self.refresh_user()

    def loadUser(self):
        if self.load_user:
            self.user = self.load_user()
            self.hasUser = self.user is not None
            self.isAdmin = self.user and self.user.is_admin

class RestAPI:
    def __init__(self, app: Flask = None, base_url="http://localhost:5000", load_user: Callable = None, refresh_user: Callable = None):
        self.__APIDoc__ = {}
        self.__APIDocSubtypes__ = {}
        self.__APIRoute2Type__ = []
        self.__TSTypes__ = {
            'bool': 'boolean',
            'str': 'string',
            'float': 'number',
            'int': 'number',
            'NoneType': 'null',
            'Any': 'unknown'
        }
        self.app = app
        self.load_user = load_user
        self.refresh_user = refresh_user
        self.base_url = 'http://localhost:5000'
        if app is not None:
            self.init_app(app)

    def init_app(self, app: Flask):
        if not hasattr(app, 'extensions'):
            app.extensions = {}
        app.extensions['restapi'] = self
        app.route = self.route_decorator(app.route)
        app.cli.add_command(self.get_types_command)
        app.cli.add_command(self.get_fetch_command)
        app.cli.add_command(self.get_all_command)
        
    @click.command("rest-get-types", help="Print API TypeScript types")
    @with_appcontext
    def get_types_command(self):
        print(self.get_typescript_types())

    @click.command("rest-get-fetch", help="Print API TypeScript fetch functions")
    @with_appcontext
    def get_fetch_command(self):
        print(self.generate_typescript_fetch_functions())

    @click.command("rest-all", help="Print API TypeScript types and fetch functions")
    @with_appcontext
    def get_all_command(self):
        print('import { v4 as uuidv4 } from "uuid";')
        print(self.get_typescript_types())
        print(self.generate_typescript_fetch_functions()) 
        
    def route_decorator(self, original_route):
        def new_route_decorator(*args, **kwargs):
            req = kwargs.pop('req', None)  # Add this line to get the 'req' parameter

            if 'response_type' in kwargs:
                response_type = kwargs.pop('response_type')
                methods = kwargs.get('methods', ['GET'])
                self.add_type_information(args[0], methods, response_type, req)
            def decorator(f):
                if req:
                    @wraps(f)
                    def wrapped(*f_args, **f_kwargs):
                        rest_context = RestContext(request.headers, request, self.load_user, self.refresh_user)

                        if req == 'user' and not rest_context.hasUser:
                            return jsonify(APIResponse(False, message="Unauthorized").__dict__), 401
                        elif req == 'admin' and not rest_context.isAdmin:
                            return jsonify(APIResponse(False, message="Forbidden").__dict__), 403

                        return f(rest_context, *f_args, **f_kwargs)
                else:
                    @wraps(f)
                    def wrapped(*f_args, **f_kwargs):
                        rest_context = RestContext(request.headers, request, self.load_user, self.refresh_user)
                        return f(rest_context, *f_args, **f_kwargs)

                return original_route(*args, **kwargs)(wrapped)

            return decorator
        return new_route_decorator

    def add_type_information(self, endpoint, methods, response_type,  req=None):
        types = {f.name: self.__TSTypes__.get(f.type.__name__, f.type.__name__) for f in response_type.__dataclass_fields__.values()}
        name = response_type.__name__
        _endpoint = endpoint
        _args = []
        for m in routeArgs.findall(endpoint):
            _endpoint = _endpoint.replace('<', '').replace('>', '')
            _argsType, _argName = m.split(':')
            _endpoint = _endpoint.replace(m, '${%s}' % _argName)
            _args.append([_argName, _argsType])

        self.__APIDoc__[name] = dict(route=endpoint, methods=methods, response=types, name=name)
        self.__APIRoute2Type__.append({'route': _endpoint, 'type': name, 'method': methods[0], 'name': name, 'args': _args, 'req': req})
        
    def get_api_types(self) -> Dict[str, Dict[str, str]]:
        return self.__APIDoc__

    def get_typescript_types(self) -> str:
        def process_type(t: type) -> str:
            if t.__name__ in self.__TSTypes__:
                return self.__TSTypes__[t.__name__]
            elif t.__name__ == 'List':
                subtype = t.__args__[0]
                return f'Array<{process_type(subtype)}>'
            else:
                return t.__name__

        def generate_types(cls: type) -> str:
            result = f'export interface {cls.__name__} {{\n'
            for field in cls.__dataclass_fields__.values():
                result += f"  {field.name}: {process_type(field.type)};\n"
            result += '}\n\n'
            return result

        visited_types = set()
        result_types = []

        def visit_type(cls):
            if cls in visited_types or cls in self.__TSTypes__:
                return
            visited_types.add(cls)
            if hasattr(cls, '__dataclass_fields__'):
                for field in cls.__dataclass_fields__.values():
                    visit_type(field.type)
                result_types.append(generate_types(cls))

        for cls in self.__APIDoc__.values():
            response_type_name = cls['name']
            response_type = globals()[response_type_name]
            visit_type(response_type)

        return ''.join(result_types)

    def generate_typescript_fetch_functions(self) -> str:
        result = []
        def to_camel_case(s: str) -> str:
            s = s.strip('/').replace('-', '_')
            return ''.join(word.capitalize() if i > 0 else word for i, word in enumerate(s.split('_')))

        for route_info in self.__APIRoute2Type__:
            route = route_info['route']
            method = route_info['method']
            response_type = route_info['type']
            func_name = f"{to_camel_case(route)}Fetch"


            headers = f'headers: new Headers({{"Content-Type": "application/json", "X-Request-Id": uuidv4(), "X-Fyrest-Session": session}})'

            if method == 'GET':
                result.append(f'''
    export async function {func_name}(params: {{ [key: string]: any }}): Promise<{response_type}> {{
        const queryParams = Object.entries(params).map(([key, value]) => `${{encodeURIComponent(key)}}=${{encodeURIComponent(value)}}`).join('&');
        const url = `{self.base_url}{route}` + (queryParams ? `?${{queryParams}}` : '');
        const response = await fetch(url, {{
            method: '{method}',
            {headers}
        }});
        return (await response.json()) as {response_type};
    }}
    ''')
            else:
                result.append(f'''
    export async function {func_name}(params: {{ [key: string]: any }}): Promise<{response_type}> {{
        const response = await fetch(`{self.base_url}{route}`, {{
            method: '{method}',
            {headers},
            body: JSON.stringify(params)
        }});
        return (await response.json()) as {response_type} & {{ success: boolean }};
    }}
    ''')

        return '\n'.join(result)
