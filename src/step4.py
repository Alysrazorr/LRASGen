
import ast
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import logger
from config import DTO_EXPANSION_MAX_DEPTH, STEP4_MAX_WORKERS, STEP4_PROGRESS_EVERY
from frameworks import FRAMEWORKS
import llm
from llm import ask
from normalize import (parameter_entities, rebuild_parameters,
                        response_entities, rebuild_responses)


_FRAMEWORK_HINTS = {
    "django": """
[Django REST Framework hints]
- DRF ModelViewSet/ReadOnlyModelViewSet list endpoints auto-generate pagination params: limit, offset
- DRF ViewSets support ordering params via ordering_fields attribute — add "ordering" query param
- Check method bodies for self.request.GET.get('name'), self.request.query_params.get('name')
- Check self.kwargs for URL path params (e.g., self.kwargs['pk'] for detail endpoints)
- Check serializer_class fields — each serializer field may be a writable body param on POST/PUT/PATCH
""",
    "flask": """
[Flask hints]
- Check route decorators for <type:variable> URL patterns (path params)
- @use_args() decorator: each method's @use_args dict defines its exact query parameters with types and validation. Extract only those parameters.
- Check method bodies for request.args.get(), request.form.get(), request.json.get(), request.get_json()
- Check for Flask-RESTful reqparse.RequestParser definitions
""",
    "tornado": """
[Tornado hints]
- IMPORTANT: Tornado handlers have EMPTY method signatures (def get(self), def post(self))
- Check method bodies for self.get_argument('name'), self.get_query_argument('name')
- Check for self.get_body_argument('name'), self.request.body
- URL path params come from regex groups in handler registration, NOT from method signatures
- Check for self.path_args, self.path_kwargs
""",
    "express": """
[Express hints]
- Check for req.params (URL path params), req.query (query string params)
- Check for req.body (POST/PUT body), req.headers (header params)
- Check route definitions for :param patterns (e.g., /api/users/:id)
""",
    "nestjs": """
[NestJS hints]
- Check for @Param(), @Query(), @Body(), @Headers() decorators
- Check DTO class definitions for class-validator decorators (@IsString, @IsInt, etc.)
- Check for @ApiParam(), @ApiQuery() Swagger decorators
""",
    "koa": """
[Koa hints]
- ctx.params holds the route parameters declared in the router pattern, ctx.query
  the query string, ctx.request.body the parsed body, and ctx.headers the headers.
- A matched route pattern such as /users/:id makes id a path parameter.
- Read body parameters from the keys of ctx.request.body, whether they are read one
  at a time or destructured, and from the fields of the class the body is assigned
  to.
- A middleware in front of the handler may parse the body or the query and pass the
  result as a plain object argument. Follow the call and read that object's keys.
""",
    "nextjs": """
[Next.js hints]
- With the App Router, the request method is the name of the exported function
  (GET, POST, and so on). The path parameter is named by the directory: app/users/[id]
  makes id a path parameter, and [...slug] is a catch-all segment.
- The handler reads query parameters through request.nextUrl.searchParams.get("name")
  and the body through await request.json().
- With the Pages Router, the handler takes (req, res) and reads query parameters,
  including the route parameters, from req.query.
""",
    "aspnetcore": """
[ASP.NET Core hints]
- Check for [FromQuery], [FromRoute], [FromBody], [FromHeader], [FromForm] attributes
- Check for [Required], [StringLength], [Range] validation attributes on model properties
- Check action method parameters and their types
""",
    "spring-boot": """
[Spring Boot hints]
- @RequestParam, @RequestHeader and @PathVariable are required unless the
  annotation sets required = false; a defaultValue also makes the parameter
  optional.
- A parameter annotated @ModelAttribute, and an unannotated parameter whose type is
  a class, is bound from the query string or the form field by field. Treat each of
  its fields as its own parameter. @RequestBody is one parameter, not several.
- Pageable and Sort parameters are built by Spring Data from the request, so their
  names are not in the signature. When a handler takes one, record page, size and
  sort as query parameters.
- A MultipartFile parameter arrives as form data.
- @Valid on a parameter makes the Bean Validation annotations on its class into
  constraints on the fields that class contributes.
""",
    "spring-boot-kotlin": """
[Spring Boot with Kotlin hints]
- Request binding follows Spring Boot: @RequestParam, @RequestHeader and
  @PathVariable are required unless required = false is set, and @RequestBody is
  one parameter.
- A constructor property with a default value is optional, so record it with
  require "false" and keep the default in default_value.
- A nullable type such as String? or Int? records as its non-null type; the
  nullability belongs in require, not in the type name.
- @field: and @param: targets carry the same meaning as the undecorated annotation.
- Pageable and Sort are built by Spring Data from the request, the same as in Java.
""",
    "webpy": """
[Web.py hints]
- Check method bodies for web.input() to get query/form params
- web.input() called with no arguments returns the entire form as a dict, so the
  field names do not appear at the call site. When the handler forwards that dict
  to another function or backend, follow the call and read the keys the callee
  reads. Those keys are often held as dict literals in a settings or constants
  module. List each key as its own parameter; never collapse them into a single
  object parameter named after the dict.
- The key names of a dict literal are the parameter names, whatever the values
  map to internally (a boolean config dict maps a param name to the mlmmj flag it
  controls; the parameter name is the key, not the value).
- A form field arrives as text, so record it with type "string". A dict whose name
  says boolean describes how the server reads the value, not what the client
  sends: the client sends "yes" or "no", and the field is a string parameter.
- Check URL routing patterns for regex groups (e.g., '/(\\d+)')
- Check for web.data() for raw request body
""",
    "jdk": """
[JDK HttpServer hints]
- The handler implements com.sun.net.httpserver.HttpHandler. It reads the request
  from an HttpExchange, builds a parameter map from the query string and the body,
  and passes that map down the call chain.
- The parameter names are therefore not in the handler. Look in Related_code for
  every place a callee reads the map, such as parameters.get("name"), or where a
  helper is called with a name and the map, such as getIds("name", parameters).
  Each such name is a parameter of the endpoint that serves the request.
- These parameters arrive in the query string or the body, so record them with the
  position the request carries them in, not as path parameters.
- A value read from the parameter map arrives as text unless the code parses it
  into another type, so record the type the client sends. Code such as
  "yes".equals(parameters.get("enabledOnly")) shows the client sends a string.
""",
    "jersey": """
[JAX-RS / Jersey hints]
- IMPORTANT: Many JAX-RS resource methods have no explicit @QueryParam parameters.
  Query/pagination/filter parameters are injected through context objects accessed
  via getters like getPagination(), getFilter(), getUser(), etc.
- When you see a getter call in the method body (e.g. getPagination(),
  getFilter()), this indicates that the endpoint accepts parameters defined by
  the getter's return type. Find the return type in Related_code, expand its
  fields, and treat each field as a query parameter with the field's declared
  type. Do NOT invent parameter names — only use fields actually declared in the
  return type's source code.
- Some query parameters are named by an enumeration rather than by an annotation.
  A helper loops over EnumType.values() and looks the request parameter up under
  the constant's own name, as in getQueryParameters().getFirst(op.name()) or
  op.parseFilter(param). Every constant of that type is then a parameter of the
  endpoint, named exactly as the constant is written, and typed by whatever the
  code parses the value into, which is a string when it is only parsed later.
  Such a helper is often inherited from a base class and called by several
  handlers, so follow the handler's call chain and give those constants to every
  endpoint whose handler reaches it.
- Check for @BeanParam — these are injected DTO beans whose fields become
  individual query/path/header/form parameters. Treat each field as a separate
  parameter with the bean's class as the type.
- @Context parameters (UriInfo, HttpHeaders, SecurityContext, etc.) are injected
  by the framework. Record each one as a parameter with its class name as the type.
""",
}


