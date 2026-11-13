"""ReData engine: sync databases, files and APIs into DuckDB staging tables.

The package has three layers:

  connectors, pipeline   sources, sync modes, saved cursor state, schema drift
  engine                 the DuckDB workspace and the active dataset
  server, cli            the FastAPI app behind the browser UI, and the CLI
"""

__version__ = "1.2.0"
