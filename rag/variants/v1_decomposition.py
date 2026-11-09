import re


def queries(requirement):
    return [part.strip() for part in re.split(r"[;\n]|\band\b", requirement) if part.strip()][:12]


def rank(requirement, search):
    merged = {}
    for query in queries(requirement):
        for item, score in search(query):
            if item["id"] not in merged or score > merged[item["id"]][1]:
                merged[item["id"]] = (item, score)
    return sorted(merged.values(), key=lambda pair: pair[1], reverse=True)