_PROMPT_PARAM = """\
## Source Code

```
%s
```

## Questions

1. In the source code, there is an endpoint: %s, and its method name is: %s. What parameters does this endpoint accept?
2. For each parameter, provide: name, type, require ("true" or "false"), position (path, query, header, body, or form), and description.
2a. Answer "require" with "true" unless the code declares the parameter optional
   in so many words: a required = false on the annotation, a nullable or
   Optional wrapper, or a body field the handler guards before reading. Anything
   else is "true", including a parameter the code merely reads and one that
   carries a default value. Most parameters of a real API are required, so a
   list that answers "false" throughout is almost certainly wrong.
3. If an annotation gives the parameter an alias (e.g. @RequestParam("foo")), use the annotation value as the parameter name, not the variable name.
4. The parameters of an endpoint come from the method you were given, and from
   nowhere else. A resource class holds several methods side by side - get,
   post, put, delete - and each carries its own decorators. A @use_args({...})
   written above get says what get accepts; it says nothing about post, which
   takes its content from the body the client sent. Read the decorators written
   directly above THIS method and take the parameters from those. Where this
   method has no @use_args, it has none of the dictionary's parameters, and a
   list copied from a sibling method is wrong however plausible it looks. Do not
   include parameters from request.args.get() calls either.
5. If the endpoint does not contain any parameters, return an empty array.
6. If the parameter's type is string, what is its length range?
7. If the parameter's type is string and resembles a date or datetime format, what is its possible date-format placeholders?
8. If the parameter's type is integer, what is its value range?
9. If the parameter is an enumeration or dictionary, what is the enumeration value or dictionary value?
10. If the parameter is a nested parameter, ask the same questions of the parameters inside it.

## Notice

- An API parameter is a value sent by the API client in the HTTP request: path variables (/users/{id}), query string parameters (?page=1), HTTP headers, request body, or form data.
- If a parameter's type is a custom class that IS sent by the client (e.g. AlbumRequest, LoginRequest, PostRequest), write its exact simple class name as the type — not "object". Do NOT expand nested fields; we will handle expansion in post-processing.
- For standard types (String, Integer, int, Long, long, Boolean, boolean, Float, float, Double, double, BigDecimal, Date, LocalDate, DateTime, Instant, UUID, etc.), use the conventional short name (string, integer, boolean, number).

## Example

An answer in this format:

```
%s
```

## Rules

- You must answer every question for every parameter, one entry per parameter.
- You must extract information from the specified code to answer the questions.
- You must answer the questions according to the JSON format: %s.
- %s"""


_PROMPT_RESP = """\
## Source Code

```
%s
```

## Questions

1. In the source code, there is an endpoint: %s, and its method name is: %s. What responses does this endpoint return?
2. All the return status codes and their descriptions are needed.
3. If the response contains data, save its structure in the "data_schema" field. If the data has a name, put it in "data_schema > name". Each field is a <name, type> pair in "data_schema > schema".
4. If the response contains an exception description, fill in the "exception" field.
5. If the exception is unclear, it may not be included.
6. Go through all return branches in the source code.
7. If the endpoint does not return any responses, return an empty array.
8. The endpoint is served by %s. Besides the responses the handler code itself
   produces, include the responses that framework returns on its own for the
   requests it handles, because a client receives those as well. Leave out any
   response the framework would not produce for this endpoint.
9. List a status code only where something in the code or in that framework's
   own handling of this endpoint produces it. An error code is not a property
   every endpoint has: do not add one because endpoints in general tend to
   return it, and do not carry one over from another endpoint. An endpoint
   whose code shows a single success path returns a single response.
10. An error code belongs to this endpoint only where the code in front of you
   brings it about. Find the line that produces it before you report it: a
   lookup that answers 404 when it comes back empty, a check that answers 400
   for the values it received, an authorization check that answers 401 or 403,
   a catch that answers 500. Where there is no such line, the endpoint does not
   carry that code, however likely the framework is to return it on its own.
   A code the framework answers before any handler runs belongs to no endpoint:
   leave out 405 and 415 entirely. The server error is the exception, and it is
   narrower than it looks: the endpoint carries 500 where the handler does not
   produce the answer itself but asks another class for it and answers with what
   comes back, and where nothing in the handler catches a failure of that call.
   The hand-off is the whole of what the handler does between reading the request
   and answering it; a handler that carries out part of the work itself and only
   reaches out for one step of it carries no 500. A handler that reads the
   request, decides with its own code and answers from what it holds carries no
   500 either. The endpoint always carries its success code; every other code it
   carries is one its own code brings about.

## Example

An answer in this format:

```
%s
```

## Rules

- You must extract information from the specified code to answer the questions.
- You must answer the questions according to the JSON format: %s."""


