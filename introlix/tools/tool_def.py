SEARCH_TOOL_DEF = {
    "type": "function",
    "function": {
        "name": "search",
        "description": (
            "Search the internet for current information. Use when you need up-to-date "
            "facts or data you are not certain about. Pass one or more search queries."
            "Only use this if big search needs to be done, as it is slower than fast_search."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "queries": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of search queries to run.",
                }
            },
            "required": ["queries"],
        },
    },
}

FAST_SEARCH_TOOL_DEF = {
    "type": "function",
    "function": {
        "name": "fast_search",
        "description": (
            "A faster web search using DDGS. Use for quick lookups where comprehensive "
            "results are less important than speed. Like fact checkup or simple queries."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "queries": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of search queries to run.",
                }
            },
            "required": ["queries"],
        },
    },
}