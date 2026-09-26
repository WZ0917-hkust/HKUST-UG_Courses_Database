import re
import time
from urllib.parse import quote, urljoin, urlencode, urlparse, unquote
from playwright.sync_api import sync_playwright

import pandas as pd
import requests
from bs4 import BeautifulSoup
from tqdm import tqdm


# ============================================================
# Config
# ============================================================

HKUST_RESULTS_URL = (
    "https://registry.hkust.edu.hk/useful-tools/"
    "credit-transfer/database-institution/results-institution"
)

EPFL_INSTITUTION = "Ecole Polytechnique Federale de Lausanne"

# HKUST 当前数据库页面使用的 snapshot / transfer term
HKUST_TRANSFER_TERM = "2025-26 Fall"

TARGET_ACADEMIC_YEAR = "2026-27"
TARGET_EPFL_YEAR = "2026-2027"
TARGET_TERM = "Spring"

MAX_HKUST_PAGES = 200
REQUEST_DELAY = 0.15

TERM_ORDER = {
    "Fall": 0,
    "Winter": 1,
    "Spring": 2,
    "Summer": 3,
}

session = requests.Session()
session.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 Chrome/152 Safari/537.36"
    )
})


# ============================================================
# Utilities
# ============================================================

def clean(s):
    s = re.sub(r"\s+", " ", str(s)).strip()
    s = re.sub(r"^\+\s*", "", s)
    return s


def normalize_epfl_code(code):
    """
    HKUST 有些记录写 CS442 / EE451 / BIOENG315，
    而 EPFL canonical code 是 CS-442 / EE-451 / BIOENG-315。
    """
    if not code:
        return None

    code = clean(code).replace("–", "-").replace("—", "-")

    # CS442 -> CS-442
    m = re.fullmatch(r"([A-Za-z]+)(\d+[A-Za-z]?)", code)
    if m:
        return f"{m.group(1).upper()}-{m.group(2)}"

    return code


def parse_valid_term(s):
    """
    '2027-28 Winter' -> (2027, 1)
    """
    if not s:
        return None

    m = re.search(
        r"(20\d{2})-\d{2}\s+(Fall|Winter|Spring|Summer)",
        s,
        re.I,
    )

    if not m:
        return None

    year = int(m.group(1))
    term = m.group(2).capitalize()

    return year, TERM_ORDER[term]


def valid_in_spring_2027(valid_till):
    """
    Target = 2026-27 Spring.

    Examples:
      2026-27 Winter -> False
      2026-27 Spring -> True
      2026-27 Summer -> True
      2027-28 Winter -> True
    """
    parsed = parse_valid_term(valid_till)

    if parsed is None:
        return False

    target = (2026, TERM_ORDER["Spring"])
    return parsed >= target


def looks_like_code(s):
    """
    宽松识别 EPFL course code。
    也允许 FR-DÉB-IV-P 之类的非数字 code。
    """
    if not s:
        return False

    s = clean(s)

    if len(s) > 40:
        return False
    if " " in s:
        return False
    if s.lower().startswith("ref"):
        return False
    if not re.search(r"[A-Za-zÀ-ÖØ-öø-ÿ]", s):
        return False

    return True


# ============================================================
# 1. Scrape HKUST mappings
# ============================================================

