"""Neo4j bolt driver wrapper (read queries for the MCP server)."""
from neo4j import GraphDatabase

from config import NEO4J_PASSWORD, NEO4J_URI, NEO4J_USER

_driver = None


def driver():
    global _driver
    if _driver is None:
        _driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    return _driver


def read(cypher: str, **params) -> list[dict]:
    records, _, _ = driver().execute_query(cypher, params, routing_="r")
    return [r.data() for r in records]
