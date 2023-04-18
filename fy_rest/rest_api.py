import time
import re
from dataclasses import dataclass
from typing import Dict, Callable
from flask import request, Flask, jsonify, current_app, Response
from flask.cli import with_appcontext
from functools import wraps
from .typescript import TypeScriptGenerator
import click
import __main__

@dataclass
class APIResponse:
    success: bool
    data: any = None
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
        TypeScriptGenerator.get_typescript(APIResponse)
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
                 refresh_user: Callable = None,
                 before_ts=''):
        self.app = app
        self.load_user = load_user
        self.refresh_user = refresh_user
        self.base_url = base_url
        self.before_ts = before_ts + "\n"
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
        print(rest_api.before_ts)
        print(TypeScriptGenerator.get_all_types())
        print(
            TypeScriptGenerator.get_all_routes(RestAPI.__APIRoute2Type__,
                                               self.base_url))

    def get_all(self):
        base = self.before_ts
        types = TypeScriptGenerator.get_all_types()
        fetchs = TypeScriptGenerator.get_all_routes(RestAPI.__APIRoute2Type__,
                                                    self.base_url)
        return f'''{base}\n{types}\n{fetchs}'''

    def route_decorator(self, original_route):

        def new_route_decorator(*args, **kwargs):
            req = kwargs.pop('req', None)

            accept_files = None
            if 'accept_files' in kwargs:
                accept_files = kwargs.pop('accept_files')

            def decorator(f):
                if 'response_type' in kwargs:
                    response_type = kwargs.pop('response_type')
                    methods = kwargs.get('methods', ['GET'])
                    self.add_type_information(args[0], methods, response_type,
                                              req, f.__name__, accept_files)

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

        TypeScriptGenerator.get_typescript(response_type)

        RestAPI.__APIRoute2Type__.append({
            'route': endpoint,
            'type': response_type.__name__,
            'method': methods[0],
            'name': response_type.__name__,
            'req': req,
            'func_name': func_name,
            'accept_files': accept_files
        })

    def get_api_types(self) -> Dict[str, Dict[str, str]]:
        return RestAPI.__APIDoc__