# The parameter answer's shape, taken from the original implementation's
# json_schema_for_parameter so that the model is asked for the same thing here
# as it was there. The list is wrapped in the "parameters" key the rest of this
# module reads.
_EXAMPLE_PARAM = {
    "parameters": [
        {
            "name": "str_param",
            "type": "string",
            "require": "true",
            "position": "query",
            "description": "some string parameter",
            "max_length": "128",
            "min_length": "16",
            "dictionary": [{"key1": "value1", "key2": "value2"}],
            "enum": ["enum1", "enum2", "enum3"],
            "format": "yyyy-mm-dd hh24:mi:ss",
            "default_value": "hello world"
        }, {
            "name": "num_param",
            "type": "int",
            "require": "true",
            "position": "path",
            "description": "some number parameter",
            "min": 2,
            "max": 16,
            "default_value": 0
        }, {
            "name": "bool_param",
            "type": "boolean",
            "require": "true",
            "position": "query",
            "description": "some boolean parameter",
            "default_value": True
        }, {
            "name": "nested_param",
            "type": "NestedRequest",
            "require": "true",
            "position": "body",
            "description": "some nested parameter",
            "nested_parameters": [{
                "name": "str_param",
                "type": "string",
                "require": "true",
                "position": "query",
                "description": "some string parameter",
                "max_length": "128",
                "min_length": "16",
                "dictionary": [{"key1": "value1", "key2": "value2"}],
                "enum": ["enum1", "enum2", "enum3"],
                "format": "yyyy-mm-dd hh24:mi:ss",
                "default_value": "hello world"
            }, {
                "name": "num_param",
                "type": "int",
                "require": "true",
                "position": "path",
                "description": "some number parameter",
                "min": 2,
                "max": 16,
                "default_value": 0
            }, {
                "name": "bool_param",
                "type": "boolean",
                "require": "true",
                "position": "query",
                "description": "some boolean parameter",
                "default_value": True
            }]
        }
    ],
}

_EXAMPLE_RESP = {
    "responses": [
        {
            "status_code": 200,
            "description": "some response",
            "data_schema": [
                {
                    "name": "UserInfo",
                    "schema": {
                        "username": "string",
                        "password": "string",
                        "birthday": "date",
                        "age": "integer",
                        "email": "string",
                        "is_vip": "boolean",
                        "expires": "long",
                    },
                }
            ],
        },
    ],
}


_SCHEMA_PARAM = {
    "type": "object",
    "properties": {
        "parameters": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "parameter name (use annotation alias if present)"},
                    "type": {"type": "string", "description": "data type: string, integer, number, boolean, or the exact simple class name for custom types"},
                    "require": {"type": "string", "description": "'true' if required, 'false' if optional"},
                    "optional_because": {"type": "string", "description": "when require is 'false', the declaration in the code that makes it optional, quoted from the code exactly as written; empty when the parameter is required"},
                    "position": {"type": "string", "description": "path, query, header, body, or form"},
                    "description": {"type": "string"},
                    "min": {"type": "integer", "description": "smallest allowed value, when the code states one"},
                    "max": {"type": "integer", "description": "largest allowed value, when the code states one"},
                    "min_length": {"type": "string", "description": "shortest allowed length, when the code states one"},
                    "max_length": {"type": "string", "description": "longest allowed length, when the code states one"},
                    "format": {"type": "string", "description": "the format the code parses the value with"},
                    "enum": {"type": "array", "description": "the values the code enumerates, when it enumerates them"},
                    "dictionary": {"type": "array", "description": "the key and value pairs the code tabulates"},
                    "default_value": {"description": "the value the code falls back to, when it has one"},
                },
                "required": ["name", "type"],
            },
        },
    },
    "required": ["parameters"],
}

_SCHEMA_RESP = {
    "type": "object",
    "properties": {
        "responses": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "status_code": {"type": "integer"},
                    "description": {"type": "string"},
                    "data_schema": {"type": "array"},
                },
            },
        },
    },
    "required": ["responses"],
}


import re as _re_mod

_JAVA_FIELD_RE = _re_mod.compile(
    r'(?:public|protected|private)\s+'
    r'(?!(?:static\s+final|final\s+static)\s+)'
    r'(?:(?:static\s+)?(?:final\s+)?)?'
    r'(\w+(?:\.\w+)*(?:<[^>]+>)?)\s+(\w+)\s*[=;]')


_CS_PROP_RE = _re_mod.compile(
    r'public\s+([\w.]+(?:<[\w.,\s]+>)?(?:\?)?)\s+'
    r'(\w+)\s*\{[^}]*get[^}]*\}'
)


def _find_dto_file(class_name, deps):
    for ext in ('.java', '.cs', '.kt'):
        target = class_name + ext
        for key in deps:
            if os.path.basename(key) == target:
                return deps[key]
    return None


def _extract_dto_fields(class_name, deps, visited=None):
    if visited is None:
        visited = set()
    if class_name in visited:
        return []
    visited.add(class_name)

    code = _find_dto_file(class_name, deps)
    if not code:
        return []

    is_csharp = 'namespace ' in code and ('class ' in code) and not ('import ' in code)

    if is_csharp:
        fields = _extract_cs_properties(class_name, code, deps, visited)
    elif _is_kotlin_code(code):
        fields = _extract_kotlin_fields(class_name, code, deps, visited)
    else:
        if _re_mod.search(r'\brecord\s+\w+', code):
            fields = _extract_record_components(class_name, code, deps, visited)
        else:
            fields = _extract_java_fields(class_name, code, deps, visited)

    return list(fields.values())