def parse_hkust_rendered_text(text):
    tokens = [
        clean(x)
        for x in text.splitlines()
        if clean(x)
    ]

    rows = []

    # ============================================================
    # Find institution blocks.
    #
    # 页面结构是：
    #
    #   Country
    #   Institution
    #   HKUST
    #   ... mappings ...
    #
    # 下一个 institution 又会出现新的 "HKUST" header。
    # ============================================================

    hkust_headers = [
        i for i, token in enumerate(tokens)
        if token == "HKUST"
    ]

    epfl_blocks = []

    for n, hkust_idx in enumerate(hkust_headers):

        if hkust_idx < 1:
            continue

        institution = tokens[hkust_idx - 1]

        if institution != EPFL_INSTITUTION:
            continue

        block_start = hkust_idx + 1

        if n + 1 < len(hkust_headers):
            next_hkust_idx = hkust_headers[n + 1]

            # 下一 institution header 格式：
            #
            # Country
            # Institution
            # HKUST
            #
            # 因此 block 到下一 HKUST 前两行结束。
            block_end = max(
                block_start,
                next_hkust_idx - 2
            )
        else:
            block_end = len(tokens)

        epfl_blocks.append(
            tokens[block_start:block_end]
        )

    # 当前这一页没有 EPFL institution block
    if not epfl_blocks:
        return []

    # ============================================================
    # Parse every Ref No. inside EPFL block
    # ============================================================

    for block in epfl_blocks:

        ref_indices = []

        for i, token in enumerate(block):
            if re.fullmatch(
                r"Ref\s*No\.?\s*:?\s*B\d{6}-\d{2}",
                token,
                re.I,
            ):
                ref_indices.append(i)

        for n, ref_idx in enumerate(ref_indices):

            # ----------------------------------------------------
            # Bound this record by the next Ref No.
            # ----------------------------------------------------

            record_start = max(
                0,
                ref_idx - 2,
            )

            if n + 1 < len(ref_indices):
                # 下一条的 title/code 在 next ref 前两行，
                # 所以当前 record 在那里之前结束。
                record_end = max(
                    ref_idx + 1,
                    ref_indices[n + 1] - 2,
                )
            else:
                record_end = len(block)

            record = block[
                record_start:record_end
            ]

            # ref_idx 在 record 里的新位置
            local_ref_idx = ref_idx - record_start

            # ----------------------------------------------------
            # Ref No.
            # ----------------------------------------------------

            ref_match = re.search(
                r"(B\d{6}-\d{2})",
                block[ref_idx],
                re.I,
            )

            if not ref_match:
                continue

            ref_no = ref_match.group(1).upper()

            # ----------------------------------------------------
            # EPFL title + code
            #
            # Example:
            #
            # Data-intensive Systems
            # CS-300
            # Ref No.: B045855-02
            # ----------------------------------------------------

            if ref_idx < 2:
                continue

            epfl_title = block[ref_idx - 2]
            epfl_code_raw = block[ref_idx - 1]

            if epfl_code_raw == "#":
                epfl_code = None
            else:
                epfl_code = normalize_epfl_code(
                    epfl_code_raw
                )

            # ----------------------------------------------------
            # Valid till
            # ----------------------------------------------------

            valid_till = None
            valid_idx = None

            # Search only after Ref No.
            search_end = min(
                len(block),
                record_end,
            )

            for i in range(
                ref_idx + 1,
                search_end,
            ):

                token = block[i]

                # Case:
                # Valid till 2028-29 Winter
                m = re.search(
                    r"Valid\s+till.*?"
                    r"(20\d{2}-\d{2})\s+"
                    r"(Fall|Winter|Spring|Summer)",
                    token,
                    re.I,
                )

                if m:
                    valid_till = (
                        f"{m.group(1)} "
                        f"{m.group(2).capitalize()}"
                    )
                    valid_idx = i
                    break

                # Case:
                #
                # Valid till
                # 2028-29 Winter
                #
                if token.lower() == "valid till":

                    for j in range(
                        i + 1,
                        min(i + 4, search_end),
                    ):

                        m = re.fullmatch(
                            r"(20\d{2}-\d{2})\s+"
                            r"(Fall|Winter|Spring|Summer)",
                            block[j],
                            re.I,
                        )

                        if m:
                            valid_till = (
                                f"{m.group(1)} "
                                f"{m.group(2).capitalize()}"
                            )

                            valid_idx = j
                            break

                    if valid_till:
                        break

            if valid_till is None:
                print(
                    f"WARNING: no valid_till for "
                    f"{ref_no}: "
                    f"{epfl_title} / {epfl_code_raw}"
                )
                continue

            # ----------------------------------------------------
            # HKUST target
            #
            # Example:
            #
            # Database Management Systems
            # COMP3311
            # 3 Credits
            # ----------------------------------------------------

            credit_idx = None
            hkust_credits = None

            for i in range(
                valid_idx + 1,
                search_end,
            ):

                m = re.fullmatch(
                    r"(\d+(?:\.\d+)?)\s+"
                    r"Credits?",
                    block[i],
                    re.I,
                )

                if m:
                    credit_idx = i
                    hkust_credits = float(
                        m.group(1)
                    )
                    break

            if credit_idx is None:
                print(
                    f"WARNING: no credits for "
                    f"{ref_no}: "
                    f"{epfl_title} / {epfl_code_raw}"
                )
                continue

            if credit_idx < 2:
                continue

            hkust_title = block[
                credit_idx - 2
            ]

            hkust_code = block[
                credit_idx - 1
            ]

            # ----------------------------------------------------
            # Save
            # ----------------------------------------------------

            rows.append({
                "ref_no": ref_no,

                "epfl_title_hkust":
                    epfl_title,

                "epfl_code_raw":
                    epfl_code_raw,

                "epfl_code":
                    epfl_code,

                "valid_till":
                    valid_till,

                "valid_in_spring_2027":
                    valid_in_spring_2027(
                        valid_till
                    ),

                "hkust_title":
                    hkust_title,

                "hkust_code":
                    hkust_code,

                "hkust_credits":
                    hkust_credits,

                "raw_summary":
                    " | ".join(record),
            })

    return rows

