from agent.marketplace_port import Unavailable


def ingest_repository(*args, **kwargs):
    raise Unavailable(
        "GitHub MCP repository ingestion is unavailable: a verified third-party server, "
        "scoped tools and repository/ref provenance have not been configured. "
        "Manual repository-text uploads are supported and labelled as uploads."
    )