_RECORD_COMPONENT_RE = _re_mod.compile(
    r'(?:@\w+(?:\([^)]*\))?\s+)*'
    r'(\w+(?:\.\w+)*(?:<[^>]+>)?)\s+(\w+)'
)

def _is_kotlin_code(code):
    return bool(_re_mod.search(r'\b(val|var)\s+\w+\s*:', code))


def _declaration_params(code, decl_pattern):
    """Return the text between a declaration's parentheses.

    The opening paren is taken from the declaration itself rather than by
    locating the first ")" and scanning back. Annotations on the parameters
    carry parens of their own, so scanning back from the file's first ")" lands
    on an annotation instead of the parameter list and yields no fields.
    """
    decl = _re_mod.search(decl_pattern, code)
    if not decl:
        return None
    start = decl.end() - 1
    depth = 0
    for i in range(start, len(code)):
        if code[i] == '(':
            depth += 1
        elif code[i] == ')':
            depth -= 1
            if depth == 0:
                return code[start + 1:i]
    return None


_KOTLIN_PARAM_RE = _re_mod.compile(
    r'(?:@\w+(?:\s*\([^)]*\))?\s+)*'
    r'(?:override\s+)?'
    r'(?:val|var)\s+'
    r'(\w+)\s*:\s*'
    r'([\w.?]+(?:<[^>]+>)?)'
    r'(?:\s*[=)])'
)


def _extract_kotlin_fields(class_name, code, deps, visited):
    fields = {}

    class_match = _re_mod.search(
        r'(?:data\s+)?class\s+\w+\s*(?:\([^)]*\))?\s*(?::\s*(\w+))?',
        code
    )
    parent = class_match.group(1) if class_match and class_match.group(1) else None
    if parent and parent not in ('Object', 'object', 'Any'):
        for pf in _extract_dto_fields(parent, deps, visited):
            fields[pf['name']] = pf

    params_str = _declaration_params(code, r'(?:data\s+)?class\s+\w+\s*\(')
    if params_str is None:
        return fields

    bracket_depth = 0
    current = ''
    for ch in params_str + ',':
        if ch == '<': bracket_depth += 1
        elif ch == '>': bracket_depth -= 1
        if ch == ',' and bracket_depth == 0:
            current = current.strip()
            pm = _re_mod.search(r'\b(?:val|var)\s+(\w+)\s*:\s*([\w.?]+(?:<[^>]+>)?)', current)
            if pm:
                fname = pm.group(1)
                ftype_raw = pm.group(2)
                ftype = _re_mod.sub(r'<.*>', '', ftype_raw)
                if not fname.startswith('_'):
                    fields[fname] = {'name': fname, 'type': ftype}
            current = ''
        else:
            current += ch

    return fields


def _extract_record_components(class_name, code, deps, visited):
    fields = {}

    components_str = _declaration_params(code, r'\brecord\s+\w+\s*\(')
    if components_str is None:
        return fields

    for cm in _RECORD_COMPONENT_RE.finditer(components_str):
        ftype = _re_mod.sub(r'<.*>', '', cm.group(1))
        fname = cm.group(2)
        if fname.isupper() and '_' in fname:
            continue
        if not fname.startswith('_') and not fname.startswith('serial'):
            fields[fname] = {'name': fname, 'type': ftype}

    return fields


def _extract_java_fields(class_name, code, deps, visited):
    fields = {}
    class_match = _re_mod.search(r'class\s+\w+\s+extends\s+(\w+)', code)
    parent = class_match.group(1) if class_match else None
    if parent and parent not in ('Object', 'Object()'):
        for pf in _extract_dto_fields(parent, deps, visited):
            fields[pf['name']] = pf

    for m in _JAVA_FIELD_RE.finditer(code):
        ftype = _re_mod.sub(r'<.*>', '', m.group(1))
        fname = m.group(2)
        if fname.isupper() and '_' in fname:
            continue
        if not fname.startswith('_') and not fname.startswith('serial'):
            fields[fname] = {'name': fname, 'type': ftype}

    return fields


def _extract_cs_properties(class_name, code, deps, visited):
    fields = {}
    class_match = _re_mod.search(r'class\s+\w+\s*:\s*(\w+)', code)
    parent = class_match.group(1) if class_match else None
    if parent and parent not in ('Object', 'object'):
        for pf in _extract_dto_fields(parent, deps, visited):
            fields[pf['name']] = pf

    for m in _CS_PROP_RE.finditer(code):
        ftype = _re_mod.sub(r'<.*>', '', m.group(1))
        fname = m.group(2)
        if fname.isupper() and '_' in fname:
            continue
        if not fname.startswith('_'):
            fields[fname] = {'name': fname, 'type': ftype}

    return fields


_DTO_TAG_RE = _re_mod.compile(r'\[(?:DTO|class):(\w+)\]')


# JAX-RS turns one string from the request into a parameter of the declared
# type through a static factory, or, for a class that carries a single value,
# through a constructor that takes one string.
_STRING_FACTORY_RE = _re_mod.compile(
    r"static\s+[\w<>\[\],\s]*?\b\w+\s+(?:valueOf|fromString)\s*\(\s*(?:final\s+)?String\b")
_STRING_CTOR_RE = _re_mod.compile(
    r"\bpublic\s+\w+\s*\(\s*(?:final\s+)?String\s+\w+\s*\)")


def _reads_one_string(type_name, deps):
    """Whether a value of this type arrives as a single string.

    A static valueOf(String) or fromString(String) settles it. A constructor
    taking one string settles it only for a type that holds no more than one
    value of its own, which is what separates Tiltak's Fnr from Scout's User:
    both have such a constructor, but User carries id, name, emailAddress and
    ratings, so it is a payload rather than a scalar.
    """
    src = _find_dto_file(type_name, deps)
    if not src:
        return False
    if _STRING_FACTORY_RE.search(src):
        return True
    if _STRING_CTOR_RE.search(src):
        return len(_extract_dto_fields(type_name, deps)) <= 1
    return False


