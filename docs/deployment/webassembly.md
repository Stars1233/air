# Emscripten/WebAssembly

Air supports Python runtimes that report `sys.platform == "emscripten"`.
This page documents Air's runtime behavior rather than an integration with a
specific hosting provider.

## Threadless execution

Python threads may be unavailable on WebAssembly runtimes. Air therefore runs
plain `def` handlers, synchronous dependencies, and synchronous exception
handlers on the event loop under Emscripten.

Keep synchronous work short. Use `async def` for handlers and dependencies that
perform I/O:

```python
import air

app = air.Air()


@app.page
async def index() -> air.H1:
    result = await load_data()
    return air.H1(result)
```

## Runtime dependencies

Air omits its local server and terminal presentation dependencies on
Emscripten. HTML parsing and serialization use dependencies that can be
installed without native extension modules.

The hosting runtime remains responsible for connecting Air's ASGI application
to incoming requests and for packaging application dependencies.

## Runtime configuration

`AIRFORM_SECRET` configures form signing when the runtime exposes environment
variables normally. Runtimes that provide secrets through another API can
configure the same value directly:

```python
import air

air.configure_csrf_secret(runtime_secret)
```

Call this before rendering or validating forms. Every process or isolate that
can serve the application must use the same secret.

Storage, static assets, database bindings, application lifecycle behavior, and
deployment configuration are responsibilities of the hosting integration.
