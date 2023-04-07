# Fyrest

A Flask extension for creating RESTful APIs with TypeScript type generation. This library is still in development and should be considered a playground at this stage. Do not use it in production environments.

## Installation

Install the package using pip:

```bash
pip install git+https://github.com/Fy-/FyRest.git
```

## Usage 
Import and use the ```RestAPI``` class in your Flask application:

```python
from flask import Flask
from fy_rest import RestAPI
api = RestApi(base_url="http://localhost:5000", load_user: None, refresh_user: None)

app = Flask(__name__)
api.init_app(app)
```

## Creating API Routes

```python
from dataclasses import dataclass
from fy_rest import APIResponse
from flask import jsonify

@dataclass
class User:
    id: int
    name: str
    
@dataclass
class UserResponse(APIResponse):
    data: User

api.register_types([User, UserResponse]) #: need to find a better way to do that.

@app.route('/users', methods=['GET'], response_type=UserResponse)
def get_users(ctx):
    users = [User(id=1, name='Alice'), User(id=2, name='Bob')]
    return jsonify(UserResponse(data=users, success=True, time=ctx.get_time()))
```

## CLI Commands
Fyrest provides three CLI commands to help you generate TypeScript types and fetch functions for your API:

`flask rest-all`: Prints both the TypeScript types and fetch functions for your API.

This command will output the TypeScript types and fetch functions as requested.
Or you can just access https://localhost:5000/ts

```bash
$ flask rest-all
import { v4 as uuidv4 } from "uuid";

export interface User {
  id: number;
  name: string;
}

export interface UserResponse {
  success: boolean;
  data: User;
  message: string;
  time: number;
}

export async function usersFetch(params: { [key: string]: any }): Promise<UserResponse> {
    const queryParams = Object.entries(params).map(([key, value]) => `${encodeURIComponent(key)}=${encodeURIComponent(value)}`).join('&');
    const url = `http://localhost:5000/users` + (queryParams ? `?${queryParams}` : '');
    const response = await fetch(url, {
        method: 'GET',
        headers: new Headers({"Content-Type": "application/json", "X-Request-Id": uuidv4(), "X-Fyrest-Session": session})
    });
    return (await response.json()) as UserResponse;
}
```