# A handler that binds a bean, as Spring's @ModelAttribute does, receives one
# request parameter per field of that bean.
_JAVA_BEAN_PARAM_RE = _re_mod.compile(
    r'@ModelAttribute\b(?:\([^)]*\))?'
    r'(?:\s*@\w+(?:\([^)]*\))?)*'
    r'\s*(?:final\s+)?([A-Z]\w*)\s+(\w+)\s*[,)]')


def _declares_required(name, codes):
    """Whether the code marks this parameter required in so many words.

    A handler that declares its parameters one at a time often says of each one
    whether it is required, in the annotation that declares it: Spring's
    @RequestParam takes required, Swagger's @ApiImplicitParam states the name
    and the requiredness side by side. Reading that is what separates the
    parameters an endpoint cannot be called without from the ones it merely
    accepts, which is the difference the answer records.
    """
    if not name or not codes:
        return False
    for m in _re_mod.finditer(r'name\s*=\s*"%s"' % _re_mod.escape(name), codes):
        if _re_mod.search(r'\brequired\s*=\s*true\b', codes[m.end():m.end() + 240]):
            return True
    return False


def _bean_field_names(code, deps):
    """The fields of every bean the code binds as a request parameter, by name.

    Each maps to the type the class declares for it. That type is the one the
    request parameter has: a field declared TreeSet<String> is a parameter that
    arrives more than once, and the model reading the field on its own reports
    the element type as often as the container, which is what leaves the same
    parameter typed string on some endpoints and array on others.

    A bean-bound request is reported field by field, flattened into ordinary
    parameters with nothing left to say where they came from, so the fields
    arrive looking like so many loose query parameters. Reading the bean out of
    the code recovers that. It matters for requiredness: the class declares no
    field optional, and a parameter the code does not mark optional is required.
    """
    fields = {}
    for class_name, _param_name in _JAVA_BEAN_PARAM_RE.findall(code or ""):
        for field in _extract_dto_fields(class_name, deps) or []:
            fields[field["name"]] = field["type"]
    return fields


_DTO_EXTENDS_RE = _re_mod.compile(r'\bclass\s+(\w+)\b[^{;]*?\bextends\s+([\w.]+)')
_DTO_KOTLIN_BASE_RE = _re_mod.compile(r'\bclass\s+(\w+)\s*(?:<[^>]*>)?\s*\([^)]*\)\s*:\s*([\w.]+)')
_DTO_CSHARP_BASE_RE = _re_mod.compile(r'\bclass\s+(\w+)\s*:\s*([\w.]+)')


def _dto_parent(class_name, code):
    """The class this one extends, if the file says it extends one."""
    for rx in (_DTO_EXTENDS_RE, _DTO_KOTLIN_BASE_RE, _DTO_CSHARP_BASE_RE):
        m = rx.search(code or "")
        if m and m.group(1) == class_name:
            return m.group(2).split(".")[-1]
    return None


# What the container hands a handler that the client never sends. A parameter
# of one of these types is not part of the request, so it is not a parameter of
# the endpoint.
_INJECTED_ARG_TYPES = {
    "httpservletresponse", "httpservletrequest", "servletresponse", "servletrequest",
    "principal", "authentication", "userdetails", "model", "modelmap",
    "modelandview", "extendedmodelmap", "bindingresult", "errors", "uriinfo",
    "securitycontext", "httpsession", "webrequest", "nativewebrequest",
    "redirectattributes", "multipartfile", "httpheaders", "servletcontext",
    "applicationcontext", "requestcontext", "session",
}

# An annotation that says the framework fills the argument in from somewhere
# other than the request: the security context, the session, a request
# attribute. Blog writes "@CurrentUser UserPrincipal currentUser" on thirty of
# its handlers, and none of them is a parameter the client sends.
_INJECTED_ARG_ANNOTATION_RE = _re_mod.compile(
    r'@(CurrentUser|AuthenticationPrincipal|LoggedInUser|AuthUser|CurrentAccount|'
    r'CurrentMember|SessionAttribute|RequestAttribute)\b(?:\([^)]*\))?\s+'
    r'(?:final\s+)?([A-Z]\w*)\s+(\w+)')


def _injected_class_names(codes):
    """The classes the code's own annotations have the framework supply."""
    return {m.group(2) for m in _INJECTED_ARG_ANNOTATION_RE.finditer(codes or "")}


def _own_dto_fields(class_name, deps):
    """The fields the class declares itself, without the ones it inherits.

    A class that extends another carries the base class's fields too, and the
    expansion walks the whole hierarchy, so a request that names four fields
    arrives with the audit trail its base class adds: createdAt, updatedAt,
    createdBy and updatedBy, identical on every class of the project and on the
    request of every endpoint that takes one. They are not what the request
    declares, so the expansion reports the class's own fields and stops there.
    """
    own = {f["name"]: f for f in _extract_dto_fields(class_name, deps) or []}
    parent = _dto_parent(class_name, _find_dto_file(class_name, deps))
    if parent:
        for f in _extract_dto_fields(parent, deps) or []:
            own.pop(f["name"], None)
    return list(own.values())


def _expand_dto_params(params, deps, max_depth=DTO_EXPANSION_MAX_DEPTH):
    result = []
    for p in params:
        result.extend(_try_expand_param(p, deps, visited=set(), depth=0, max_depth=max_depth))
    return result


