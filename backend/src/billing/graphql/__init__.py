"""
GraphQL API setup with Strawberry.

Provides GraphQL endpoint at /graphql with:
- Interactive GraphiQL interface
- Efficient data loading (DataLoader)
- Cursor-based pagination
- Type-safe schema

Usage:
    Add to FastAPI app:
    from billing.graphql import graphql_app
    app.mount("/graphql", graphql_app)
"""

from strawberry.fastapi import GraphQLRouter
from billing.graphql.schema import schema

# Create GraphQL router with GraphiQL interface enabled
graphql_app = GraphQLRouter(
    schema,
    graphiql=True,  # Enable interactive GraphiQL interface
    path="/",  # Root path when mounted
)

__all__ = ["graphql_app", "schema"]