def fetch_all_hkust_epfl_mappings():

    all_rows = {}
    seen_ranges = set()

    with sync_playwright() as p:

        browser = p.chromium.launch(
            headless=True,
        )

        context = browser.new_context(
            viewport={
                "width": 1440,
                "height": 1200,
            },
            locale="en-US",
        )

        page = context.new_page()

        try:

            for page_no in range(
                MAX_HKUST_PAGES
            ):
            # for page_no in range(
            #     7,8
            # ):

                params = {
                    "admission_term":
                        HKUST_TRANSFER_TERM,

                    "country_institution":
                        "Any",

                    "institution":
                        "Any",

                    "hkust_subject":
                        "Any",

                    "hkust_course_code":
                        "Any",

                    "page":
                        page_no,
                }

                url = (
                    HKUST_RESULTS_URL
                    + "?"
                    + urlencode(params)
                )

                print()
                print(
                    f"HKUST page "
                    f"{page_no} ..."
                )

                # ------------------------------
                # Load actual browser page
                # ------------------------------

                page.goto(
                    url,
                    wait_until="domcontentloaded",
                    timeout=60000,
                )

                # 等 JS 把 results 填进去
                try:
                    page.wait_for_function(
                        """
                        () => {
                            const t =
                                document.body.innerText;

                            return (
                                t.includes("Showing") &&
                                t.includes("Valid till")
                            );
                        }
                        """,
                        timeout=30000,
                    )

                except Exception:

                    # 有时候页面数据加载较慢，
                    # 再给它一点时间
                    page.wait_for_timeout(5000)

                body_text = (
                    page
                    .locator("body")
                    .inner_text()
                )

                # ------------------------------
                # Debug
                # ------------------------------

                if page_no == 0:
                    with open(
                        "debug_hkust_page0.txt",
                        "w",
                        encoding="utf-8",
                    ) as f:
                        f.write(body_text)

                if page_no == 7:
                    print("\n===== PAGE 7 DEBUG =====")

                    print(
                        "EPFL name count:",
                        body_text.count(EPFL_INSTITUTION)
                    )

                    lines = body_text.splitlines()

                    for i, line in enumerate(lines):
                        if (
                            "Ecole Polytechnique" in line
                            or "CS-300" in line
                            or "PHYS-438" in line
                        ):
                            print(f"\n--- around line {i} ---")

                            start = max(0, i - 20)
                            end = min(len(lines), i + 80)

                            for j in range(start, end):
                                print(f"{j:05d}: {lines[j]}")

                    with open(
                        "debug_hkust_page7.txt",
                        "w",
                        encoding="utf-8"
                    ) as f:
                        f.write(body_text)

                    print("===== END PAGE 7 DEBUG =====\n")

                # ------------------------------
                # Did JS actually load?
                # ------------------------------

                range_match = re.search(
                    r"Showing\s+"
                    r"([\d,]+)\s*-\s*"
                    r"([\d,]+)\s+of\s+"
                    r"([\d,]+)",
                    body_text,
                    re.I,
                )

                if not range_match:

                    print(
                        "  WARNING: no "
                        "'Showing x-y of z' "
                        "found."
                    )

                    # 保存完整页面方便排查
                    with open(
                        f"debug_hkust_"
                        f"page{page_no}.html",
                        "w",
                        encoding="utf-8",
                    ) as f:
                        f.write(
                            page.content()
                        )

                    # 第一页都没渲染成功，
                    # 没必要继续 200 页
                    if page_no == 0:
                        raise RuntimeError(
                            "\nHKUST page did not "
                            "finish rendering.\n\n"
                            "Open "
                            "debug_hkust_page0.txt "
                            "and check what the "
                            "browser actually saw."
                        )

                    continue

                first = int(
                    range_match
                    .group(1)
                    .replace(",", "")
                )

                last = int(
                    range_match
                    .group(2)
                    .replace(",", "")
                )

                total = int(
                    range_match
                    .group(3)
                    .replace(",", "")
                )

                print(
                    f"  database range: "
                    f"{first}-{last} / "
                    f"{total}"
                )

                current_range = (
                    first,
                    last,
                )

                # 如果 page 参数失效，
                # 会一直得到同一页。
                if current_range in seen_ranges:

                    print(
                        "  Repeated database "
                        "range detected."
                    )

                    print(
                        "  Pagination appears "
                        "to have stopped."
                    )

                    break

                seen_ranges.add(
                    current_range
                )

                # ------------------------------
                # Parse EPFL records
                # ------------------------------

                rows = (
                    parse_hkust_rendered_text(
                        body_text
                    )
                )

                old_count = len(
                    all_rows
                )

                for row in rows:
                    all_rows[
                        row["ref_no"]
                    ] = row

                new_count = (
                    len(all_rows)
                    - old_count
                )

                print(
                    f"  EPFL mappings on "
                    f"this page: "
                    f"{len(rows)}"
                )

                print(
                    f"  new: {new_count}, "
                    f"total unique: "
                    f"{len(all_rows)}"
                )

                # IMPORTANT:
                #
                # 不再因为连续几页没 EPFL
                # 就停止！
                #
                # 只有真正到数据库最后一页
                # 才停止。

                if last >= total:
                    print(
                        "Reached final "
                        "HKUST page."
                    )
                    break

                page.wait_for_timeout(
                    int(
                        REQUEST_DELAY
                        * 1000
                    )
                )

        finally:
            browser.close()

    if not all_rows:

        raise RuntimeError(
            "\nNo EPFL mappings were "
            "parsed.\n\n"
            "Please inspect:\n"
            "  debug_hkust_page0.txt\n"
            "and any "
            "debug_hkust_page*.html files."
        )

    return pd.DataFrame(
        all_rows.values()
    )