def _try_expand_param(p, deps, visited, depth, max_depth):
    type_name = (p.get("type") or "").strip()
    type_clean = _re_mod.sub(r'<[^>]*>', '', type_name).strip()
    p.setdefault("_depth", depth)

    if not type_name or type_clean in _PRIMITIVE_TYPES or depth >= max_depth:
        return [p]

    if type_name in visited:
        return [p]

    # A query, path or header value arrives as one string. Expanding such a
    # parameter into the fields of its class invents parameters the API does not
    # have: enviroCar takes bbox as one comma separated value, and expanding it
    # produced lowerleft, lowerRight, upperRight and upperLeft. A request body is
    # different, and so is a JAX-RS bean parameter, whose fields carry their own
    # parameter annotations and which therefore stays expandable.
    position = (p.get("position") or "").lower()
    if position in ("query", "path", "header") and _reads_one_string(type_clean, deps):
        p["type"] = "string"
        return [p]

    dto_file = _find_dto_file(type_clean, deps)
    if not dto_file:
        return [p]

    visited.add(type_name)
    fields = _own_dto_fields(type_name, deps)
    if not fields:
        return [p]

    result = []
    for f in fields:
        # In a request body, a field typed as another class is the nested object
        # the body holds. The body is written as the class declares it, so the
        # field is not a parameter of the endpoint and is left out. A parameter
        # the framework binds from the query string is the other case: there the
        # field is a parameter of its own, and it is reported as one.
        if (position == "body"
                and bool(_find_dto_file(f["type"], deps))
                and f["type"] not in _PRIMITIVE_TYPES):
            continue

        # A field reached by expanding a DTO is required unless the field itself
        # says otherwise, and the class it was read from is what would say so.
        # These fields arrive with no annotation to read, so the expansion has
        # to answer for them, and it answers "required" the way the rest of the
        # pipeline does for a parameter the code does not mark optional.
        result.append({
            "name": f["name"],
            "type": f["type"],
            "_class_name": type_name,
            "_depth": depth,
            "require": "true",
            "position": p.get("position", "query"),
            "description": p.get("description", ""),
        })
    return result


_PRIMITIVE_TYPES = {
    "string", "String", "integer", "Integer", "int", "Int",
    "long", "Long", "boolean", "Boolean", "bool", "Bool",
    "float", "Float", "double", "Double", "number", "Number",
    "BigDecimal", "Date", "LocalDate", "LocalDateTime", "DateTime",
    "Instant", "UUID", "array", "Array", "List", "Collection",
    "Map", "Dictionary", "Set", "MutableSet", "MutableList",
    "object", "Object",
    "IEnumerable", "IList", "IDictionary", "Enum", "enum",
    "", "void",
}


_FLASK_TYPE_MAP = {
    "Integer": "integer", "Str": "string", "Boolean": "boolean",
    "Float": "number", "Decimal": "number", "DateTime": "string",
    "DelimitedList": "array", "List": "array", "Dict": "object",
    "Raw": "string", "Nested": "object",
}


def _resolve_flask_use_args(entry_path, class_name, method_name):
    try:
        with open(entry_path, 'r', encoding='utf-8', errors='replace') as f:
            source = f.read()
        tree = ast.parse(source)
    except Exception:
        return None

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == method_name:
                    for decorator in item.decorator_list:
                        if isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Name) and decorator.func.id == 'use_args':
                            if decorator.args and isinstance(decorator.args[0], ast.Dict):
                                params = []
                                for key_node, value_node in zip(decorator.args[0].keys, decorator.args[0].values):
                                    name = key_node.value if isinstance(key_node, ast.Constant) else None
                                    if not name: continue
                                    ftype = "string"
                                    if isinstance(value_node, ast.Call) and isinstance(value_node.func, ast.Attribute):
                                        ftype = _FLASK_TYPE_MAP.get(value_node.func.attr, "string")
                                    params.append({"name": name, "type": ftype, "require": "false", "position": "query", "description": ""})
                                return params
    return None


# A request's parameters are sometimes never named where the request arrives:
# the handler builds an opaque map and passes it down, and the names appear only
# where a callee reads them back.
_PARAM_MAP_READ_RE = _re_mod.compile(
    r'\b(?:params|parameters|query|queryParams|form|formParams|formData|'
    r'inputs|args|arguments)\.get\("([^"]+)"\)'
)
# The helper is named like a getter, which keeps statement ids passed to a
# database call such as selectList("Mapper.findById", parameters) out.
_PARAM_MAP_HELPER_RE = _re_mod.compile(
    r'\bget\w*\(\s*"([^"]+)"\s*,\s*'
    r'(?:params|parameters|query|queryParams|form|formParams|inputs)\b'
)


def _extract_implicit_params(entry_code, deps):
    params = set()
    for key, code in deps.items():
        if key == "entry_code_file":
            continue
        params.update(_re_mod.findall(r'getParameter(?:Values)?\("([^"]+)"\)', code))
        params.update(_PARAM_MAP_READ_RE.findall(code))
        params.update(_PARAM_MAP_HELPER_RE.findall(code))
    if not params:
        return None
    return sorted(params)


def _assemble_codes(entry_file_path, deps):
    codes = f'Entry_code({entry_file_path}):\n<<<\n{deps["entry_code_file"]}\n>>>\n'
    for key, code in deps.items():
        if key != "entry_code_file":
            codes += f'\nRelated_code({key}):\n<<<\n{code}\n>>>\n'
    return codes


def _dedup_params(params, endpoint_path):
    path_slots = {}
    for m in _re_mod.finditer(r'\{(\w+)\}', endpoint_path):
        path_slots[m.group(1)] = len(path_slots)

    seen = {}
    result = []
    for p in params:
        pos = p.get("position", "")
        name = p.get("name", "")
        cn = p.get("_class_name", "")
        if pos == "path":
            slot = path_slots.get(name)
            key = ("path", slot) if slot is not None else ("path", name)
        elif pos == "body":
            # A body may nest two classes that name a field the same way, so the
            # class stays part of a body field's identity.
            key = (pos, cn, name)
        else:
            # A query, header or form parameter is the one the client sends
            # under that name, whichever side of the handler it was read from.
            # Reading the name from the handler and again from the bean it binds
            # describes one parameter twice, not two.
            key = (pos, name)
        if key not in seen:
            seen[key] = len(result)
            result.append(p)
        elif cn and not result[seen[key]].get("_class_name"):
            # Keep the reading that came from the class: it carries the field's
            # own type and the description written beside it, where the flattened
            # one carries the bean's type name and the bean's description.
            result[seen[key]] = p
    return result


