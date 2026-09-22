def classify_intent(query: str) -> str:
    """
    Lightweight intent classification based on keywords in the query.
    Maps the natural language query to an analysis type.
    """
    query_lower = query.lower()
    
    if "vegetation" in query_lower or "green" in query_lower or "crop" in query_lower:
        return "vegetation"
    elif "flood" in query_lower:
        return "flood"
    elif "water" in query_lower or "lake" in query_lower or "river" in query_lower:
        return "water"
    else:
        return "unknown"