# ============================================================
# 2. Query official EPFL Coursebook
# ============================================================

EPFL_STUDYPLAN_ROOT = "https://edu.epfl.ch/studyplan/en/"


def get_epfl_links(url):
    r = session.get(url, timeout=30)
    r.raise_for_status()

    soup = BeautifulSoup(r.text, "html.parser")

    result = []

    for a in soup.find_all("a", href=True):
        href = urljoin(url, a["href"])

        if href.startswith("https://edu.epfl.ch/"):
            result.append(href)

    return list(dict.fromkeys(result))


def discover_epfl_coursebook_urls(codes):
    """
    从 EPFL 当前 Study Plans 出发：

        root
          -> bachelor/master/minor/... category
          -> individual programme
          -> coursebook links

    只寻找我们真正关心的 HKUST mapping course codes。
    """

    wanted = {
        normalize_epfl_code(c)
        for c in codes
        if c
    }

    found = {}

    # ============================================================
    # 1. Discover category pages automatically
    #
    # Examples:
    # /studyplan/en/bachelor/
    # /studyplan/en/master/
    # /studyplan/en/minor/
    # /studyplan/en/doctoral-school/
    # ...
    # ============================================================

    print("\nDiscovering EPFL study-plan categories...")

    root_links = get_epfl_links(
        EPFL_STUDYPLAN_ROOT
    )

    prefix = "/studyplan/en/"

    category_urls = []

    for url in root_links:
        path = urlparse(url).path

        if not path.startswith(prefix):
            continue

        remainder = (
            path[len(prefix):]
            .strip("/")
        )

        # exactly one component after /studyplan/en/
        if (
            remainder
            and "/" not in remainder
        ):
            category_urls.append(
                url.rstrip("/") + "/"
            )

    category_urls = sorted(
        set(category_urls)
    )

    print(
        f"  categories found: "
        f"{len(category_urls)}"
    )

    for x in category_urls:
        print("   ", x)

    # ============================================================
    # 2. Discover all programme pages
    # ============================================================

    programme_urls = set()

    print(
        "\nDiscovering EPFL programmes..."
    )

    for category_url in category_urls:

        try:
            links = get_epfl_links(
                category_url
            )

        except Exception as e:
            print(
                f"  WARNING: "
                f"{category_url}: {e}"
            )
            continue

        category_path = (
            urlparse(category_url)
            .path
            .rstrip("/")
            + "/"
        )

        for url in links:

            path = urlparse(url).path

            if not path.startswith(
                category_path
            ):
                continue

            remainder = (
                path[
                    len(category_path):
                ]
                .strip("/")
            )

            # Individual programme:
            #
            # /studyplan/en/master/data-science/
            #
            # but NOT:
            #
            # .../coursebook/...
            if (
                remainder
                and "/" not in remainder
                and "coursebook" not in remainder
            ):
                programme_urls.add(
                    url.rstrip("/") + "/"
                )

    programme_urls = sorted(
        programme_urls
    )

    print(
        f"  programmes found: "
        f"{len(programme_urls)}"
    )

    # ============================================================
    # Helper: determine whether a coursebook URL corresponds
    # to one of our wanted codes.
    # ============================================================

    def match_code(url):
        path = unquote(
            urlparse(url).path
        )

        last = (
            path.rstrip("/")
            .split("/")[-1]
        )

        last_lower = last.lower()

        for code in wanted:

            if not code:
                continue

            c = code.lower()

            # Typical:
            #
            # algorithms-i-CS-250
            # image-analysis-...-EE-451
            #
            if (
                last_lower.endswith(
                    "-" + c
                )
                or last_lower == c
            ):
                return code

            # A few legacy HKUST codes lack "-"
            #
            # COM480 -> COM-480
            #
            compact = c.replace("-", "")

            if last_lower.replace(
                "-", ""
            ).endswith(
                compact
            ):
                return code

        return None

    # ============================================================
    # 3. Crawl each programme page and collect coursebook URLs
    # ============================================================

    print(
        "\nScanning programme pages "
        "for mapped EPFL courses..."
    )

    for n, programme_url in enumerate(
        programme_urls,
        1,
    ):

        try:
            links = get_epfl_links(
                programme_url
            )

        except Exception as e:
            print(
                f"  WARNING [{n}/"
                f"{len(programme_urls)}]: "
                f"{programme_url}: {e}"
            )
            continue

        for url in links:

            if "/coursebook/" not in url:
                continue

            code = match_code(url)

            if not code:
                continue

            # First valid URL is sufficient.
            if code not in found:
                found[code] = url

                print(
                    f"  FOUND "
                    f"{code:15} "
                    f"{url}"
                )

        # All candidate courses already resolved
        if len(found) == len(wanted):
            break

    print()
    print(
        f"EPFL coursebook URLs found: "
        f"{len(found)} / {len(wanted)}"
    )

    missing = sorted(
        wanted - set(found)
    )

    if missing:
        print(
            f"Not present in current "
            f"2026-27 study plans: "
            f"{len(missing)}"
        )

        print(
            "  "
            + ", ".join(missing)
        )

    return found


