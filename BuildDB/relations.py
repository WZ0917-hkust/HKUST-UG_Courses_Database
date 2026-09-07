"""保留条件原文，解析布尔表达式并建立反向引用。"""
import re

CODE = re.compile(r'\b([A-Z]{4})\s*(\d{4}[A-Z]*)\b')
FIELDS = {'Pre-requisite': 'Pre-Requisite-of', 'Co-requisite': 'Co-Requisite-of', 'Exclusion': 'Exclusion-of'}


def analyze(raw):
    normalized = CODE.sub(lambda m: ''.join(m.groups()).upper(), raw)
    refs = sorted(set(''.join(m.groups()).upper() for m in CODE.finditer(raw)))
    tokens = re.findall(r'[A-Z]{2,8}\d{4}[A-Z]*|\bAND\b|\bOR\b|[()]', normalized, re.I)
    # Natural-language requirements remain explicit rather than being silently discarded.
    residue = re.sub(r'[A-Z]{2,8}\d{4}[A-Z]*|\bAND\b|\bOR\b|[()\s]', '', normalized, flags=re.I)
    if not raw.strip():
        return {'References': [], 'Expression': None}
    if residue:
        return {'References': refs, 'Expression': {'Text': raw}}
    pos = 0

    def atom():
        nonlocal pos
        if pos >= len(tokens):
            raise ValueError()
        token = tokens[pos].upper()
        pos += 1
        if token == '(':
            node = expression('OR')
            if pos >= len(tokens) or tokens[pos] != ')':
                raise ValueError()
            pos += 1
            return node
        if CODE.fullmatch(token):
            return {'Course': token}
        raise ValueError()

    def expression(op):
        nonlocal pos
        child = atom if op == 'AND' else lambda: expression('AND')
        nodes = [child()]
        while pos < len(tokens) and tokens[pos].upper() == op:
            pos += 1
            nodes.append(child())
        return nodes[0] if len(nodes) == 1 else {op: nodes}

    try:
        tree = expression('OR')
        if pos != len(tokens):
            raise ValueError()
    except ValueError:
        tree = {'Text': raw}
    return {'References': refs, 'Expression': tree}


def link_courses(database):
    missing = set()
    for course in database.values():
        for reverse in FIELDS.values():
            course['Meta'][reverse] = []
    for code, course in database.items():
        meta = course['Meta']
        meta['Relations'] = {}
        for field, reverse in FIELDS.items():
            relation = analyze(meta[field])
            meta['Relations'][field] = relation
            for target in relation['References']:
                if target in database:
                    database[target]['Meta'][reverse].append(code)
                else:
                    missing.add(target)
    for course in database.values():
        for reverse in FIELDS.values():
            course['Meta'][reverse] = sorted(set(course['Meta'][reverse]))
    return sorted(missing)
