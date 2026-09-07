import argparse
from datetime import datetime
from pathlib import Path
import re
import sys
from zoneinfo import ZoneInfo

from .client import Client, candidate_terms
from .parser import parse_courses
from .relations import link_courses
from .storage import save


def main():
    parser = argparse.ArgumentParser(description='爬取 HKUST 本科学科课程数据库（每次一个学期）')
    parser.add_argument('--term', help='例如 2610；省略则探测当前、后一个、前三个学期')
    parser.add_argument('--output', type=Path, help='默认 BuildDB/CoursesDB_学期_yyyymmdd_hhmm.json')
    parser.add_argument('--delay', type=float, default=0.5, help='请求间隔秒数')
    args = parser.parse_args()
    if args.term and not re.fullmatch(r'\d{2}[1-4]0', args.term):
        parser.error('--term 格式应为 2610、2620、2630、2640 等')
    if args.delay < 0:
        parser.error('--delay 不能小于 0')
    now = datetime.now(ZoneInfo('Asia/Hong_Kong'))
    client = Client(args.delay)
    available = {}
    for term in [args.term] if args.term else candidate_terms(now.date()):
        try:
            available[term] = client.discover(term)
            print(f'[学期] {term}: 可访问，{len(available[term])} 个本科学科', flush=True)
        except Exception as exc:
            print(f'[学期] {term}: 无法访问/未公开: {exc}', flush=True)
    if not available:
        print('没有可访问学期。', file=sys.stderr)
        return 1
    term = next(iter(available))
    output = args.output or Path(__file__).resolve().parent / f'CoursesDB_{term}_{now:%Y%m%d_%H%M}.json'
    partial = output.with_suffix('.partial.json')
    departments = available[term]
    print(f'[爬取学期] {term}\n[学科列表] ' + ', '.join(departments), flush=True)
    database, failures = {}, []
    for i, department in enumerate(departments, 1):
        try:
            courses = parse_courses(client.get(term, department))
            if not courses:
                raise ValueError('页面没有课程，不能视作成功')
            for code, course in courses.items():
                course['Meta']['Term'] = term
                if code in database and database[code] != course:
                    raise ValueError(f'不同学科页面课程内容冲突: {code}')
            database.update(courses)
            save(database, partial)
            print(f'[{i}/{len(departments)}] {department}: {len(courses)} 门；累计 {len(database)}', flush=True)
        except Exception as exc:
            failures.append(department)
            print(f'[失败] {department}: {exc}', file=sys.stderr, flush=True)
    missing = link_courses(database)
    save(database, partial)
    print(f'[后处理] {len(missing)} 个引用课程不在本次数据库中: ' + ', '.join(missing), flush=True)
    if failures:
        print(f'未完成学科: {", ".join(failures)}；部分数据保存在 {partial}，未覆盖正式文件。', file=sys.stderr)
        return 1
    save(database, output)
    partial.unlink(missing_ok=True)
    print(f'[完成] {len(database)} 门课程 → {output}', flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
