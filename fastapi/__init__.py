import types
import inspect

class FastAPI:
    def __init__(self):
        self.routes = {"GET": {}, "POST": {}, "PUT": {}}
    def middleware(self, *a, **kw):
        def deco(fn):
            return fn
        return deco
    def mount(self, *a, **kw):
        pass
    def get(self, path, **kw):
        def deco(fn):
            self.routes["GET"][path] = fn
            return fn
        return deco
    def post(self, path, **kw):
        def deco(fn):
            self.routes["POST"][path] = fn
            return fn
        return deco
    def put(self, path, **kw):
        def deco(fn):
            self.routes["PUT"][path] = fn
            return fn
        return deco

class Request:
    def __init__(self, headers=None):
        self.headers = headers or {}

class BackgroundTasks:
    pass

class UploadFile:
    def __init__(self, filename="", file=None, content_type=""):
        self.filename = filename
        self.file = file
        self.content_type = content_type

def Form(default=None):
    return default

def File(default=None):
    return default

class HTTPException(Exception):
    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail

class HTMLResponse:
    def __init__(self, content="", status_code=200, headers=None):
        self.text = content
        self.status_code = status_code
        self.headers = headers or {}

class RedirectResponse(HTMLResponse):
    def __init__(self, url, status_code=307):
        super().__init__("", status_code)
        self.headers["location"] = url

class Jinja2Templates:
    def __init__(self, directory):
        self.directory = directory
    def TemplateResponse(self, name, context, status_code=200):
        return HTMLResponse(context.get("message", ""), status_code=status_code)

class StaticFiles:
    def __init__(self, directory, name=None):
        pass

class TestClient:
    def __init__(self, app):
        self.app = app
    def _prepare(self, data):
        if data is None:
            return {}
        if isinstance(data, dict):
            items = data.items()
        else:
            items = data
        kwargs = {}
        for k, v in items:
            if k in kwargs:
                if isinstance(kwargs[k], list):
                    kwargs[k].append(v)
                else:
                    kwargs[k] = [kwargs[k], v]
            else:
                kwargs[k] = v
        return kwargs
    def _call(self, method, path, data=None, headers=None, files=None):
        func = self.app.routes[method.upper()][path]
        kwargs = self._prepare(data)
        if files:
            for k, (filename, content, mime) in files.items():
                kwargs[k] = UploadFile(
                    filename,
                    types.SimpleNamespace(read=lambda: content),
                    mime,
                )
        sig = inspect.signature(func)
        for name, param in sig.parameters.items():
            if name == "request":
                continue
            if name not in kwargs and param.default is not inspect._empty:
                kwargs[name] = param.default
            ann = param.annotation
            if getattr(ann, "__origin__", None) is list:
                val = kwargs.get(name)
                if val is None:
                    kwargs[name] = []
                elif not isinstance(val, list):
                    kwargs[name] = [val]
        if sig.parameters and list(sig.parameters.keys())[0] == "request":
            return func(Request(headers), **kwargs)
        return func(**kwargs)
    def post(self, path, data=None, headers=None, files=None):
        return self._call("POST", path, data, headers, files)
    def put(self, path, data=None, headers=None, files=None):
        return self._call("PUT", path, data, headers, files)
    def get(self, path, params=None, headers=None):
        return self._call("GET", path, params, headers)

TestClient.__test__ = False

# expose submodules
responses = types.ModuleType("fastapi.responses")
responses.HTMLResponse = HTMLResponse
responses.RedirectResponse = RedirectResponse

templating = types.ModuleType("fastapi.templating")
templating.Jinja2Templates = Jinja2Templates

staticfiles = types.ModuleType("fastapi.staticfiles")
staticfiles.StaticFiles = StaticFiles

testclient = types.ModuleType("fastapi.testclient")
testclient.TestClient = TestClient

__all__ = [
    "FastAPI",
    "Request",
    "Form",
    "File",
    "UploadFile",
    "HTTPException",
    "BackgroundTasks",
    "responses",
    "templating",
    "staticfiles",
    "testclient",
]

import sys
sys.modules.setdefault("fastapi.responses", responses)
sys.modules.setdefault("fastapi.templating", templating)
sys.modules.setdefault("fastapi.staticfiles", staticfiles)
sys.modules.setdefault("fastapi.testclient", testclient)
