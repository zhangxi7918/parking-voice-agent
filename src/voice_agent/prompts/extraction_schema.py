VISITOR_EXTRACTION_SCHEMA = {
    "type": "object",
    "required": ["visitor_name", "phone", "plate_number", "visit_purpose", "host_name"],
    "properties": {
        "visitor_name": {"type": "string"},
        "phone": {"type": "string"},
        "plate_number": {"type": "string"},
        "company": {"type": ["string", "null"]},
        "visit_purpose": {"type": "string"},
        "host_name": {"type": "string"},
        "arrival_time": {"type": ["string", "null"]},
    },
}