def _import_pairs(path):
    """The (module, level) of every import in a Python file."""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            tree = ast.parse(fh.read())
    except (OSError, SyntaxError):
        return []
    pairs = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            pairs.append((node.module or "", node.level))
        elif isinstance(node, ast.Import):
            for alias in node.names:
                pairs.append((alias.name, 0))
    return pairs


def _resolve_module(owner_path, module, level, deps):
    """Turn an import into the dependency key it refers to, or None.

    A relative import is resolved against the importing file's own directory,
    which is what distinguishes the api/util.py that "from .util import x" means
    from the resources/util.py of the same name.
    """
    if level:
        base = os.path.dirname(os.path.abspath(owner_path))
        for _ in range(level - 1):
            base = os.path.dirname(base)
        want = os.path.join(base, (module.replace(".", os.sep) + ".py")
                           if module else "__init__.py")
    else:
        want = None

    norm = lambda p: os.path.normcase(os.path.abspath(p))
    if want and os.path.isfile(want) and any(norm(k) == norm(want) for k in deps):
        return next(k for k in deps if norm(k) == norm(want))

    if not level and module:
        suffix = os.sep + module.replace(".", os.sep) + ".py"
        for k in deps:
            if k != "entry_code_file" and os.path.normcase(k).endswith(os.path.normcase(suffix)):
                return k
    return None


def _scope_deps(entry_path, deps, endpoint):
    """Narrow the context to the module that serves this endpoint.

    A Flask app registers its routes in a single module, so walking imports from
    that module reaches the whole package, and every endpoint of the app was sent
    all of it. For Gramps that is 583 KB of context resent once per endpoint,
    which came to 132 million prompt tokens for one API.

    An endpoint names its handler class, and the route table says which module
    defines that class, so the context can be the route table plus that module
    and the modules it imports. The one hop keeps the model classes that step4
    reads field names out of. Anything that cannot be resolved leaves the
    context as it was, so a framework this does not fit is unaffected.
    """
    method_name = endpoint.get("method_name") or ""
    class_name = method_name.split(".")[0]
    if not class_name or "entry_code_file" not in deps:
        return deps

    # The route table imports each handler class from the module that defines it,
    # so read those modules and keep the one that declares this class.
    declared = _re_mod.compile(rf"^class\s+{_re_mod.escape(class_name)}\b",
                               _re_mod.MULTILINE)
    handler = None
    for module, level in _import_pairs(entry_path):
        if not module:
            continue
        candidate = _resolve_module(entry_path, module, level, deps)
        if candidate is None:
            continue
        try:
            with open(candidate, "r", encoding="utf-8", errors="replace") as fh:
                body = fh.read()
        except OSError:
            continue
        if declared.search(body):
            handler = candidate
            break
    if handler is None:
        return deps

    keep = {handler}
    for module, level in _import_pairs(handler):
        dep = _resolve_module(handler, module, level, deps)
        if dep:
            keep.add(dep)

    return {k: v for k, v in deps.items() if k == "entry_code_file" or k in keep}


# The constraint fields an answer may carry. They are asked for in the same
# call as the parameter itself, and travel with it from there to the spec.
# A default value is left out. No parameter of any of the fifty-three APIs
# carries one in GTa, so every one the pipeline reports is a parameter it has
# invented, and the answer costs a call to obtain.
_CARRIED_CONSTRAINT_KEYS = ("min", "max", "min_length", "max_length", "format",
                            "enum", "dictionary")


def _declares_optional(param, codes):
    """Whether the code itself declares the parameter optional.

    The model answers "false" for most of the parameters it reads, because most
    parameters of a real API look optional, and that answer carries nothing to
    check it against. So it is asked to quote the declaration that makes the
    parameter optional, and the quote is looked for in the code. A parameter is
    optional when the code says so, and required otherwise.
    """
    reason = param.get("optional_because") or ""
    if not reason or not codes:
        return False
    for line in str(reason).replace(";", "\n").split("\n"):
        line = line.strip().strip("`").strip()
        if len(line) >= 6 and line in codes:
            return True
    return False


