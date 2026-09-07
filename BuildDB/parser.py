"""WCQ HTML parser; ignores mobile duplicate rows and respects rowspan."""
import re
from bs4 import BeautifulSoup


def text(node):
    return ' '.join(node.stripped_strings) if node else ''


def subjects(html):
    soup = BeautifulSoup(html, 'html.parser')
    return sorted({m.group(1).upper() for a in soup.select('div.depts a.ug[href]')
                   if (m := re.search(r'/subject/([A-Za-z]+)(?:[/?#]|$)', a['href']))})


def grid(table):
    spans = {}
    for row in table.find_all('tr'):
        if row.find_parent('table') is not table:
            continue
        if any(c.startswith('mobile') for c in row.get('class', [])):
            continue
        cells = {}
        for col, (cell, left) in list(spans.items()):
            cells[col] = cell
            if left == 1:
                del spans[col]
            else:
                spans[col] = (cell, left - 1)
        col = 0
        for cell in row.find_all(['td', 'th'], recursive=False):
            while col in cells:
                col += 1
            for _ in range(int(cell.get('colspan', 1))):
                cells[col] = cell
                count = int(cell.get('rowspan', 1))
                if count > 1:
                    spans[col] = (cell, count - 1)
                col += 1
        yield cells


def number(cell):
    value = ' '.join(t.strip() for t in cell.find_all(string=True)
                     if not any('quotadetail' in p.get('class', []) for p in t.parents)).strip().replace(',', '')
    if value in ('', '-', '--', 'N/A', 'TBA'):
        return None
    if not re.fullmatch(r'-?\d+', value):
        raise ValueError(f'Unexpected enrollment value: {value!r}')
    return int(value)


def parse_courses(html):
    soup = BeautifulSoup(html, 'html.parser')
    courses = {}
    for block in soup.select('div.course'):
        heading = text(block.select_one('.subject'))
        match = re.match(r'([A-Z]{2,8})\s*(\d{4}[A-Z]*)\s*-\s*(.*?)\s*\(([^()]+)\s+units?\)', heading)
        if not match:
            raise ValueError(f'Unrecognized course heading: {heading}')
        dept, num, title, credit = match.groups()
        code = dept + num
        credits = float(credit) if re.fullmatch(r'\d+(?:\.\d+)?', credit) else credit
        if isinstance(credits, float) and credits.is_integer():
            credits = int(credits)
        meta = dict(Code=code, Title=title, Credits=credits, Description='', Consent=False)
        meta.update({'Pre-requisite': '', 'Co-requisite': '', 'Exclusion': ''})
        names = {'DESCRIPTION': 'Description', 'PRE-REQUISITE': 'Pre-requisite', 'CO-REQUISITE': 'Co-requisite', 'EXCLUSION': 'Exclusion'}
        for row in block.select('.courseattr tr'):
            th = row.find('th', recursive=False)
            td = row.find('td', recursive=False)
            key = names.get(text(th).upper())
            if key and td:
                meta[key] = text(td)
        meta['Consent'] = bool(block.select('.popup.consent, .popupconsent, .consent'))
        data = {k: {} for k in ('Lecture', 'Tutorial', 'Labs', 'Research', 'Others')}
        table = block.select_one('table.sections')
        headers = {}
        if table:
            for cells in grid(table):
                if any(c.name == 'th' for c in cells.values()):
                    headers = {text(c).lower(): i for i, c in cells.items()}
                    continue
                section_cell = cells.get(headers.get('section', 0))
                section = re.match(r'^([A-Z]+\d+[A-Z]*|[A-Z][A-Z0-9_-]*)\s*(?:\(|$)', text(section_cell))
                if not section:
                    continue
                name = section.group(1)
                group = next((g for p, g in [('LA', 'Labs'), ('L', 'Lecture'), ('T', 'Tutorial'), ('R', 'Research')]
                              if re.fullmatch(p + r'\d+[A-Z]*', name)), 'Others')
                entry = {}
                for key, alternatives in {'Quota': ['quota'], 'Enroll': ['enrol', 'enroll'], 'Avail': ['avail'], 'Waitlist': ['wait', 'waitlist']}.items():
                    index = next((headers[a] for a in alternatives if a in headers), None)
                    if index is None or index not in cells:
                        raise ValueError(f'{code}/{name}: missing {key} column')
                    entry[key] = number(cells[index])
                if group == 'Lecture':
                    cell = cells.get(headers.get('instructor'))
                    names_list = [text(a) for a in cell.select('a')] if cell else []
                    entry['Instructor'] = list(dict.fromkeys(names_list or ([text(cell)] if text(cell) else [])))
                old = data[group].get(name)
                if old:
                    if any(old[k] != entry[k] for k in ('Quota', 'Enroll', 'Avail', 'Waitlist')):
                        raise ValueError(f'{code}/{name}: conflicting repeated section')
                    if group == 'Lecture':
                        entry['Instructor'] = list(dict.fromkeys(old['Instructor'] + entry['Instructor']))
                data[group][name] = entry
        for key in ('Quota', 'Enroll', 'Waitlist'):
            values = [s[key] for s in data['Lecture'].values()]
            meta[key] = None if None in values else sum(values)
        cc = {}
        # Include tooltip attributes as well as visible text.
        labels = text(block) + ' ' + ' '.join(str(n.get(a, '')) for n in block.find_all(True) for a in ('title', 'data-original-title'))
        pattern = r'Common\s+Core\s*\(([^)]+)\)\s*for\s*30-(?:credit|cr)\s+prog\s+in\s*(22\s*[-–]\s*24|25|26)'
        for category, year in re.findall(pattern, labels, re.I):
            cc.setdefault('CC22' if year.startswith('22') else 'CC' + year, {})[category.strip()] = True
        courses[code] = {'Meta': meta, 'Data': data, 'CC': cc}
    return courses