def find_epfl_coursebook_url(code):
    """
    EPFL Graph Search 的 course/{CODE} 页面会给官方
    edu.epfl.ch Coursebook URL，因此不需要自己猜 slug。
    """
    if not code:
        return None

    candidates = []

    normalized = normalize_epfl_code(code)
    if normalized:
        candidates.append(normalized)

    if code not in candidates:
        candidates.append(code)

    # 偶尔有 (d) suffix
    stripped = re.sub(r"\([a-z]\)$", "", normalized or "")
    if stripped and stripped not in candidates:
        candidates.append(stripped)

    for candidate in candidates:
        graph_url = (
            "https://graphsearch.epfl.ch/en/course/"
            + quote(candidate, safe="-()")
        )

        try:
            r = session.get(graph_url, timeout=20)

            if r.status_code != 200:
                continue

            soup = BeautifulSoup(r.text, "html.parser")

            for a in soup.find_all("a", href=True):
                href = a["href"]

                if "edu.epfl.ch/coursebook/" in href:
                    return urljoin(graph_url, href)

        except requests.RequestException:
            continue

    return None


def parse_epfl_coursebook_page(
    url,
    code,
):
    r = session.get(
        url,
        timeout=30,
    )
    r.raise_for_status()

    soup = BeautifulSoup(
        r.text,
        "html.parser",
    )

    lines = [
        clean(x)
        for x in (
            soup
            .get_text(
                "\n",
                strip=True,
            )
            .splitlines()
        )
        if clean(x)
    ]

    text = "\n".join(lines)

    # ============================================================
    # Title
    # ============================================================

    h1 = soup.find("h1")

    title = (
        clean(h1.get_text())
        if h1
        else None
    )

    # ============================================================
    # Credits
    #
    # e.g.
    # CS-250 / 8 credits
    # ============================================================

    ects = None

    for line in lines[:100]:

        m = re.search(
            r"/\s*"
            r"(\d+(?:\.\d+)?)"
            r"\s+credits?",
            line,
            re.I,
        )

        if m:
            ects = float(
                m.group(1)
            )
            break

    # ============================================================
    # Language
    # ============================================================

    language = None

    for i, line in enumerate(lines):

        m = re.match(
            r"Language\s*:\s*(.*)",
            line,
            re.I,
        )

        if m:
            language = (
                m.group(1)
                .strip()
            )

            if (
                not language
                and i + 1 < len(lines)
            ):
                language = (
                    lines[i + 1]
                )

            break

    # ============================================================
    # 2026-27 existence
    # ============================================================

    has_2627 = (
        "2026-2027" in text
    )

    # ============================================================
    # Spring detection
    #
    # EPFL official pages look like:
    #
    # Computer Science
    # 2026-2027 Bachelor semester 4
    # Semester: Spring
    #
    # A course can appear in many programmes.
    # ANY Spring listing => offered Spring 2027.
    # ============================================================

    spring_2027 = False
    spring_snippets = []

    for i, line in enumerate(lines):

        if "2026-2027" not in line:
            continue

        start = max(
            0,
            i - 1,
        )

        end = min(
            len(lines),
            i + 20,
        )

        window = lines[
            start:end
        ]

        window_text = (
            "\n".join(window)
        )

        is_spring = bool(
            re.search(
                r"Semester\s*:\s*"
                r"Spring\b",
                window_text,
                re.I,
            )
        )

        # Just in case a French fragment occurs
        if not is_spring:
            is_spring = bool(
                re.search(
                    r"Semestre\s*:\s*"
                    r"Printemps\b",
                    window_text,
                    re.I,
                )
            )

        # Some plan labels themselves say:
        # 2026-2027 Spring semester
        if not is_spring:
            is_spring = bool(
                re.search(
                    r"2026-2027\s+"
                    r"Spring\s+semester",
                    window_text,
                    re.I,
                )
            )

        if is_spring:
            spring_2027 = True

            spring_snippets.append(
                " | ".join(window)
            )

    return {
        "epfl_code":
            code,

        "epfl_title_official":
            title,

        "epfl_ects":
            ects,

        "language":
            language,

        "coursebook_url":
            url,

        "has_2026_27_listing":
            has_2627,

        "not_given_2026_27":
            False,

        "spring_2027":
            spring_2027,

        "spring_program_info":
            " || ".join(
                spring_snippets[:10]
            ),
    }