def _process_endpoint(entry_path, deps, endpoint):
    framework = endpoint.get("framework", "")
    framework_name = FRAMEWORKS.get(framework, {}).get("name", framework)

    codes = _assemble_codes(entry_path, _scope_deps(entry_path, deps, endpoint))

    bean_fields = _bean_field_names(codes, deps)
    path_slots = set(_re_mod.findall(r'\{([^}]+)\}', endpoint["endpoint_path"]))

    def _required(param):
        """Whether this parameter is required, read from how the handler takes it.

        A handler that binds a bean receives the whole bean, so the fields of
        that bean are the request whether or not any one of them is annotated,
        and the classes holding them declare none of their fields optional. A
        handler that names its parameters one at a time is the other case: there
        a parameter is required only where something says so, because a query
        parameter a handler reads optionally is the ordinary shape of such an
        endpoint rather than an exception to it.
        """
        if param.get("name") in path_slots:
            return "true"
        if param.get("name") in bean_fields:
            # A field of the bean the handler binds. The bean is the request:
            # the framework fills every field it can, and the class declares
            # none of them optional, so none of them is.
            return "true"
        if _declares_required(param.get("name"), codes):
            return "true"
        if bean_fields and not _declares_optional(param, codes):
            return "true"
        return "false"
    ep_name = f'{endpoint["http_method"]} "{endpoint["endpoint_path"]}"'
    method_name = endpoint["method_name"]
    params = []
    responses = []
    errors = []

    hint = _FRAMEWORK_HINTS.get(framework, "")

    implicit = _extract_implicit_params(deps.get("entry_code_file", ""), deps)
    if implicit:
        hint += (
            f"\n[Request parameters read by name]\n"
            f"The request's parameters are not all named where the request arrives. "
            f"Related_code reads the following names from a request parameter map, "
            f"either as a lookup such as parameters.get(\"name\") or as the name "
            f"argument of a helper that takes that map. Each name is a parameter of "
            f"the endpoint: {', '.join(implicit)}. Include the ones that apply to "
            f"each endpoint.\n"
        )

    if framework == "flask" and "." in method_name:
        parts = method_name.rsplit(".", 1)
        resolved = _resolve_flask_use_args(entry_path, parts[0], parts[1])
        if resolved:
            params = resolved

    if not params:
        try:
            prompt = _PROMPT_PARAM % (codes, ep_name, method_name,
                                      json.dumps(_EXAMPLE_PARAM, indent=4),
                                      str(_SCHEMA_PARAM), hint)
            r, _ = ask([{"role": "user", "content": prompt}],
                       extract=parameter_entities, rebuild=rebuild_parameters)
            raw = r.get("parameters", [])
            for p in raw:
                flat = {
                    "name": p.get("name"),
                    "type": p.get("type"),
                    "require": _required(p),
                    "position": p.get("position"),
                    "description": p.get("description"),
                }
                for key in _CARRIED_CONSTRAINT_KEYS:
                    if p.get(key) is not None:
                        flat[key] = p[key]
                params.append(flat)
                for nested in p.get("nested_parameters") or []:
                    nested["position"] = nested.get("position", p.get("position", "body"))
                    nested_flat = {
                        "name": nested.get("name"),
                        "type": nested.get("type"),
                        "require": _required(nested),
                        "position": nested.get("position"),
                        "description": nested.get("description"),
                    }
                    for key in _CARRIED_CONSTRAINT_KEYS:
                        if nested.get(key) is not None:
                            nested_flat[key] = nested[key]
                    params.append(nested_flat)
        except Exception as e:
            errors.append(f"params: {e}")

    try:
        prompt = _PROMPT_RESP % (codes, ep_name, method_name, framework_name,
                                 json.dumps(_EXAMPLE_RESP, indent=4),
                                 str(_SCHEMA_RESP))
        r, _ = ask([{"role": "user", "content": prompt}],
                   extract=response_entities, rebuild=rebuild_responses)
        for resp in r.get("responses", []):
            responses.append({
                "status_code": resp.get("status_code"),
                "description": resp.get("description"),
                "data_schema": resp.get("data_schema"),
            })
    except Exception as e:
        errors.append(f"responses: {e}")

    seen_sc = set()
    deduped_resp = []
    for r in responses:
        sc = r.get("status_code")
        if sc not in seen_sc:
            seen_sc.add(sc)
            deduped_resp.append(r)
    responses = deduped_resp

    params = _expand_dto_params(params, deps)
    params = _dedup_params(params, endpoint["endpoint_path"])

    # A parameter that is a field of a bean this handler binds takes the type
    # the bean declares for it. The model reads the field on its own and reports
    # the element type as often as the container, so a TreeSet<String> comes
    # back as string about as often as it comes back as array, and the same
    # parameter ends up typed differently from one endpoint to the next.
    for p in params:
        declared = bean_fields.get(p.get("name"))
        if declared:
            p["type"] = declared

    # An argument the container supplies is not something the client sends.
    injected = _injected_class_names(codes)
    params = [
        p for p in params
        if str(p.get("type") or "").split("<")[0].strip().lower() not in _INJECTED_ARG_TYPES
        and (p.get("_class_name") or "") not in injected
    ]

    # What the request carries to the endpoint is what it names in the path and
    # the query, and what the body's own class declares. A header and a form
    # field are neither: the specification describes them where they belong, as
    # a header of the request and as the media type of the body, and reporting
    # them as parameters of the endpoint puts the same thing in two places.
    params = [p for p in params
              if (p.get("position") or "").lower() not in ("header", "form")]

    # A parameter that turns out to be a field of a bean this handler binds is
    # required, whatever the model answered while reading it as a loose
    # parameter: the bean is what declares the field, and it declares none of
    # them optional.
    return {
        "endpoint_path": endpoint["endpoint_path"],
        "http_method": endpoint["http_method"],
        "method_name": endpoint["method_name"],
        "source_file": endpoint.get("source_file"),
        "parameters": params,
        "responses": responses,
        "errors": errors,
    }


def run_parallel(tasks, max_workers=STEP4_MAX_WORKERS):
    work_items = []
    for t in tasks:
        api = t["api"]
        s2 = t["step2_result"]
        s3 = t["step3_result"]
        tid = t["task_id"]
        entry_to_deps = s2.get("entry_to_deps", {})
        for ep in s3.get("endpoints", []):
            entry_path = ep.get("source_file", "")
            deps = entry_to_deps.get(entry_path, {"entry_code_file": ""})
            ep_with_fw = dict(ep)
            ep_with_fw["framework"] = api["framework"]
            work_items.append((tid, entry_path, deps, ep_with_fw))

    logger.info(f"Step4 dispatching {len(work_items)} endpoints x 2 = "
                f"{len(work_items)*2} LLM calls to {max_workers} workers")

    results_by_task = {}
    done = 0
    total = len(work_items)
    total_params = 0
    total_resps = 0

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            pool.submit(_process_endpoint, ep_path, deps, endpoint): (tid, ep_path)
            for tid, ep_path, deps, endpoint in work_items
        }
        for fut in as_completed(futures):
            tid, ep_path = futures[fut]
            r = fut.result()
            done += 1
            results_by_task.setdefault(tid, []).append(r)
            total_params += len(r["parameters"])
            total_resps += len(r["responses"])
            if done % STEP4_PROGRESS_EVERY == 0 or done == total:
                logger.step("Step4", done, total, f"{total_params} params, {total_resps} responses")

    return results_by_task, total_params, total_resps
