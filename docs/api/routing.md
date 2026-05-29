## Routing

If you need to knit several Python modules with their own Air views into one, you will need to use Routing. This allow the near seamless combination of multiple Air apps into one. Larger sites are often built from multiple routers.

For this example, let's imagine we have an e-commerce store with a shopping cart app with a `cart.py` and `main.py` file.

```python title="cart.py"
import air

router = air.AirRouter()


@router.page
def cart_page():
    return air.H1("I am a shopping cart")
```

Then in our main page we can load that and tie it into our `main.py` app.

```python title="cart.py"
import air
from cart import router as cart_router

app = air.Air()
app.include_router(cart_router)


@app.page
def index():
    return air.H1("Home page")
```

`AirRouter` allows the sharing of sessions and other application states between routes.

In addition, we can add links through the `.url()` method available on route functions:

```python title="main.py"
import air
from cart import router as cart_router, cart_page

app = air.Air()
app.include_router(cart_router)


@app.page
def index():
    return air.Div(
        air.H1("Home page"),
        air.A("View cart", href=cart_page.url()),
    )
```

## Query Parameters

Air supports query parameters through FastAPI's `Query()` validator, which you can import as `air.Query()`:

```python
import air

app = air.Air()


@app.get("/search")
def search(q: str = air.Query(""), page: int = air.Query(1)):
    return air.H1(f"Search: {q} (page {page})")


# Generate URLs with query parameters
@app.page
def index():
    return air.Div(
        air.A("Search", href=search.url(query_params={"q": "air", "page": 1}))
    )
```

The `.url()` method accepts a `query_params` argument for generating URLs with query strings. This works with both scalar values and lists:

```python
@app.get("/filter")
def filter_items(
    tags: list[str] | None = air.Query(None),
):  # List parameters require explicit air.Query(None) for parsing
    return air.H1(f"Filtered by: {tags}")


# Generates: /filter?tags=python&tags=web
url = filter_items.url(query_params={"tags": ["python", "web"]})
```

---

::: air.routing