def parse_epfl_coursebook(url, code):
    r = session.get(url, timeout=30)
    r.raise_for_status()

    soup = BeautifulSoup(r.text, "html.parser")

    lines = [
        clean(x)
        for x in soup.get_text("\n", strip=True).splitlines()
        if clean(x)
    ]

    text = "\n".join(lines)

    # ---------- Title ----------
    h1 = soup.find("h1")
    title = clean(h1.get_text()) if h1 else None

    # ---------- Credits ----------
    ects = None

    for line in lines[:40]:
        m = re.search(
            r"/\s*(\d+(?:\.\d+)?)\s+credits?",
            line,
            re.I,
        )
        if m:
            ects = float(m.group(1))
            break

    # ---------- Language ----------
    language = None

    for i, line in enumerate(lines):
        if line.lower().startswith("language:"):
            language = line.split(":", 1)[1].strip()

            if not language and i + 1 < len(lines):
                language = lines[i + 1]

            break

    # ---------- Is it offered Spring 2027? ----------
    not_given_2627 = bool(
        re.search(
            r"(Pas donné|Not given|Not offered)"
            r".{0,50}2026[-–]27",
            text,
            re.I | re.S,
        )
    )

    spring_2027 = False

    # Coursebook program blocks look like:
    #
    # Computer Science
    # 2026-2027 Bachelor semester 4
    # Semester: Spring
    #
    # Search every 2026-2027 occurrence.
    for m in re.finditer(
        re.escape(TARGET_EPFL_YEAR),
        text,
    ):
        segment = text[
            m.start():
            min(len(text), m.start() + 700)
        ]

        if re.search(
            r"Semester:\s*Spring",
            segment,
            re.I,
        ):
            spring_2027 = True
            break

    if not_given_2627:
        spring_2027 = False

    # Useful diagnostics
    has_2627 = TARGET_EPFL_YEAR in text

    # Grab program snippets for manual inspection
    spring_program_snippets = []

    for m in re.finditer(
        re.escape(TARGET_EPFL_YEAR),
        text,
    ):
        segment = text[
            max(0, m.start() - 120):
            min(len(text), m.start() + 350)
        ]

        if re.search(
            r"Semester:\s*Spring",
            segment,
            re.I,
        ):
            spring_program_snippets.append(
                clean(segment.replace("\n", " | "))
            )

    return {
        "epfl_code": normalize_epfl_code(code),
        "epfl_title_official": title,
        "epfl_ects": ects,
        "language": language,
        "coursebook_url": url,
        "has_2026_27_listing": has_2627,
        "not_given_2026_27": not_given_2627,
        "spring_2027": spring_2027,
        "spring_program_info": " || ".join(
            spring_program_snippets[:5]
        ),
    }


