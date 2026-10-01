# Notebooks

Optional folder for Jupyter notebooks used for exploration, prototyping, or
data analysis. Notebooks are not part of the installable package under
`src/`.

To use notebooks, add Jupyter as a dev dependency:

```bash
uv add --dev jupyterlab
```

Then launch it from the project root:

```bash
uv run jupyter lab
```

Keep reusable logic in `src/python_template/` and import it from notebooks
instead of duplicating code, e.g.:

```python
from python_template import greet

greet("World")
```