def parse_epfl_coursebook_rendered(
    text,
    code,
    url,
    title=None,
):
    lines = [
        clean(x)
        for x in text.splitlines()
        if clean(x)
    ]

    full_text = "\n".join(lines)

    # ============================================================
    # ECTS
    #
    # Example:
    # CS-250 / 8 credits
    # ============================================================

    ects = None

    for line in lines:
        m = re.search(
            r"/\s*(\d+(?:\.\d+)?)\s+credits?",
            line,
            re.I,
        )

        if m:
            ects = float(m.group(1))
            break

    # ============================================================
    # Language
    # ============================================================

    language = None

    for i, line in enumerate(lines):

        m = re.match(
            r"Language\s*:\s*(.*)",
            line,
            re.I,
        )

        if not m:
            continue

        language = m.group(1).strip()

        if (
            not language
            and i + 1 < len(lines)
        ):
            language = lines[i + 1]

        break

    # ============================================================
    # Check whether course has a 2026-2027 listing
    # ============================================================

    has_2627 = any(
        "2026-2027" in line
        for line in lines
    )

    # ============================================================
    # Explicit "not given" detection
    # ============================================================

    not_given_2627 = bool(
        re.search(
            r"(?:"
            r"not\s+(?:given|offered)"
            r"|pas\s+donn[ée]"
            r")"
            r".{0,80}"
            r"2026\s*[-–]\s*27",
            full_text,
            re.I | re.S,
        )
    )

    # ============================================================
    # Detect Spring 2027
    #
    # Typical official EPFL page:
    #
    # Computer Science
    # 2026-2027 Bachelor semester 4
    # Semester: Spring
    # Exam form: ...
    #
    # A course can appear under several programs.
    # If ANY 2026-2027 program listing says Spring,
    # we consider the course offered in Spring 2027.
    # ============================================================

    spring_2027 = False
    spring_program_snippets = []

    for i, line in enumerate(lines):

        if "2026-2027" not in line:
            continue

        # Include previous line because that is often
        # the programme name.
        start = max(0, i - 1)
        end = min(len(lines), i + 15)

        window = lines[start:end]

        is_spring = any(
            re.search(
                r"Semester\s*:\s*Spring\b",
                x,
                re.I,
            )
            for x in window
        )

        # Additional fallback:
        #
        # 2026-2027 Spring semester
        #
        if not is_spring:
            is_spring = bool(
                re.search(
                    r"2026-2027\s+Spring\s+semester",
                    line,
                    re.I,
                )
            )

        if is_spring:
            spring_2027 = True

            spring_program_snippets.append(
                " | ".join(window)
            )

    if not_given_2627:
        spring_2027 = False

    return {
        "epfl_code": code,

        "epfl_title_official": title,

        "epfl_ects": ects,

        "language": language,

        "coursebook_url": url,

        "has_2026_27_listing":
            has_2627,

        "not_given_2026_27":
            not_given_2627,

        "spring_2027":
            spring_2027,

        "spring_program_info":
            " || ".join(
                spring_program_snippets[:10]
            ),
    }


def check_epfl_courses(codes):

    columns = [
        "epfl_code",
        "epfl_title_official",
        "epfl_ects",
        "language",
        "coursebook_url",
        "has_2026_27_listing",
        "not_given_2026_27",
        "spring_2027",
        "spring_program_info",
    ]

    unique_codes = sorted(
        {
            normalize_epfl_code(c)
            for c in codes
            if c
        }
    )

    if not unique_codes:
        return pd.DataFrame(
            columns=columns
        )

    # ============================================================
    # Find URLs from CURRENT EPFL study plans
    # ============================================================

    url_map = (
        discover_epfl_coursebook_urls(
            unique_codes
        )
    )

    results = []

    print(
        "\nReading EPFL coursebooks..."
    )

    for code in tqdm(
        unique_codes,
        desc="Checking EPFL",
    ):

        url = url_map.get(code)

        # --------------------------------------------------------
        # If a mapped course does not occur anywhere in
        # EPFL's CURRENT study plans, it is not offered
        # in Spring 2027.
        #
        # This is NOT "manual check".
        # --------------------------------------------------------

        if not url:

            results.append({
                "epfl_code":
                    code,

                "epfl_title_official":
                    None,

                "epfl_ects":
                    None,

                "language":
                    None,

                "coursebook_url":
                    None,

                "has_2026_27_listing":
                    False,

                "not_given_2026_27":
                    True,

                "spring_2027":
                    False,

                "spring_program_info":
                    (
                        "Course not found in "
                        "current EPFL 2026-27 "
                        "study plans"
                    ),
            })

            continue

        try:

            row = (
                parse_epfl_coursebook_page(
                    url,
                    code,
                )
            )

            results.append(row)

            if row["spring_2027"]:
                status = "SPRING"

            elif row[
                "has_2026_27_listing"
            ]:
                status = "NOT SPRING"

            else:
                status = (
                    "NO 26-27 LISTING"
                )

            tqdm.write(
                f"{code:15} "
                f"{status:18} "
                f"{row['epfl_title_official'] or ''}"
            )

        except Exception as e:

            tqdm.write(
                f"{code:15} ERROR: {e}"
            )

            # THIS is a real unresolved case.
            results.append({
                "epfl_code":
                    code,

                "epfl_title_official":
                    None,

                "epfl_ects":
                    None,

                "language":
                    None,

                "coursebook_url":
                    url,

                "has_2026_27_listing":
                    None,

                "not_given_2026_27":
                    None,

                "spring_2027":
                    None,

                "spring_program_info":
                    f"ERROR: {e}",
            })

    return pd.DataFrame(
        results,
        columns=columns,
    )
# ============================================================
# Main
# ============================================================

def main():

    # --------------------------------------------------------
    # A. HKUST: ALL EPFL mappings
    # --------------------------------------------------------

    hkust = fetch_all_hkust_epfl_mappings()

    hkust = hkust.sort_values([
        "epfl_code",
        "valid_till",
        "hkust_code",
    ])

    hkust.to_csv(
        "01_hkust_all_epfl_mappings.csv",
        index=False,
        encoding="utf-8-sig",
    )

    print()
    print("HKUST EPFL mappings:", len(hkust))
    print(
        "Mappings still valid in Spring 2027:",
        hkust["valid_in_spring_2027"].sum()
    )

    # --------------------------------------------------------
    # B. Only courses whose mapping is still valid
    # --------------------------------------------------------

    valid = hkust[
        hkust["valid_in_spring_2027"]
    ].copy()

    codes = (
        valid["epfl_code"]
        .dropna()
        .unique()
        .tolist()
    )

    print()
    print(
        f"Checking {len(codes)} unique EPFL courses "
        f"against official 2026-27 Coursebook..."
    )

    # --------------------------------------------------------
    # C. EPFL: Spring 2027 check
    # --------------------------------------------------------

    epfl = check_epfl_courses(codes)

    epfl.to_csv(
        "02_epfl_course_checks.csv",
        index=False,
        encoding="utf-8-sig",
    )

    # --------------------------------------------------------
    # D. Join
    # --------------------------------------------------------

    merged = valid.merge(
        epfl,
        on="epfl_code",
        how="left",
    )

    merged.to_csv(
        "03_valid_mappings_with_epfl_info.csv",
        index=False,
        encoding="utf-8-sig",
    )

    # Final result:
    # 2026-27 Spring at EPFL
    # AND valid HKUST mapping
    final = merged[
        merged["spring_2027"] == True
    ].copy()

    final = final.sort_values([
        "epfl_code",
        "hkust_code",
        "ref_no",
    ])

    final.to_csv(
        "04_spring2027_transferable.csv",
        index=False,
        encoding="utf-8-sig",
    )

    # --------------------------------------------------------
    # E. Unresolved courses
    # --------------------------------------------------------

    unresolved = merged[
        merged["spring_2027"].isna()
        | merged["coursebook_url"].isna()
    ].copy()

    unresolved.to_csv(
        "05_unresolved_manual_check.csv",
        index=False,
        encoding="utf-8-sig",
    )

    # --------------------------------------------------------
    # Console summary
    # --------------------------------------------------------

    print()
    print("=" * 70)
    print("DONE")
    print("=" * 70)

    print(
        f"All HKUST EPFL mappings:           {len(hkust)}"
    )
    print(
        f"Valid in Spring 2027:             {len(valid)}"
    )
    print(
        f"Spring 2027 + valid mapping:      {len(final)}"
    )
    print(
        f"Need manual check:                {len(unresolved)}"
    )

    print()
    print("Output files:")
    print("  01_hkust_all_epfl_mappings.csv")
    print("  02_epfl_course_checks.csv")
    print("  03_valid_mappings_with_epfl_info.csv")
    print("  04_spring2027_transferable.csv   <-- MAIN RESULT")
    print("  05_unresolved_manual_check.csv")

    print()
    print("Preview:")
    print(
        final[[
            "epfl_code",
            "epfl_title_official",
            "epfl_ects",
            "hkust_code",
            "hkust_title",
            "hkust_credits",
            "valid_till",
        ]]
        .head(50)
        .to_string(index=False)
    )


if __name__ == "__main__":
    main()